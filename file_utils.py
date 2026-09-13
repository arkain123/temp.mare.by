import json
import os
import random
import string
import threading
from datetime import datetime

from config import (
    BANNED_EXTENSIONS,
    DEFAULT_EXPIRE,
    EXPIRE_OPTIONS,
    METADATA_FILE,
    UPLOAD_FOLDER,
)

metadata_lock = threading.Lock()


def load_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_metadata(metadata):
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def add_metadata(filename, original, size, expire_str):
    if expire_str not in EXPIRE_OPTIONS:
        expire_str = DEFAULT_EXPIRE

    expiry_timestamp = datetime.now().timestamp() + EXPIRE_OPTIONS[expire_str]

    with metadata_lock:
        metadata = load_metadata()
        metadata[filename] = {
            'original': original,
            'expiry': expiry_timestamp,
            'expire_str': expire_str,
            'size': size,
            'upload_time': datetime.now().isoformat(),
        }
        save_metadata(metadata)


def remove_metadata(filename):
    with metadata_lock:
        metadata = load_metadata()
        if filename in metadata:
            del metadata[filename]
            save_metadata(metadata)


def delete_expired_files():
    now = datetime.now().timestamp()
    with metadata_lock:
        metadata = load_metadata()
        to_delete = [f for f, d in metadata.items() if now > d.get('expiry', 0)]
        for filename in to_delete:
            path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"[CLEANUP] File deleted: {filename}")
                except OSError as e:
                    print(f"[CLEANUP] Error in deleting {filename}: {e}")
            metadata.pop(filename, None)
        if to_delete:
            save_metadata(metadata)

def is_allowed_file(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext not in BANNED_EXTENSIONS


def generate_short_id(length=8):
    chars = string.ascii_lowercase + string.digits + string.ascii_uppercase
    existing = os.listdir(UPLOAD_FOLDER) if os.path.isdir(UPLOAD_FOLDER) else []

    while True:
        short_id = ''.join(random.choice(chars) for _ in range(length))
        if not any(f.startswith(short_id) for f in existing):
            return short_id


def delete_uploaded_file(filename):
    if not filename or filename != os.path.basename(filename) or filename in (".", ".."):
        return False, "Incorrect filename"

    path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.isfile(path):
        return False, "File not found"

    try:
        os.remove(path)
        return True, "File deleted"
    except OSError as e:
        return False, f"Deleting error: {e}"
