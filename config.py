import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
METADATA_FILE = os.path.join(BASE_DIR, "file_metadata.json")

ESCALATED_IP_FILE = "/home/arkain123/apps/mare.by/escalated_ip.txt"
BLOCKED_IP_FILE = "/home/arkain123/apps/mare.by/blocked_ip.txt"

BANNED_EXTENSIONS = {
    'exe', 'scr', 'cpl', 'docm',
    'jar', 'html', 'htm', 'sh', 'bat', 'cmd',
    'js', 'vbs', 'ps1', 'msi', 'dll',
}

MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1024 MB

# TTL
EXPIRE_OPTIONS = {
    '1h': 3600,
    '6h': 6 * 3600,
    '12h': 12 * 3600,
    '1d': 24 * 3600,
    '3d': 3 * 24 * 3600,
    '7d': 7 * 24 * 3600,
}
DEFAULT_EXPIRE = '1d'

EXPIRE_LABELS = {
    '1h': '1 hour',
    '6h': '6 hours',
    '12h': '12 hours',
    '1d': '1 day',
    '3d': '3 days',
    '7d': '7 days',
}

BASE_URL = "https://temp.mare.by"
MIRRORS = ["https://temp.mare.by", "https://temp.mare.of.by"]

# Telegram
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TG_ADMIN_IDS = {
    x.strip() for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip()
}
TG_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
