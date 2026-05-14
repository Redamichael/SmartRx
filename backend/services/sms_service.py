"""
SmartRx AI — SMS Notification Service (Phase 7)
Provider: Africa's Talking (Ethiopia's primary SMS gateway)
Supports: Amharic + English bilingual message templates
Features: Alert SMS, prescription confirmation, stockout warnings,
          outbreak alerts, offline queue with retry logic
"""

import json
import sqlite3
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent.parent / "smartrx_demo.db"

# ─── Africa's Talking config (set via env in production) ──────────────────────
AT_CONFIG = {
    "api_key":   "your_africas_talking_api_key",   # env: AT_API_KEY
    "username":  "smartrx_ethiopia",               # env: AT_USERNAME
    "sender_id": "SmartRx",                        # approved sender ID
    "sandbox":   True,                             # flip to False for production
}

# ─── Bilingual SMS Templates ──────────────────────────────────────────────────
TEMPLATES = {
    "stockout_alert": {
        "en": "⚠ SMARTRX ALERT: {medicine} is OUT OF STOCK at {pharmacy} ({sub_city}). "
              "Nearest stock: {nearest_pharmacy} ({distance_km}km). "
              "Call: {nearest_phone}",
        "am": "⚠ ስማርትRX ማስጠንቀቂያ: {medicine_am} ክምችት አልቋል — {pharmacy_am} ({sub_city})። "
              "ቅርብ ፋርማሲ: {nearest_pharmacy_am} ({distance_km}ኪ.ሜ)። ይደውሉ: {nearest_phone}",
    },
    "low_stock_warning": {
        "en": "📦 SmartRx: {medicine} running LOW at {pharmacy}. "
              "Only {quantity} units left (reorder point: {reorder_point}). "
              "Action required.",
        "am": "📦 ስማርትRX: {medicine_am} ክምችት እያለቀ ነው — {pharmacy_am}። "
              "{quantity} ክፍሎች ብቻ ቀርተዋል (ዳግም ትዕዛዝ ነጥብ: {reorder_point})። እርምጃ ያስፈልጋል።",
    },
    "outbreak_alert": {
        "en": "🚨 OUTBREAK SIGNAL — SmartRx AI: Unusual spike in {medicine} demand "
              "({spike_pct}% above baseline) in {region}. Possible disease outbreak. "
              "Health authorities notified.",
        "am": "🚨 ወረርሽኝ ምልክት — ስማርትRX AI: {medicine_am} ፍላጎት ያልተለመደ ጭማሪ "
              "({spike_pct}% ከተለመደ በላይ) — {region}። ሊሆን የሚችል ወረርሽኝ። "
              "የጤና ባለሥልጣናት ተነግሯቸዋል።",
    },
    "prescription_confirmed": {
        "en": "✅ SmartRx: Your prescription has been processed. "
              "{medicine_count} medicine(s) found. "
              "Nearest pharmacy: {pharmacy} ({distance_km}km away). Open: {hours}",
        "am": "✅ ስማርትRX: ማዘዣዎ ተሰርቷል። "
              "{medicine_count} መድሃኒቶች ተገኝተዋል። "
              "ቅርብ ፋርማሲ: {pharmacy_am} ({distance_km}ኪ.ሜ)። ሰዓት: {hours}",
    },
    "redistribution_approved": {
        "en": "📦 SmartRx: Redistribution approved. Transfer {quantity} units of "
              "{medicine} FROM {source_pharmacy} TO {target_pharmacy} ({distance_km}km). "
              "Urgency score: {urgency}/100.",
        "am": "📦 ስማርትRX: ማሰራጨት ጸድቋል። {quantity} ክፍሎች {medicine_am} "
              "ከ {source_pharmacy_am} ወደ {target_pharmacy_am} ({distance_km}ኪ.ሜ)። "
              "አሳሳቢነት: {urgency}/100።",
    },
    "expiry_warning": {
        "en": "⏰ SmartRx Expiry Alert: {quantity} units of {medicine} at {pharmacy} "
              "expire in {days_to_expiry} days (Batch: {batch}). Please take action.",
        "am": "⏰ ስማርትRX ጊዜ ማለፊያ: {quantity} ክፍሎች {medicine_am} — {pharmacy_am} "
              "በ{days_to_expiry} ቀናት ያልፋሉ (ባች: {batch})። እርምጃ ይውሰዱ።",
    },
    "welcome": {
        "en": "👋 Welcome to SmartRx AI — Ethiopia's Smart Pharmacy Network! "
              "Find medicines near you, scan prescriptions, and get real-time stock info. "
              "Powered by AI for Ethiopian healthcare.",
        "am": "👋 ወደ ስማርትRX AI እንኳን ደህና መጡ — የኢትዮጵያ ስማርት ፋርማሲ ኔትወርክ! "
              "ቅርብ መድሃኒቶችን ይፈልጉ፣ ማዘዣ ይቃኙ፣ የቀጥታ ክምችት መረጃ ያግኙ።",
    },
}

# ─── Africa's Talking HTTP client (real + sandbox) ───────────────────────────

class AfricasTalkingClient:
    """Thin wrapper around Africa's Talking SMS API."""

    SANDBOX_URL    = "https://api.sandbox.africastalking.com/version1/messaging"
    PRODUCTION_URL = "https://api.africastalking.com/version1/messaging"

    def __init__(self, api_key: str, username: str, sender_id: str, sandbox: bool = True):
        self.api_key   = api_key
        self.username  = username
        self.sender_id = sender_id
        self.url       = self.SANDBOX_URL if sandbox else self.PRODUCTION_URL
        self.sandbox   = sandbox

    def send(self, phone: str, message: str) -> dict:
        """
        Send SMS via Africa's Talking.
        Returns: {"status": "success"|"error", "message_id": str, "cost": str}
        """
        if self.api_key == "your_africas_talking_api_key":
            # Demo mode — simulate success
            return self._demo_response(phone, message)

        try:
            import urllib.request
            import urllib.parse
            payload = urllib.parse.urlencode({
                "username":  self.username,
                "to":        phone,
                "message":   message,
                "from":      self.sender_id,
            }).encode()
            req = urllib.request.Request(
                self.url, data=payload, method="POST",
                headers={
                    "apiKey":       self.api_key,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept":       "application/json",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                msgs   = result.get("SMSMessageData", {}).get("Recipients", [{}])
                if msgs and msgs[0].get("status") == "Success":
                    return {
                        "status":     "success",
                        "message_id": msgs[0].get("messageId", ""),
                        "cost":       msgs[0].get("cost", ""),
                        "phone":      phone,
                    }
                return {"status": "error", "reason": str(result)}
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    def _demo_response(self, phone: str, message: str) -> dict:
        """Simulate a successful send for demo/dev mode."""
        msg_id = f"ATDemo_{int(time.time())}_{abs(hash(phone))%9999:04d}"
        print(f"  [SMS DEMO] → {phone}")
        print(f"  Message: {message[:100]}{'...' if len(message)>100 else ''}")
        return {
            "status":     "success",
            "message_id": msg_id,
            "cost":       "ETB 0.35",
            "phone":      phone,
            "demo":       True,
        }

    def send_bulk(self, recipients: list[dict]) -> list[dict]:
        """Send to multiple recipients. Each dict: {phone, message}"""
        return [self.send(r["phone"], r["message"]) for r in recipients]


# ─── Notification Service ─────────────────────────────────────────────────────

class NotificationService:

    def __init__(self):
        self.client = AfricasTalkingClient(**AT_CONFIG)

    def _get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = lambda c, r: dict(zip([d[0] for d in c.description], r))
        return conn

    def _log(self, conn, alert_id, user_id, patient_id,
             channel, recipient, message, message_am,
             status, provider_msg_id=None, failed_reason=None):
        conn.execute("""
            INSERT INTO notifications
                (alert_id, user_id, patient_id, channel, recipient,
                 message, message_amharic, status, provider,
                 provider_msg_id, sent_at, failed_reason)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            alert_id, user_id, patient_id, channel, recipient,
            message, message_am, status, "africas_talking",
            provider_msg_id,
            datetime.now().isoformat() if status in ("sent","delivered") else None,
            failed_reason
        ))
        conn.commit()

    # ── Alert-triggered SMS ──────────────────────────────────

    def send_stockout_alert(self, pharmacy_id: int, medicine_id: int,
                             alert_id: Optional[int] = None):
        """Send stockout alert SMS to pharmacy staff."""
        conn = self._get_db()
        # Get pharmacy staff phones
        staff = conn.execute("""
            SELECT u.phone, u.full_name, u.full_name_am, u.id
            FROM users u WHERE u.pharmacy_id=? AND u.role='pharmacy_staff'
            AND u.phone IS NOT NULL
        """, (pharmacy_id,)).fetchall()

        # Get medicine details
        med = conn.execute(
            "SELECT name_english, name_amharic FROM medicines WHERE id=?",
            (medicine_id,)
        ).fetchone()
        pharm = conn.execute(
            "SELECT name, name_amharic, sub_city FROM pharmacies WHERE id=?",
            (pharmacy_id,)
        ).fetchone()

        if not med or not pharm:
            conn.close(); return []

        # Find nearest pharmacy with stock
        nearest = conn.execute("""
            SELECT p.name, p.name_amharic, p.phone,
                   ABS(p.latitude - ph.latitude) + ABS(p.longitude - ph.longitude) as approx_dist
            FROM inventory i
            JOIN pharmacies p ON p.id = i.pharmacy_id
            JOIN pharmacies ph ON ph.id = ?
            WHERE i.medicine_id=? AND i.stock_status != 'out' AND i.pharmacy_id != ?
            ORDER BY approx_dist LIMIT 1
        """, (pharmacy_id, medicine_id, pharmacy_id)).fetchone()

        results = []
        for s in staff:
            msg_en = TEMPLATES["stockout_alert"]["en"].format(
                medicine=med["name_english"], pharmacy=pharm["name"],
                sub_city=pharm["sub_city"] or "",
                nearest_pharmacy=nearest["name"] if nearest else "N/A",
                distance_km=round(nearest["approx_dist"]*111, 1) if nearest else "?",
                nearest_phone=nearest["phone"] if nearest else "N/A"
            )
            msg_am = TEMPLATES["stockout_alert"]["am"].format(
                medicine_am=med["name_amharic"] or med["name_english"],
                pharmacy_am=pharm["name_amharic"] or pharm["name"],
                sub_city=pharm["sub_city"] or "",
                nearest_pharmacy_am=nearest["name_amharic"] if nearest else "N/A",
                distance_km=round(nearest["approx_dist"]*111, 1) if nearest else "?",
                nearest_phone=nearest["phone"] if nearest else "N/A"
            )
            r = self.client.send(s["phone"], msg_am + "\n---\n" + msg_en)
            self._log(conn, alert_id, s["id"], None, "sms", s["phone"],
                      msg_en, msg_am,
                      "sent" if r["status"]=="success" else "failed",
                      r.get("message_id"), r.get("reason"))
            results.append(r)

        conn.close()
        return results

    def send_outbreak_alert(self, medicine_id: int, region: str,
                             spike_pct: float, alert_id: Optional[int] = None):
        """Send outbreak signal to health workers and analysts."""
        conn = self._get_db()
        workers = conn.execute("""
            SELECT u.phone, u.id FROM users u
            WHERE u.role IN ('health_worker','analyst','admin')
            AND u.phone IS NOT NULL
        """).fetchall()

        med = conn.execute(
            "SELECT name_english, name_amharic FROM medicines WHERE id=?",
            (medicine_id,)
        ).fetchone()
        if not med:
            conn.close(); return []

        results = []
        for w in workers:
            msg_en = TEMPLATES["outbreak_alert"]["en"].format(
                medicine=med["name_english"], spike_pct=round(spike_pct),
                region=region or "Addis Ababa"
            )
            msg_am = TEMPLATES["outbreak_alert"]["am"].format(
                medicine_am=med["name_amharic"] or med["name_english"],
                spike_pct=round(spike_pct), region=region or "አዲስ አበባ"
            )
            r = self.client.send(w["phone"], msg_am + "\n---\n" + msg_en)
            self._log(conn, alert_id, w["id"], None, "sms", w["phone"],
                      msg_en, msg_am,
                      "sent" if r["status"]=="success" else "failed",
                      r.get("message_id"), r.get("reason"))
            results.append(r)

        conn.close()
        return results

    def send_prescription_confirmation(self, patient_phone: str,
                                        prescription_data: dict,
                                        patient_id: Optional[int] = None):
        """Confirm prescription processing to patient via SMS."""
        medicines = prescription_data.get("medicines", [])
        nearest   = None
        for m in medicines:
            if m.get("nearest_pharmacies"):
                nearest = m["nearest_pharmacies"][0]
                break

        msg_en = TEMPLATES["prescription_confirmed"]["en"].format(
            medicine_count=len(medicines),
            pharmacy=nearest["pharmacy_name"] if nearest else "See app",
            distance_km=nearest["distance_km"] if nearest else "?",
            hours="24h" if nearest and nearest.get("open_24h") else "Check hours"
        )
        msg_am = TEMPLATES["prescription_confirmed"]["am"].format(
            medicine_count=len(medicines),
            pharmacy_am=nearest.get("name_amharic","") if nearest else "አፕሊኬሽኑን ይመልከቱ",
            distance_km=nearest["distance_km"] if nearest else "?",
            hours="24 ሰዓት" if nearest and nearest.get("open_24h") else "ሰዓት ይፈትሹ"
        )

        conn = self._get_db()
        r = self.client.send(patient_phone, msg_am + "\n---\n" + msg_en)
        self._log(conn, None, None, patient_id, "sms", patient_phone,
                  msg_en, msg_am,
                  "sent" if r["status"]=="success" else "failed",
                  r.get("message_id"), r.get("reason"))
        conn.close()
        return r

    def send_expiry_alert(self, pharmacy_id: int, medicine_id: int,
                           quantity: int, days_to_expiry: int, batch: str):
        """Notify pharmacy staff of upcoming medicine expiry."""
        conn = self._get_db()
        staff = conn.execute("""
            SELECT u.phone, u.id FROM users u
            WHERE u.pharmacy_id=? AND u.role='pharmacy_staff' AND u.phone IS NOT NULL
        """, (pharmacy_id,)).fetchall()

        med   = conn.execute("SELECT name_english, name_amharic FROM medicines WHERE id=?", (medicine_id,)).fetchone()
        pharm = conn.execute("SELECT name, name_amharic FROM pharmacies WHERE id=?", (pharmacy_id,)).fetchone()
        if not med or not pharm:
            conn.close(); return []

        results = []
        for s in staff:
            msg_en = TEMPLATES["expiry_warning"]["en"].format(
                quantity=quantity, medicine=med["name_english"],
                pharmacy=pharm["name"], days_to_expiry=days_to_expiry, batch=batch
            )
            msg_am = TEMPLATES["expiry_warning"]["am"].format(
                quantity=quantity, medicine_am=med["name_amharic"] or med["name_english"],
                pharmacy_am=pharm["name_amharic"] or pharm["name"],
                days_to_expiry=days_to_expiry, batch=batch
            )
            r = self.client.send(s["phone"], msg_am + "\n---\n" + msg_en)
            self._log(conn, None, s["id"], None, "sms", s["phone"],
                      msg_en, msg_am,
                      "sent" if r["status"]=="success" else "failed",
                      r.get("message_id"), r.get("reason"))
            results.append(r)
        conn.close()
        return results

    def send_welcome(self, phone: str, patient_id: Optional[int] = None):
        """Welcome SMS for new patient registration."""
        msg_en = TEMPLATES["welcome"]["en"]
        msg_am = TEMPLATES["welcome"]["am"]
        conn = self._get_db()
        r = self.client.send(phone, msg_am + "\n---\n" + msg_en)
        self._log(conn, None, None, patient_id, "sms", phone,
                  msg_en, msg_am,
                  "sent" if r["status"]=="success" else "failed",
                  r.get("message_id"), r.get("reason"))
        conn.close()
        return r

    # ── Offline queue processor ──────────────────────────────

    def process_pending_notifications(self) -> dict:
        """
        Retry all pending/failed notifications (offline queue).
        Call this periodically or on reconnect.
        """
        conn = self._get_db()
        pending = conn.execute("""
            SELECT * FROM notifications
            WHERE status IN ('pending','failed') AND retry_count < 3
            ORDER BY created_at ASC LIMIT 50
        """).fetchall()

        sent = failed = 0
        for n in pending:
            r = self.client.send(n["recipient"], n["message_amharic"] or n["message"])
            status = "sent" if r["status"] == "success" else "failed"
            conn.execute("""
                UPDATE notifications
                SET status=?, provider_msg_id=?, sent_at=?,
                    failed_reason=?, retry_count=retry_count+1
                WHERE id=?
            """, (
                status,
                r.get("message_id"),
                datetime.now().isoformat() if status=="sent" else None,
                r.get("reason"),
                n["id"]
            ))
            if status == "sent": sent += 1
            else:                failed += 1

        conn.commit()
        conn.close()
        return {"processed": len(pending), "sent": sent, "failed": failed}

    def scan_and_alert(self) -> dict:
        """
        Main alert scanner: checks DB for new critical events
        and fires SMS for unnotified ones.
        """
        conn   = self._get_db()
        alerts = conn.execute("""
            SELECT a.*, m.name_english, m.name_amharic, p.name as pharm_name,
                   p.sub_city, p.id as pharm_id
            FROM alerts a
            LEFT JOIN medicines  m ON m.id = a.medicine_id
            LEFT JOIN pharmacies p ON p.id = a.pharmacy_id
            WHERE a.is_resolved=0 AND a.severity='critical'
              AND a.id NOT IN (SELECT DISTINCT alert_id FROM notifications WHERE alert_id IS NOT NULL)
            LIMIT 20
        """).fetchall()
        conn.close()

        fired = 0
        for alert in alerts:
            if alert["alert_type"] == "stockout" and alert["pharm_id"]:
                self.send_stockout_alert(alert["pharm_id"], alert["medicine_id"], alert["id"])
                fired += 1
            elif alert["alert_type"] == "outbreak":
                self.send_outbreak_alert(
                    alert["medicine_id"], alert["sub_city"], 150.0, alert["id"]
                )
                fired += 1

        return {"alerts_scanned": len(alerts), "sms_fired": fired}


# ─── API route for Flask ──────────────────────────────────────────────────────

def register_sms_routes(app):
    """Register SMS endpoints on the Flask app."""
    from flask import Blueprint, request, jsonify, g
    from backend.api.auth_utils import require_auth

    sms_bp  = Blueprint("sms", __name__, url_prefix="/api/sms")
    service = NotificationService()

    @sms_bp.post("/send-alert")
    @require_auth
    def send_alert_sms():
        if g.role not in ("admin", "health_worker"):
            return jsonify({"error": "Forbidden"}), 403
        body = request.get_json(silent=True) or {}
        t    = body.get("type", "stockout")

        if t == "stockout":
            r = service.send_stockout_alert(
                body.get("pharmacy_id"), body.get("medicine_id")
            )
        elif t == "outbreak":
            r = service.send_outbreak_alert(
                body.get("medicine_id"), body.get("region",""),
                body.get("spike_pct", 150)
            )
        elif t == "welcome":
            r = service.send_welcome(body.get("phone"))
        else:
            return jsonify({"error": "Unknown type"}), 400

        return jsonify({"results": r if isinstance(r, list) else [r]})

    @sms_bp.post("/prescription-confirm")
    @require_auth
    def confirm_prescription():
        body = request.get_json(silent=True) or {}
        r = service.send_prescription_confirmation(
            body.get("phone"), body.get("prescription_data", {}),
            body.get("patient_id")
        )
        return jsonify(r)

    @sms_bp.post("/process-queue")
    @require_auth
    def process_queue():
        if g.role != "admin":
            return jsonify({"error": "Admin only"}), 403
        return jsonify(service.process_pending_notifications())

    @sms_bp.post("/scan-alerts")
    @require_auth
    def scan_alerts():
        if g.role not in ("admin", "health_worker"):
            return jsonify({"error": "Forbidden"}), 403
        return jsonify(service.scan_and_alert())

    @sms_bp.get("/history")
    @require_auth
    def sms_history():
        from backend.database.db import query
        rows = query("""
            SELECT n.*, u.username, p.name as pharmacy_name
            FROM notifications n
            LEFT JOIN users u ON u.id = n.user_id
            LEFT JOIN pharmacies p ON p.id = (SELECT pharmacy_id FROM users WHERE id = n.user_id)
            ORDER BY n.created_at DESC LIMIT 100
        """)
        return jsonify({"count": len(rows), "results": rows})

    @sms_bp.get("/templates")
    def get_templates():
        return jsonify({
            "templates": list(TEMPLATES.keys()),
            "detail": {k: {"en": v["en"][:80]+"...", "am": v["am"][:80]+"..."}
                       for k, v in TEMPLATES.items()},
            "provider": "Africa's Talking",
            "sandbox":  AT_CONFIG["sandbox"],
        })

    app.register_blueprint(sms_bp)
    return sms_bp


# ─── Demo runner ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═"*54)
    print("  SmartRx AI — SMS Notification Demo")
    print("  Provider: Africa's Talking (Demo mode)")
    print("═"*54)

    svc = NotificationService()

    print("\n[1] Stockout alert → pharmacy staff")
    r = svc.send_stockout_alert(pharmacy_id=1, medicine_id=23, alert_id=1)
    print(f"  Sent: {len(r)} SMS | Status: {[x['status'] for x in r]}")

    print("\n[2] Outbreak alert → health workers")
    r = svc.send_outbreak_alert(medicine_id=49, region="Bole, Addis Ababa",
                                 spike_pct=220.0, alert_id=3)
    print(f"  Sent: {len(r)} SMS")

    print("\n[3] Prescription confirmation → patient")
    r = svc.send_prescription_confirmation(
        "+251911234567",
        {"medicines": [{"name":"Amoxicillin","nearest_pharmacies":[{
            "pharmacy_name":"Bole Kenema Pharmacy",
            "name_amharic":"ቦሌ ቀነማ ፋርማሲ",
            "distance_km":1.2, "open_24h":True
        }]}]}
    )
    print(f"  Status: {r['status']} | ID: {r.get('message_id','?')}")

    print("\n[4] Welcome SMS → new patient")
    r = svc.send_welcome("+251922345678")
    print(f"  Status: {r['status']}")

    print("\n[5] Scan alerts and fire pending SMS")
    r = svc.scan_and_alert()
    print(f"  Scanned: {r['alerts_scanned']} | SMS fired: {r['sms_fired']}")

    print("\n[6] Process offline queue")
    r = svc.process_pending_notifications()
    print(f"  Processed: {r['processed']} | Sent: {r['sent']} | Failed: {r['failed']}")

    # Show notification log
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = lambda c,r: dict(zip([d[0] for d in c.description], r))
    logs = conn.execute(
        "SELECT channel, status, recipient, created_at FROM notifications ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    print(f"\n  Notification log ({len(logs)} recent):")
    for log in logs:
        print(f"    {log['status']:10} | {log['channel']:5} | {log['recipient']} | {log['created_at'][:16]}")

    print("\n" + "═"*54)
    print("✅ Phase 7 — SMS Notifications COMPLETE")
    print("   To use in production:")
    print("   1. Set AT_CONFIG['api_key'] = os.environ['AT_API_KEY']")
    print("   2. Set AT_CONFIG['sandbox'] = False")
    print("   3. Register 'SmartRx' sender ID with Africa's Talking")
    print("═"*54 + "\n")
