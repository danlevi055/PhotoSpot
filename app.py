"""
PhotoSpot - אפליקציית תיעוד תמונות עם מיקום
Backend: Flask

אחסון גמיש שנקבע לפי משתני סביבה - כך שאותו קוד רץ גם מקומית וגם בענן:
  - מסד נתונים:  Postgres אם DATABASE_URL מוגדר, אחרת SQLite מקומי.
  - תמונות:      Cloudinary אם CLOUDINARY_URL מוגדר, אחרת תיקייה מקומית uploads/.

מקומית (בלי משתני סביבה) הכל עובד עם קבצים מקומיים - לא צריך חשבונות ענן.
בענן (עם משתני הסביבה) התמונות והמטא-דאטה נשמרים בשירותים חיצוניים קבועים,
כדי שהמערכת תעבוד 24/7 גם כשהמחשב שלך כבוי.
"""

import os
import sqlite3
from datetime import datetime, timezone

from flask import (
    Flask, request, jsonify, render_template, send_from_directory, abort,
    session, redirect, url_for,
)
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

# קוד הכניסה לאתר. ניתן לשנות דרך משתנה סביבה ACCESS_CODE.
ACCESS_CODE = os.environ.get("ACCESS_CODE", "DAN123")

# --- בחירת מנגנוני אחסון לפי משתני סביבה ---
DATABASE_URL = os.environ.get("DATABASE_URL")             # קיים -> משתמשים ב-Postgres
USE_POSTGRES = bool(DATABASE_URL)
USE_CLOUDINARY = bool(os.environ.get("CLOUDINARY_URL"))   # קיים -> משתמשים ב-Cloudinary

# מייבאים ספריות ענן רק כשצריך, כדי שפיתוח מקומי לא ידרוש אותן.
if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

if USE_CLOUDINARY:
    import cloudinary
    import cloudinary.uploader
    cloudinary.config()  # קורא אוטומטית את CLOUDINARY_URL ממשתני הסביבה

# תו ה-placeholder בשאילתות שונה בין שני מנועי מסד הנתונים.
PLACEHOLDER = "%s" if USE_POSTGRES else "?"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
# מפתח סודי לחתימה על ה-session (העוגייה שזוכרת שהמשתמש עבר את השער).
# בפרודקשן כדאי להגדיר SECRET_KEY אמיתי דרך משתנה סביבה.
app.secret_key = os.environ.get("SECRET_KEY", "photospot-dev-secret-change-me")

# מוודאים שתיקיית ההעלאות המקומית קיימת (בשימוש רק במצב מקומי)
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# מסד נתונים
# ---------------------------------------------------------------------------

def get_db():
    """פותח חיבור למסד הנתונים המתאים (Postgres בענן / SQLite מקומי)."""
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def dict_cursor(conn):
    """מחזיר cursor ששורותיו נגישות לפי שם עמודה, בשני המנועים."""
    if USE_POSTGRES:
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return conn.cursor()


def init_db():
    """יוצר את טבלת התמונות אם היא לא קיימת."""
    conn = get_db()
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS photos (
                id        SERIAL PRIMARY KEY,
                image_url TEXT NOT NULL,
                lat       DOUBLE PRECISION,
                lng       DOUBLE PRECISION,
                caption   TEXT,
                timestamp TEXT NOT NULL
            )
            """
        )
    else:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS photos (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                image_url TEXT NOT NULL,
                lat       REAL,
                lng       REAL,
                caption   TEXT,
                timestamp TEXT NOT NULL
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


def save_image(file, ext):
    """
    שומר את התמונה ומחזיר URL לגישה אליה.
    בענן:    מעלה ל-Cloudinary ומחזיר URL מלא (https://res.cloudinary.com/...).
    מקומית:  שומר לתיקיית uploads/ ומחזיר נתיב יחסי (/uploads/...).
    """
    if USE_CLOUDINARY:
        result = cloudinary.uploader.upload(file, folder="photospot")
        return result["secure_url"]

    # מצב מקומי: שם קובץ ייחודי לפי חותמת זמן, כדי למנוע דריסה.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    filename = f"{stamp}.{ext}"
    file.save(os.path.join(UPLOAD_DIR, filename))
    return f"/uploads/{filename}"


# ---------------------------------------------------------------------------
# שער כניסה (קוד גישה)
# ---------------------------------------------------------------------------

@app.before_request
def require_access_code():
    """
    רץ לפני כל בקשה. אם המשתמש עדיין לא עבר את השער -
    מפנה אותו לעמוד הכניסה (ומחזיר 401 עבור בקשות API).
    עמוד הכניסה עצמו פתוח כדי שאפשר יהיה להזין את הקוד.
    """
    if request.endpoint == "login":
        return None
    if session.get("authenticated"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "נדרש קוד גישה"}), 401
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """עמוד הכניסה: מציג טופס לקוד, ובודק אותו בשליחה."""
    error = None
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        if code == ACCESS_CODE:
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "קוד שגוי. נסה שוב."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    """יציאה - מנקה את ה-session ומחזיר לעמוד הכניסה."""
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes ראשיים
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """מגיש את העמוד הראשי."""
    return render_template("index.html")


@app.route("/api/photos", methods=["POST"])
def upload_photo():
    """
    מקבל multipart form: image, lat, lng, caption.
    שומר את התמונה (ענן/מקומי) ואת המטא-דאטה למסד הנתונים.
    """
    # 1. ולידציה - חייבת להיות תמונה בבקשה
    if "image" not in request.files:
        return jsonify({"error": "לא נשלחה תמונה"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "שם קובץ ריק"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "סוג קובץ לא נתמך (רק תמונות)"}), 400

    # 2. שמירת התמונה וקבלת ה-URL אליה
    ext = file.filename.rsplit(".", 1)[1].lower()  # תקין - allowed_file כבר אימת שיש סיומת
    image_url = save_image(file, ext)

    # 3. קריאת שאר השדות מהטופס
    lat = parse_float(request.form.get("lat"))
    lng = parse_float(request.form.get("lng"))
    caption = (request.form.get("caption") or "").strip()
    timestamp = datetime.now(timezone.utc).isoformat()

    # 4. שמירה למסד הנתונים
    conn = get_db()
    cur = conn.cursor()
    sql = (
        f"INSERT INTO photos (image_url, lat, lng, caption, timestamp) "
        f"VALUES ({PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER})"
    )
    if USE_POSTGRES:
        cur.execute(sql + " RETURNING id", (image_url, lat, lng, caption, timestamp))
        photo_id = cur.fetchone()[0]
    else:
        cur.execute(sql, (image_url, lat, lng, caption, timestamp))
        photo_id = cur.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        "id": photo_id,
        "url": image_url,
        "lat": lat,
        "lng": lng,
        "caption": caption,
        "timestamp": timestamp,
    }), 201


@app.route("/api/photos", methods=["GET"])
def list_photos():
    """מחזיר JSON עם כל הרשומות, מהחדשה לישנה."""
    conn = get_db()
    cur = dict_cursor(conn)
    cur.execute(
        "SELECT id, image_url, lat, lng, caption, timestamp "
        "FROM photos ORDER BY id DESC"
    )
    rows = cur.fetchall()
    conn.close()

    photos = []
    for row in rows:
        photos.append({
            "id": row["id"],
            "url": row["image_url"],
            "lat": row["lat"],
            "lng": row["lng"],
            "caption": row["caption"],
            "timestamp": row["timestamp"],
        })
    return jsonify(photos)


@app.route("/uploads/<name>")
def uploaded_file(name):
    """מגיש קובץ תמונה מהתיקייה המקומית (רלוונטי רק במצב מקומי)."""
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
