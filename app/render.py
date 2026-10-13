"""Builds the final 9:16 video with ffmpeg: hide foreign text, light visual variation,
retime each scene to fit the Vietnamese voice, burn Vietnamese subtitles, mux new audio."""
import json
import os
import random
import subprocess

import numpy as np

from . import config, tts

W, H, FPS = 1080, 1920, 30
SR = tts.SR


def _run(args):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg lỗi: " + p.stderr[-1500:])


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    return int(s["width"]), int(s["height"]), float(d["format"]["duration"])


# ---------------- pass 1: clean + vary + fit to 1080x1920 ----------------
def _base(src, plan, out, seed):
    w, h, _ = _probe(src)
    rnd = random.Random(seed)
    z = rnd.uniform(1.04, 1.08)
    sat, con, bri = rnd.uniform(1.05, 1.15), rnd.uniform(1.02, 1.07), rnd.uniform(0.0, 0.03)
    warm = rnd.uniform(0.0, 0.05)
    flip = config.FLIP_ENABLED and plan.get("flip_safe")

    chain, last = [], "0:v"
    for i, b in enumerate(plan["text_bands"]):
        y0 = int(b["y_top"] * h) // 2 * 2
        bh = max(2, int((b["y_bottom"] - b["y_top"]) * h) // 2 * 2)
        x0 = int(b.get("x_left", 0) * w) // 2 * 2
        bw = max(2, int((b.get("x_right", 1) - b.get("x_left", 0)) * w) // 2 * 2)
        bw = min(bw, w - x0)
        if b.get("windows") and not b.get("always"):
            en = "+".join(f"between(t,{a:.2f},{z:.2f})" for a, z in b["windows"])
            enable = f":enable='{en}'"
        else:
            enable = ""
        rad = max(2, min(24, bh // 4, bw // 4))          # boxblur radius must fit inside the crop
        chain.append(f"[{last}]split[m{i}][c{i}];[c{i}]crop={bw}:{bh}:{x0}:{y0},"
                     f"boxblur={rad}:4:{max(1, rad // 2)}:4[b{i}];"
                     f"[m{i}][b{i}]overlay={x0}:{y0}{enable}[o{i}]")
        last = f"o{i}"
    zw, zh = int(w * z) // 2 * 2, int(h * z) // 2 * 2
    grade = (f"scale={zw}:{zh},crop={w // 2 * 2}:{h // 2 * 2},"
             f"eq=saturation={sat:.3f}:contrast={con:.3f}:brightness={bri:.3f},"
             f"colorbalance=rm={warm:.3f}:bm={-warm:.3f}" + (",hflip" if flip else ""))
    tall = h / w >= 16 / 9 - 0.02
    if tall:
        chain.append(f"[{last}]{grade},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                     f"fps={FPS},setsar=1[v]")
        s = max(W / w, H / h); hc = h * s; off = -(hc - H) / 2
    else:
        chain.append(f"[{last}]{grade},split[g1][g2];"
                     f"[g1]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:3[bg];"
                     f"[g2]scale={W}:-2[fg];[bg][fg]overlay=0:(H-h)/2,fps={FPS},setsar=1[v]")
        s = W / w; hc = h * s; off = (H - hc) / 2
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-filter_complex", ";".join(chain),
          "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", out])

    def y_out(yn):  # map a source y (0..1) to output pixels
        return ((yn - 0.5) * z + 0.5) * hc + off
    bands = [(y_out(b["y_top"]), y_out(b["y_bottom"])) for b in plan["text_bands"]]
    return [(max(0, a), min(H, b)) for a, b in bands if b > 0 and a < H]


# ---------------- subtitles (ASS) ----------------
def _ass_time(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _esc(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _chunks(text, n=7):
    out, cur = [], []
    for w in text.split():
        cur.append(w)
        if len(cur) >= n or w[-1] in ".,?!:;":
            out.append(" ".join(cur)); cur = []
    return out + ([" ".join(cur)] if cur else [])


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Be Vietnam Pro ExtraBold,78,&H00191919,&H00191919,&H10FFFFFF,&H00000000,0,0,0,0,100,100,0,0,3,20,0,5,80,80,0,1
Style: Head,Be Vietnam Pro Black,96,&H00141414,&H00141414,&H003BD4FF,&H00000000,0,0,0,0,100,100,0,0,3,20,0,8,70,70,0,1
Style: Badge,Be Vietnam Pro Black,108,&H00FFFFFF,&H00FFFFFF,&H002828E6,&H00000000,0,0,0,0,100,100,0,0,3,22,0,5,70,70,0,1
Style: Shape,Be Vietnam Pro Bold,20,&H00EBF8FF,&H00EBF8FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _write_ass(path, timeline, total, end_start, plan, bands, vo_durs, cta_dur):
    sub_y = int(sum(bands[0]) / 2) if bands else int(H * 0.70)   # bands[0] = most frequent caption line
    ev = []
    pop = "\\fscx85\\fscy85\\t(0,140,\\fscx100\\fscy100)"
    for i, (seg, (ts, T)) in enumerate(zip(plan["segments"], timeline)):
        ch = _chunks(seg["subtitle"]); tot = sum(len(c) for c in ch) or 1; t0 = ts
        for j, c in enumerate(ch):
            t1 = ts + T if j == len(ch) - 1 else t0 + vo_durs[i] * len(c) / tot
            ev.append(f"Dialogue: 2,{_ass_time(t0)},{_ass_time(t1)},Sub,,0,0,0,,{{\\an5\\pos(540,{sub_y}){pop}}}{_esc(c)}")
            t0 = t1
    if plan.get("headline") and timeline:
        ts, T = timeline[0]
        ev.append(f"Dialogue: 3,{_ass_time(ts)},{_ass_time(ts + T)},Head,,0,0,0,,{{\\pos(540,120){pop}}}{_esc(plan['headline'])}")
    ev.append(f"Dialogue: 2,{_ass_time(end_start)},{_ass_time(total)},Sub,,0,0,0,,{{\\an5\\pos(540,{sub_y}){pop}}}{_esc(plan['cta_subtitle'] or plan['cta_voice'])}")
    by = 1560 if sub_y < 1300 else 700
    ev.append(f"Dialogue: 3,{_ass_time(end_start + 0.3)},{_ass_time(total)},Badge,,0,0,0,,"
              f"{{\\an5\\pos(540,{by})\\fscx60\\fscy60\\t(0,220,\\fscx100\\fscy100)}}{_esc(plan.get('cta_badge') or 'XEM BÌNH LUẬN')}")
    ev.append(f"Dialogue: 3,{_ass_time(end_start + 0.6)},{_ass_time(total)},Shape,,0,0,0,,"
              f"{{\\an7\\pos(490,{by + 100})\\1c&H2828E6&\\1a&H00&\\p1}}m 0 0 l 100 0 l 50 60{{\\p0}}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(ASS_HEAD + "\n".join(ev) + "\n")


# ---------------- audio ----------------
def _music(n, total):
    bpm = 100; beat = 60 / bpm; mus = np.zeros(n, np.float32)
    chords = [[261.6, 329.6, 392.0], [220.0, 261.6, 329.6], [174.6, 220.0, 261.6], [196.0, 246.9, 293.7]]
    for bi in range(int(total / beat) + 1):
        st = int(bi * beat * SR); L = int(0.5 * SR); sg = np.arange(L) / SR
        note = sum(np.sin(2 * np.pi * f * sg) for f in chords[(bi // 4) % 4]) / 3 * np.exp(-sg * 6)
        e = min(n, st + L); mus[st:e] += note[:e - st] * (0.5 if bi % 2 == 0 else 0.3)
    return mus


def _mix(path, voices, starts, total):
    n = int(total * SR) + 1; mix = np.zeros(n, np.float32)
    for v, t in zip(voices, starts):
        o = int(t * SR); mix[o:o + len(v)] += v[:max(0, n - o)]
    if config.MUSIC_ENABLED:
        win = int(0.2 * SR)
        env = np.convolve(np.abs(mix), np.ones(win) / win, "same")
        duck = np.convolve(np.where(env > 0.01, 0.08, 0.2), np.ones(win) / win, "same")
        mix += _music(n, total) * duck * np.minimum(1, (total - np.arange(n) / SR) / 0.8)
    peak = np.abs(mix).max() or 1
    (mix / peak * 0.92).astype(np.float32).tofile(path)


# ---------------- main entry ----------------
def render(src, plan, workdir, out_path, seed=0):
    base = os.path.join(workdir, "base.mp4")
    bands = _base(src, plan, base, seed)

    voices = [tts.speak(s["voice"]) for s in plan["segments"]]
    cta = tts.speak(plan["cta_voice"])
    vo_durs = [len(v) / SR for v in voices]

    timeline, t = [], 0.0
    for s, vd in zip(plan["segments"], vo_durs):
        dsrc = s["end"] - s["start"]
        T = max(vd + 0.25, dsrc / 1.2)
        timeline.append((t, T)); t += T
    end_start = t
    cta_T = len(cta) / SR + 1.3
    total = end_start + cta_T

    parts, fc = [], []
    for i, (s, (ts, T)) in enumerate(zip(plan["segments"], timeline)):
        dsrc = s["end"] - s["start"]
        slow = min(T / dsrc, 2.5); pad = T - dsrc * slow
        f = f"[0:v]trim={s['start']:.3f}:{s['end']:.3f},setpts=(PTS-STARTPTS)*{slow:.4f}"
        if pad > 0.01:
            f += f",tpad=stop_mode=clone:stop_duration={pad:.3f}"
        fc.append(f + f"[s{i}]"); parts.append(f"[s{i}]")
    last_end = plan["segments"][-1]["end"]
    fc.append(f"[0:v]trim={max(0, last_end - 0.1):.3f}:{last_end:.3f},setpts=PTS-STARTPTS,"
              f"tpad=stop_mode=clone:stop_duration={cta_T:.3f}[se]")
    parts.append("[se]")

    ass = os.path.join(workdir, "subs.ass")
    _write_ass(ass, timeline, total, end_start, plan, bands, vo_durs, len(cta) / SR)
    wav = os.path.join(workdir, "mix.f32")
    _mix(wav, voices + [cta], [ts + 0.05 for ts, _ in timeline] + [end_start + 0.1], total)

    ass_esc = ass.replace(":", "\\:")
    fc.append("".join(parts) + f"concat=n={len(parts)}:v=1:a=0,fps={FPS},trim=0:{total:.3f},"
              f"subtitles='{ass_esc}':fontsdir='{config.FONT_DIR}'[v]")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", base, "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", wav,
          "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "1:a", "-t", f"{total:.3f}",
          "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_path])
    return {"duration": total}


def telegram_preview(path, workdir):
    """Telegram bots can only send files up to 50 MB; make a lighter copy when needed."""
    if os.path.getsize(path) < 48 * 1024 * 1024:
        return path
    small = os.path.join(workdir, "preview.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf", "scale=720:-2", "-c:v", "libx264",
          "-crf", "28", "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k", small])
    return small
