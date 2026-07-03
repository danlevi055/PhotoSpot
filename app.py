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
import hmac
import time
import secrets
import sqlite3
from collections import defaultdict
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

# ---------------------------------------------------------------------------
# ⚠️ אבטחה: סודות (חובה להגדיר דרך משתני סביבה — אין ברירות מחדל מסוכנות)
# ---------------------------------------------------------------------------

# קודי גישה חלשים/ידועים שאסור להשתמש בהם
_WEAK_CODES = {
    "", "dan123", "photospot", "1234", "12345", "123456", "0000",
    "password", "admin", "changeme", "test", "photospot-dev-secret-change-me",
}


def _require_access_code():
    """
    מחזיר קוד גישה חזק ממשתנה הסביבה ACCESS_CODE.
    אם לא הוגדר / חלש מדי — עוצר את העלייה עם הסבר, כדי שהאתר
    לעולם לא ירוץ עם קוד ברירת-מחדל שכל אחד מכיר.
    """
    code = os.environ.get("ACCESS_CODE", "").strip()
    if len(code) < 6 or code.lower() in _WEAK_CODES:
        raise RuntimeError(
            "\n"
            "==================================================================\n"
            " עצירה מטעמי אבטחה: לא הוגדר קוד גישה חזק.\n"
            " הגדר משתנה סביבה ACCESS_CODE (לפחות 6 תווים, לא קוד נפוץ):\n"
            "   PowerShell:  $env:ACCESS_CODE=\"בחר-קוד-חזק-כאן\"\n"
            "   Linux/macOS: export ACCESS_CODE='בחר-קוד-חזק-כאן'\n"
            " (בענן/Render: הגדר את זה תחת Environment Variables של השירות.)\n"
            "==================================================================\n"
        )
    return code


ACCESS_CODE = _require_access_code()

# מפתח סודי לחתימה על ה-session. אם לא סופק (או נשאר ברירת-המחדל הישנה) —
# נוצר מפתח אקראי חזק בזמן ריצה. סוד ידוע = תוקף יכול לזייף עוגיית כניסה!
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "photospot-dev-secret-change-me":
    SECRET_KEY = secrets.token_hex(32)
    print("[PhotoSpot] אזהרה: SECRET_KEY לא הוגדר — נוצר מפתח אקראי זמני. "
          "כדי לשמור sessions בין הרצות, הגדר SECRET_KEY במשתני הסביבה.")

# האם לאכוף עוגייה מאובטחת (HTTPS בלבד). ברירת מחדל: כן.
# לבדיקות מקומיות דרך http://localhost אפשר לכבות עם COOKIE_SECURE=0
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") != "0"

# מצב דיבוג — כבוי כברירת מחדל! אסור להפעיל באתר חשוף לאינטרנט (RCE).
DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

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
app.config.update(
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,          # אין גישה לעוגייה מ-JS (הגנה מ-XSS)
    SESSION_COOKIE_SAMESITE="Lax",         # הגנה בסיסית מ-CSRF
    SESSION_COOKIE_SECURE=COOKIE_SECURE,   # העוגייה נשלחת רק על HTTPS
)

# מוודאים שתיקיית ההעלאות המקומית קיימת (בשימוש רק במצב מקומי)
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# הגבלת קצב פשוטה בזיכרון (הגנה מ-brute force ומהצפת העלאות)
# ---------------------------------------------------------------------------

_rate_buckets = defaultdict(list)


def client_ip():
    """כתובת ה-IP האמיתית של הלקוח (מאחורי Cloudflare/פרוקסי)."""
    fwd = request.headers.get("CF-Connecting-IP") \
        or request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


def rate_limited(bucket, key, max_hits, window_seconds):
    """
    מחזיר True אם הלקוח חרג מהמכסה (max_hits בתוך window_seconds).
    אחרת רושם את הפעולה ומחזיר False.
    """
    now = time.time()
    ident = f"{bucket}:{key}"
    hits = [t for t in _rate_buckets[ident] if now - t < window_seconds]
    if len(hits) >= max_hits:
        _rate_buckets[ident] = hits
        return True
    hits.append(now)
    _rate_buckets[ident] = hits
    return False


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


# חתימות בייטים אמיתיות של פורמטי תמונה (כדי לוודא שהקובץ באמת תמונה,
# ולא קובץ מסוכן שרק שינו לו את הסיומת).
def sniff_image_type(head):
    """מזהה סוג תמונה מ-12 הבייטים הראשונים, או None אם לא תמונה מוכרת."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


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
# כותרות אבטחה בכל תגובה
# ---------------------------------------------------------------------------

@app.after_request
def set_security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


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
        # הגבלת קצב: מקסימום 5 ניסיונות ל-5 דקות לכל IP (מונע ניחוש הקוד)
        if rate_limited("login", client_ip(), max_hits=5, window_seconds=300):
            return render_template(
                "login.html",
                error="יותר מדי ניסיונות. נסה שוב בעוד כמה דקות.",
            ), 429
        code = (request.form.get("code") or "").strip()
        # השוואה בזמן קבוע — מונעת timing attack
        if hmac.compare_digest(code, ACCESS_CODE):
            session.clear()
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
    # הגבלת קצב: מקסימום 30 העלאות בשעה לכל IP (מונע הצפה ומילוי דיסק)
    if rate_limited("upload", client_ip(), max_hits=30, window_seconds=3600):
        return jsonify({"error": "יותר מדי העלאות. נסה שוב מאוחר יותר."}), 429

    # 1. ולידציה - חייבת להיות תמונה בבקשה
    if "image" not in request.files:
        return jsonify({"error": "לא נשלחה תמונה"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "שם קובץ ריק"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "סוג קובץ לא נתמך (רק תמונות)"}), 400

    # 2. אימות תוכן אמיתי: קוראים את תחילת הקובץ ובודקים חתימת בייטים.
    #    כך קובץ שרק *נקרא* .jpg אבל אינו תמונה - נדחה. הסיומת נקבעת לפי התוכן.
    head = file.stream.read(12)
    file.stream.seek(0)
    ext = sniff_image_type(head)
    if ext is None:
        return jsonify({"error": "הקובץ אינו תמונה תקינה"}), 400

    # 3. שמירת התמונה וקבלת ה-URL אליה
    image_url = save_image(file, ext)

    # 4. קריאת שאר השדות מהטופס
    lat = parse_float(request.form.get("lat"))
    lng = parse_float(request.form.get("lng"))
    caption = (request.form.get("caption") or "").strip()[:200]
    timestamp = datetime.now(timezone.utc).isoformat()

    # 5. שמירה למסד הנתונים
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
    # מגישים אך ורק קבצים עם סיומת תמונה מוכרת (הגנה נוספת)
    if not safe_name or not allowed_file(safe_name):
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
    # ⚠️ debug כבוי כברירת מחדל. הפעלה רק מקומית ולעולם לא באתר חשוף.
    app.run(host="0.0.0.0", port=port, debug=DEBUG)
