"""
SmartRx AI — Prescription Routes
POST /api/prescriptions                 Upload & process prescription (OCR + AI)
GET  /api/prescriptions/<id>            Prescription detail
GET  /api/prescriptions/mine            Patient's own prescriptions
PUT  /api/prescriptions/<id>/fill       Mark prescription as filled
POST /api/prescriptions/manual          Manual prescription entry (staff)
GET  /api/prescriptions/<id>/find-medicines  Find pharmacies for extracted medicines
"""

import os
import re
import json
import base64
import io
from difflib import SequenceMatcher
from flask import Blueprint, request, jsonify, g
from datetime import datetime, date, timedelta
from ..database.db import query, execute, haversine_km
from .auth_utils import require_auth, optional_auth
from PIL import Image, ImageOps, ImageFilter
import pytesseract

# Set Tesseract path for Windows
import os
if os.name == 'nt':  # Windows
    possible_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Users\RedaM\AppData\Local\Tesseract-OCR\tesseract.exe',
        'tesseract.exe'  # in PATH
    ]
    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break

# Optional Gemini API import
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyBF4ly8Sb9X2_ciKZcV6M-5nxP4LBbaWS4").strip()
if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY":
    try:
        import google.genai as genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        GEMINI_AVAILABLE = True
    except Exception as e:
        GEMINI_AVAILABLE = False
        print(f"⚠️ Gemini API disabled: {e} - using fallback extraction")
else:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini API key not configured - using fallback extraction")

prescriptions_bp = Blueprint("prescriptions", __name__, url_prefix="/api/prescriptions")

STRENGTH_RE = re.compile(
    r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*(?:mg|g|mcg|iu|ml|%|tabs?|caps?)",
    re.IGNORECASE,
)


def _normalize_match_text(text: str) -> str:
    """Normalize OCR/database text for medicine matching."""
    text = (text or "").lower()
    text = text.replace("×", " x ")
    text = re.sub(r"[^0-9a-z\/\-\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_strength(text: str | None) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _ocr_windows(normalized_text: str, target_words: int) -> list[str]:
    """Return token windows so matching can tolerate OCR spelling errors."""
    tokens = normalized_text.split()
    if not tokens:
        return []
    windows = []
    min_size = max(1, target_words - 1)
    max_size = min(len(tokens), target_words + 2)
    for size in range(min_size, max_size + 1):
        for start in range(0, len(tokens) - size + 1):
            windows.append(" ".join(tokens[start:start + size]))
    return windows


def _is_short_acronym(text: str) -> bool:
    compact = re.sub(r"[^a-z0-9]+", "", text.lower())
    return len(compact) <= 4 and compact.isalpha()


def _crop_to_ink(image: Image.Image) -> Image.Image:
    """Crop a mostly blank prescription photo to the area containing dark ink."""
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray)
    pixels = gray.load()
    width, height = gray.size
    xs = []
    ys = []
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            if pixels[x, y] < 185:
                xs.append(x)
                ys.append(y)
    if not xs or not ys:
        return image
    pad_x = max(30, int((max(xs) - min(xs)) * 0.35))
    pad_y = max(30, int((max(ys) - min(ys)) * 0.8))
    left = max(0, min(xs) - pad_x)
    top = max(0, min(ys) - pad_y)
    right = min(width, max(xs) + pad_x)
    bottom = min(height, max(ys) + pad_y)
    if right - left < 40 or bottom - top < 20:
        return image
    return image.crop((left, top, right, bottom))


def _prepare_ocr_images(image: Image.Image) -> list[Image.Image]:
    """Build OCR variants for phone photos with small handwriting."""
    variants = []
    for base in (image, _crop_to_ink(image)):
        gray = ImageOps.grayscale(base)
        gray = ImageOps.autocontrast(gray)
        for scale in (2, 3, 4):
            resized = gray.resize((gray.width * scale, gray.height * scale))
            sharp = resized.filter(ImageFilter.SHARPEN)
            thresholded = sharp.point(lambda px: 255 if px > 170 else 0)
            variants.extend([resized, sharp, thresholded])
    return variants


# ── Medicine name lookup ────────────────────


def _perform_ocr(image_b64: str) -> str:
    """
    Perform OCR on base64 image using Tesseract.
    Prescriptions are expected to be written in English.
    """
    try:
        image_data = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(image_data))

        images = _prepare_ocr_images(image)

        best_text = ""
        configs = (
            "--oem 3 --psm 7",
            "--oem 3 --psm 6",
            "--oem 3 --psm 8",
            "--oem 3 --psm 11",
            "--oem 3 --psm 12",
        )
        for img in images:
            for config in configs:
                text = pytesseract.image_to_string(img, lang="eng", config=config).strip()
                if len(text) > len(best_text):
                    best_text = text
                extracted = _fallback_extract_medicines(text)
                if extracted:
                    print(f"OCR text: {text}")
                    return text
        if best_text:
            print(f"OCR text: {best_text}")
            return best_text
    except Exception as e:
        print(f"OCR failed: {e}")
    return ""


def _mock_ocr_extract() -> str:
    """
    Simulate OCR output from a prescription image.
    Fallback when real OCR fails.
    """
    samples = [
        """ሕክምና መስጫ / PRESCRIPTION
ታካሚ: አበበ ደስታ   ቀን: 2024-11-15
ምርመራ: Malaria (ወባ)
Rx:
1. Artemether-Lumefantrine 20/120mg × 24 tabs
   Sig: 4 tabs BD × 3 days
2. Paracetamol 500mg × 10 tabs
   Sig: 1-2 tabs TDS PRN""",
    ]
    return samples[0]


def _clean_english_drug_name(name: str) -> str:
    """Keep only plausible English medicine-name text from AI/OCR output."""
    if not name:
        return ""
    name = re.sub(r"[^A-Za-z0-9 \-\/]+", " ", name)
    name = re.sub(r"\b(?:dr|doctor|patient|name|age|date|phone|tel|rx|sig|take|give)\b", " ", name, flags=re.I)
    name = re.sub(r"\b\d{3,}\b", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" -/")
    if len(name) < 3 or not re.search(r"[A-Za-z]", name):
        return ""
    return name


def _parse_json_array(text: str) -> list:
    """Parse Gemini JSON even when the model wraps it in a fenced block."""
    if not text:
        return []
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    data = json.loads(cleaned)
    return data if isinstance(data, list) else []


def _find_medicine_by_name(name: str) -> dict | None:
    """Find the best English/generic medicine record from the database."""
    if not name:
        return None

    name = _clean_english_drug_name(name)
    normalized = _normalize_match_text(name)
    if not normalized:
        return None

    medicines = query(
        "SELECT id, name_english, name_amharic, generic_name, strength, dosage_form, unit_price_etb, is_essential, requires_prescription FROM medicines"
    )

    best_match = None
    best_score = 0.0
    for med in medicines:
        for candidate in (med.get("name_english"), med.get("generic_name")):
            if not candidate:
                continue
            candidate_norm = _normalize_match_text(candidate)
            if not candidate_norm:
                continue

            if normalized == candidate_norm:
                return {**med, "confidence": 0.95}
            if normalized in candidate_norm or candidate_norm in normalized:
                return {**med, "confidence": 0.85}

            score = SequenceMatcher(None, normalized, candidate_norm).ratio()
            if score > best_score:
                best_score = score
                best_match = med

    if best_match and best_score >= 0.55:
        return {**best_match, "confidence": round(best_score, 3)}
    return None


def _fallback_extract_medicines(ocr_text: str) -> list[dict]:
    """
    Extract medicines by scanning English/generic database names.
    Used only when Gemini is unavailable or fails.
    """
    extracted = []
    if not ocr_text or not ocr_text.strip():
        return extracted

    SIG_RE = re.compile(r"\b(?:sig|take|give)\b:?\s*([^\n]+)", re.IGNORECASE)
    normalized_text = _normalize_match_text(ocr_text)
    strength_m = STRENGTH_RE.search(ocr_text)
    extracted_strength_norm = _normalize_strength(strength_m.group(0)) if strength_m else ""
    medicines = query(
        "SELECT id, name_english, name_amharic, generic_name, strength, dosage_form, unit_price_etb, is_essential, requires_prescription FROM medicines WHERE is_active=1"
    )

    candidates = []
    for med in medicines:
        best_for_med = None
        for source_rank, candidate in enumerate((med.get("name_english"), med.get("generic_name"))):
            candidate = _clean_english_drug_name(candidate)
            if not candidate:
                continue
            candidate_norm = _normalize_match_text(candidate)
            if not candidate_norm:
                continue

            score = 0.0
            matched_text = ""
            pattern = r"(?<![A-Za-z0-9])" + re.escape(candidate_norm) + r"(?![A-Za-z0-9])"
            if re.search(pattern, normalized_text):
                score = 0.98
                matched_text = candidate_norm
            elif _is_short_acronym(candidate_norm):
                # Acronyms like ORS are too short for fuzzy matching; noisy OCR otherwise over-matches them.
                continue
            else:
                for window in _ocr_windows(normalized_text, len(candidate_norm.split())):
                    ratio = SequenceMatcher(None, window, candidate_norm).ratio()
                    if ratio > score:
                        score = ratio
                        matched_text = window

            med_strength_norm = _normalize_strength(med.get("strength"))
            strength_matches = False
            if extracted_strength_norm and med_strength_norm:
                if extracted_strength_norm == med_strength_norm:
                    strength_matches = True
                    score += 0.08
                elif extracted_strength_norm in med_strength_norm or med_strength_norm in extracted_strength_norm:
                    strength_matches = True
                    score += 0.04
                else:
                    score -= 0.04

            min_score = 0.68 if strength_matches else 0.78
            if _is_short_acronym(candidate_norm):
                min_score = 0.98
            if score < min_score:
                continue

            score = min(0.99, score - (source_rank * 0.01))
            item = (score, len(candidate_norm), candidate, med, candidate_norm, matched_text)
            if best_for_med is None or item[0] > best_for_med[0]:
                best_for_med = item
        if best_for_med:
            candidates.append(best_for_med)

    accepted_names = []
    for score, _, medicine_name, med_match, candidate_norm, matched_text in sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True):
        if any(e["medicine"] and e["medicine"]["id"] == med_match["id"] for e in extracted):
            continue
        if any(candidate_norm in accepted or accepted in candidate_norm for accepted in accepted_names):
            continue
        accepted_names.append(candidate_norm)
        nearby_text = ocr_text
        dosage = SIG_RE.search(nearby_text)
        entry = {
            "raw_text": matched_text or medicine_name,
            "matched_name": med_match["name_english"],
            "dosage_instruction": dosage.group(1).strip() if dosage else None,
            "extracted_strength": strength_m.group(0).strip() if strength_m else None,
            "medicine": med_match,
            "confidence": round(score, 3),
            "requires_substitution": False,
        }
        extracted.append(entry)
    return extracted


def _ai_extract_medicines(ocr_text: str) -> list[dict]:
    """
    Extract medicines from OCR text using Gemini if available.
    Otherwise use the regex fallback.
    """
    if GEMINI_AVAILABLE:
        try:
            prompt = f"""
You are reading OCR text from an English prescription.
Return only real prescribed drug or medicine names. Ignore patient names, doctor names, phone numbers, clinic names, dates, diagnoses, addresses, and instructions that do not contain a drug name.

For each medicine, provide:
- name: The English medicine/drug name only
- strength: Dosage strength if mentioned (e.g., 500mg)
- dosage: Instructions like "1 tab OD"
- quantity: Amount prescribed (e.g., 10 tabs)

Prescription text:
{ocr_text}

Return ONLY a valid JSON array of objects with keys: name, strength, dosage, quantity.
If no English medicine names are present, return [].
Do not include any other text.
"""
            response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
            extracted_data = _parse_json_array(response.candidates[0].content.parts[0].text)
            extracted = []
            for item in extracted_data:
                if not isinstance(item, dict):
                    continue
                name = _clean_english_drug_name(item.get("name", ""))
                if not name:
                    continue
                med_match = _find_medicine_by_name(name)
                if med_match:
                    extracted.append({
                        "raw_text": name,
                        "matched_name": med_match["name_english"],
                        "dosage_instruction": item.get("dosage"),
                        "extracted_strength": item.get("strength"),
                        "medicine": med_match,
                        "confidence": med_match["confidence"],
                        "requires_substitution": False,
                    })
            if extracted:
                return extracted
        except Exception as e:
            print(f"Gemini extraction failed: {e}")
    return _fallback_extract_medicines(ocr_text)


# ── Routes ────────────────────────────────────────────────────

@prescriptions_bp.post("")
@optional_auth
def upload_prescription():
    """
    Upload a prescription image (base64) or text for AI processing.
    Body (JSON):
    {
      "image_base64": "...",   // optional: base64 image
      "ocr_text":     "...",   // optional: raw text (manual/kiosk entry)
      "language":     "amharic" | "english",
      "patient_id":   int      // optional
    }
    Returns extracted medicines with confidence scores and pharmacy availability.
    """
    body       = request.get_json(silent=True) or {}
    image_b64  = body.get("image_base64", "")
    ocr_text   = body.get("ocr_text", "").strip()
    language   = "english"
    patient_id = body.get("patient_id") or (g.user_id if g.role == "patient" else None)

    # Step 1: OCR (real OCR if image provided)
    if not ocr_text:
        if image_b64:
            ocr_text = _perform_ocr(image_b64)
            # If OCR fails, ocr_text remains empty, extraction will handle it
        else:
            return jsonify({"error": "Provide image_base64 or ocr_text"}), 400

    # Step 2: AI extraction
    extracted = _ai_extract_medicines(ocr_text)
    if not extracted:
        return jsonify({
            "error": "No medicines found in the prescription. Please ensure the prescription is clear and contains medicine names.",
            "ocr_text": ocr_text,
            "hint": "OCR did not produce a recognizable medicine name. Try typing the medicine text in the box, or upload a closer, brighter photo.",
        }), 400

    # Step 3: Overall confidence
    confidences = [e["confidence"] for e in extracted if e["medicine"]]
    overall_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

    # Step 4: Store prescription record
    primary_med_id = None
    if extracted and extracted[0]["medicine"]:
        primary_med_id = extracted[0]["medicine"]["id"]

    ai_json = json.dumps([{
        "medicine_id":   e["medicine"]["id"] if e["medicine"] else None,
        "name":          e["matched_name"],
        "name_amharic":  e["medicine"]["name_amharic"] if e["medicine"] else None,
        "confidence":    e["confidence"],
        "dosage":        e.get("dosage_instruction"),
        "strength":      e.get("extracted_strength"),
    } for e in extracted])

    prescription_id = execute("""
        INSERT INTO prescriptions
            (patient_id, ocr_raw_text, ai_extracted_medicines,
             extraction_confidence, extraction_model,
             primary_medicine_id, language_detected,
             prescribed_date, filled)
        VALUES (?,?,?,?,?,?,?,date('now'),0)
    """, (patient_id, ocr_text, ai_json, overall_confidence,
          "smartrx-nlp-v1", primary_med_id, language))

    # Step 5: For each extracted medicine, find nearest in-stock pharmacies
    try:
        user_lat = float(body["lat"]) if body.get("lat") is not None else None
        user_lon = float(body["lon"]) if body.get("lon") is not None else None
    except (TypeError, ValueError):
        user_lat = None
        user_lon = None

    medicines_with_stock = []
    for e in extracted:
        med = e["medicine"]
        nearby = []
        if med:
            stock_rows = query("""
                SELECT p.id, p.name, p.name_amharic, p.sub_city,
                       p.latitude, p.longitude, p.phone, p.open_24h,
                       i.quantity, i.stock_status,
                       (SELECT unit_price_etb FROM medicines WHERE id=i.medicine_id) as unit_price_etb
                FROM inventory i
                JOIN pharmacies p ON p.id = i.pharmacy_id
                WHERE i.medicine_id = ? AND i.stock_status != 'out' AND p.is_active = 1
            """, (med["id"],))

            for s in stock_rows:
                dist = None
                if user_lat is not None and user_lon is not None:
                    dist = haversine_km(user_lat, user_lon, float(s["latitude"]), float(s["longitude"]))
                nearby.append({
                    "pharmacy_id":   s["id"],
                    "pharmacy_name": s["name"],
                    "name_amharic":  s["name_amharic"],
                    "sub_city":      s["sub_city"],
                    "latitude":      float(s["latitude"]),
                    "longitude":     float(s["longitude"]),
                    "phone":         s["phone"],
                    "open_24h":      bool(s["open_24h"]),
                    "distance_km":   round(dist, 2) if dist is not None else None,
                    "quantity":      s["quantity"],
                    "stock_status":  s["stock_status"],
                    "price_etb":     s["unit_price_etb"],
                })
            nearby.sort(key=lambda x: (
                {"adequate": 0, "low": 1, "critical": 2}.get(x["stock_status"], 3),
                x["distance_km"] if x["distance_km"] is not None else 999999
            ))
            nearby = nearby[:5]

        medicines_with_stock.append({
            "raw_text":    e["raw_text"],
            "name":        e["matched_name"],
            "name_amharic": med["name_amharic"] if med else None,
            "generic_name": med["generic_name"] if med else None,
            "confidence":  e["confidence"],
            "dosage_instruction": e.get("dosage_instruction"),
            "extracted_strength": e.get("extracted_strength"),
            "medicine_id": med["id"] if med else None,
            "matched":     med is not None,
            "requires_prescription": med["requires_prescription"] if med else False,
            "nearest_pharmacies": nearby,
        })

    return jsonify({
        "prescription_id":      prescription_id,
        "ocr_text":             ocr_text,
        "language_detected":    language,
        "overall_confidence":   overall_confidence,
        "medicines_extracted":  len(medicines_with_stock),
        "medicines":            medicines_with_stock,
        "next_steps": {
            "fill_at_pharmacy": f"/api/prescriptions/{prescription_id}/fill",
            "view_detail":      f"/api/prescriptions/{prescription_id}",
        }
    }), 201


@prescriptions_bp.post("/manual")
@require_auth
def manual_prescription():
    """
    Manual entry by pharmacy staff or health worker.
    Body: { "medicine_ids": [int], "patient_id": int, "diagnosis": str,
            "diagnosis_amharic": str, "prescribing_facility": str }
    """
    if g.role not in ("pharmacy_staff", "health_worker", "admin"):
        return jsonify({"error": "Insufficient permissions"}), 403

    body = request.get_json(silent=True) or {}
    med_ids = body.get("medicine_ids", [])
    if not med_ids:
        return jsonify({"error": "medicine_ids required"}), 400

    primary_med = med_ids[0] if med_ids else None
    ai_json = json.dumps([{"medicine_id": mid, "confidence": 1.0} for mid in med_ids])

    pid = execute("""
        INSERT INTO prescriptions
            (patient_id, diagnosis_english, diagnosis_amharic,
             primary_medicine_id, ai_extracted_medicines,
             prescribing_facility, prescribing_doctor,
             prescribed_date, extraction_model, extraction_confidence,
             language_detected, filled)
        VALUES (?,?,?,?,?,?,?,date('now'),'manual',1.0,'amharic',0)
    """, (body.get("patient_id"), body.get("diagnosis"),
          body.get("diagnosis_amharic"), primary_med, ai_json,
          body.get("prescribing_facility"), body.get("prescribing_doctor")))

    return jsonify({"prescription_id": pid, "status": "created",
                    "detail": f"/api/prescriptions/{pid}"}), 201


@prescriptions_bp.get("/mine")
@require_auth
def my_prescriptions():
    if g.role != "patient":
        return jsonify({"error": "Patient access only"}), 403

    patient = query("SELECT id FROM patients WHERE phone=(SELECT phone FROM users WHERE id=?)",
                    (g.user_id,), one=True)
    patient_id = patient["id"] if patient else None

    rows = query("""
        SELECT p.id, p.diagnosis_english, p.diagnosis_amharic,
               p.prescribed_date, p.filled, p.filled_at,
               p.extraction_confidence, p.language_detected,
               ph.name as filled_pharmacy, ph.name_amharic as filled_pharmacy_am,
               m.name_english as primary_medicine, m.name_amharic as primary_medicine_am
        FROM prescriptions p
        LEFT JOIN pharmacies ph ON ph.id = p.filled_pharmacy_id
        LEFT JOIN medicines  m  ON m.id  = p.primary_medicine_id
        WHERE p.patient_id = ?
        ORDER BY p.prescribed_date DESC LIMIT 50
    """, (patient_id,))

    return jsonify({"count": len(rows), "results": rows})


@prescriptions_bp.get("/<int:pres_id>")
@optional_auth
def prescription_detail(pres_id: int):
    p = query("SELECT * FROM prescriptions WHERE id=?", (pres_id,), one=True)
    if not p:
        return jsonify({"error": "Prescription not found"}), 404

    # Parse extracted medicines JSON
    medicines = []
    try:
        extracted = json.loads(p["ai_extracted_medicines"] or "[]")
        for e in extracted:
            if e.get("medicine_id"):
                med = query("SELECT id, name_english, name_amharic, strength, dosage_form, "
                            "unit_price_etb FROM medicines WHERE id=?",
                            (e["medicine_id"],), one=True)
                e["medicine_detail"] = med
            medicines.append(e)
    except Exception:
        pass

    result = {**p, "extracted_medicines_parsed": medicines}
    return jsonify(result)


@prescriptions_bp.put("/<int:pres_id>/fill")
@require_auth
def fill_prescription(pres_id: int):
    """
    Mark prescription as filled at a pharmacy.
    Body: { "pharmacy_id": int }
    Also decrements inventory for each extracted medicine.
    """
    body       = request.get_json(silent=True) or {}
    pharmacy_id = body.get("pharmacy_id")
    if not pharmacy_id:
        return jsonify({"error": "pharmacy_id required"}), 400

    p = query("SELECT * FROM prescriptions WHERE id=?", (pres_id,), one=True)
    if not p:
        return jsonify({"error": "Prescription not found"}), 404
    if p["filled"]:
        return jsonify({"error": "Prescription already filled"}), 409

    # Extract medicine IDs
    try:
        extracted = json.loads(p["ai_extracted_medicines"] or "[]")
        med_ids   = [e["medicine_id"] for e in extracted if e.get("medicine_id")]
    except Exception:
        med_ids = []

    # Decrement inventory and log transactions
    dispensed = []
    for mid in med_ids:
        inv = query("SELECT quantity, reorder_point FROM inventory "
                    "WHERE pharmacy_id=? AND medicine_id=?", (pharmacy_id, mid), one=True)
        if inv and inv["quantity"] > 0:
            new_qty = max(0, inv["quantity"] - 1)
            rp = inv["reorder_point"] or 20
            ns = ("out" if new_qty == 0 else
                  "critical" if new_qty <= rp*0.5 else
                  "low"      if new_qty <= rp else "adequate")
            execute("UPDATE inventory SET quantity=?, stock_status=?, updated_at=? "
                    "WHERE pharmacy_id=? AND medicine_id=?",
                    (new_qty, ns, datetime.now().isoformat(), pharmacy_id, mid))
            execute("""INSERT INTO transactions
                (pharmacy_id, medicine_id, prescription_id, quantity_dispensed,
                 transaction_date, month, year, prescription_required)
                VALUES (?,?,?,1,date('now'),
                        CAST(strftime('%m','now') AS INTEGER),
                        CAST(strftime('%Y','now') AS INTEGER),1)""",
                    (pharmacy_id, mid, pres_id))
            dispensed.append(mid)

    # Mark filled
    execute("""UPDATE prescriptions
               SET filled=1, filled_at=?, filled_pharmacy_id=?
               WHERE id=?""",
            (datetime.now().isoformat(), pharmacy_id, pres_id))

    return jsonify({
        "prescription_id": pres_id,
        "filled":          True,
        "pharmacy_id":     pharmacy_id,
        "medicines_dispensed": len(dispensed),
        "filled_at":       datetime.now().isoformat(),
    })
