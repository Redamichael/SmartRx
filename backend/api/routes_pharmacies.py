"""
SmartRx AI — Pharmacy Routes
GET  /api/pharmacies                 List / search pharmacies
GET  /api/pharmacies/nearby          Find nearest pharmacies (with haversine)
GET  /api/pharmacies/<id>            Pharmacy detail
GET  /api/pharmacies/<id>/inventory  Full inventory for a pharmacy
GET  /api/pharmacies/<id>/stock-summary  Dashboard summary
PUT  /api/pharmacies/<id>/inventory/<med_id>  Update stock (staff only)
GET  /api/pharmacies/<id>/alerts     Pharmacy-specific alerts
GET  /api/pharmacies/<id>/low-stock  Medicines below reorder point
"""

from flask import Blueprint, request, jsonify, g
from datetime import datetime
from ..database.db import query, execute, haversine_km
from .auth_utils import require_auth, require_role, optional_auth

pharmacies_bp = Blueprint("pharmacies", __name__, url_prefix="/api/pharmacies")


def _pharmacy_row(p: dict, distance_km: float = None) -> dict:
    d = {
        "id":            p["id"],
        "name":          p["name"],
        "name_amharic":  p["name_amharic"],
        "sub_city":      p["sub_city"],
        "woreda":        p.get("woreda"),
        "latitude":      p["latitude"],
        "longitude":     p["longitude"],
        "phone":         p["phone"],
        "open_24h":      bool(p["open_24h"]),
        "type":          p["type"],
        "region":        p.get("region", "Addis Ababa"),
        "license_number": p.get("license_number"),
    }
    if distance_km is not None:
        d["distance_km"] = round(distance_km, 2)
    return d


@pharmacies_bp.get("")
@optional_auth
def list_pharmacies():
    """
    Query params:
      q        - name search (EN or Amharic)
      sub_city - filter by sub-city
      type     - private | government | ngo
      open_24h - true/false
      page, per_page
    """
    q        = request.args.get("q", "").strip()
    sub_city = request.args.get("sub_city", "").strip()
    ptype    = request.args.get("type", "").strip()
    open_24h = request.args.get("open_24h", "").strip().lower()
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(1, int(request.args.get("per_page", 25))))
    offset   = (page - 1) * per_page

    conditions = ["is_active = 1"]
    params     = []

    if q:
        conditions.append("(LOWER(name) LIKE LOWER(?) OR LOWER(name_amharic) LIKE LOWER(?))")
        like = f"%{q}%"
        params += [like, like]
    if sub_city:
        conditions.append("LOWER(sub_city) = LOWER(?)")
        params.append(sub_city)
    if ptype:
        conditions.append("type = ?")
        params.append(ptype)
    if open_24h == "true":
        conditions.append("open_24h = 1")

    where = " AND ".join(conditions)
    total = query(f"SELECT COUNT(*) as n FROM pharmacies WHERE {where}",
                  tuple(params), one=True)["n"]
    rows  = query(f"SELECT * FROM pharmacies WHERE {where} "
                  f"ORDER BY name LIMIT ? OFFSET ?",
                  tuple(params) + (per_page, offset))

    return jsonify({
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "results":  [_pharmacy_row(p) for p in rows],
    })


@pharmacies_bp.get("/nearby")
@optional_auth
def nearby_pharmacies():
    """
    Find pharmacies within radius_km of lat/lon.
    Optionally filter by medicine_id to show only pharmacies that stock it.
    Query params: lat*, lon*, radius_km (default 5), medicine_id, limit (default 10)
    """
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon are required"}), 400

    radius    = float(request.args.get("radius_km", 5))
    medicine_id = request.args.get("medicine_id", type=int)
    limit     = min(50, int(request.args.get("limit", 10)))

    if medicine_id:
        rows = query("""
            SELECT p.*, i.quantity, i.stock_status, m.unit_price_etb
            FROM pharmacies p
            JOIN inventory i ON i.pharmacy_id = p.id AND i.medicine_id = ?
            JOIN medicines m ON m.id = ?
            WHERE p.is_active = 1 AND i.stock_status != 'out'
        """, (medicine_id, medicine_id))
    else:
        rows = query("SELECT * FROM pharmacies WHERE is_active = 1")

    results = []
    for p in rows:
        dist = haversine_km(lat, lon, p["latitude"], p["longitude"])
        if dist <= radius:
            item = _pharmacy_row(p, distance_km=dist)
            if medicine_id:
                item["quantity"]     = p.get("quantity")
                item["stock_status"] = p.get("stock_status")
                item["price_etb"]    = p.get("unit_price_etb")
            results.append(item)

    results.sort(key=lambda x: x["distance_km"])
    results = results[:limit]

    return jsonify({
        "center":      {"lat": lat, "lon": lon},
        "radius_km":   radius,
        "medicine_id": medicine_id,
        "count":       len(results),
        "results":     results,
    })


@pharmacies_bp.get("/<int:pharm_id>")
@optional_auth
def pharmacy_detail(pharm_id: int):
    p = query("SELECT * FROM pharmacies WHERE id=? AND is_active=1", (pharm_id,), one=True)
    if not p:
        return jsonify({"error": "Pharmacy not found"}), 404

    # Stock summary
    stock = query("""
        SELECT
            COUNT(*) as total_medicines,
            SUM(CASE WHEN stock_status='out'      THEN 1 ELSE 0 END) as stockout,
            SUM(CASE WHEN stock_status='critical' THEN 1 ELSE 0 END) as critical,
            SUM(CASE WHEN stock_status='low'      THEN 1 ELSE 0 END) as low,
            SUM(CASE WHEN stock_status='adequate' THEN 1 ELSE 0 END) as adequate,
            SUM(CASE WHEN stock_status='overstock' THEN 1 ELSE 0 END) as overstock,
            SUM(CASE WHEN expiry_date < date('now', '+90 days') AND expiry_date IS NOT NULL
                     THEN 1 ELSE 0 END) as expiring_90d
        FROM inventory WHERE pharmacy_id=?
    """, (pharm_id,), one=True)

    # Active alerts count
    alerts = query("""
        SELECT COUNT(*) as n FROM alerts
        WHERE pharmacy_id=? AND is_resolved=0
    """, (pharm_id,), one=True)

    result = _pharmacy_row(p)
    result["stock_summary"]   = stock
    result["active_alerts"]   = alerts["n"]
    result["address"]         = p.get("address")
    result["facility_code"]   = p.get("facility_code")
    result["last_inspection"] = p.get("last_inspection")
    return jsonify(result)


@pharmacies_bp.get("/<int:pharm_id>/inventory")
@require_auth
def pharmacy_inventory(pharm_id: int):
    """
    Full inventory list for a pharmacy.
    Staff can only view their own pharmacy; admin/analyst see all.
    Query params: status (filter), category, q (medicine name search), page, per_page
    """
    if g.role == "pharmacy_staff" and g.pharmacy_id != pharm_id:
        return jsonify({"error": "Access denied"}), 403

    status   = request.args.get("status", "").strip()
    category = request.args.get("category", "").strip()
    q        = request.args.get("q", "").strip()
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(200, max(1, int(request.args.get("per_page", 50))))
    offset   = (page - 1) * per_page

    conditions = ["i.pharmacy_id = ?"]
    params     = [pharm_id]

    if status:
        statuses = [s.strip() for s in status.split(",")]
        conditions.append(f"i.stock_status IN ({','.join('?'*len(statuses))})")
        params += statuses
    if category:
        conditions.append("LOWER(m.category) = LOWER(?)")
        params.append(category)
    if q:
        conditions.append("(LOWER(m.name_english) LIKE LOWER(?) OR LOWER(m.name_amharic) LIKE LOWER(?))")
        params += [f"%{q}%", f"%{q}%"]

    where = " AND ".join(conditions)
    total = query(f"""
        SELECT COUNT(*) as n FROM inventory i
        JOIN medicines m ON m.id = i.medicine_id
        WHERE {where}
    """, tuple(params), one=True)["n"]

    rows = query(f"""
        SELECT
            i.id, i.medicine_id, i.quantity, i.stock_status,
            i.reorder_point, i.reorder_quantity, i.batch_number,
            i.expiry_date, i.last_reorder_date, i.shortage_risk,
            i.avg_daily_demand, i.days_of_stock,
            m.name_english, m.name_amharic, m.category, m.atc_code,
            m.strength, m.dosage_form, m.unit_price_etb, m.is_essential,
            m.requires_prescription
        FROM inventory i
        JOIN medicines m ON m.id = i.medicine_id
        WHERE {where}
        ORDER BY
            CASE i.stock_status
                WHEN 'out'      THEN 0
                WHEN 'critical' THEN 1
                WHEN 'low'      THEN 2
                WHEN 'adequate' THEN 3
                WHEN 'overstock' THEN 4
                ELSE 5
            END,
            m.is_essential DESC, m.name_english
        LIMIT ? OFFSET ?
    """, tuple(params) + (per_page, offset))

    return jsonify({
        "pharmacy_id": pharm_id,
        "total":       total,
        "page":        page,
        "per_page":    per_page,
        "results": [{
            **r,
            "is_essential":          bool(r["is_essential"]),
            "requires_prescription": bool(r["requires_prescription"]),
        } for r in rows],
    })


@pharmacies_bp.put("/<int:pharm_id>/inventory/<int:med_id>")
@require_auth
def update_stock(pharm_id: int, med_id: int):
    """
    Update stock quantity for a medicine at a pharmacy.
    Roles: pharmacy_staff (own pharmacy), admin.
    Body: { "quantity": int, "batch_number": str, "expiry_date": "YYYY-MM-DD",
            "operation": "set"|"add"|"subtract" }
    """
    if g.role == "pharmacy_staff" and g.pharmacy_id != pharm_id:
        return jsonify({"error": "Access denied — not your pharmacy"}), 403
    if g.role not in ("pharmacy_staff", "admin"):
        return jsonify({"error": "Insufficient permissions"}), 403

    body = request.get_json(silent=True) or {}
    qty  = body.get("quantity")
    if qty is None:
        return jsonify({"error": "quantity is required"}), 400

    qty = int(qty)
    operation = body.get("operation", "set")  # set | add | subtract

    inv = query("SELECT * FROM inventory WHERE pharmacy_id=? AND medicine_id=?",
                (pharm_id, med_id), one=True)
    if not inv:
        return jsonify({"error": "Inventory record not found"}), 404

    old_qty = inv["quantity"]
    if operation == "add":
        new_qty = old_qty + qty
    elif operation == "subtract":
        new_qty = max(0, old_qty - qty)
    else:
        new_qty = max(0, qty)

    # Compute new status
    rp = inv["reorder_point"] or 20
    if new_qty == 0:
        new_status = "out"
    elif new_qty <= rp * 0.5:
        new_status = "critical"
    elif new_qty <= rp:
        new_status = "low"
    elif new_qty > rp * 5:
        new_status = "overstock"
    else:
        new_status = "adequate"

    fields  = ["quantity=?", "stock_status=?", "updated_at=?"]
    params  = [new_qty, new_status, datetime.now().isoformat()]
    if body.get("batch_number"):
        fields.append("batch_number=?"); params.append(body["batch_number"])
    if body.get("expiry_date"):
        fields.append("expiry_date=?"); params.append(body["expiry_date"])
    if body.get("reorder_point"):
        fields.append("reorder_point=?"); params.append(int(body["reorder_point"]))

    params += [pharm_id, med_id]
    execute(f"UPDATE inventory SET {', '.join(fields)} WHERE pharmacy_id=? AND medicine_id=?",
            tuple(params))

    # Log transaction if adding stock (restocking)
    if operation in ("add", "set") and new_qty > old_qty:
        execute("""INSERT INTO transactions
            (pharmacy_id, medicine_id, quantity_dispensed, transaction_date, month, year, notes)
            VALUES (?,?,?,date('now'),
                    CAST(strftime('%m','now') AS INTEGER),
                    CAST(strftime('%Y','now') AS INTEGER),
                    'Stock replenishment')""",
                (pharm_id, med_id, new_qty - old_qty))

    return jsonify({
        "pharmacy_id":  pharm_id,
        "medicine_id":  med_id,
        "old_quantity": old_qty,
        "new_quantity": new_qty,
        "operation":    operation,
        "stock_status": new_status,
        "updated_at":   datetime.now().isoformat(),
    })


@pharmacies_bp.get("/<int:pharm_id>/low-stock")
@require_auth
def low_stock(pharm_id: int):
    """Medicines at or below reorder point — for replenishment orders."""
    if g.role == "pharmacy_staff" and g.pharmacy_id != pharm_id:
        return jsonify({"error": "Access denied"}), 403

    rows = query("""
        SELECT
            i.medicine_id, i.quantity, i.stock_status, i.reorder_point,
            i.reorder_quantity, i.avg_daily_demand, i.days_of_stock,
            i.expiry_date, i.shortage_risk,
            m.name_english, m.name_amharic, m.category,
            m.strength, m.dosage_form, m.unit_price_etb, m.is_essential
        FROM inventory i
        JOIN medicines m ON m.id = i.medicine_id
        WHERE i.pharmacy_id = ?
          AND i.stock_status IN ('out','critical','low')
        ORDER BY
            CASE i.stock_status WHEN 'out' THEN 0 WHEN 'critical' THEN 1 ELSE 2 END,
            m.is_essential DESC
    """, (pharm_id,))

    total_reorder_cost = sum(
        (r["reorder_quantity"] or 100) * (r["unit_price_etb"] or 0)
        for r in rows
    )

    return jsonify({
        "pharmacy_id":        pharm_id,
        "low_stock_count":    len(rows),
        "estimated_reorder_cost_etb": round(total_reorder_cost, 2),
        "results": [{
            **r,
            "is_essential": bool(r["is_essential"]),
            "suggested_order_qty": r["reorder_quantity"] or 100,
        } for r in rows],
    })


@pharmacies_bp.get("/<int:pharm_id>/alerts")
@require_auth
def pharmacy_alerts(pharm_id: int):
    if g.role == "pharmacy_staff" and g.pharmacy_id != pharm_id:
        return jsonify({"error": "Access denied"}), 403

    resolved = request.args.get("resolved", "false").lower() == "true"
    rows = query("""
        SELECT a.*, m.name_english as medicine_name, m.name_amharic as medicine_name_am
        FROM alerts a
        LEFT JOIN medicines m ON m.id = a.medicine_id
        WHERE a.pharmacy_id = ? AND a.is_resolved = ?
        ORDER BY
            CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
            a.created_at DESC
        LIMIT 50
    """, (pharm_id, 1 if resolved else 0))

    return jsonify({"pharmacy_id": pharm_id, "count": len(rows), "results": rows})


@pharmacies_bp.get("/sub-cities")
def sub_cities():
    rows = query("""
        SELECT sub_city, COUNT(*) as pharmacy_count
        FROM pharmacies WHERE is_active=1 AND sub_city IS NOT NULL
        GROUP BY sub_city ORDER BY sub_city
    """)
    return jsonify(rows)
