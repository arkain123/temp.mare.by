import os

from flask import Flask

from config import MAX_FILE_SIZE, UPLOAD_FOLDER
from routes import bp, start_cleanup_thread_once


def create_app():
    app = Flask(__name__, static_url_path='/static')
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    app.register_blueprint(bp)
    return app


app = create_app()
start_cleanup_thread_once()


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5001)
