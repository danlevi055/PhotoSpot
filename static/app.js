/*
 * PhotoSpot - לוגיקת צד לקוח
 * vanilla JavaScript (בלי framework)
 */

// ---------------------------------------------------------------------------
// אלמנטים מה-DOM
// ---------------------------------------------------------------------------
const form = document.getElementById("upload-form");
const imageInput = document.getElementById("image-input");
const captionInput = document.getElementById("caption-input");
const preview = document.getElementById("preview");
const getLocationBtn = document.getElementById("get-location-btn");
const locationStatus = document.getElementById("location-status");
const submitBtn = document.getElementById("submit-btn");
const formMessage = document.getElementById("form-message");
const gallery = document.getElementById("gallery");

// מחזיק את הקואורדינטות האחרונות שהתקבלו
let currentCoords = { lat: null, lng: null };

// ---------------------------------------------------------------------------
// מפה (Leaflet)
// ---------------------------------------------------------------------------
// מרכז התחלתי: מרכז ישראל (בערך). הזום יתעדכן לפי התמונות.
const map = L.map("map").setView([31.5, 34.9], 7);

// שכבת אריחים מ-OpenStreetMap (בלי מפתח API)
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

// שכבת קבוצה שמחזיקה את כל הסמנים - נוח לניקוי ורענון
const markersLayer = L.layerGroup().addTo(map);

// ---------------------------------------------------------------------------
// תצוגה מקדימה של התמונה שנבחרה
// ---------------------------------------------------------------------------
imageInput.addEventListener("change", () => {
  const file = imageInput.files[0];
  if (file) {
    preview.src = URL.createObjectURL(file);
    preview.classList.remove("hidden");
  } else {
    preview.classList.add("hidden");
  }
});

// ---------------------------------------------------------------------------
// קבלת מיקום GPS דרך navigator.geolocation
// ---------------------------------------------------------------------------
getLocationBtn.addEventListener("click", () => {
  // בדיקה שהדפדפן תומך
  if (!("geolocation" in navigator)) {
    locationStatus.textContent = "⚠️ הדפדפן לא תומך במיקום.";
    locationStatus.className = "location-status error";
    return;
  }

  locationStatus.textContent = "⏳ מאתר מיקום...";
  locationStatus.className = "location-status";

  navigator.geolocation.getCurrentPosition(
    // הצלחה
    (position) => {
      currentCoords.lat = position.coords.latitude;
      currentCoords.lng = position.coords.longitude;
      locationStatus.textContent =
        `✅ מיקום זוהה: ${currentCoords.lat.toFixed(5)}, ${currentCoords.lng.toFixed(5)}`;
      locationStatus.className = "location-status ok";
    },
    // שגיאה / דחיית הרשאה
    (error) => {
      let msg = "⚠️ לא ניתן לקבל מיקום.";
      if (error.code === error.PERMISSION_DENIED) {
        msg = "⚠️ הרשאת המיקום נדחתה. אפשר להעלות תמונה גם בלי מיקום.";
      } else if (error.code === error.POSITION_UNAVAILABLE) {
        msg = "⚠️ המיקום אינו זמין כרגע.";
      } else if (error.code === error.TIMEOUT) {
        msg = "⚠️ תם הזמן לקבלת מיקום.";
      }
      locationStatus.textContent = msg;
      locationStatus.className = "location-status error";
    },
    // אפשרויות
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
  );
});

// ---------------------------------------------------------------------------
// שליחת הטופס ל-backend
// ---------------------------------------------------------------------------
form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const file = imageInput.files[0];
  if (!file) {
    showMessage("יש לבחור תמונה.", "error");
    return;
  }

  // בניית גוף הבקשה כ-multipart form
  const formData = new FormData();
  formData.append("image", file);
  formData.append("caption", captionInput.value);
  if (currentCoords.lat !== null && currentCoords.lng !== null) {
    formData.append("lat", currentCoords.lat);
    formData.append("lng", currentCoords.lng);
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "שולח...";

  try {
    const response = await fetch("/api/photos", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "שגיאה בשליחה");
    }

    showMessage("✅ התמונה נשמרה!", "ok");

    // איפוס הטופס
    form.reset();
    preview.classList.add("hidden");
    currentCoords = { lat: null, lng: null };
    locationStatus.textContent = "המיקום עדיין לא זוהה.";
    locationStatus.className = "location-status";

    // רענון הגלריה והמפה
    loadPhotos();
  } catch (err) {
    showMessage("❌ " + err.message, "error");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "⬆️ שלח";
  }
});

// ---------------------------------------------------------------------------
// טעינת כל התמונות והצגתן בגלריה ובמפה
// ---------------------------------------------------------------------------
async function loadPhotos() {
  try {
    const response = await fetch("/api/photos");
    const photos = await response.json();

    renderGallery(photos);
    renderMarkers(photos);
  } catch (err) {
    gallery.innerHTML = `<p class="empty">שגיאה בטעינת התמונות.</p>`;
  }
}

// בונה את הגלריה
function renderGallery(photos) {
  if (photos.length === 0) {
    gallery.innerHTML = `<p class="empty">אין עדיין תמונות.</p>`;
    return;
  }

  gallery.innerHTML = "";
  photos.forEach((photo) => {
    const item = document.createElement("div");
    item.className = "gallery-item";

    const hasLocation = photo.lat !== null && photo.lng !== null;
    const locationText = hasLocation
      ? `${photo.lat.toFixed(4)}, ${photo.lng.toFixed(4)}`
      : "ללא מיקום";

    item.innerHTML = `
      <img src="${photo.url}" alt="${escapeHtml(photo.caption) || "תמונה"}" loading="lazy">
      <div class="gallery-info">
        <p class="caption">${escapeHtml(photo.caption) || "<em>ללא כיתוב</em>"}</p>
        <p class="meta">📍 ${locationText}</p>
        <p class="meta">🕒 ${formatDate(photo.timestamp)}</p>
      </div>
    `;
    gallery.appendChild(item);
  });
}

// בונה את הסמנים על המפה
function renderMarkers(photos) {
  markersLayer.clearLayers();
  const bounds = [];

  photos.forEach((photo) => {
    if (photo.lat === null || photo.lng === null) return;

    const marker = L.marker([photo.lat, photo.lng]);

    // תוכן החלון שנפתח בלחיצה על הסמן - כולל את התמונה
    const popupHtml = `
      <div class="popup">
        <img src="${photo.url}" alt="תמונה" style="max-width:200px;display:block;">
        <p>${escapeHtml(photo.caption) || "<em>ללא כיתוב</em>"}</p>
      </div>
    `;
    marker.bindPopup(popupHtml);
    markersLayer.addLayer(marker);
    bounds.push([photo.lat, photo.lng]);
  });

  // אם יש סמנים - נתאים את התצוגה כדי שכולם ייראו
  if (bounds.length > 0) {
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
  }
}

// ---------------------------------------------------------------------------
// פונקציות עזר
// ---------------------------------------------------------------------------

// מציג הודעה מתחת לטופס
function showMessage(text, type) {
  formMessage.textContent = text;
  formMessage.className = "form-message " + type;
}

// ממיר ISO timestamp לתצוגה קריאה
function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("he-IL");
  } catch {
    return iso;
  }
}

// בריחה מתווי HTML כדי למנוע הזרקת קוד (XSS)
function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// טעינה ראשונית
// ---------------------------------------------------------------------------
loadPhotos();
