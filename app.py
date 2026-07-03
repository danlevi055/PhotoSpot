"""
PhotoSpot - אפליקציית תיעוד תמונות עם מיקום
Backend: Flask + SQLite

הרצה:
    pip install -r requirements.txt
    python app.py
"""

import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template, send_from_directory, abort
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# הגדרות בסיסיות
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "photospot.db")

# סוגי קבצים מותרים (רק תמונות)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
# מגבלת גודל קובץ: 8 מגה-בייט
MAX_CONTENT_LENGTH = 8 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# מוודאים שתיקיית ההעלאות קיימת
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# מסד נתונים (SQLite)
# ---------------------------------------------------------------------------

def get_db():
    """פותח חיבור למסד הנתונים ומחזיר שורות כמילון."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """יוצר את טבלת התמונות אם היא לא קיימת."""
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS photos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            filename  TEXT    NOT NULL,
            lat       REAL,
            lng       REAL,
            caption   TEXT,
            timestamp TEXT    NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# פונקציות עזר
# ---------------------------------------------------------------------------

def allowed_file(filename):
    """בודק שסיומת הקובץ היא של תמונה מותרת."""
    return "." in filename and \
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_float(value):
    """ממיר בבטחה מחרוזת למספר עשרוני, ומחזיר None אם נכשל."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """מגיש את העמוד הראשי."""
    return render_template("index.html")


@app.route("/api/photos", methods=["POST"])
def upload_photo():
    """
    מקבל multipart form: image, lat, lng, caption.
    שומר את התמונה לתיקיית uploads/ ואת המטא-דאטה למסד הנתונים.
    """
    # 1. ולידציה - חייבת להיות תמונה בבקשה
    if "image" not in request.files:
        return jsonify({"error": "לא נשלחה תמונה"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "שם קובץ ריק"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "סוג קובץ לא נתמך (רק תמונות)"}), 400

    # 2. שם קובץ בטוח + תוספת חותמת זמן כדי למנוע דריסה
    original = secure_filename(file.filename)
    ext = original.rsplit(".", 1)[1].lower()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    filename = f"{stamp}.{ext}"
    file.save(os.path.join(UPLOAD_DIR, filename))

    # 3. קריאת שאר השדות מהטופס
    lat = parse_float(request.form.get("lat"))
    lng = parse_float(request.form.get("lng"))
    caption = (request.form.get("caption") or "").strip()
    timestamp = datetime.now(timezone.utc).isoformat()

    # 4. שמירה למסד הנתונים
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO photos (filename, lat, lng, caption, timestamp) "
        "VALUES (?, ?, ?, ?, ?)",
        (filename, lat, lng, caption, timestamp),
    )
    conn.commit()
    photo_id = cur.lastrowid
    conn.close()

    return jsonify({
        "id": photo_id,
        "filename": filename,
        "url": f"/uploads/{filename}",
        "lat": lat,
        "lng": lng,
        "caption": caption,
        "timestamp": timestamp,
    }), 201


@app.route("/api/photos", methods=["GET"])
def list_photos():
    """מחזיר JSON עם כל הרשומות, מהחדשה לישנה."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, filename, lat, lng, caption, timestamp "
        "FROM photos ORDER BY id DESC"
    ).fetchall()
    conn.close()

    photos = []
    for row in rows:
        photos.append({
            "id": row["id"],
            "filename": row["filename"],
            "url": f"/uploads/{row['filename']}",
            "lat": row["lat"],
            "lng": row["lng"],
            "caption": row["caption"],
            "timestamp": row["timestamp"],
        })
    return jsonify(photos)


@app.route("/uploads/<name>")
def uploaded_file(name):
    """מגיש קובץ תמונה מתיקיית ההעלאות (עם שם קובץ בטוח)."""
    safe_name = secure_filename(name)
    if not safe_name:
        abort(404)
    return send_from_directory(UPLOAD_DIR, safe_name)


@app.errorhandler(413)
def too_large(_e):
    """נקרא כאשר הקובץ חורג ממגבלת הגודל."""
    return jsonify({"error": "הקובץ גדול מדי (מקסימום 8MB)"}), 413


# ---------------------------------------------------------------------------
# נקודת הכניסה
# ---------------------------------------------------------------------------

# מאתחלים את מסד הנתונים בזמן טעינת המודול (עובד גם תחת gunicorn).
init_db()

if __name__ == "__main__":
    # קריאת PORT ממשתנה סביבה, ברירת מחדל 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
