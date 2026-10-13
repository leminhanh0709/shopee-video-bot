"""Claude watches sampled frames and writes the Vietnamese voice-over plan as JSON."""
import base64
import json
import os
import re
import subprocess

import anthropic

from . import config

PROMPT = """Bạn là biên kịch video ngắn bán hàng affiliate trên Facebook Reels cho thị trường Việt Nam.
Bạn được xem các khung hình lấy mẫu từ một video (kèm mốc thời gian). Video gốc có thể có chữ nước ngoài in trên hình.
Video này đã được chủ sở hữu cho phép dùng và chỉnh sửa. Nhiệm vụ: viết lại toàn bộ lời thoại tiếng Việt để lồng tiếng, tắt tiếng gốc.

ĐỊNH HƯỚNG NỘI DUNG (quan trọng nhất):
- Bán GIẢI PHÁP, không bán sản phẩm. Xoáy vào vấn đề/nhu cầu của người xem, kể như đang chia sẻ mẹo, hài hước, lôi cuốn, tự nhiên như người thật nói.
- 3 giây đầu phải có hook mạnh (câu hỏi gây tò mò, nghịch lý, hoặc "đừng làm X").
- Chỉ nhắc tới sản phẩm ĐÚNG 1 LẦN ở câu kêu gọi cuối (cta), nhẹ nhàng, ví dụ "loại bột mình hay dùng để ở bình luận nha".
- Được thêm/bớt/đổi ý so với video gốc cho đúng định hướng, nhưng KHÔNG bịa công dụng, KHÔNG nói về sức khỏe/dinh dưỡng/y tế, KHÔNG hứa hẹn quá đà. Thông tin kỹ thuật (định lượng, thời gian, nhiệt độ) phải đúng như video gốc hiển thị.
- Nếu có bước quan trọng chỉ hiện bằng chữ (ví dụ ở khung cuối) mà không có cảnh riêng, hãy lồng nó vào lời thoại ở cảnh phù hợp.
- Giọng văn: tiếng Việt đời thường, câu ngắn, dễ đọc thành tiếng. Không dùng emoji trong voice.

CÁCH CHIA ĐOẠN:
- Chia video thành các đoạn liên tiếp (segments) theo từng cảnh/bước hoặc từng lần chữ gốc đổi. Đoạn sau bắt đầu đúng chỗ đoạn trước kết thúc, từ 0 đến end_cut.
- Mỗi đoạn có "voice" (câu đọc lồng tiếng) và "subtitle" (phụ đề hiển thị, có thể dùng số như 70ml, 100g).
- Giọng đọc khoảng 4,5 âm tiết/giây. Video được làm chậm tối đa 2,5 lần để khớp thoại, nên voice của mỗi đoạn không được dài quá (thời lượng đoạn × 2,5 × 4,5) âm tiết. Ưu tiên ngắn gọn.
- end_cut: thời điểm nên dừng video gốc, cắt bỏ phần kết có khung tiêu đề/chữ nước ngoài lớn hoặc logo kênh. Nếu không có thì bằng thời lượng video.

CHE CHỮ GỐC:
- text_bands: liệt kê các dải ngang có chữ nước ngoài in trên hình (phụ đề, tiêu đề, watermark) trong khoảng 0..end_cut, theo tỉ lệ chiều cao khung hình (0 = mép trên, 1 = mép dưới). Gộp các vị trí gần nhau. Ước lượng rộng tay một chút.
- flip_safe: true nếu lật ngang hình không làm lộ chữ/logo bị ngược trên sản phẩm, ngược lại false.

{extra}
Thời lượng video: {duration:.2f} giây.

Chỉ trả về đúng 1 khối JSON, không giải thích, theo mẫu:
{{
 "summary": "tóm tắt video gốc 1 câu",
 "headline": "CHỮ HOOK HIỆN TRÊN MÀN HÌNH ĐOẠN ĐẦU, tối đa 5 từ, viết hoa",
 "segments": [{{"start": 0.0, "end": 1.5, "voice": "...", "subtitle": "..."}}],
 "end_cut": 21.6,
 "cta_voice": "câu kêu gọi cuối, nhắc sản phẩm 1 lần, mời xem link ở bình luận",
 "cta_subtitle": "...",
 "cta_badge": "XEM BÌNH LUẬN",
 "text_bands": [{{"y_top": 0.16, "y_bottom": 0.23}}],
 "flip_safe": false,
 "post_caption": "caption bài đăng Facebook 1-2 câu, giọng chia sẻ mẹo, không chèn link, kèm 3-5 hashtag tiếng Việt"
}}"""


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def sample_frames(path, workdir, max_frames):
    dur = probe_duration(path)
    step = max(0.5, dur / max_frames)
    fdir = os.path.join(workdir, "frames")
    os.makedirs(fdir, exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vf", f"fps=1/{step},scale=384:-2",
                    "-q:v", "5", os.path.join(fdir, "f%04d.jpg")], check=True)
    files = sorted(os.listdir(fdir))
    # fps filter places frame k at roughly (k + 0.5) * step
    return dur, [(min(dur, (i + 0.5) * step), os.path.join(fdir, f)) for i, f in enumerate(files)]


def _parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Claude không trả JSON")
    return json.loads(m.group(0))


def _clean(plan, dur):
    end_cut = float(plan.get("end_cut") or dur)
    end_cut = min(max(end_cut, 1.0), dur)
    segs = sorted((s for s in plan.get("segments", []) if s.get("voice")), key=lambda s: float(s["start"]))
    out, t = [], 0.0
    for i, s in enumerate(segs):
        e = float(s["end"]) if i < len(segs) - 1 else end_cut
        e = min(max(e, t + 0.4), end_cut)
        if e - t < 0.3:
            continue
        out.append({"start": round(t, 3), "end": round(e, 3), "voice": s["voice"].strip(),
                    "subtitle": (s.get("subtitle") or s["voice"]).strip()})
        t = e
    if not out:
        raise ValueError("Kịch bản không có đoạn nào")
    out[-1]["end"] = round(end_cut, 3)
    plan["segments"], plan["end_cut"] = out, end_cut
    bands = []
    for b in plan.get("text_bands", []) or []:
        try:
            y0, y1 = sorted((float(b["y_top"]), float(b["y_bottom"])))
            if 0 <= y0 < y1 <= 1 and y1 - y0 < 0.5:
                bands.append({"y_top": max(0, y0 - 0.015), "y_bottom": min(1, y1 + 0.015)})
        except Exception:
            pass
    plan["text_bands"] = bands
    plan.setdefault("cta_badge", "XEM BÌNH LUẬN")
    plan.setdefault("headline", "")
    plan.setdefault("post_caption", "")
    return plan


def write_script(video_path, workdir, rewrite_note=None, previous=None):
    dur, frames = sample_frames(video_path, workdir, config.MAX_FRAMES)
    extra = ""
    if config.STYLE_NOTE:
        extra += f"GHI CHÚ PHONG CÁCH CỦA CHỦ PAGE: {config.STYLE_NOTE}\n"
    if previous:
        extra += ("Đây là bản viết lại. Bản trước (KHÔNG lặp lại hook và câu đùa cũ, đổi góc tiếp cận):\n"
                  + json.dumps({k: previous.get(k) for k in ("headline", "segments", "cta_voice")}, ensure_ascii=False) + "\n")
    if rewrite_note:
        extra += f"YÊU CẦU CHỈNH SỬA: {rewrite_note}\n"
    content = []
    for t, f in frames:
        with open(f, "rb") as fh:
            content.append({"type": "text", "text": f"t={t:.1f}s"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                         "data": base64.b64encode(fh.read()).decode()}})
    content.append({"type": "text", "text": PROMPT.format(extra=extra, duration=dur)})
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(model=config.CLAUDE_MODEL, max_tokens=4000,
                                 messages=[{"role": "user", "content": content}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return _clean(_parse_json(text), dur)
