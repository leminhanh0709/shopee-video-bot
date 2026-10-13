"""Entry point: Drive watcher + job worker + Telegram approval listener."""
import json
import os
import re
import shutil
import threading
import time
import traceback

from . import claude_script, config, db, drive, facebook, render, textdetect, telegram_bot as tg

URL_RE = re.compile(r"https?://\S+")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def job_dir(job_id):
    d = os.path.join(config.WORK_DIR, f"job{job_id}")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------- Drive watcher ----------------
def scan_drive():
    for f in drive.list_inbox():
        if db.exists(f["id"]):
            continue
        link = drive.product_link_from(f["name"], f.get("description", ""))
        jid = db.create(f["id"], f["name"], link)
        if jid:
            log("new job", jid, f["name"], link)


# ---------------- Worker ----------------
def caption_for(job, plan):
    lines = [f"🎬 #{job['id']} · {job['name']}",
             f"🔗 Link: {job['product_link'] or 'CHƯA CÓ – reply tin này bằng link Shopee'}",
             f"🪝 Hook: {plan.get('headline', '')}",
             "", "📝 Thoại:"]
    for s in plan["segments"]:
        lines.append(f"• {s['voice']}")
    lines.append(f"• {plan.get('cta_voice', '')}")
    lines += ["", "Reply tin này bằng góp ý (vd: 'hài hơn, ngắn lại') để bot viết lại theo ý mày."]
    return "\n".join(lines)


CURRENT = {"job": None, "name": "", "step": "", "since": 0}


def step(job, text):
    CURRENT.update(job=job["id"], name=job["name"], step=text, since=time.time())
    log(job["id"], text)


def process(job):
    jid = job["id"]
    db.update(jid, status="processing", attempts=(job["attempts"] or 0) + 1)
    tg.send_text(f"⏳ Bắt đầu làm video #{jid} ({job['name']}). Khoảng 5–10 phút.")
    d = job_dir(jid)
    src = os.path.join(d, "src.mp4")
    if not os.path.exists(src):
        step(job, "tải video từ Drive")
        drive.download(job["drive_file_id"], src)
    previous = json.loads(job["script_json"]) if job.get("script_json") else None
    step(job, "Claude viết thoại")
    plan = claude_script.write_script(src, d, rewrite_note=job.get("rewrite_note"), previous=previous)
    step(job, "tìm chữ nước ngoài để che")
    try:
        bands, title_t = textdetect.detect(src, d, plan["end_cut"])
        if title_t and title_t < plan["end_cut"] and any(s["start"] < title_t - 0.3 for s in plan["segments"]):
            plan["end_cut"] = title_t
            plan["segments"] = [s for s in plan["segments"] if s["start"] < title_t - 0.3]
            plan["segments"][-1]["end"] = title_t
        plan["text_bands"] = bands
    except Exception as e:
        log(jid, "OCR failed, using Claude's estimate:", e)
    out = os.path.join(d, "final.mp4")
    step(job, "lồng tiếng và dựng video")
    render.render(src, plan, d, out, seed=jid * 100 + (job["attempts"] or 0))
    name = re.sub(r"\.[A-Za-z0-9]+$", "", job["name"]) + f"__vi_v{(job['attempts'] or 0) + 1}.mp4"
    out_id, _ = drive.upload(out, name, config.DRIVE_OUTPUT_FOLDER_ID, description=job["product_link"] or "")
    try:
        drive.move(job["drive_file_id"], config.DRIVE_SOURCE_DONE_FOLDER_ID)
    except Exception as e:
        log(jid, "move source failed (ignored):", e)
    preview = render.telegram_preview(out, d)
    tg.send_video(preview, f"🎬 #{jid} · {job['name']}", None)
    msg = tg.send_text(caption_for(job, plan), markup=tg.buttons(jid))
    msg_id = msg["message_id"] if msg else None
    db.update(jid, status="waiting_approval", script=plan, output_path=out, output_drive_id=out_id,
              tg_message_id=msg_id, rewrite_note=None, error=None)
    CURRENT.update(job=None, step="")
    log(jid, "sent for approval")


def worker():
    last_scan = 0
    while True:
        try:
            if time.time() - last_scan > config.DRIVE_POLL_SECONDS:
                last_scan = time.time()
                scan_drive()
            job = db.next_queued()
            if not job:
                time.sleep(5)
                continue
            try:
                process(job)
            except Exception as e:
                traceback.print_exc()
                CURRENT.update(job=None, step="")
                db.update(job["id"], status="failed", error=str(e)[:1000])
                tg.send_text(f"❌ Video #{job['id']} ({job['name']}) bị lỗi:\n{str(e)[:800]}",
                             markup=json.dumps({"inline_keyboard": [[{"text": "🔁 Thử lại",
                                                                       "callback_data": f"retry:{job['id']}"}]]}))
        except Exception:
            traceback.print_exc()
            time.sleep(30)


# ---------------- Telegram listener ----------------
def approve(job):
    jid = job["id"]
    tg.clear_buttons(job["tg_message_id"])
    if not config.FB_ENABLED:
        db.update(jid, status="approved")
        tg.send_text("✅ Đã duyệt. Video thành phẩm đã nằm trong thư mục Drive. (Chưa bật đăng Facebook – FB_ENABLED=0)",
                     reply_to=job["tg_message_id"])
        return
    if not job["product_link"]:
        tg.send_text("⚠️ Chưa có link sản phẩm. Reply tin video bằng link Shopee rồi bấm Duyệt lại.",
                     reply_to=job["tg_message_id"])
        return
    tg.send_text("⏳ Đang đăng lên fanpage...", reply_to=job["tg_message_id"])
    plan = json.loads(job["script_json"])
    vid, _, url = facebook.publish(job["output_path"], plan.get("post_caption", ""), job["product_link"])
    db.update(jid, status="posted", fb_post_id=vid)
    tg.send_text(f"🎉 Đã đăng và comment link: {url}", reply_to=job["tg_message_id"])
    shutil.rmtree(job_dir(jid), ignore_errors=True)


def status_text():
    lines = ["✅ Bot đang chạy."]
    if CURRENT["job"]:
        mins = int((time.time() - CURRENT["since"]) // 60)
        lines.append(f"⚙️ Đang làm #{CURRENT['job']} ({CURRENT['name']}): {CURRENT['step']} ({mins} phút)")
    else:
        lines.append("💤 Không có video nào đang làm.")
    c = db.counts()
    lines.append(f"📥 Đang chờ làm: {c.get('queued', 0)} · 👀 Chờ duyệt: {c.get('waiting_approval', 0)} · "
                 f"❌ Lỗi: {c.get('failed', 0)} · 🎉 Đã đăng: {c.get('posted', 0)}")
    return "\n".join(lines)


STATUS_VI = {"queued": "đang chờ làm", "processing": "đang làm", "waiting_approval": "đang chờ mày duyệt",
             "approved": "đã duyệt", "posted": "đã đăng", "rejected": "đã bỏ", "failed": "bị lỗi"}


def handle_callback(cb):
    data = cb.get("data", "")
    if str(cb["from"]["id"]) != str(config.TELEGRAM_ADMIN_CHAT_ID):
        return tg.answer(cb["id"], "Không có quyền")
    action, _, jid = data.partition(":")
    job = db.get(int(jid)) if jid.isdigit() else None
    if not job:
        return tg.answer(cb["id"], "Không tìm thấy video")
    if action == "ok" and job["status"] == "waiting_approval":
        tg.answer(cb["id"], "Đang xử lý")
        try:
            approve(job)
        except Exception as e:
            traceback.print_exc()
            tg.send_text(f"❌ Đăng lỗi: {str(e)[:800]}", reply_to=job["tg_message_id"],
                         markup=tg.buttons(job["id"]))
    elif action == "re" and job["status"] == "waiting_approval":
        tg.answer(cb["id"], "Đang viết lại")
        tg.clear_buttons(job["tg_message_id"])
        db.update(job["id"], status="queued")
        tg.send_text("🔁 Đang viết lại thoại, vài phút nữa có bản mới.", reply_to=job["tg_message_id"])
    elif action == "no":
        tg.answer(cb["id"], "Đã bỏ")
        tg.clear_buttons(job["tg_message_id"])
        db.update(job["id"], status="rejected")
        shutil.rmtree(job_dir(job["id"]), ignore_errors=True)
    elif action == "retry" and job["status"] == "failed":
        tg.answer(cb["id"], "Thử lại")
        db.update(job["id"], status="queued")
    else:
        tg.answer(cb["id"], f"Video #{job['id']} {STATUS_VI.get(job['status'], job['status'])}, không cần bấm nữa")


def handle_message(msg):
    if str(msg.get("chat", {}).get("id")) != str(config.TELEGRAM_ADMIN_CHAT_ID):
        return
    text = (msg.get("text") or "").strip()
    if text in ("/start", "/help"):
        return tg.send_text("Bot đang chạy. Thả video vào thư mục Drive 'Chờ làm' (tên file kèm __mã link Shopee). "
                            "Reply tin video bằng link để gắn link, hoặc bằng góp ý để viết lại.")
    if text == "/status":
        return tg.send_text(status_text())
    rep = msg.get("reply_to_message")
    if not rep or not text:
        return
    job = db.by_message(rep["message_id"])
    if not job:
        return
    m = URL_RE.search(text)
    if m and "shopee" in m.group(0):
        db.update(job["id"], product_link=m.group(0))
        tg.send_text(f"🔗 Đã gắn link cho #{job['id']}. Bấm Duyệt để đăng.", reply_to=job["tg_message_id"])
    elif job["status"] == "waiting_approval":
        tg.clear_buttons(job["tg_message_id"])
        db.update(job["id"], status="queued", rewrite_note=text)
        tg.send_text("🔁 Ok, đang viết lại theo góp ý.", reply_to=job["tg_message_id"])


def listener():
    offset = 0
    while True:
        for u in tg.updates(offset):
            offset = u["update_id"] + 1
            try:
                if "callback_query" in u:
                    handle_callback(u["callback_query"])
                elif "message" in u:
                    handle_message(u["message"])
            except Exception:
                traceback.print_exc()


def main():
    db.init()
    db.reset_stuck()
    log("bot started · TTS:", config.TTS_PROVIDER, "· model:", config.CLAUDE_MODEL, "· FB:", config.FB_ENABLED)
    tg.send_text("🤖 Bot video Shopee đã khởi động.")
    threading.Thread(target=listener, daemon=True).start()
    worker()


if __name__ == "__main__":
    main()
