"""Find burned-in foreign (Chinese/Japanese/Korean) text with OCR so we know exactly where to hide it.
Much more precise than asking the LLM to guess positions."""
import os
import re
import subprocess

FOREIGN = re.compile(r"[぀-ヿ㐀-鿿가-힯＀-￯]")
_engine = None


def _ocr():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def detect(src, workdir, end_cut, max_samples=100):
    """Returns (bands, title_card_time).
    bands: list of dicts, most subtitle-like first:
      y_top, y_bottom, x_left, x_right (0..1 of frame), weight (frames seen),
      windows [(t0, t1), ...] = when the text is on screen (source seconds), always (bool).
    title_card_time: start of a dense text card near the end (to cut), or None."""
    d = os.path.join(workdir, "ocr")
    os.makedirs(d, exist_ok=True)
    step = max(0.5, end_cut / max_samples)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-t", f"{end_cut:.3f}", "-i", src,
                    "-vf", f"fps=1/{step},scale=540:-2", os.path.join(d, "f%03d.jpg")], check=True)
    files = sorted(f for f in os.listdir(d) if f.endswith(".jpg"))
    eng = _ocr()
    boxes, title_t = [], None
    for i, f in enumerate(files):
        p = os.path.join(d, f)
        res, _ = eng(p)
        w, h = _size(p)
        t = (i + 0.5) * step
        found = []
        for box, txt, score in (res or []):
            if float(score) < 0.4 or not FOREIGN.search(txt):
                continue
            xs = [pt[0] for pt in box]; ys = [pt[1] for pt in box]
            found.append((min(ys) / h, max(ys) / h, min(xs) / w, max(xs) / w, t))
        if len(found) >= 5:                 # wall of text = title/recipe card
            if t > end_cut * 0.7 and title_t is None:
                title_t = max(0.5, t - step)
            continue
        boxes += found

    # group boxes that sit on the same text line (similar vertical centre and height)
    bands = []
    for y0, y1, x0, x1, t in sorted(boxes):
        c, hh = (y0 + y1) / 2, y1 - y0
        for b in bands:
            if abs(b["c"] - c) <= 0.02 and abs(b["h"] - hh) <= 0.03:
                b["y0"] = min(b["y0"], y0); b["y1"] = max(b["y1"], y1)
                b["x0"] = min(b["x0"], x0); b["x1"] = max(b["x1"], x1); b["ts"].add(t)
                break
        else:
            bands.append({"c": c, "h": hh, "y0": y0, "y1": y1, "x0": x0, "x1": x1, "ts": {t}})
    n_frames = max(1, len(files))
    out = []
    for b in bands:
        ts = sorted(b["ts"])
        wins = []
        for t in ts:                                   # visible from half a step before to a step after
            a, z = max(0.0, t - step), min(end_cut, t + step)
            if wins and a <= wins[-1][1] + 6.0:     # bridge short gaps (OCR misses faint frames)
                wins[-1][1] = z
            else:
                wins.append([a, z])
        out.append({"y_top": max(0.0, b["y0"] - 0.012), "y_bottom": min(1.0, b["y1"] + 0.012),
                    "x_left": max(0.0, b["x0"] - 0.03), "x_right": min(1.0, b["x1"] + 0.03),
                    "weight": len(ts), "windows": [tuple(x) for x in wins],
                    # watermarks/channel names: small, keep reappearing, OCR misses faint frames -> hide all video
                    "always": len(ts) >= 0.25 * n_frames or (len(ts) >= 8 and b["y1"] - b["y0"] <= 0.08)})
    # put the band that looks most like a subtitle line first (thin + frequent); our subtitles go there
    out.sort(key=lambda b: -(b["weight"] * (1.0 if b["y_bottom"] - b["y_top"] <= 0.09 else 0.3)))
    return out[:8], title_t


def _size(path):
    from PIL import Image
    with Image.open(path) as im:
        return im.size
