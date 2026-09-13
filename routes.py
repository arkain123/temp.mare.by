import json
import os
import threading
import time
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from config import (
    BASE_URL,
    DEFAULT_EXPIRE,
    EXPIRE_LABELS,
    EXPIRE_OPTIONS,
    MIRRORS,
    TG_WEBHOOK_SECRET,
)
from file_utils import (
    add_metadata,
    delete_expired_files,
    generate_short_id,
    is_allowed_file,
    load_metadata,
    metadata_lock,
    remove_metadata,
    save_metadata,
)
from ip_utils import is_ip_in_list, load_banned_ips, load_escalated_ips
from telegram_bot import (
    handle_telegram_callback,
    send_telegram_notification,
)

bp = Blueprint("main", __name__)


# ---------- Cleanup thread (every 10 min) ----------
def _cleanup_worker():
    while True:
        time.sleep(600)
        try:
            delete_expired_files()
        except Exception as e:
            print(f"[CLEANUP] worker error: {e}")


_cleanup_thread_started = False
_cleanup_thread_lock = threading.Lock()


def start_cleanup_thread_once():
    global _cleanup_thread_started
    with _cleanup_thread_lock:
        if _cleanup_thread_started:
            return
        _cleanup_thread_started = True
    t = threading.Thread(target=_cleanup_worker, daemon=True)
    t.start()


# ---------- helpers ----------
def get_real_ip(req):
    cf_ip = req.headers.get('CF-Connecting-IP')
    if cf_ip:
        return cf_ip
    forwarded_ip = req.headers.get('X-Forwarded-For')
    if forwarded_ip:
        return forwarded_ip.split(',')[0].strip()
    return req.remote_addr


def process_upload(file, expire_str, source='web'):
    if not is_allowed_file(file.filename):
        return None, "Banned extension!", 400

    ext = os.path.splitext(file.filename)[1].lower() if '.' in file.filename else ''
    short_id = generate_short_id()
    filename = short_id + ext
    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    file_url = f"{BASE_URL}/{filename}"
    file_size = os.path.getsize(file_path)

    if expire_str not in EXPIRE_OPTIONS:
        expire_str = DEFAULT_EXPIRE

    add_metadata(filename, file.filename, file_size, expire_str)
    return filename, file_url, file_size


# ---------- IP Ban ----------
@bp.before_request
def block_banned_ips():
    p = request.path
    if p == '/blocked' or p.startswith('/static/') or p == '/faq' or p.startswith('/telegram/'):
        return

    user_ip = get_real_ip(request)
    if not is_ip_in_list(user_ip, load_banned_ips()):
        return

    filename = p.lstrip('/')
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    if filename and os.path.exists(os.path.join(upload_folder, filename)):
        return

    if p.startswith('/api/') or p == '/config':
        return "Your IP has been blocked for violating mare policies", 403

    return redirect(url_for('main.blocked_page'))


# ---------- Routes ----------
@bp.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        if "file" not in request.files:
            return "Choose a file!", 400

        file = request.files["file"]
        if file.filename == "":
            return "Choose a file!", 400

        expire_str = request.form.get('expire', DEFAULT_EXPIRE)
        result = process_upload(file, expire_str, source='web')
        if not isinstance(result, tuple) or len(result) != 3:
            return result[1], result[2]
        filename, file_url, file_size = result

        user_ip = get_real_ip(request)
        escalated = is_ip_in_list(user_ip, load_escalated_ips())
        expire_readable = EXPIRE_LABELS.get(expire_str, '1 day')

        log_msg = (
            f"[UPLOAD] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - "
            f"IP: {user_ip} - File: {filename} (original: {file.filename}) - "
            f"Size: {file_size} bytes - URL: {file_url} - Expire: {expire_str}"
        )
        if escalated:
            log_msg += " [ESCALATED]"
        print(log_msg)

        send_telegram_notification(
            filename, file.filename, file_size, file_url,
            user_ip, expire_str, escalated, source='web',
        )
        return render_template("success.html", file_url=file_url, expire=expire_readable)

    return render_template("upload.html", mirrors=MIRRORS)


@bp.route("/api/upload", methods=["POST"])
def api_upload():
    if 'files[]' not in request.files:
        return "No file part", 400

    files = request.files.getlist('files[]')
    if not files or files[0].filename == '':
        return "No selected file", 400

    file = files[0]
    expire_str = request.form.get('expire', DEFAULT_EXPIRE)
    if expire_str not in EXPIRE_OPTIONS:
        expire_str = request.args.get('expire', DEFAULT_EXPIRE)

    result = process_upload(file, expire_str, source='api')
    if not isinstance(result, tuple) or len(result) != 3:
        return result[1], result[2]
    filename, file_url, file_size = result

    user_ip = get_real_ip(request)
    escalated = is_ip_in_list(user_ip, load_escalated_ips())

    log_msg = (
        f"[API UPLOAD] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - "
        f"IP: {user_ip} - File: {filename} (original: {file.filename}) - "
        f"Size: {file_size} bytes - URL: {file_url} - Expire: {expire_str}"
    )
    if escalated:
        log_msg += " [ESCALATED]"
    print(log_msg)

    send_telegram_notification(
        filename, file.filename, file_size, file_url,
        user_ip, expire_str, escalated, source='api',
    )
    return file_url, 200


@bp.route('/config')
def sharex_config():
    config = {
        "Version": "18.0.0",
        "Name": "temp.mare.by",
        "DestinationType": "FileUploader, ImageUploader",
        "RequestMethod": "POST",
        "RequestURL": f"{BASE_URL}/api/upload",
        "Parameters": {"output": "text", "expire": "1d"},
        "Body": "MultipartFormData",
        "FileFormName": "files[]",
        "URL": "{response}",
        "ErrorMessage": "{response}",
    }
    response = current_app.response_class(
        response=json.dumps(config, indent=2),
        status=200,
        mimetype='application/octet-stream',
    )
    response.headers["Content-Disposition"] = "attachment; filename=temp.mare.by.sxcu"
    return response


@bp.route('/faq')
def faq():
    return render_template('faq.html')


@bp.route('/blocked')
def blocked_page():
    return render_template('blocked.html'), 403


@bp.route('/banned.html')
def banned_redirect():
    return redirect(url_for('main.blocked_page'))


@bp.route('/robots.txt')
def robots_txt():
    return send_from_directory(current_app.root_path, 'robots.txt')


@bp.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='favicon-32x32.png'))


@bp.route("/<filename>")
def download_file(filename):
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    file_path = os.path.join(upload_folder, filename)

    if not os.path.exists(file_path):
        return "File not found!", 404

    metadata = load_metadata()
    if filename in metadata:
        now = datetime.now().timestamp()
        if now > metadata[filename].get('expiry', 0):
            try:
                os.remove(file_path)
            except OSError:
                pass
            remove_metadata(filename)
            return "File expired!", 410
    else:
        try:
            os.remove(file_path)
        except OSError:
            pass
        return "File not found!", 404

    return send_from_directory(upload_folder, filename, as_attachment=False)


# ---------- Telegram webhook ----------
@bp.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if TG_WEBHOOK_SECRET and secret != TG_WEBHOOK_SECRET:
        return "forbidden", 403

    update = request.get_json(silent=True) or {}
    try:
        if "callback_query" in update:
            handle_telegram_callback(update["callback_query"])
    except Exception as e:
        print(f"[TG WEBHOOK] error: {e}")

    return "ok", 200
