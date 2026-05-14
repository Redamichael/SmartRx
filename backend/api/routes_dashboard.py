"""
SmartRx AI — Dashboard, Alerts, Forecasts & Analytics Routes

GET  /api/dashboard/overview          System-wide KPIs
GET  /api/dashboard/stock-map         All pharmacies with stock status (map view)
GET  /api/dashboard/shortage-heatmap  Sub-city shortage aggregation

GET  /api/alerts                      All active alerts (paginated)
PUT  /api/alerts/<id>/resolve         Resolve an alert
PUT  /api/alerts/<id>/read            Mark as read

GET  /api/forecasts                   Shortage forecasts (next 7/14/30 days)
GET  /api/forecasts/at-risk           Medicines with high/critical predicted risk

GET  /api/redistribution              Redistribution suggestions
POST /api/redistribution              Create suggestion (AI engine)
PUT  /api/redistribution/<id>/approve Approve a suggestion

GET  /api/analytics/demand            Demand trends (time-series)
GET  /api/analytics/top-medicines     Most dispensed medicines
GET  /api/analytics/outbreak-signals  Recent anomaly/outbreak events
GET  /api/analytics/availability-rate Availability % by category / sub-city
"""

from flask import Blueprint, request, jsonify, g
from datetime import datetime, date, timedelta
import json, math, random
from ..database.db import query, execute, haversine_km
from .auth_utils import require_auth, require_role

dashboard_bp      = Blueprint("dashboard",      __name__, url_prefix="/api/dashboard")
alerts_bp         = Blueprint("alerts",         __name__, url_prefix="/api/alerts")
forecasts_bp      = Blueprint("forecasts",      __name__, url_prefix="/api/forecasts")
redistribution_bp = Blueprint("redistribution", __name__, url_prefix="/api/redistribution")
analytics_bp      = Blueprint("analytics",      __name__, url_prefix="/api/analytics")


# ═══════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.get("/overview")
@require_auth
def system_overview():
    """
    System-wide KPIs for the health-worker / admin dashboard.
    Returns: stock health, alert counts, prescription stats, recent activity.
    """
    # Stock health
    stock = query("""
        SELECT
            COUNT(*) as total_records,
            SUM(CASE WHEN stock_status='out'      THEN 1 ELSE 0 END) as stockouts,
            SUM(CASE WHEN stock_status='critical' THEN 1 ELSE 0 END) as critical,
            SUM(CASE WHEN stock_status='low'      THEN 1 ELSE 0 END) as low,
            SUM(CASE WHEN stock_status='adequate' THEN 1 ELSE 0 END) as adequate,
            SUM(CASE WHEN stock_status='overstock' THEN 1 ELSE 0 END) as overstock,
            SUM(CASE WHEN expiry_date < date('now','+90 days') AND expiry_date IS NOT NULL
                     THEN 1 ELSE 0 END) as expiring_90d
        FROM inventory
    """, one=True)

    # Essential medicines stockout rate
    essential_stock = query("""
        SELECT
            COUNT(DISTINCT i.medicine_id) as essential_total,
            SUM(CASE WHEN i.stock_status='out' THEN 1 ELSE 0 END) as essential_stockouts
        FROM inventory i
        JOIN medicines m ON m.id = i.medicine_id
        WHERE m.is_essential = 1
    """, one=True)

    # Active alerts by severity
    alerts = query("""
        SELECT severity, COUNT(*) as n
        FROM alerts WHERE is_resolved=0
        GROUP BY severity
    """)
    alert_counts = {r["severity"]: r["n"] for r in alerts}

    # Prescriptions stats (last 30 days)
    prescs = query("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN filled=1 THEN 1 ELSE 0 END) as filled,
            ROUND(AVG(extraction_confidence)*100, 1) as avg_ai_confidence_pct
        FROM prescriptions
        WHERE prescribed_date >= date('now','-30 days')
    """, one=True)

    # Transactions (last 7 days)
    txn = query("""
        SELECT
            COUNT(*) as transactions_7d,
            SUM(total_price_etb) as revenue_7d,
            COUNT(DISTINCT pharmacy_id) as active_pharmacies_7d
        FROM transactions
        WHERE transaction_date >= date('now','-7 days')
    """, one=True)

    # Pharmacies summary
    pharmacies = query("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN open_24h=1 THEN 1 ELSE 0 END) as open_24h_count
        FROM pharmacies WHERE is_active=1
    """, one=True)

    # Outbreak signals (unresolved)
    outbreaks = query("""
        SELECT COUNT(*) as n FROM anomaly_events
        WHERE is_outbreak=1 AND resolved_at IS NULL
    """, one=True)

    availability_pct = 0
    if stock["total_records"]:
        availability_pct = round(
            100 * (stock["adequate"] + stock["overstock"]) / stock["total_records"], 1
        )

    return jsonify({
        "generated_at": datetime.now().isoformat(),
        "pharmacies": {
            "total":       pharmacies["total"],
            "open_24h":    pharmacies["open_24h_count"],
        },
        "stock_health": {
            "total_records":     stock["total_records"],
            "stockouts":         stock["stockouts"],
            "critical":          stock["critical"],
            "low":               stock["low"],
            "adequate":          stock["adequate"],
            "overstock":         stock["overstock"],
            "expiring_90_days":  stock["expiring_90d"],
            "availability_pct":  availability_pct,
        },
        "essential_medicines": {
            "total":     essential_stock["essential_total"],
            "stockouts": essential_stock["essential_stockouts"],
            "coverage_pct": round(
                100 * (1 - (essential_stock["essential_stockouts"] or 0) /
                       max(1, essential_stock["essential_total"])), 1
            ),
        },
        "alerts": {
            "critical": alert_counts.get("critical", 0),
            "warning":  alert_counts.get("warning",  0),
            "info":     alert_counts.get("info",     0),
            "total":    sum(alert_counts.values()),
        },
        "prescriptions_30d": {
            "total":            prescs["total"],
            "filled":           prescs["filled"],
            "fill_rate_pct":    round(100 * (prescs["filled"] or 0) / max(1, prescs["total"]), 1),
            "avg_ai_confidence_pct": prescs["avg_ai_confidence_pct"],
        },
        "transactions_7d": {
            "count":               txn["transactions_7d"],
            "revenue_etb":         round(txn["revenue_7d"] or 0, 2),
            "active_pharmacies":   txn["active_pharmacies_7d"],
        },
        "outbreak_signals": outbreaks["n"],
    })


@dashboard_bp.get("/stock-map")
@require_auth
def stock_map():
    """
    Returns all pharmacies with their stock health for the map view.
    Each pharmacy gets: coordinates, stock summary, alert count, top shortage.
    """
    rows = query("""
        SELECT
            p.id, p.name, p.name_amharic, p.sub_city,
            p.latitude, p.longitude, p.phone, p.open_24h, p.type,
            COUNT(i.id) as total_medicines,
            SUM(CASE WHEN i.stock_status='out'      THEN 1 ELSE 0 END) as stockouts,
            SUM(CASE WHEN i.stock_status='critical' THEN 1 ELSE 0 END) as critical,
            SUM(CASE WHEN i.stock_status='low'      THEN 1 ELSE 0 END) as low,
            SUM(CASE WHEN i.stock_status='adequate' THEN 1 ELSE 0 END) as adequate,
            COUNT(a.id) as active_alerts
        FROM pharmacies p
        LEFT JOIN inventory i ON i.pharmacy_id = p.id
        LEFT JOIN alerts    a ON a.pharmacy_id  = p.id AND a.is_resolved = 0
        WHERE p.is_active = 1
        GROUP BY p.id
    """)

    def _health_score(r):
        total = r["total_medicines"] or 1
        return round(100 * r["adequate"] / total, 1)

    def _status_color(score):
        if score >= 80: return "green"
        if score >= 50: return "yellow"
        if score >= 20: return "orange"
        return "red"

    features = []
    for r in rows:
        score  = _health_score(r)
        color  = _status_color(score)
        features.append({
            "id":              r["id"],
            "name":            r["name"],
            "name_amharic":    r["name_amharic"],
            "sub_city":        r["sub_city"],
            "lat":             r["latitude"],
            "lon":             r["longitude"],
            "phone":           r["phone"],
            "open_24h":        bool(r["open_24h"]),
            "type":            r["type"],
            "health_score":    score,
            "status_color":    color,
            "stock": {
                "total":    r["total_medicines"],
                "stockout": r["stockouts"],
                "critical": r["critical"],
                "low":      r["low"],
                "adequate": r["adequate"],
            },
            "active_alerts":   r["active_alerts"],
        })

    return jsonify({
        "total_pharmacies": len(features),
        "pharmacies": features,
    })


@dashboard_bp.get("/shortage-heatmap")
@require_auth
def shortage_heatmap():
    """Aggregate shortage severity by sub-city for choropleth map."""
    rows = query("""
        SELECT
            p.sub_city,
            COUNT(DISTINCT p.id) as pharmacies,
            SUM(CASE WHEN i.stock_status='out'      THEN 1 ELSE 0 END) as stockouts,
            SUM(CASE WHEN i.stock_status='critical' THEN 1 ELSE 0 END) as critical,
            SUM(i.id) as total_records,
            COUNT(DISTINCT CASE WHEN i.stock_status='out' THEN i.medicine_id END) as medicines_stockedout
        FROM pharmacies p
        JOIN inventory i ON i.pharmacy_id = p.id
        WHERE p.is_active = 1
        GROUP BY p.sub_city
        ORDER BY stockouts DESC
    """)

    def _severity(r):
        total = r["total_records"] or 1
        rate  = (r["stockouts"] + r["critical"] * 0.5) / total
        if rate > 0.20: return "critical"
        if rate > 0.10: return "high"
        if rate > 0.05: return "medium"
        return "low"

    return jsonify([{
        **r,
        "shortage_rate_pct": round(100 * r["stockouts"] / max(1, r["total_records"]), 1),
        "severity": _severity(r),
    } for r in rows])


# ═══════════════════════════════════════════════════════════════
# ALERTS
# ═══════════════════════════════════════════════════════════════

@alerts_bp.get("")
@require_auth
def list_alerts():
    """
    Query params: severity, alert_type, pharmacy_id, resolved, page, per_page
    """
    severity    = request.args.get("severity", "").strip()
    alert_type  = request.args.get("type", "").strip()
    pharmacy_id = request.args.get("pharmacy_id", type=int)
    resolved    = request.args.get("resolved", "false").lower() == "true"
    page        = max(1, int(request.args.get("page", 1)))
    per_page    = min(100, max(1, int(request.args.get("per_page", 20))))
    offset      = (page - 1) * per_page

    conditions = ["a.is_resolved = ?"]
    params     = [1 if resolved else 0]

    # Staff only see their pharmacy
    if g.role == "pharmacy_staff" and g.pharmacy_id:
        conditions.append("a.pharmacy_id = ?")
        params.append(g.pharmacy_id)
    elif pharmacy_id:
        conditions.append("a.pharmacy_id = ?")
        params.append(pharmacy_id)

    if severity:
        conditions.append("a.severity = ?")
        params.append(severity)
    if alert_type:
        conditions.append("a.alert_type = ?")
        params.append(alert_type)

    where = " AND ".join(conditions)
    total = query(f"SELECT COUNT(*) as n FROM alerts a WHERE {where}",
                  tuple(params), one=True)["n"]

    rows = query(f"""
        SELECT
            a.*,
            p.name  as pharmacy_name, p.name_amharic as pharmacy_name_am,
            p.sub_city,
            m.name_english as medicine_name, m.name_amharic as medicine_name_am,
            m.category, m.is_essential
        FROM alerts a
        LEFT JOIN pharmacies p ON p.id = a.pharmacy_id
        LEFT JOIN medicines  m ON m.id = a.medicine_id
        WHERE {where}
        ORDER BY
            CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
            a.created_at DESC
        LIMIT ? OFFSET ?
    """, tuple(params) + (per_page, offset))

    return jsonify({
        "total": total, "page": page, "per_page": per_page,
        "pages": max(1, -(-total // per_page)),
        "results": rows,
    })


@alerts_bp.put("/<int:alert_id>/resolve")
@require_auth
def resolve_alert(alert_id: int):
    if g.role not in ("admin", "pharmacy_staff", "health_worker", "analyst"):
        return jsonify({"error": "Insufficient permissions"}), 403

    a = query("SELECT * FROM alerts WHERE id=?", (alert_id,), one=True)
    if not a:
        return jsonify({"error": "Alert not found"}), 404
    if a["is_resolved"]:
        return jsonify({"error": "Already resolved"}), 409

    body = request.get_json(silent=True) or {}
    execute("""UPDATE alerts
               SET is_resolved=1, resolved_by=?, resolved_at=?
               WHERE id=?""",
            (g.user_id, datetime.now().isoformat(), alert_id))

    return jsonify({"alert_id": alert_id, "resolved": True,
                    "resolved_by": g.user_id,
                    "resolved_at": datetime.now().isoformat()})


@alerts_bp.put("/<int:alert_id>/read")
@require_auth
def mark_read(alert_id: int):
    execute("UPDATE alerts SET is_read=1 WHERE id=?", (alert_id,))
    return jsonify({"alert_id": alert_id, "is_read": True})


# ═══════════════════════════════════════════════════════════════
# FORECASTS  (LSTM output endpoint — populated by ML pipeline)
# ═══════════════════════════════════════════════════════════════

@forecasts_bp.get("")
@require_auth
def list_forecasts():
    """
    Query params: pharmacy_id, medicine_id, horizon (7|14|30), risk, page
    Returns stored LSTM forecasts. Falls back to heuristic if DB empty.
    """
    pharmacy_id = request.args.get("pharmacy_id", type=int)
    medicine_id = request.args.get("medicine_id", type=int)
    horizon     = int(request.args.get("horizon", 7))
    risk        = request.args.get("risk", "").strip()
    page        = max(1, int(request.args.get("page", 1)))
    per_page    = min(100, max(1, int(request.args.get("per_page", 20))))
    offset      = (page - 1) * per_page

    # Check if ML forecasts exist in DB
    has_forecasts = query("SELECT COUNT(*) as n FROM forecasts", one=True)["n"]

    if has_forecasts:
        conditions = ["f.horizon_days = ?"]
        params     = [horizon]
        if pharmacy_id:
            conditions.append("f.pharmacy_id = ?"); params.append(pharmacy_id)
        if medicine_id:
            conditions.append("f.medicine_id = ?"); params.append(medicine_id)
        if risk:
            conditions.append("f.predicted_risk = ?"); params.append(risk)

        where = " AND ".join(conditions)
        total = query(f"SELECT COUNT(*) as n FROM forecasts f WHERE {where}",
                      tuple(params), one=True)["n"]
        rows = query(f"""
            SELECT f.*, m.name_english, m.name_amharic, m.category, m.is_essential,
                   p.name as pharmacy_name, p.name_amharic as pharmacy_name_am, p.sub_city
            FROM forecasts f
            JOIN medicines  m ON m.id = f.medicine_id
            JOIN pharmacies p ON p.id = f.pharmacy_id
            WHERE {where}
            ORDER BY
                CASE f.predicted_risk WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                                      WHEN 'medium'   THEN 2 ELSE 3 END,
                f.target_date
            LIMIT ? OFFSET ?
        """, tuple(params) + (per_page, offset))
        return jsonify({"source": "lstm_model", "total": total,
                        "page": page, "per_page": per_page, "results": rows})

    # ── Heuristic fallback (pre-ML): avg demand × days ────────
    return _heuristic_forecast(pharmacy_id, medicine_id, horizon, risk, page, per_page, offset)


def _heuristic_forecast(pharmacy_id, medicine_id, horizon, risk, page, per_page, offset):
    """
    Compute short-term forecast from 30-day rolling average.
    Used before LSTM model is trained.
    """
    conditions = ["i.stock_status IN ('out','critical','low')"]
    params     = []
    if pharmacy_id:
        conditions.append("i.pharmacy_id = ?"); params.append(pharmacy_id)
    if medicine_id:
        conditions.append("i.medicine_id = ?"); params.append(medicine_id)

    where = " AND ".join(conditions)
    rows = query(f"""
        SELECT
            i.pharmacy_id, i.medicine_id, i.quantity,
            i.stock_status, i.reorder_point, i.avg_daily_demand,
            i.days_of_stock, i.shortage_risk,
            m.name_english, m.name_amharic, m.category, m.is_essential,
            p.name as pharmacy_name, p.name_amharic as pharmacy_name_am, p.sub_city
        FROM inventory i
        JOIN medicines  m ON m.id = i.medicine_id
        JOIN pharmacies p ON p.id = i.pharmacy_id
        WHERE {where}
        ORDER BY
            CASE i.stock_status WHEN 'out' THEN 0 WHEN 'critical' THEN 1 ELSE 2 END,
            m.is_essential DESC
        LIMIT ? OFFSET ?
    """, tuple(params) + (per_page, offset))

    results = []
    target  = (date.today() + timedelta(days=horizon)).isoformat()
    for r in rows:
        avg_daily = r["avg_daily_demand"] or 5
        predicted = round(avg_daily * horizon, 1)
        days_left = r["days_of_stock"] or 0

        if days_left == 0 or r["stock_status"] == "out":
            pred_risk = "critical"
        elif days_left <= 3:
            pred_risk = "critical"
        elif days_left <= 7:
            pred_risk = "high"
        elif days_left <= 14:
            pred_risk = "medium"
        else:
            pred_risk = "low"

        if risk and pred_risk != risk:
            continue

        results.append({
            "pharmacy_id":       r["pharmacy_id"],
            "pharmacy_name":     r["pharmacy_name"],
            "pharmacy_name_am":  r["pharmacy_name_am"],
            "sub_city":          r["sub_city"],
            "medicine_id":       r["medicine_id"],
            "name_english":      r["name_english"],
            "name_amharic":      r["name_amharic"],
            "category":          r["category"],
            "is_essential":      bool(r["is_essential"]),
            "current_stock":     r["quantity"],
            "avg_daily_demand":  avg_daily,
            "predicted_demand":  predicted,
            "horizon_days":      horizon,
            "target_date":       target,
            "predicted_risk":    pred_risk,
            "days_of_stock":     days_left,
            "confidence_lower":  round(predicted * 0.75, 1),
            "confidence_upper":  round(predicted * 1.25, 1),
            "model_version":     "heuristic_v1",
        })

    total = query(f"SELECT COUNT(*) as n FROM inventory i "
                  f"JOIN medicines m ON m.id=i.medicine_id WHERE {where}",
                  tuple(params), one=True)["n"]
    return jsonify({"source": "heuristic", "total": total, "page": page,
                    "per_page": per_page, "results": results})


@forecasts_bp.get("/at-risk")
@require_auth
def at_risk_medicines():
    """
    Top medicines predicted to stock-out within the horizon.
    Combines current inventory state + demand trends.
    Query params: horizon_days (default 7), limit (default 20)
    """
    horizon = int(request.args.get("horizon_days", 7))
    limit   = min(100, int(request.args.get("limit", 20)))

    rows = query("""
        SELECT
            i.medicine_id, i.quantity, i.stock_status,
            i.avg_daily_demand, i.days_of_stock, i.shortage_risk,
            m.name_english, m.name_amharic, m.category, m.is_essential,
            COUNT(DISTINCT i.pharmacy_id) as affected_pharmacies,
            SUM(CASE WHEN i.stock_status='out' THEN 1 ELSE 0 END) as stockout_count
        FROM inventory i
        JOIN medicines m ON m.id = i.medicine_id
        WHERE i.stock_status IN ('out','critical','low')
           OR (i.avg_daily_demand IS NOT NULL
               AND i.quantity / MAX(i.avg_daily_demand, 0.1) <= ?)
        GROUP BY i.medicine_id
        ORDER BY stockout_count DESC, m.is_essential DESC, i.days_of_stock ASC
        LIMIT ?
    """, (horizon, limit))

    return jsonify({
        "horizon_days": horizon,
        "count":        len(rows),
        "results": [{
            **r,
            "is_essential":    bool(r["is_essential"]),
            "estimated_stockout_date": (
                date.today() + timedelta(days=int(r["days_of_stock"] or 0))
            ).isoformat() if r["days_of_stock"] else "already_stockedout",
        } for r in rows],
    })


# ═══════════════════════════════════════════════════════════════
# REDISTRIBUTION
# ═══════════════════════════════════════════════════════════════

@redistribution_bp.get("")
@require_auth
def list_redistributions():
    status  = request.args.get("status", "suggested").strip()
    page    = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    offset  = (page - 1) * per_page

    total = query("SELECT COUNT(*) as n FROM redistribution_suggestions WHERE status=?",
                  (status,), one=True)["n"]
    rows = query("""
        SELECT
            rs.*,
            m.name_english, m.name_amharic, m.category, m.is_essential,
            sp.name as source_name, sp.name_amharic as source_name_am,
            sp.sub_city as source_sub_city,
            tp.name as target_name, tp.name_amharic as target_name_am,
            tp.sub_city as target_sub_city
        FROM redistribution_suggestions rs
        JOIN medicines  m  ON m.id  = rs.medicine_id
        JOIN pharmacies sp ON sp.id = rs.source_pharmacy_id
        JOIN pharmacies tp ON tp.id = rs.target_pharmacy_id
        WHERE rs.status = ?
        ORDER BY rs.urgency_score DESC, rs.created_at DESC
        LIMIT ? OFFSET ?
    """, (status, per_page, offset))

    return jsonify({"total": total, "page": page, "per_page": per_page,
                    "results": [{**r, "is_essential": bool(r["is_essential"])} for r in rows]})


@redistribution_bp.post("")
@require_auth
def generate_redistribution():
    """
    AI engine: scan inventory for overstock vs stockout pairs
    and auto-generate redistribution suggestions.
    Roles: admin, analyst, health_worker
    """
    if g.role not in ("admin", "analyst", "health_worker"):
        return jsonify({"error": "Insufficient permissions"}), 403

    # Find medicines with both overstock somewhere and stockout elsewhere
    overstock_rows = query("""
        SELECT i.pharmacy_id, i.medicine_id, i.quantity, i.reorder_point,
               p.latitude, p.longitude, p.name, p.name_amharic
        FROM inventory i
        JOIN pharmacies p ON p.id = i.pharmacy_id
        WHERE i.stock_status IN ('overstock','adequate')
          AND i.quantity > i.reorder_point * 3
    """)

    stockout_rows = query("""
        SELECT i.pharmacy_id, i.medicine_id, i.quantity, i.reorder_point,
               i.stock_status,
               p.latitude, p.longitude, p.name, p.name_amharic, p.sub_city
        FROM inventory i
        JOIN pharmacies p ON p.id = i.pharmacy_id
        WHERE i.stock_status IN ('out','critical')
    """)

    # Index overstock by medicine
    overstock_by_med = {}
    for o in overstock_rows:
        overstock_by_med.setdefault(o["medicine_id"], []).append(o)

    created = []
    for s in stockout_rows:
        mid  = s["medicine_id"]
        sources = overstock_by_med.get(mid, [])
        if not sources:
            continue

        # Pick closest source with enough surplus
        best_source = None
        best_dist   = float("inf")
        for src in sources:
            dist = haversine_km(s["latitude"], s["longitude"],
                                src["latitude"], src["longitude"])
            surplus = src["quantity"] - src["reorder_point"] * 2
            if surplus >= 10 and dist < best_dist:
                best_source = src
                best_dist   = dist

        if not best_source:
            continue

        # Suggested qty: enough to bring target to reorder_point * 2
        suggested_qty = max(10, (s["reorder_point"] or 20) * 2 - s["quantity"])
        urgency = round(
            100 * (1 if s["stock_status"] == "out" else 0.7) *
            (1 / max(1, best_dist / 10)), 1
        )
        urgency = min(100.0, urgency)

        rationale = (
            f"Source '{best_source['name']}' has {best_source['quantity']} units "
            f"({best_source['quantity'] - best_source['reorder_point']} above reorder). "
            f"Target '{s['name']}' has {s['quantity']} units (status: {s['stock_status']}). "
            f"Distance: {round(best_dist, 1)} km. Suggested transfer: {suggested_qty} units."
        )

        # Avoid duplicate suggestions
        existing = query("""
            SELECT id FROM redistribution_suggestions
            WHERE medicine_id=? AND source_pharmacy_id=? AND target_pharmacy_id=?
              AND status IN ('suggested','approved','in_transit')
        """, (mid, best_source["pharmacy_id"], s["pharmacy_id"]), one=True)

        if not existing:
            rid = execute("""
                INSERT INTO redistribution_suggestions
                    (medicine_id, source_pharmacy_id, target_pharmacy_id,
                     suggested_quantity, urgency_score, distance_km,
                     rationale, status, suggested_by)
                VALUES (?,?,?,?,?,?,?,'suggested','ai_engine')
            """, (mid, best_source["pharmacy_id"], s["pharmacy_id"],
                  suggested_qty, urgency, round(best_dist, 2), rationale))
            created.append(rid)

    return jsonify({
        "suggestions_created": len(created),
        "suggestion_ids":      created,
        "message": f"{len(created)} redistribution suggestions generated by AI engine.",
    }), 201


@redistribution_bp.put("/<int:rid>/approve")
@require_auth
def approve_redistribution(rid: int):
    if g.role not in ("admin", "health_worker"):
        return jsonify({"error": "Insufficient permissions"}), 403

    body = request.get_json(silent=True) or {}
    r    = query("SELECT * FROM redistribution_suggestions WHERE id=?", (rid,), one=True)
    if not r:
        return jsonify({"error": "Suggestion not found"}), 404
    if r["status"] != "suggested":
        return jsonify({"error": f"Cannot approve — current status: {r['status']}"}), 409

    approved_qty = body.get("approved_quantity", r["suggested_quantity"])
    execute("""UPDATE redistribution_suggestions
               SET status='approved', approved_by=?, approved_at=?, approved_quantity=?
               WHERE id=?""",
            (g.user_id, datetime.now().isoformat(), approved_qty, rid))

    # Generate approval alert
    execute("""INSERT INTO alerts
        (alert_type, severity, pharmacy_id, medicine_id, title, title_amharic, message)
        VALUES ('redistribution','info',?,?,
            'Redistribution approved — transfer in progress',
            'ማሰራጨት ጸድቋል — ዝውውር በሂደት ላይ ነው',
            ?)""",
        (r["target_pharmacy_id"], r["medicine_id"],
         f"Transfer of {approved_qty} units approved. Expected arrival: 1-2 days."))

    return jsonify({"id": rid, "status": "approved",
                    "approved_quantity": approved_qty,
                    "approved_at": datetime.now().isoformat()})


# ═══════════════════════════════════════════════════════════════
# ANALYTICS
# ═══════════════════════════════════════════════════════════════

@analytics_bp.get("/demand")
@require_auth
def demand_trends():
    """
    Time-series demand for a medicine (or all), aggregated by day/week/month.
    Query params: medicine_id, pharmacy_id, period (day|week|month),
                  start_date, end_date
    """
    medicine_id = request.args.get("medicine_id", type=int)
    pharmacy_id = request.args.get("pharmacy_id", type=int)
    period      = request.args.get("period", "week")
    start       = request.args.get("start_date",
                                   (date.today() - timedelta(days=90)).isoformat())
    end         = request.args.get("end_date", date.today().isoformat())

    conditions = ["t.transaction_date BETWEEN ? AND ?"]
    params     = [start, end]
    if medicine_id:
        conditions.append("t.medicine_id = ?"); params.append(medicine_id)
    if pharmacy_id:
        conditions.append("t.pharmacy_id = ?"); params.append(pharmacy_id)
    where = " AND ".join(conditions)

    GROUP_BY = {
        "day":   "t.transaction_date",
        "week":  "t.year || '-W' || printf('%02d', CAST(strftime('%W', t.transaction_date) AS INTEGER))",
        "month": "t.year || '-' || printf('%02d', t.month)",
    }.get(period, "t.year || '-W' || printf('%02d', CAST(strftime('%W', t.transaction_date) AS INTEGER))")

    # SQLite: week not stored in transactions, compute it
    rows = query(f"""
        SELECT
            {GROUP_BY} as period_label,
            SUM(t.quantity_dispensed) as total_dispensed,
            COUNT(*) as transaction_count,
            COUNT(DISTINCT t.pharmacy_id) as pharmacies,
            COUNT(DISTINCT t.medicine_id) as medicines,
            ROUND(SUM(t.total_price_etb), 2) as revenue_etb
        FROM transactions t
        WHERE {where}
        GROUP BY {GROUP_BY}
        ORDER BY period_label
    """, tuple(params))

    # Pull medicine/pharmacy name for context
    context = {}
    if medicine_id:
        m = query("SELECT name_english, name_amharic FROM medicines WHERE id=?",
                  (medicine_id,), one=True)
        if m: context["medicine"] = m
    if pharmacy_id:
        p = query("SELECT name, name_amharic FROM pharmacies WHERE id=?",
                  (pharmacy_id,), one=True)
        if p: context["pharmacy"] = p

    return jsonify({"period": period, "start": start, "end": end,
                    "context": context, "data_points": len(rows), "series": rows})


@analytics_bp.get("/top-medicines")
@require_auth
def top_medicines():
    """Most dispensed medicines over a time window."""
    days  = min(365, int(request.args.get("days", 30)))
    limit = min(50, int(request.args.get("limit", 15)))
    pharmacy_id = request.args.get("pharmacy_id", type=int)

    conditions = ["t.transaction_date >= date('now', ?)"]
    params     = [f"-{days} days"]
    if pharmacy_id:
        conditions.append("t.pharmacy_id = ?"); params.append(pharmacy_id)
    where = " AND ".join(conditions)

    rows = query(f"""
        SELECT
            m.id, m.name_english, m.name_amharic, m.category, m.is_essential,
            SUM(t.quantity_dispensed) as total_dispensed,
            COUNT(*) as transaction_count,
            ROUND(SUM(t.total_price_etb), 2) as revenue_etb,
            COUNT(DISTINCT t.pharmacy_id) as dispensing_pharmacies
        FROM transactions t
        JOIN medicines m ON m.id = t.medicine_id
        WHERE {where}
        GROUP BY m.id
        ORDER BY total_dispensed DESC
        LIMIT ?
    """, tuple(params) + (limit,))

    return jsonify({
        "days": days, "limit": limit,
        "results": [{**r, "is_essential": bool(r["is_essential"])} for r in rows],
    })


@analytics_bp.get("/outbreak-signals")
@require_auth
def outbreak_signals():
    """Recent anomaly/outbreak events with severity breakdown."""
    days  = min(365, int(request.args.get("days", 90)))
    limit = min(200, int(request.args.get("limit", 50)))

    rows = query("""
        SELECT
            ae.*,
            m.name_english, m.name_amharic, m.category,
            p.name as pharmacy_name, p.name_amharic as pharmacy_name_am,
            p.sub_city
        FROM anomaly_events ae
        JOIN medicines m ON m.id = ae.medicine_id
        LEFT JOIN pharmacies p ON p.id = ae.pharmacy_id
        WHERE ae.event_date >= date('now', ?)
        ORDER BY ae.is_outbreak DESC, ae.anomaly_score DESC, ae.event_date DESC
        LIMIT ?
    """, (f"-{days} days", limit))

    outbreaks = [r for r in rows if r["is_outbreak"]]
    anomalies = [r for r in rows if not r["is_outbreak"]]

    return jsonify({
        "total":           len(rows),
        "outbreak_count":  len(outbreaks),
        "anomaly_count":   len(anomalies),
        "days_window":     days,
        "outbreaks":       outbreaks,
        "anomalies":       anomalies,
    })


@analytics_bp.get("/availability-rate")
@require_auth
def availability_rate():
    """
    Medicine availability % broken down by category and sub-city.
    Key metric for health ministry reporting.
    """
    # By category
    by_category = query("""
        SELECT
            m.category,
            COUNT(*) as total_records,
            SUM(CASE WHEN i.stock_status IN ('adequate','overstock') THEN 1 ELSE 0 END) as available,
            SUM(CASE WHEN i.stock_status = 'out' THEN 1 ELSE 0 END) as stockout,
            ROUND(
                100.0 * SUM(CASE WHEN i.stock_status IN ('adequate','overstock') THEN 1 ELSE 0 END)
                / COUNT(*), 1
            ) as availability_pct
        FROM inventory i
        JOIN medicines m ON m.id = i.medicine_id
        GROUP BY m.category
        ORDER BY availability_pct ASC
    """)

    # By sub-city
    by_subcity = query("""
        SELECT
            p.sub_city,
            COUNT(*) as total_records,
            SUM(CASE WHEN i.stock_status IN ('adequate','overstock') THEN 1 ELSE 0 END) as available,
            SUM(CASE WHEN i.stock_status = 'out' THEN 1 ELSE 0 END) as stockout,
            ROUND(
                100.0 * SUM(CASE WHEN i.stock_status IN ('adequate','overstock') THEN 1 ELSE 0 END)
                / COUNT(*), 1
            ) as availability_pct
        FROM inventory i
        JOIN pharmacies p ON p.id = i.pharmacy_id
        GROUP BY p.sub_city
        ORDER BY availability_pct ASC
    """)

    # Essential medicines specifically
    essential = query("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN i.stock_status IN ('adequate','overstock') THEN 1 ELSE 0 END) as available,
            ROUND(
                100.0 * SUM(CASE WHEN i.stock_status IN ('adequate','overstock') THEN 1 ELSE 0 END)
                / COUNT(*), 1
            ) as availability_pct
        FROM inventory i
        JOIN medicines m ON m.id = i.medicine_id
        WHERE m.is_essential = 1
    """, one=True)

    return jsonify({
        "essential_medicines": essential,
        "by_category":         by_category,
        "by_sub_city":         by_subcity,
    })


@analytics_bp.get("/expiry-watch")
@require_auth
def expiry_watch():
    """Medicines expiring within 30/60/90 days across the network."""
    rows = query("""
        SELECT
            i.pharmacy_id, i.medicine_id, i.quantity,
            i.batch_number, i.expiry_date,
            julianday(i.expiry_date) - julianday('now') as days_to_expiry,
            m.name_english, m.name_amharic, m.category, m.unit_price_etb,
            p.name as pharmacy_name, p.name_amharic as pharmacy_name_am,
            p.sub_city, p.phone
        FROM inventory i
        JOIN medicines  m ON m.id  = i.medicine_id
        JOIN pharmacies p ON p.id  = i.pharmacy_id
        WHERE i.expiry_date IS NOT NULL
          AND i.expiry_date <= date('now', '+90 days')
          AND i.quantity > 0
        ORDER BY i.expiry_date ASC
        LIMIT 200
    """)

    expiring_30  = [r for r in rows if (r["days_to_expiry"] or 0) <= 30]
    expiring_60  = [r for r in rows if 30 < (r["days_to_expiry"] or 0) <= 60]
    expiring_90  = [r for r in rows if 60 < (r["days_to_expiry"] or 0) <= 90]
    total_value  = sum((r["unit_price_etb"] or 0) * r["quantity"] for r in rows)

    return jsonify({
        "expiring_30_days":  {"count": len(expiring_30),  "items": expiring_30},
        "expiring_60_days":  {"count": len(expiring_60),  "items": expiring_60},
        "expiring_90_days":  {"count": len(expiring_90),  "items": expiring_90},
        "total_at_risk_etb": round(total_value, 2),
    })
