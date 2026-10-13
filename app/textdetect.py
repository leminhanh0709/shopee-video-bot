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


def detect(src, workdir, end_cut, samples=24):
    """Returns (bands, title_card_time).
    bands: list of {"y_top","y_bottom","weight"} (0..1 of frame height), most frequent first.
    title_card_time: start of a dense text card near the end (to cut), or None."""
    d = os.path.join(workdir, "ocr")
    os.makedirs(d, exist_ok=True)
    step = max(0.4, end_cut / samples)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-t", f"{end_cut:.3f}", "-i", src,
                    "-vf", f"fps=1/{step},scale=540:-2", os.path.join(d, "f%03d.jpg")], check=True)
    files = sorted(f for f in os.listdir(d) if f.endswith(".jpg"))
    eng = _ocr()
    boxes, title_t = [], None
    for i, f in enumerate(files):
        p = os.path.join(d, f)
        res, _ = eng(p)
        h = _height(p)
        found = []
        for box, txt, score in (res or []):
            if float(score) < 0.5 or not FOREIGN.search(txt):
                continue
            ys = [pt[1] for pt in box]
            found.append((min(ys) / h, max(ys) / h))
        t = (i + 0.5) * step
        if len(found) >= 5:                 # wall of text = title/recipe card
            if t > end_cut * 0.7 and title_t is None:
                title_t = max(0.5, t - step)
            continue
        boxes += found

    # merge overlapping boxes into horizontal bands, counting how often each band shows up
    boxes.sort()
    bands = []
    for y0, y1 in boxes:
        if bands and y0 <= bands[-1][1] + 0.015:
            bands[-1][1] = max(bands[-1][1], y1); bands[-1][2] += 1
        else:
            bands.append([y0, y1, 1])
    out = [{"y_top": max(0.0, a - 0.012), "y_bottom": min(1.0, b + 0.012), "weight": n} for a, b, n in bands]
    # put the band that looks most like a subtitle line first (thin + frequent); our subtitles go there
    out.sort(key=lambda b: -(b["weight"] * (1.0 if b["y_bottom"] - b["y_top"] <= 0.09 else 0.3)))
    # never hide more than ~40% of the frame; keep the most frequent bands
    kept, cover = [], 0.0
    for b in out:
        hgt = b["y_bottom"] - b["y_top"]
        if cover + hgt > 0.4:
            continue
        kept.append(b); cover += hgt
    return kept, title_t


def _height(path):
    from PIL import Image
    with Image.open(path) as im:
        return im.height
