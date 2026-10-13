"""Vietnamese text-to-speech. Returns mono float32 numpy audio at 24 kHz."""
import html
import subprocess
import time

import numpy as np
import requests

from . import config

SR = 24000


def _decode(audio_bytes):
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(SR), "pipe:1"],
                       input=audio_bytes, capture_output=True, check=True)
    x = np.frombuffer(p.stdout, np.float32).copy()
    idx = np.where(np.abs(x) > 0.01)[0]          # trim leading/trailing silence
    if len(idx):
        x = x[max(idx[0] - int(0.03 * SR), 0): idx[-1] + int(0.06 * SR)]
    return x


def _retry(fn, tries=4):
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


# ---------------- Vbee ----------------
def _vbee_chunk(text):
    r = requests.post("https://api.vbee.vn/v1/tts", timeout=60, headers={
        "Authorization": f"Bearer {config.VBEE_TOKEN}", "App-Id": config.VBEE_APP_ID,
        "Content-Type": "application/json"}, json={
        "text": text, "voiceCode": config.VBEE_VOICE, "outputFormat": "mp3",
        "bitrate": 128, "speed": config.VBEE_SPEED, "mode": "sync"})
    if r.status_code != 200 or r.headers.get("content-type", "").startswith("application/json"):
        raise RuntimeError(f"Vbee lỗi {r.status_code}: {r.text[:300]}")
    return r.content


def _split(text, limit):
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > limit:
            parts.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return parts + ([cur] if cur else [])


def _vbee(text):
    return np.concatenate([_decode(_retry(lambda c=c: _vbee_chunk(c))) for c in _split(text, 290)])


# ---------------- Azure ----------------
def _azure(text):
    ssml = (f"<speak version='1.0' xml:lang='vi-VN'><voice name='{config.AZURE_VOICE}'>"
            f"<prosody rate='{config.AZURE_RATE}'>{html.escape(text)}</prosody></voice></speak>")

    def call():
        r = requests.post(f"https://{config.AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1",
                          timeout=60, data=ssml.encode("utf-8"), headers={
                              "Ocp-Apim-Subscription-Key": config.AZURE_SPEECH_KEY,
                              "Content-Type": "application/ssml+xml",
                              "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                              "User-Agent": "shopee-video-bot"})
        r.raise_for_status()
        return r.content
    return _decode(_retry(call))


# ---------------- FPT.AI ----------------
def _fpt(text):
    def call():
        r = requests.post("https://api.fpt.ai/hmi/tts/v5", timeout=60, data=text.encode("utf-8"), headers={
            "api-key": config.FPT_API_KEY, "voice": config.FPT_VOICE, "speed": config.FPT_SPEED})
        r.raise_for_status()
        url = r.json()["async"]
        for _ in range(40):                      # audio file appears after a few seconds
            time.sleep(1.5)
            a = requests.get(url, timeout=30)
            if a.status_code == 200 and len(a.content) > 1000:
                return a.content
        raise RuntimeError("FPT.AI chưa trả file âm thanh")
    return _decode(_retry(call))


def speak(text):
    provider = {"vbee": _vbee, "azure": _azure, "fpt": _fpt}.get(config.TTS_PROVIDER)
    if not provider:
        raise RuntimeError(f"TTS_PROVIDER không hợp lệ: {config.TTS_PROVIDER}")
    return provider(text)
