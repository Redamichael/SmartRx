"""
SmartRx AI — Database Loader
Seeds all CSV datasets into the database in dependency order.
Run: python3 -m backend.database.db_loader
"""

import csv
import json
import sys
import os
from pathlib import Path
from datetime import datetime, date
from typing import Optional

# ── Path setup ────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.database.connection import engine, SessionLocal, init_db
from backend.models.models import (
    Pharmacy, Medicine, Inventory, Patient, Prescription,
    Transaction, WeeklyDemand, AnomalyEvent, Alert, User,
    PharmacyType, StockStatus, ShortageRisk, DosageForm,
    StorageCondition, UserRole, AlertType, AlertSeverity,
    Gender
)

DATASETS = Path(__file__).parent.parent / "datasets"

# ─── Helpers ──────────────────────────────────────────────────

def read_csv(filename: str) -> list[dict]:
    path = DATASETS / filename
    if not path.exists():
        print(f"  ⚠️  {filename} not found — skipping")
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def to_bool(val) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes")

def to_int(val) -> Optional[int]:
    try:
        return int(float(val)) if val not in (None, "", "None") else None
    except Exception:
        return None

def to_float(val) -> Optional[float]:
    try:
        return float(val) if val not in (None, "", "None") else None
    except Exception:
        return None

def to_date(val) -> Optional[date]:
    if not val or val in ("None", ""):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None

def safe_enum(enum_class, val, default=None):
    """Return enum member or default if val not valid."""
    try:
        return enum_class(val)
    except (ValueError, KeyError):
        return default

def batch_insert(session, objects, label, batch_size=500):
    total = len(objects)
    for i in range(0, total, batch_size):
        session.bulk_save_objects(objects[i:i+batch_size])
        session.flush()
    print(f"  ✓ {label}: {total:,} rows")

# ─── Loaders ──────────────────────────────────────────────────

def load_pharmacies(session):
    rows = read_csv("pharmacies.csv")
    objs = []
    for r in rows:
        objs.append(Pharmacy(
            id             = int(r["id"]),
            name           = r["name"],
            name_amharic   = r.get("name_amharic"),
            sub_city       = r.get("sub_city"),
            woreda         = r.get("woreda"),
            latitude       = float(r["latitude"]),
            longitude      = float(r["longitude"]),
            phone          = r.get("phone"),
            type           = safe_enum(PharmacyType, r.get("type"), PharmacyType.private),
            license_number = r.get("license_number"),
            region         = r.get("region", "Addis Ababa"),
            open_24h       = to_bool(r.get("open_24h", False)),
            is_active      = True,
        ))
    batch_insert(session, objs, "pharmacies")


def load_medicines(session):
    rows = read_csv("medicines.csv")
    objs = []

    FORM_MAP = {
        "Tablet": DosageForm.tablet, "Capsule": DosageForm.capsule,
        "Syrup": DosageForm.syrup, "Injection": DosageForm.injection,
        "IV Bag": DosageForm.iv_bag, "Inhaler": DosageForm.inhaler,
        "Eye Drop": DosageForm.eye_drop, "Eye Oint": DosageForm.eye_oint,
        "Cream": DosageForm.cream, "Lotion": DosageForm.lotion,
        "Solution": DosageForm.solution, "Sachet": DosageForm.sachet,
        "Vial": DosageForm.vial,
    }
    STORE_MAP = {
        "Room temperature": StorageCondition.room_temp,
        "Refrigerate": StorageCondition.refrigerate,
        "Freeze": StorageCondition.freeze,
        "Below 25C": StorageCondition.below_25c,
    }

    for r in rows:
        atc = r.get("atc_code", "")
        objs.append(Medicine(
            id                    = int(r["id"]),
            name_english          = r["name_english"],
            name_amharic          = r.get("name_amharic"),
            generic_name          = r.get("generic_name", r["name_english"]),
            category              = r.get("category", "General"),
            atc_code              = atc or None,
            atc_level1            = atc[0] if atc else None,
            atc_level2            = atc[:3] if len(atc) >= 3 else None,
            strength              = r.get("strength", ""),
            dosage_form           = FORM_MAP.get(r.get("dosage_form"), DosageForm.tablet),
            unit_price_etb        = to_float(r.get("unit_price_etb")),
            is_essential          = to_bool(r.get("is_essential", False)),
            requires_prescription = to_bool(r.get("requires_prescription", False)),
            storage_condition     = STORE_MAP.get(
                r.get("storage_condition", "Room temperature"),
                StorageCondition.room_temp
            ),
            shelf_life_months     = to_int(r.get("shelf_life_months", 24)) or 24,
            is_active             = True,
        ))
    batch_insert(session, objs, "medicines")


def load_inventory(session):
    rows = read_csv("inventory.csv")
    objs = []
    STATUS_MAP = {s: StockStatus(s) for s in ["out","critical","low","adequate","overstock"]}
    for r in rows:
        qty = to_int(r.get("quantity", 0)) or 0
        rp  = to_int(r.get("reorder_point", 20)) or 20
        objs.append(Inventory(
            id                = int(r["id"]),
            pharmacy_id       = int(r["pharmacy_id"]),
            medicine_id       = int(r["medicine_id"]),
            quantity          = qty,
            stock_status      = STATUS_MAP.get(r.get("stock_status", "adequate"), StockStatus.adequate),
            reorder_point     = rp,
            batch_number      = r.get("batch_number"),
            expiry_date       = to_date(r.get("expiry_date")),
            last_reorder_date = to_date(r.get("last_reorder_date")),
            updated_at        = datetime.now(),
        ))
    batch_insert(session, objs, "inventory")


def load_patients(session):
    rows = read_csv("patients.csv")
    objs = []
    for r in rows:
        g = r.get("gender", "")
        objs.append(Patient(
            id                    = int(r["id"]),
            name_amharic          = r.get("name_amharic"),
            age                   = to_int(r.get("age")),
            gender                = Gender.M if g == "M" else (Gender.F if g == "F" else None),
            sub_city              = r.get("sub_city"),
            phone                 = r.get("phone"),
            has_chronic_condition = to_bool(r.get("has_chronic_condition", False)),
            created_at            = to_date(r.get("created_at")) or date.today(),
        ))
    batch_insert(session, objs, "patients")


def load_prescriptions(session):
    rows = read_csv("prescriptions.csv")
    objs = []
    for r in rows:
        filled = to_bool(r.get("filled", False))
        fp_id  = to_int(r.get("filled_pharmacy_id"))
        objs.append(Prescription(
            id                  = int(r["id"]),
            patient_id          = to_int(r.get("patient_id")),
            diagnosis_english   = r.get("diagnosis_english"),
            diagnosis_amharic   = r.get("diagnosis_amharic"),
            primary_medicine_id = to_int(r.get("primary_medicine_id")),
            prescribing_facility= r.get("prescribing_facility"),
            prescribed_date     = to_date(r.get("prescribed_date")),
            filled              = filled,
            filled_at           = datetime.now() if filled else None,
            filled_pharmacy_id  = fp_id if filled else None,
            language_detected   = "amharic",
        ))
    batch_insert(session, objs, "prescriptions")


def load_transactions(session):
    rows = read_csv("transactions.csv")
    BATCH = 2000
    total = len(rows)
    count = 0
    for i in range(0, total, BATCH):
        chunk = rows[i:i+BATCH]
        objs  = []
        for r in chunk:
            d = to_date(r.get("transaction_date")) or date.today()
            objs.append(Transaction(
                id                  = int(r["id"]),
                pharmacy_id         = int(r["pharmacy_id"]),
                medicine_id         = int(r["medicine_id"]),
                quantity_dispensed  = to_int(r.get("quantity_dispensed")) or 1,
                unit_price_etb      = to_float(r.get("unit_price_etb")),
                total_price_etb     = to_float(r.get("total_price_etb")),
                transaction_date    = d,
                month               = d.month,
                year                = d.year,
                day_of_week         = d.weekday(),
                is_weekend          = d.weekday() >= 5,
                prescription_required = to_bool(r.get("prescription_required", False)),
            ))
        session.bulk_save_objects(objs)
        session.flush()
        count += len(objs)
        pct = int(100 * count / total)
        print(f"  → transactions: {count:,}/{total:,} ({pct}%)", end="\r")
    print(f"  ✓ transactions: {total:,} rows              ")


def load_weekly_demand(session):
    rows = read_csv("weekly_demand.csv")
    RISK_MAP = {r: ShortageRisk(r) for r in ["low","medium","high","critical"]}
    BATCH = 2000
    total = len(rows)
    count = 0
    for i in range(0, total, BATCH):
        chunk = rows[i:i+BATCH]
        objs  = []
        for r in chunk:
            objs.append(WeeklyDemand(
                id              = int(r["id"]),
                pharmacy_id     = int(r["pharmacy_id"]),
                medicine_id     = int(r["medicine_id"]),
                year            = to_int(r.get("year")) or 2024,
                week            = to_int(r.get("week")) or 1,
                total_dispensed = to_int(r.get("total_dispensed")) or 0,
                avg_daily       = to_float(r.get("avg_daily")),
                days_recorded   = to_int(r.get("days_recorded")),
                shortage_risk   = RISK_MAP.get(r.get("shortage_risk","low"), ShortageRisk.low),
            ))
        session.bulk_save_objects(objs)
        session.flush()
        count += len(objs)
    print(f"  ✓ weekly_demand: {total:,} rows")


def load_outbreak_signals(session):
    rows = read_csv("outbreak_signals.csv")
    objs = []
    for r in rows:
        d = to_date(r.get("transaction_date")) or date.today()
        qty = to_float(r.get("quantity_dispensed")) or 0
        objs.append(AnomalyEvent(
            id              = int(r["id"]),
            pharmacy_id     = to_int(r.get("pharmacy_id")),
            medicine_id     = int(r["medicine_id"]),
            detected_at     = datetime.now(),
            event_date      = d,
            anomaly_score   = min(1.0, qty / 200.0),   # normalise
            threshold       = 0.65,
            spike_magnitude = qty,
            observed_demand = qty,
            is_outbreak     = to_bool(r.get("is_outbreak_signal", True)),
            event_name      = r.get("event_name"),
        ))
    batch_insert(session, objs, "anomaly_events (outbreak signals)")


def seed_default_users(session):
    """Create default admin and demo users."""
    import hashlib
    def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

    users = [
        User(username="admin",     email="admin@smartrx.et",     password_hash=hash_pw("Admin@2024"),   role=UserRole.admin,          full_name="System Admin",         full_name_am="ሲስተም አስተዳዳሪ",  is_verified=True),
        User(username="analyst1",  email="analyst@smartrx.et",   password_hash=hash_pw("Analyst@2024"), role=UserRole.analyst,         full_name="Health Ministry Analyst", full_name_am="የጤና ሚኒስትሪ ተንታኝ", is_verified=True),
        User(username="manager1",  email="manager@smartrx.et",   password_hash=hash_pw("Manager@2024"), role=UserRole.analyst,         full_name="Pharmacy Manager",      full_name_am="ፋርማሲ አስተዳዳሪ",   is_verified=True),
        User(username="staff_bole",email="bole@smartrx.et",       password_hash=hash_pw("Staff@2024"),   role=UserRole.pharmacy_staff,  full_name="Bole Pharmacy Staff",  full_name_am="ቦሌ ፋርማሲ ሰራተኛ", is_verified=True, pharmacy_id=1),
        User(username="staff_piassa",email="piassa@smartrx.et",   password_hash=hash_pw("Staff@2024"),   role=UserRole.pharmacy_staff,  full_name="Piassa Staff",         full_name_am="ፒያሳ ሰራተኛ",      is_verified=True, pharmacy_id=2),
        User(username="worker1",   email="worker@smartrx.et",     password_hash=hash_pw("Worker@2024"),  role=UserRole.health_worker,   full_name="Health Worker",        full_name_am="የጤና ሰራተኛ",      is_verified=True),
        User(username="patient1",  email="patient@smartrx.et",    password_hash=hash_pw("Patient@2024"), role=UserRole.patient,         full_name="Demo Patient",         full_name_am="ናሙና ታካሚ",       is_verified=True),
    ]
    session.bulk_save_objects(users)
    print(f"  ✓ users: {len(users)} default accounts")


def seed_sample_alerts(session):
    """Seed a few realistic alerts for dashboard demo."""
    alerts = [
        Alert(alert_type=AlertType.stockout,   severity=AlertSeverity.critical,
              pharmacy_id=2,  medicine_id=23,
              title="Stock-out: Artemether-Lumefantrine at Piassa Medhanealem",
              title_amharic="ክምችት አለቀ፡ አርቴሜተር-ሉሜፋንትሪን በፒያሳ",
              message="0 units remaining. 3-day demand forecast: 45 units.",
              message_amharic="0 ክፍሎች ቀርተዋል። የ3 ቀን ፍላጎት ትንበያ: 45 ክፍሎች።"),

        Alert(alert_type=AlertType.low_stock,  severity=AlertSeverity.warning,
              pharmacy_id=1,  medicine_id=9,
              title="Critical stock: Amoxicillin 500mg at Bole Kenema",
              title_amharic="ወሳኝ ክምችት፡ አሞክሲሲሊን 500mg በቦሌ ቀነማ",
              message="8 units remaining. Reorder point: 20. Forecasted stockout in 2 days.",
              message_amharic="8 ክፍሎች ቀርተዋል። ዳግም ትዕዛዝ ነጥብ: 20።"),

        Alert(alert_type=AlertType.outbreak,   severity=AlertSeverity.critical,
              pharmacy_id=None, medicine_id=49,
              title="Outbreak signal: ORS demand spike — Bole, Kirkos sub-cities",
              title_amharic="ወረርሽኝ ምልክት፡ ኦአርኤስ ፍላጎት ጭማሪ — ቦሌ፣ ቅርቆስ",
              message="ORS dispensing 3.2x above 30-day baseline. Possible diarrhea outbreak.",
              message_amharic="ኦአርኤስ ማከፋፈል ከ30 ቀን መስመር በላይ 3.2x ነው።"),

        Alert(alert_type=AlertType.expiry,     severity=AlertSeverity.warning,
              pharmacy_id=8,  medicine_id=38,
              title="Expiry alert: Insulin Regular — expiring in 45 days",
              title_amharic="ጊዜ ማለፊያ ማስጠንቀቂያ፡ ኢንሱሊን ሬጉላር — በ45 ቀናት ያልፋል",
              message="12 vials of Insulin Regular (Batch BATCH-08-038-4521) expire on 2025-06-23.",
              message_amharic="12 ቫይሎች ኢንሱሊን ሬጉላር ሰኔ 23 ቀን 2025 ያልፋሉ።"),

        Alert(alert_type=AlertType.redistribution, severity=AlertSeverity.info,
              pharmacy_id=15, medicine_id=23,
              title="Redistribution suggested: 120 units Artemether from Arada Tsehay → Piassa",
              title_amharic="ማሰራጨት ተጠቆመ፡ 120 ክፍሎች አርቴሜተር ከአራዳ → ፒያሳ",
              message="Source pharmacy has 340 units (170% above reorder). Target has 0.",
              message_amharic="ምንጭ ፋርማሲ 340 ክፍሎች አለው (ከዳግም ትዕዛዝ 170% በላይ)።"),
    ]
    session.bulk_save_objects(alerts)
    print(f"  ✓ alerts: {len(alerts)} sample alerts")


# ─── Main ─────────────────────────────────────────────────────

def run_all(reset: bool = False):
    print("\n" + "═" * 54)
    print("  SmartRx AI — Database Loader")
    print("═" * 54)

    # 1. Init schema
    print("\n[1/3] Creating schema...")
    if reset:
        from backend.models.models import Base
        Base.metadata.drop_all(bind=engine)
        print("  ↻  Existing tables dropped")
    init_db()

    # 2. Load data in dependency order
    print("\n[2/3] Loading datasets...")
    session = SessionLocal()
    try:
        load_pharmacies(session);    session.commit()
        load_medicines(session);     session.commit()
        load_inventory(session);     session.commit()
        load_patients(session);      session.commit()
        load_prescriptions(session); session.commit()
        load_transactions(session);  session.commit()
        load_weekly_demand(session); session.commit()
        load_outbreak_signals(session); session.commit()

        # 3. Seed reference data
        print("\n[3/3] Seeding reference data...")
        seed_default_users(session);  session.commit()
        seed_sample_alerts(session);  session.commit()

    except Exception as e:
        session.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        session.close()

    # 4. Summary
    print("\n" + "═" * 54)
    _print_summary()
    print("═" * 54)
    print("✅ Database ready!\n")


def _print_summary():
    """Print row counts for all tables."""
    from sqlalchemy import text
    with engine.connect() as conn:
        tables = [
            ("pharmacies",                "Pharmacies"),
            ("medicines",                 "Medicines"),
            ("inventory",                 "Inventory records"),
            ("patients",                  "Patients"),
            ("prescriptions",             "Prescriptions"),
            ("transactions",              "Transactions"),
            ("weekly_demand",             "Weekly demand records"),
            ("anomaly_events",            "Anomaly / outbreak events"),
            ("alerts",                    "Alerts"),
            ("users",                     "Users"),
        ]
        print("\n  Table                        Rows")
        print("  " + "-" * 40)
        for tbl, label in tables:
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
                print(f"  {label:<30} {n:>8,}")
            except Exception:
                print(f"  {label:<30} {'N/A':>8}")


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    run_all(reset=reset_flag)
