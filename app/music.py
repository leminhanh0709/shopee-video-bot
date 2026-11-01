"""Music mode: no voice-over, no AI. The bot picks a random track from the owner's music folder
on Google Drive, hides foreign text, applies the same light visual variation as voice mode, and
lays the music under the video (original sound muted)."""
import json
import os
import random

from . import config, drive, render

AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
SWAP = "__swap__"          # rewrite_note value meaning "just pick another track, no AI"


def mode_from_name(name):
    """'video_nhac_xxx' -> music, 'video_voice_xxx' -> voice, nothing -> voice."""
    for t in drive.name_tokens(name):
        if t.lower() in drive.MODE_WORDS:
            return "music" if t.lower() == "nhac" else "voice"
    return "voice"


# ---------------- library on Drive ----------------
def library():
    """All audio files in the music folder (sub-folders are included too)."""
    svc = drive.svc()
    out = []

    def walk(folder_id, mood):
        page = None
        while True:
            res = svc.files().list(q=f"'{folder_id}' in parents and trashed=false", pageSize=200, pageToken=page,
                                   fields="nextPageToken,files(id,name,mimeType)").execute()
            for f in res.get("files", []):
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    if mood is None:
                        walk(f["id"], f["name"])
                elif f["mimeType"].startswith("audio/") or f["name"].lower().endswith(AUDIO_EXT):
                    out.append({"id": f["id"], "name": f["name"], "mood": mood or "chung"})
            page = res.get("nextPageToken")
            if not page:
                break

    walk(config.DRIVE_MUSIC_FOLDER_ID, None)
    return out


def track_file(track):
    d = os.path.join(config.DATA_DIR, "music_cache")
    os.makedirs(d, exist_ok=True)
    ext = os.path.splitext(track["name"])[1].lower() or ".mp3"
    path = os.path.join(d, track["id"] + ext)
    if not os.path.exists(path):
        drive.download(track["id"], path + ".part")
        os.replace(path + ".part", path)
    return path


# ---------------- random pick ----------------
def pick(tracks, used=()):
    fresh = [t for t in tracks if t["id"] not in used]
    track = random.choice(fresh or tracks)
    return {"track_id": track["id"], "track_name": track["name"]}


# ---------------- render ----------------
def render_video(src, plan, workdir, out_path, music_path, seed=0):
    base = os.path.join(workdir, "base.mp4")
    T = plan["end_cut"]
    cut = os.path.join(workdir, "cut.mp4")          # only process the part we keep (much faster)
    render._run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-t", f"{T + 0.5:.3f}", "-an",
                 "-c:v", "copy", cut])
    render._base(cut, plan, base, seed)             # same text hiding + visual variation as voice mode
    os.remove(cut)
    fade = min(1.5, T / 4)
    af = (f"[1:a]silenceremove=start_periods=1:start_threshold=-45dB,atrim=0:{T:.3f},asetpts=PTS-STARTPTS,"
          f"afade=t=in:d=0.3,afade=t=out:st={max(0, T - fade):.3f}:d={fade:.3f},"
          f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100[a]")
    render._run(["ffmpeg", "-y", "-loglevel", "error", "-i", base, "-stream_loop", "-1", "-i", music_path,
                 "-filter_complex", af, "-map", "0:v", "-map", "[a]", "-t", f"{T:.3f}",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path])
    try:
        os.remove(base)
    except OSError:
        pass


# ---------------- Telegram ----------------
def buttons(job_id):
    return json.dumps({"inline_keyboard": [
        [{"text": "✅ Duyệt & đăng", "callback_data": f"ok:{job_id}"}],
        [{"text": "🎵 Đổi nhạc", "callback_data": f"mu:{job_id}"},
         {"text": "🗑 Bỏ", "callback_data": f"no:{job_id}"}],
    ]})


def caption(job, plan):
    links = job["product_link"]
    lines = [f"🎬 #{job['id']} · {job['name']}  (chế độ nhạc)",
             "🔗 Link:" + ("\n" + "\n".join(f"  • {l}" for l in links.splitlines()) if links
                          else " CHƯA CÓ – reply tin này bằng link Shopee (tối đa 3, mỗi link 1 dòng)"),
             f"🎵 Nhạc: {plan['track_name']}",
             "📝 Caption: " + (plan.get("post_caption") or "chưa có – reply tin này bằng caption muốn đăng"),
             "",
             "Bấm 🎵 Đổi nhạc để lấy bài ngẫu nhiên khác trong kho (không lặp bài đã dùng)."]
    return "\n".join(lines)
