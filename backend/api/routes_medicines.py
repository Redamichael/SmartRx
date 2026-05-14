"""
SmartRx AI — Medicine Routes
GET  /api/medicines                  Search medicines (EN + Amharic)
GET  /api/medicines/<id>             Medicine detail
GET  /api/medicines/<id>/availability  Stock across all pharmacies
GET  /api/medicines/categories       All categories
GET  /api/medicines/essential        WHO essential medicines list
GET  /api/medicines/<id>/alternatives Generic alternatives
"""

from flask import Blueprint, request, jsonify
from ..database.db import query, haversine_km
from .auth_utils import optional_auth

medicines_bp = Blueprint("medicines", __name__, url_prefix="/api/medicines")


def _medicine_row(m: dict) -> dict:
    """Clean up a medicine row for API response."""
    return {
        "id":                    m["id"],
        "name":                  m["name_english"],
        "name_amharic":          m["name_amharic"],
        "generic_name":          m["generic_name"],
        "category":              m["category"],
        "atc_code":              m["atc_code"],
        "strength":              m["strength"],
        "dosage_form":           m["dosage_form"],
        "unit_price_etb":        m["unit_price_etb"],
        "is_essential":          bool(m["is_essential"]),
        "requires_prescription": bool(m["requires_prescription"]),
        "storage_condition":     m["storage_condition"],
        "shelf_life_months":     m["shelf_life_months"],
    }


@medicines_bp.get("")
@optional_auth
def search_medicines():
    """
    Search medicines by English or Amharic name.
    Supports fuzzy partial matching on both scripts.
    Query params:
      q          - search term (English or Amharic)
      category   - filter by category
      essential  - true/false
      form       - dosage form filter
      page       - page number (default 1)
      per_page   - results per page (default 20, max 100)
    """
    q        = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    essential = request.args.get("essential", "").strip().lower()
    form     = request.args.get("form", "").strip()
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    offset   = (page - 1) * per_page

    conditions = ["m.is_active = 1"]
    params     = []

    if q:
        # Search English name, Amharic name, and generic name
        conditions.append("""(
            LOWER(m.name_english)  LIKE LOWER(?)
         OR LOWER(m.name_amharic)  LIKE LOWER(?)
         OR LOWER(m.generic_name)  LIKE LOWER(?)
         OR LOWER(m.atc_code)      LIKE LOWER(?)
        )""")
        like = f"%{q}%"
        params += [like, like, like, like]

    if category:
        conditions.append("LOWER(m.category) = LOWER(?)")
        params.append(category)

    if essential == "true":
        conditions.append("m.is_essential = 1")
    elif essential == "false":
        conditions.append("m.is_essential = 0")

    if form:
        conditions.append("LOWER(m.dosage_form) = LOWER(?)")
        params.append(form)

    where = " AND ".join(conditions)

    # Count total
    total = query(f"SELECT COUNT(*) as n FROM medicines m WHERE {where}",
                  tuple(params), one=True)["n"]

    rows = query(
        f"""SELECT * FROM medicines m
            WHERE {where}
            ORDER BY
              CASE WHEN LOWER(m.name_english) LIKE LOWER(?) THEN 0 ELSE 1 END,
              m.is_essential DESC,
              m.name_english ASC
            LIMIT ? OFFSET ?""",
        tuple(params) + (f"{q}%", per_page, offset)
    )

    return jsonify({
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    max(1, -(-total // per_page)),
        "results":  [_medicine_row(m) for m in rows],
    })


@medicines_bp.get("/categories")
def get_categories():
    rows = query("""
        SELECT category, COUNT(*) as count
        FROM medicines WHERE is_active=1
        GROUP BY category ORDER BY category
    """)
    return jsonify([{"category": r["category"], "count": r["count"]} for r in rows])


@medicines_bp.get("/essential")
def get_essential():
    rows = query("""
        SELECT * FROM medicines
        WHERE is_essential=1 AND is_active=1
        ORDER BY category, name_english
    """)
    return jsonify({
        "count":   len(rows),
        "results": [_medicine_row(m) for m in rows],
    })


@medicines_bp.get("/<int:med_id>")
@optional_auth
def medicine_detail(med_id: int):
    med = query("SELECT * FROM medicines WHERE id=? AND is_active=1", (med_id,), one=True)
    if not med:
        return jsonify({"error": "Medicine not found"}), 404

    # Stockout summary
    stock = query("""
        SELECT
            COUNT(*) as pharmacies_stocking,
            SUM(quantity) as total_units,
            SUM(CASE WHEN stock_status='out'      THEN 1 ELSE 0 END) as stockout_count,
            SUM(CASE WHEN stock_status='critical' THEN 1 ELSE 0 END) as critical_count,
            SUM(CASE WHEN stock_status='low'      THEN 1 ELSE 0 END) as low_count
        FROM inventory WHERE medicine_id=?
    """, (med_id,), one=True)

    # Latest forecast (next 7 days)
    forecast = query("""
        SELECT predicted_demand, predicted_risk, confidence_lower, confidence_upper, target_date
        FROM forecasts WHERE medicine_id=?
        ORDER BY target_date DESC LIMIT 1
    """, (med_id,), one=True)

    result = _medicine_row(med)
    result["stock_summary"] = stock
    result["latest_forecast"] = forecast
    return jsonify(result)


@medicines_bp.get("/<int:med_id>/availability")
@optional_auth
def medicine_availability(med_id: int):
    """
    Returns all pharmacies stocking this medicine, sorted by distance if
    lat/lon provided, else by stock level.
    Query params: lat, lon (optional)
    """
    user_lat = request.args.get("lat", type=float)
    user_lon = request.args.get("lon", type=float)
    status_filter = request.args.get("status", "").strip()  # e.g. "adequate,low"

    conditions = ["i.medicine_id = ?", "p.is_active = 1"]
    params     = [med_id]

    if status_filter:
        statuses = [s.strip() for s in status_filter.split(",")]
        placeholders = ",".join("?" * len(statuses))
        conditions.append(f"i.stock_status IN ({placeholders})")
        params += statuses

    where = " AND ".join(conditions)

    rows = query(f"""
        SELECT
            p.id, p.name, p.name_amharic, p.sub_city, p.woreda,
            p.latitude, p.longitude, p.phone, p.open_24h, p.type,
            i.quantity, i.stock_status, i.expiry_date,
            i.batch_number, i.reorder_point, i.shortage_risk,
            m.unit_price_etb
        FROM inventory i
        JOIN pharmacies p ON p.id = i.pharmacy_id
        JOIN medicines  m ON m.id = i.medicine_id
        WHERE {where}
    """, tuple(params))

    results = []
    for r in rows:
        item = dict(r)
        if user_lat is not None and user_lon is not None:
            item["distance_km"] = round(
                haversine_km(user_lat, user_lon, r["latitude"], r["longitude"]), 2
            )
        else:
            item["distance_km"] = None
        item["open_24h"] = bool(item["open_24h"])
        results.append(item)

    # Sort: by distance if provided, else by stock priority
    STATUS_ORDER = {"adequate": 0, "low": 1, "critical": 2, "out": 3, "overstock": 0}
    if user_lat is not None:
        results.sort(key=lambda x: (
            STATUS_ORDER.get(x["stock_status"], 9),
            x["distance_km"] or 9999
        ))
    else:
        results.sort(key=lambda x: STATUS_ORDER.get(x["stock_status"], 9))

    in_stock = [r for r in results if r["stock_status"] != "out"]
    return jsonify({
        "medicine_id":      med_id,
        "pharmacies_total": len(results),
        "in_stock_count":   len(in_stock),
        "results":          results,
    })


@medicines_bp.get("/<int:med_id>/alternatives")
@optional_auth
def medicine_alternatives(med_id: int):
    """Find generic alternatives (same ATC level-2, different product)."""
    med = query("SELECT * FROM medicines WHERE id=?", (med_id,), one=True)
    if not med:
        return jsonify({"error": "Medicine not found"}), 404

    atc2 = med["atc_level2"]
    if not atc2:
        return jsonify({"results": [], "note": "No ATC code available for this medicine"})

    alternatives = query("""
        SELECT m.*, i.total_qty
        FROM medicines m
        LEFT JOIN (
            SELECT medicine_id, SUM(quantity) as total_qty
            FROM inventory GROUP BY medicine_id
        ) i ON i.medicine_id = m.id
        WHERE m.atc_level2 = ? AND m.id != ? AND m.is_active = 1
        ORDER BY i.total_qty DESC NULLS LAST
    """, (atc2, med_id))

    return jsonify({
        "original":     _medicine_row(med),
        "alternatives": [_medicine_row(a) for a in alternatives],
        "count":        len(alternatives),
        "basis":        f"ATC level-2: {atc2}",
    })
