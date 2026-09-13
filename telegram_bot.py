import json
import threading
from datetime import datetime

import requests

from config import (
    ESCALATED_IP_FILE,
    EXPIRE_LABELS,
    TG_ADMIN_IDS,
    TG_BOT_TOKEN,
    TG_CHAT_ID,
)
from file_utils import delete_uploaded_file
from ip_utils import append_ip_to_file, remove_ip_from_file


# ---------- Telegram API ----------
def tg_api(method, data=None):
    if not TG_BOT_TOKEN:
        print("[TG] TELEGRAM_BOT_TOKEN is not set")
        return None
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{method}"
    try:
        r = requests.post(url, data=data or {}, timeout=10)
        if r.status_code != 200:
            print(f"[TG] {method} error: {r.status_code} {r.text}")
        return r
    except requests.RequestException as e:
        print(f"[TG] {method} exception: {e}")
        return None


def tg_send_message(chat_id, text, reply_markup=None, parse_mode=None):
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return tg_api("sendMessage", data)


def tg_answer_callback(callback_id, text=None, show_alert=False):
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text
    if show_alert:
        data["show_alert"] = "true"
    return tg_api("answerCallbackQuery", data)


def tg_edit_message_text(chat_id, message_id, text, reply_markup=None, parse_mode=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return tg_api("editMessageText", data)


def is_admin(user_id):
    return str(user_id) in TG_ADMIN_IDS


def escape_markdown(text):
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '!']
    for ch in special_chars:
        text = text.replace(ch, '\\' + ch)
    return text


def build_notification_markup(filename, user_ip, escalated):
    row = [
        {"text": "Удалить файл", "callback_data": f"del:{filename}"},
    ]
    if escalated:
        row.append({"text": "Deescalate", "callback_data": f"desc:{user_ip}"})
    else:
        row.append({"text": "Escalate", "callback_data": f"esc:{user_ip}"})
    return {"inline_keyboard": [row]}


def send_telegram_notification(filename, original_filename, file_size, file_url,
                               user_ip, expire_str, escalated=False, source='web'):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[TG] Notification skipped: missing token or chat_id")
        return

    def _send():
        expire_readable = EXPIRE_LABELS.get(expire_str, '1 day')

        filename_esc = escape_markdown(filename)
        original_filename_esc = escape_markdown(original_filename)
        user_ip_esc = escape_markdown(user_ip)
        file_url_esc = escape_markdown(file_url)

        message = (
            f"📁 *New file uploaded*\n"
            f"🔹 *Site:* TEMP.MARE.BY\n"
            f"🔹 *Source:* {source.upper()}\n"
            f"🔹 *ID:* `{filename_esc}`\n"
            f"🔹 *Original:* {original_filename_esc}\n"
            f"🔹 *Size:* {file_size / 1024:.2f} KB\n"
            f"🔹 *User IP:* `{user_ip_esc}`\n"
            f"🔹 *URL:* {file_url_esc}\n"
            f"⏳ *Expires:* {expire_readable}\n"
            f"🕒 *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if escalated:
            message += (
                "\n\n⚠ *ВНИМАНИЕ!* Файл загружен с плохого IP-адреса!\n"
                "Проверьте содержимое с особой внимательностью!\n"
                "@styrbo @voidoffear"
            )

        reply_markup = build_notification_markup(filename, user_ip, escalated)

        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        try:
            r = requests.post(url, data={
                "chat_id": TG_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(reply_markup, ensure_ascii=False),
            }, timeout=5)
            if r.status_code != 200:
                print(f"[TG] send error: {r.status_code} - {r.text}")
        except requests.RequestException as e:
            print(f"[TG] send error: {e}")

    threading.Thread(target=_send, daemon=True).start()


# ---------- Buttons ----------
def handle_telegram_callback(callback):
    callback_id = callback.get("id")
    user_id = callback.get("from", {}).get("id")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    data = callback.get("data", "")

    if not is_admin(user_id):
        tg_answer_callback(callback_id, "Unsufficient rights", show_alert=True)
        return

    if data.startswith("del:"):
        filename = data[4:]
        ok, msg = delete_uploaded_file(filename)
        if ok:
            old_text = message.get("text", "")
            new_text = old_text + f"\n\nDeleted: {filename}"
            tg_edit_message_text(
                chat_id, message_id, new_text,
                reply_markup={"inline_keyboard": []},
                parse_mode="Markdown",
            )
            tg_answer_callback(callback_id, "File deleted")
        else:
            tg_answer_callback(callback_id, msg, show_alert=True)
        return

    if data.startswith("esc:") or data.startswith("desc:"):
        action = "esc" if data.startswith("esc:") else "desc"
        ip = data.split(":", 1)[1]

        if action == "esc":
            ok, msg = append_ip_to_file(ESCALATED_IP_FILE, ip, f"via button by {user_id}")
        else:
            ok, msg = remove_ip_from_file(ESCALATED_IP_FILE, ip)

        tg_answer_callback(callback_id, msg, show_alert=True)
        if not ok:
            return

        new_escalated = (action == "esc")
        old_text = message.get("text", "")
        old_markup = message.get("reply_markup", {}) or {}
        rows = old_markup.get("inline_keyboard", [])

        new_rows = []
        for row in rows:
            new_row = []
            for btn in row:
                bd = btn.get("callback_data", "")
                if bd.startswith("esc:") or bd.startswith("desc:"):
                    if new_escalated:
                        new_row.append({"text": "Deescalate", "callback_data": f"desc:{ip}"})
                    else:
                        new_row.append({"text": "Escalate", "callback_data": f"esc:{ip}"})
                else:
                    new_row.append(btn)
            new_rows.append(new_row)

        tg_edit_message_text(
            chat_id, message_id, old_text,
            reply_markup={"inline_keyboard": new_rows},
            parse_mode="Markdown",
        )
        return

    tg_answer_callback(callback_id, "Unknown action", show_alert=True)
