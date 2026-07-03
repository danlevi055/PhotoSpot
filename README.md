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

## הערות אבטחה

- שמות הקבצים עוברים דרך `secure_filename` ומקבלים חותמת זמן ייחודית.
- מותרות רק סיומות תמונה: `png, jpg, jpeg, gif, webp`.
- מגבלת גודל קובץ: 8MB (ניתן לשנות ב-`app.py`).
- זהו פרויקט לימודי — אין אימות משתמשים; אל תשתמשו בו כמו שהוא בסביבה ציבורית.
