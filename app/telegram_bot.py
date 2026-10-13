"""Minimal Telegram Bot API client (long polling) for the approval flow."""
import json
import time

import requests

from . import config

API = "https://api.telegram.org/bot{}/{}"


def call(method, data=None, files=None, timeout=60):
    r = requests.post(API.format(config.TELEGRAM_BOT_TOKEN, method), data=data, files=files, timeout=timeout)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram {method} lỗi: {j}")
    return j["result"]


def buttons(job_id):
    return json.dumps({"inline_keyboard": [
        [{"text": "✅ Duyệt & đăng", "callback_data": f"ok:{job_id}"}],
        [{"text": "🔁 Viết lại thoại", "callback_data": f"re:{job_id}"},
         {"text": "🗑 Bỏ", "callback_data": f"no:{job_id}"}],
    ]})


def send_text(text, reply_to=None, markup=None):
    data = {"chat_id": config.TELEGRAM_ADMIN_CHAT_ID, "text": text[:4000], "disable_web_page_preview": True}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    if markup:
        data["reply_markup"] = markup
    try:
        return call("sendMessage", data)
    except Exception as e:
        print("telegram send_text failed:", e)


def send_video(path, caption, job_id):
    with open(path, "rb") as f:
        data = {"chat_id": config.TELEGRAM_ADMIN_CHAT_ID, "caption": caption[:1000], "supports_streaming": True}
        if job_id is not None:
            data["reply_markup"] = buttons(job_id)
        res = call("sendVideo", data, files={"video": f}, timeout=300)
    return res["message_id"]


def answer(callback_id, text=""):
    try:
        call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})
    except Exception:
        pass


def clear_buttons(message_id):
    try:
        call("editMessageReplyMarkup", {"chat_id": config.TELEGRAM_ADMIN_CHAT_ID, "message_id": message_id,
                                        "reply_markup": json.dumps({"inline_keyboard": []})})
    except Exception:
        pass


def updates(offset):
    try:
        return call("getUpdates", {"offset": offset, "timeout": 50,
                                   "allowed_updates": json.dumps(["message", "callback_query"])}, timeout=70)
    except Exception as e:
        print("telegram poll error:", e)
        time.sleep(5)
        return []
