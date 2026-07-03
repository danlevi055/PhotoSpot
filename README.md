# 📍 PhotoSpot

אפליקציית ווב לימודית לתיעוד תמונות עם מיקום GPS.
המשתמש מצלם או מעלה תמונה, האפליקציה קולטת את הקואורדינטות מהדפדפן,
והתמונות מוצגות בגלריה ועל גבי מפה אינטראקטיבית.

## טכנולוגיות

- **Backend:** Python 3 + Flask, מסד נתונים SQLite
- **Frontend:** HTML + JavaScript רגיל (vanilla) + CSS
- **מפה:** Leaflet עם אריחי OpenStreetMap (ללא מפתח API)

## מבנה הפרויקט

```
project/
  app.py              # שרת Flask + ה-API
  templates/
    index.html        # העמוד הראשי
  static/
    app.js            # לוגיקת צד לקוח
    style.css         # עיצוב
  uploads/            # תמונות שהועלו (נוצר אוטומטית)
  requirements.txt    # תלויות Python
  README.md
  .gitignore
```

## התקנה והרצה מקומית — צעד אחר צעד

### 1. דרישות מקדימות
ודאו ש-Python 3.8 ומעלה מותקן:

```bash
python --version
```

### 2. כניסה לתיקיית הפרויקט

```bash
cd project
```

### 3. יצירת סביבה וירטואלית (מומלץ)

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. התקנת התלויות

```bash
pip install -r requirements.txt
```

### 5. הרצת השרת

```bash
python app.py
```

השרת יעלה בכתובת: **http://localhost:5000**

כדי לשנות פורט, הגדירו את משתנה הסביבה `PORT`:

**Windows (PowerShell):**
```powershell
$env:PORT=8080; python app.py
```

**macOS / Linux:**
```bash
PORT=8080 python app.py
```

### 6. שימוש
1. פתחו את הכתובת בדפדפן.
2. בחרו או צלמו תמונה.
3. לחצו על "📡 קבל מיקום נוכחי" ואשרו את הרשאת המיקום (אופציונלי).
4. הוסיפו כיתוב אם תרצו, ולחצו "⬆️ שלח".
5. התמונה תופיע בגלריה ועל המפה.

> 💡 **הערה על מיקום:** דפדפנים מאפשרים גישה למיקום רק בכתובות מאובטחות (HTTPS)
> או ב-`localhost`. בפיתוח מקומי דרך `localhost` הכל עובד.

## הרצה בפרודקשן (gunicorn)

ב-Linux/macOS ניתן להריץ עם gunicorn:

```bash
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

## פריסה לענן 24/7 (Render + Cloudinary + Postgres)

כדי שהאתר יעבוד תמיד — גם כשהמחשב שלך כבוי — מריצים אותו על שרת ענן.
מכיוון שהדיסק בענן זמני, שומרים את **התמונות ב-Cloudinary** ואת **המטא-דאטה ב-Postgres**.
הקוד מזהה זאת אוטומטית לפי משתני הסביבה — מקומית הוא ממשיך לעבוד עם קבצים מקומיים.

### 1. חשבון Cloudinary (אחסון תמונות, חינם)
1. הירשמו ב-https://cloudinary.com/users/register_free
2. בלוח הבקרה (Dashboard) חפשו את **API Environment variable** — מחרוזת בצורה:
   `cloudinary://<api_key>:<api_secret>@<cloud_name>`
3. זהו הערך של `CLOUDINARY_URL`.

### 2. מסד נתונים Postgres (חינם — למשל Neon)
1. הירשמו ב-https://neon.tech
2. צרו Project חדש, והעתיקו את **Connection string** (מתחיל ב-`postgresql://...`).
3. זהו הערך של `DATABASE_URL`.

### 3. העלאת הקוד ל-GitHub
```bash
git add .
git commit -m "Cloud storage support"
git push
```

### 4. יצירת השירות ב-Render
1. ב-https://dashboard.render.com לחצו **New + → Web Service** ובחרו את ה-repo.
2. הגדרות:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Instance Type:** Free
3. תחת **Environment Variables** הוסיפו את המשתנים הבאים:

   | Key | Value |
   |-----|-------|
   | `DATABASE_URL`   | מחרוזת החיבור מ-Neon |
   | `CLOUDINARY_URL` | המחרוזת מ-Cloudinary |
   | `SECRET_KEY`     | טקסט אקראי ארוך (לחתימת session) |
   | `ACCESS_CODE`    | קוד הכניסה לאתר — **חזק**, לפחות 6 תווים ולא נפוץ (למשל `DanLevi2026!`) |

4. לחצו **Create Web Service**. אחרי 2–4 דקות תקבלו כתובת HTTPS קבועה:
   `https://photospot-xxxx.onrender.com`

> ⏳ **חבילת Free:** השירות "נרדם" אחרי ~15 דק' חוסר פעילות; הכניסה הראשונה אחריה
> לוקחת ~40 שניות. זה נורמלי בחבילה החינמית.

## משתני סביבה

| משתנה | חובה? | ברירת מחדל | תיאור |
|--------|--------|-------------|--------|
| `ACCESS_CODE`    | **כן** | (אין) | קוד הכניסה לאתר. חייב להיות חזק (≥6 תווים, לא נפוץ) — אחרת האפליקציה לא תעלה |
| `SECRET_KEY`     | מומלץ | מפתח אקראי זמני | מפתח לחתימת session. בלי ערך קבוע — כל הפעלה מייצרת מפתח חדש וה-sessions מתאפסים |
| `DATABASE_URL`   | לא | (SQLite מקומי) | אם מוגדר — משתמשים ב-Postgres |
| `CLOUDINARY_URL` | לא | (תיקייה מקומית) | אם מוגדר — התמונות עולות ל-Cloudinary |
| `PORT`           | לא | `5000` | פורט ההאזנה |
| `COOKIE_SECURE`  | לא | `1` (מופעל) | עוגיית ה-session נשלחת רק על HTTPS. לבדיקות מקומיות ב-`http://localhost` הגדירו `0` |
| `FLASK_DEBUG`    | לא | `0` (כבוי) | מצב דיבוג. **לעולם אל תפעילו** באתר חשוף לאינטרנט |

## הערות אבטחה

האפליקציה כוללת הגנות מובנות המתאימות לאתר חשוף לאינטרנט:
- **קוד גישה חובה וחזק** — האפליקציה מסרבת לעלות עם קוד חלש או ברירת-מחדל.
- **אימות תוכן הקובץ** — כל העלאה נבדקת לפי חתימת הבייטים, כך שקובץ שרק *נקרא* תמונה נדחה.
- **הגבלת קצב** — עד 5 ניסיונות כניסה ל-5 דקות, ועד 30 העלאות בשעה, לכל כתובת IP.
- **עוגיות מאובטחות** — `HttpOnly`, `SameSite=Lax`, ו-`Secure` (HTTPS בלבד).
- **כותרות אבטחה** — `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
- **מצב דיבוג כבוי** כברירת מחדל.
- מגבלת גודל קובץ: 8MB (ניתן לשנות ב-`app.py`).

> זהו פרויקט לימודי. יש שער כניסה משותף בקוד אחד (לא משתמשים נפרדים) — מתאים לשימוש אישי,
> לא כתחליף למערכת הרשאות מלאה.
