"""All settings come from environment variables (set them in Railway → Variables)."""
import os


def _get(name, default=None, required=False):
    v = os.environ.get(name, default)
    if required and not v:
        raise RuntimeError(f"Thiếu biến môi trường: {name}")
    return v


def _bool(name, default="0"):
    return str(os.environ.get(name, default)).strip().lower() in ("1", "true", "yes", "on")


# --- Google Drive (OAuth user token, see scripts/get_google_token.py) ---
GOOGLE_CLIENT_ID = _get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = _get("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = _get("GOOGLE_REFRESH_TOKEN")
DRIVE_INBOX_FOLDER_ID = _get("DRIVE_INBOX_FOLDER_ID")      # "Chờ làm"
DRIVE_SOURCE_DONE_FOLDER_ID = _get("DRIVE_SOURCE_DONE_FOLDER_ID")  # "Video gốc đã xử lý"
DRIVE_OUTPUT_FOLDER_ID = _get("DRIVE_OUTPUT_FOLDER_ID")    # "Thành phẩm"
DRIVE_POLL_SECONDS = int(_get("DRIVE_POLL_SECONDS", "300"))

# --- Claude ---
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _get("CLAUDE_MODEL", "claude-sonnet-4-5")
MAX_FRAMES = int(_get("MAX_FRAMES", "60"))
STYLE_NOTE = _get("STYLE_NOTE", "")  # extra direction for the script, optional

# --- Text to speech ---
TTS_PROVIDER = _get("TTS_PROVIDER", "vbee").lower()   # vbee | azure | fpt
VBEE_APP_ID = _get("VBEE_APP_ID")
VBEE_TOKEN = _get("VBEE_TOKEN")
VBEE_VOICE = _get("VBEE_VOICE", "hn_female_ngochuyen_full_48k-fhg")
VBEE_SPEED = float(_get("VBEE_SPEED", "1.1"))
AZURE_SPEECH_KEY = _get("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = _get("AZURE_SPEECH_REGION", "southeastasia")
AZURE_VOICE = _get("AZURE_VOICE", "vi-VN-HoaiMyNeural")
AZURE_RATE = _get("AZURE_RATE", "+10%")
FPT_API_KEY = _get("FPT_API_KEY")
FPT_VOICE = _get("FPT_VOICE", "banmai")
FPT_SPEED = _get("FPT_SPEED", "0")

# --- Telegram ---
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_CHAT_ID = _get("TELEGRAM_ADMIN_CHAT_ID")

# --- Facebook (phase 2) ---
FB_ENABLED = _bool("FB_ENABLED", "0")
FB_PAGE_ID = _get("FB_PAGE_ID")
FB_PAGE_TOKEN = _get("FB_PAGE_TOKEN")
FB_GRAPH_VERSION = _get("FB_GRAPH_VERSION", "v23.0")
FB_COMMENT_TEMPLATE = _get("FB_COMMENT_TEMPLATE", "Link mua mình để ở đây nha 👉 {link}")
FB_COMMENT_MULTI_HEADER = _get("FB_COMMENT_MULTI_HEADER", "Đồ mình dùng trong video để ở đây nha 👇")

# --- Video options ---
MUSIC_ENABLED = _bool("MUSIC_ENABLED", "0")
FLIP_ENABLED = _bool("FLIP_ENABLED", "0")
SHOPEE_SHORT_DOMAIN = _get("SHOPEE_SHORT_DOMAIN", "https://s.shopee.vn/")

# --- Storage ---
DATA_DIR = _get("DATA_DIR", "/data")
WORK_DIR = os.path.join(DATA_DIR, "work")
DB_PATH = os.path.join(DATA_DIR, "jobs.db")
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

os.makedirs(WORK_DIR, exist_ok=True)
