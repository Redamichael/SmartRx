"""
SmartRx AI — SQLAlchemy ORM Models
Supports both PostgreSQL (production) and SQLite (offline/demo)
"""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, BigInteger, SmallInteger, String, Text, Boolean,
    DateTime, Date, Time, Numeric, Float, Enum, ForeignKey, ARRAY,
    UniqueConstraint, Index, event, func, JSON
)
from sqlalchemy.orm import relationship, DeclarativeBase, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
import enum


class Base(DeclarativeBase):
    pass


# ─── Enums ────────────────────────────────────────────────────

class PharmacyType(str, enum.Enum):
    private           = "private"
    government        = "government"
    ngo               = "ngo"
    hospital_pharmacy = "hospital_pharmacy"

class StockStatus(str, enum.Enum):
    out      = "out"
    critical = "critical"
    low      = "low"
    adequate = "adequate"
    overstock = "overstock"

class ShortageRisk(str, enum.Enum):
    low      = "low"
    medium   = "medium"
    high     = "high"
    critical = "critical"

class DosageForm(str, enum.Enum):
    tablet      = "Tablet"
    capsule     = "Capsule"
    syrup       = "Syrup"
    injection   = "Injection"
    iv_bag      = "IV Bag"
    inhaler     = "Inhaler"
    eye_drop    = "Eye Drop"
    eye_oint    = "Eye Oint"
    cream       = "Cream"
    lotion      = "Lotion"
    solution    = "Solution"
    sachet      = "Sachet"
    vial        = "Vial"
    suppository = "Suppository"
    patch       = "Patch"

class StorageCondition(str, enum.Enum):
    room_temp   = "Room temperature"
    refrigerate = "Refrigerate"
    freeze      = "Freeze"
    below_25c   = "Below 25C"

class UserRole(str, enum.Enum):
    admin           = "admin"
    pharmacy_staff  = "pharmacy_staff"
    health_worker   = "health_worker"
    analyst         = "analyst"
    patient         = "patient"

class AlertType(str, enum.Enum):
    stockout        = "stockout"
    low_stock       = "low_stock"
    expiry          = "expiry"
    outbreak        = "outbreak"
    redistribution  = "redistribution"

class AlertSeverity(str, enum.Enum):
    info     = "info"
    warning  = "warning"
    critical = "critical"

class Gender(str, enum.Enum):
    M     = "M"
    F     = "F"
    other = "Other"

class NotificationChannel(str, enum.Enum):
    sms    = "sms"
    email  = "email"
    push   = "push"
    in_app = "in_app"

class NotificationStatus(str, enum.Enum):
    pending   = "pending"
    sent      = "sent"
    delivered = "delivered"
    failed    = "failed"

class RedistributionStatus(str, enum.Enum):
    suggested  = "suggested"
    approved   = "approved"
    in_transit = "in_transit"
    completed  = "completed"
    rejected   = "rejected"


# ─── Helper: JSON column that works on both PG and SQLite ─────
def JsonColumn():
    """Returns JSONB on PostgreSQL, JSON on SQLite."""
    try:
        return JSONB
    except Exception:
        return JSON


# ─────────────────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────────────────

class Region(Base):
    __tablename__ = "regions"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), nullable=False)
    name_am    = Column(String(200))
    code       = Column(String(10), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    sub_cities = relationship("SubCity", back_populates="region")

    def __repr__(self):
        return f"<Region {self.name} ({self.code})>"


class SubCity(Base):
    __tablename__ = "sub_cities"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    name      = Column(String(100), nullable=False)
    name_am   = Column(String(200))
    region_id = Column(Integer, ForeignKey("regions.id"))

    region    = relationship("Region", back_populates="sub_cities")


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String(200), nullable=False)
    name_amharic     = Column(String(300))
    sub_city         = Column(String(100))
    woreda           = Column(String(20))
    latitude         = Column(Numeric(10, 7), nullable=False)
    longitude        = Column(Numeric(10, 7), nullable=False)
    address          = Column(Text)
    phone            = Column(String(20))
    email            = Column(String(150))
    type             = Column(Enum(PharmacyType), default=PharmacyType.private, nullable=False)
    license_number   = Column(String(50), unique=True)
    region           = Column(String(100), default="Addis Ababa")
    open_24h         = Column(Boolean, default=False)
    is_active        = Column(Boolean, default=True)
    total_capacity   = Column(Integer)
    last_inspection  = Column(Date)
    facility_code    = Column(String(30))   # MoH linkage (Phase 2)
    created_at       = Column(DateTime, default=datetime.now)
    updated_at       = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # relationships
    inventory        = relationship("Inventory",     back_populates="pharmacy", cascade="all, delete-orphan")
    transactions     = relationship("Transaction",   back_populates="pharmacy")
    users            = relationship("User",          back_populates="pharmacy")
    alerts           = relationship("Alert",         back_populates="pharmacy")
    prescriptions_filled = relationship("Prescription", back_populates="filled_pharmacy",
                                        foreign_keys="Prescription.filled_pharmacy_id")
    forecasts        = relationship("Forecast",      back_populates="pharmacy")
    anomaly_events   = relationship("AnomalyEvent",  back_populates="pharmacy")

    __table_args__ = (
        Index("idx_pharmacies_location", "latitude", "longitude"),
        Index("idx_pharmacies_sub_city", "sub_city"),
        Index("idx_pharmacies_active",   "is_active"),
    )

    def distance_to(self, lat: float, lon: float) -> float:
        """Haversine distance in km."""
        import math
        R = 6371
        lat1, lon1 = math.radians(float(self.latitude)), math.radians(float(self.longitude))
        lat2, lon2 = math.radians(lat), math.radians(lon)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def __repr__(self):
        return f"<Pharmacy {self.id}: {self.name}>"


class Medicine(Base):
    __tablename__ = "medicines"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    name_english          = Column(String(200), nullable=False)
    name_amharic          = Column(String(300))          # ፓራሲታሞል
    name_amharic_alt      = Column(String(300))          # alternative spelling
    generic_name          = Column(String(300), nullable=False)
    category              = Column(String(100), nullable=False)
    atc_code              = Column(String(20))
    atc_level1            = Column(String(5))
    atc_level2            = Column(String(10))
    strength              = Column(String(50), nullable=False)
    dosage_form           = Column(Enum(DosageForm), nullable=False)
    unit_price_etb        = Column(Numeric(10, 2))
    is_essential          = Column(Boolean, default=False)
    requires_prescription = Column(Boolean, default=False)
    storage_condition     = Column(Enum(StorageCondition), default=StorageCondition.room_temp)
    shelf_life_months     = Column(Integer, default=24)
    controlled_substance  = Column(Boolean, default=False)
    is_active             = Column(Boolean, default=True)
    created_at            = Column(DateTime, default=datetime.now)
    updated_at            = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # relationships
    inventory      = relationship("Inventory",    back_populates="medicine")
    transactions   = relationship("Transaction",  back_populates="medicine")
    alerts         = relationship("Alert",        back_populates="medicine")
    forecasts      = relationship("Forecast",     back_populates="medicine")
    anomaly_events = relationship("AnomalyEvent", back_populates="medicine")
    weekly_demand  = relationship("WeeklyDemand", back_populates="medicine")

    __table_args__ = (
        Index("idx_medicines_atc",      "atc_code"),
        Index("idx_medicines_category", "category"),
        Index("idx_medicines_essential","is_essential"),
    )

    def __repr__(self):
        return f"<Medicine {self.id}: {self.name_english} | {self.name_amharic}>"


class Inventory(Base):
    __tablename__ = "inventory"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    pharmacy_id       = Column(Integer, ForeignKey("pharmacies.id", ondelete="CASCADE"), nullable=False)
    medicine_id       = Column(Integer, ForeignKey("medicines.id",  ondelete="CASCADE"), nullable=False)
    quantity          = Column(Integer, nullable=False, default=0)
    stock_status      = Column(Enum(StockStatus), nullable=False, default=StockStatus.adequate)
    reorder_point     = Column(Integer, default=20)
    reorder_quantity  = Column(Integer, default=100)
    unit_cost_etb     = Column(Numeric(10, 2))
    batch_number      = Column(String(100))
    expiry_date       = Column(Date)
    last_reorder_date = Column(Date)
    last_counted_date = Column(Date)
    avg_daily_demand  = Column(Numeric(8, 2))
    days_of_stock     = Column(Integer)
    shortage_risk     = Column(Enum(ShortageRisk), default=ShortageRisk.low)
    updated_at        = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    pharmacy = relationship("Pharmacy", back_populates="inventory")
    medicine = relationship("Medicine", back_populates="inventory")

    __table_args__ = (
        UniqueConstraint("pharmacy_id", "medicine_id", "batch_number",
                         name="uq_inventory_pharm_med_batch"),
        Index("idx_inventory_pharmacy", "pharmacy_id"),
        Index("idx_inventory_medicine", "medicine_id"),
        Index("idx_inventory_status",   "stock_status"),
        Index("idx_inventory_expiry",   "expiry_date"),
        Index("idx_inventory_risk",     "shortage_risk"),
    )

    def compute_status(self):
        """Compute stock_status from quantity & reorder_point."""
        if self.quantity == 0:
            return StockStatus.out
        elif self.quantity <= self.reorder_point * 0.5:
            return StockStatus.critical
        elif self.quantity <= self.reorder_point:
            return StockStatus.low
        elif self.quantity > self.reorder_point * 5:
            return StockStatus.overstock
        return StockStatus.adequate

    def __repr__(self):
        return f"<Inventory pharmacy={self.pharmacy_id} med={self.medicine_id} qty={self.quantity}>"


class Patient(Base):
    __tablename__ = "patients"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    name_amharic         = Column(String(300))
    name_english         = Column(String(200))
    age                  = Column(SmallInteger)
    gender               = Column(Enum(Gender))
    sub_city             = Column(String(100))
    phone                = Column(String(20), unique=True)
    email                = Column(String(150))
    has_chronic_condition = Column(Boolean, default=False)
    is_active            = Column(Boolean, default=True)
    created_at           = Column(DateTime, default=datetime.now)
    updated_at           = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    prescriptions = relationship("Prescription", back_populates="patient")
    transactions  = relationship("Transaction",  back_populates="patient")
    notifications = relationship("Notification", back_populates="patient")

    __table_args__ = (
        Index("idx_patients_phone",    "phone"),
        Index("idx_patients_sub_city", "sub_city"),
    )

    def __repr__(self):
        return f"<Patient {self.id}: {self.name_amharic}>"


class Prescription(Base):
    __tablename__ = "prescriptions"

    id                     = Column(Integer, primary_key=True, autoincrement=True)
    patient_id             = Column(Integer, ForeignKey("patients.id"))
    diagnosis_english      = Column(String(200))
    diagnosis_amharic      = Column(String(300))
    prescription_image_url = Column(Text)
    ocr_raw_text           = Column(Text)
    ai_extracted_medicines = Column(JSON)       # [{medicine_id, name, confidence, dosage}]
    extraction_confidence  = Column(Numeric(5, 4))
    extraction_model       = Column(String(50))
    primary_medicine_id    = Column(Integer, ForeignKey("medicines.id"))
    prescribing_facility   = Column(String(200))
    prescribing_doctor     = Column(String(200))
    prescribed_date        = Column(Date)
    valid_until            = Column(Date)
    filled                 = Column(Boolean, default=False)
    filled_at              = Column(DateTime)
    filled_pharmacy_id     = Column(Integer, ForeignKey("pharmacies.id"))
    language_detected      = Column(String(20), default="amharic")
    created_at             = Column(DateTime, default=datetime.now)
    updated_at             = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    patient          = relationship("Patient",  back_populates="prescriptions")
    filled_pharmacy  = relationship("Pharmacy", back_populates="prescriptions_filled",
                                    foreign_keys=[filled_pharmacy_id])
    transactions     = relationship("Transaction", back_populates="prescription")

    __table_args__ = (
        Index("idx_prescriptions_patient", "patient_id"),
        Index("idx_prescriptions_filled",  "filled"),
        Index("idx_prescriptions_date",    "prescribed_date"),
    )

    def __repr__(self):
        return f"<Prescription {self.id}: {self.diagnosis_english}>"


class User(Base):
    __tablename__ = "users"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    username             = Column(String(100), unique=True, nullable=False)
    email                = Column(String(150), unique=True, nullable=False)
    password_hash        = Column(String(255), nullable=False)
    full_name            = Column(String(200))
    full_name_am         = Column(String(300))
    role                 = Column(Enum(UserRole), nullable=False, default=UserRole.patient)
    pharmacy_id          = Column(Integer, ForeignKey("pharmacies.id"))
    phone                = Column(String(20))
    is_active            = Column(Boolean, default=True)
    is_verified          = Column(Boolean, default=False)
    last_login           = Column(DateTime)
    offline_token        = Column(String(500))
    offline_token_expires = Column(DateTime)
    refresh_token        = Column(String(500))
    created_at           = Column(DateTime, default=datetime.now)
    updated_at           = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    pharmacy      = relationship("Pharmacy", back_populates="users")
    notifications = relationship("Notification", back_populates="user")

    __table_args__ = (
        Index("idx_users_email",   "email"),
        Index("idx_users_role",    "role"),
        Index("idx_users_pharmacy","pharmacy_id"),
    )

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Transaction(Base):
    __tablename__ = "transactions"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    pharmacy_id         = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    medicine_id         = Column(Integer, ForeignKey("medicines.id"),  nullable=False)
    patient_id          = Column(Integer, ForeignKey("patients.id"))
    prescription_id     = Column(Integer, ForeignKey("prescriptions.id"))
    quantity_dispensed  = Column(Integer, nullable=False)
    unit_price_etb      = Column(Numeric(10, 2))
    total_price_etb     = Column(Numeric(10, 2))
    transaction_date    = Column(Date, nullable=False, default=date.today)
    month               = Column(SmallInteger)
    year                = Column(SmallInteger)
    day_of_week         = Column(SmallInteger)
    is_weekend          = Column(Boolean)
    prescription_required = Column(Boolean, default=False)
    dispensed_by        = Column(Integer, ForeignKey("users.id"))
    notes               = Column(Text)
    created_at          = Column(DateTime, default=datetime.now)

    pharmacy     = relationship("Pharmacy",     back_populates="transactions")
    medicine     = relationship("Medicine",     back_populates="transactions")
    patient      = relationship("Patient",      back_populates="transactions")
    prescription = relationship("Prescription", back_populates="transactions")

    __table_args__ = (
        Index("idx_transactions_date",       "transaction_date"),
        Index("idx_transactions_pharmacy",   "pharmacy_id", "transaction_date"),
        Index("idx_transactions_medicine",   "medicine_id",  "transaction_date"),
        Index("idx_transactions_pharm_med",  "pharmacy_id", "medicine_id", "transaction_date"),
        Index("idx_transactions_month_year", "year", "month"),
    )

    def __repr__(self):
        return f"<Transaction {self.id}: pharm={self.pharmacy_id} med={self.medicine_id} qty={self.quantity_dispensed}>"


class WeeklyDemand(Base):
    __tablename__ = "weekly_demand"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    pharmacy_id      = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    medicine_id      = Column(Integer, ForeignKey("medicines.id"),  nullable=False)
    year             = Column(SmallInteger, nullable=False)
    week             = Column(SmallInteger, nullable=False)
    total_dispensed  = Column(Integer, nullable=False, default=0)
    avg_daily        = Column(Numeric(8, 2))
    days_recorded    = Column(SmallInteger)
    shortage_risk    = Column(Enum(ShortageRisk), default=ShortageRisk.low)
    prev_week_qty    = Column(Integer)
    prev_2week_qty   = Column(Integer)
    prev_4week_qty   = Column(Integer)
    rolling_4wk_avg  = Column(Numeric(8, 2))
    is_outbreak_week = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=datetime.now)

    pharmacy = relationship("Pharmacy")
    medicine = relationship("Medicine", back_populates="weekly_demand")

    __table_args__ = (
        UniqueConstraint("pharmacy_id", "medicine_id", "year", "week",
                         name="uq_weekly_demand"),
        Index("idx_weekly_demand_pharm_med", "pharmacy_id", "medicine_id"),
        Index("idx_weekly_demand_risk",      "shortage_risk"),
        Index("idx_weekly_demand_week",      "year", "week"),
    )

    def __repr__(self):
        return f"<WeeklyDemand pharm={self.pharmacy_id} med={self.medicine_id} w{self.week}/{self.year}>"


class Forecast(Base):
    __tablename__ = "forecasts"

    id                 = Column(BigInteger, primary_key=True, autoincrement=True)
    pharmacy_id        = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    medicine_id        = Column(Integer, ForeignKey("medicines.id"),  nullable=False)
    forecast_date      = Column(Date, nullable=False)
    target_date        = Column(Date, nullable=False)
    horizon_days       = Column(SmallInteger, nullable=False)
    predicted_demand   = Column(Numeric(10, 2), nullable=False)
    confidence_lower   = Column(Numeric(10, 2))
    confidence_upper   = Column(Numeric(10, 2))
    predicted_risk     = Column(Enum(ShortageRisk), default=ShortageRisk.low)
    model_version      = Column(String(50))
    model_accuracy_mae = Column(Numeric(8, 4))
    created_at         = Column(DateTime, default=datetime.now)

    pharmacy = relationship("Pharmacy", back_populates="forecasts")
    medicine = relationship("Medicine", back_populates="forecasts")

    __table_args__ = (
        UniqueConstraint("pharmacy_id", "medicine_id", "forecast_date", "target_date",
                         name="uq_forecast"),
        Index("idx_forecasts_pharmacy", "pharmacy_id", "target_date"),
        Index("idx_forecasts_medicine", "medicine_id", "target_date"),
        Index("idx_forecasts_risk",     "predicted_risk", "target_date"),
    )


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    pharmacy_id      = Column(Integer, ForeignKey("pharmacies.id"))
    medicine_id      = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    detected_at      = Column(DateTime, nullable=False, default=datetime.now)
    event_date       = Column(Date, nullable=False)
    anomaly_score    = Column(Numeric(8, 4), nullable=False)
    threshold        = Column(Numeric(8, 4), nullable=False)
    spike_magnitude  = Column(Numeric(8, 2))
    baseline_demand  = Column(Numeric(8, 2))
    observed_demand  = Column(Numeric(8, 2))
    is_outbreak      = Column(Boolean, default=False)
    event_name       = Column(String(200))
    affected_region  = Column(String(100))
    model_version    = Column(String(50))
    resolved_at      = Column(DateTime)
    notes            = Column(Text)
    created_at       = Column(DateTime, default=datetime.now)

    pharmacy = relationship("Pharmacy", back_populates="anomaly_events")
    medicine = relationship("Medicine", back_populates="anomaly_events")

    __table_args__ = (
        Index("idx_anomaly_medicine", "medicine_id", "event_date"),
        Index("idx_anomaly_outbreak", "is_outbreak", "event_date"),
        Index("idx_anomaly_region",   "affected_region"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_type       = Column(Enum(AlertType), nullable=False)
    severity         = Column(Enum(AlertSeverity), nullable=False, default=AlertSeverity.warning)
    pharmacy_id      = Column(Integer, ForeignKey("pharmacies.id"))
    medicine_id      = Column(Integer, ForeignKey("medicines.id"))
    anomaly_id       = Column(BigInteger, ForeignKey("anomaly_events.id"))
    forecast_id      = Column(BigInteger, ForeignKey("forecasts.id"))
    title            = Column(String(300), nullable=False)
    title_amharic    = Column(String(400))
    message          = Column(Text)
    message_amharic  = Column(Text)
    metadata         = Column(JSON)
    is_read          = Column(Boolean, default=False)
    is_resolved      = Column(Boolean, default=False)
    resolved_by      = Column(Integer, ForeignKey("users.id"))
    resolved_at      = Column(DateTime)
    expires_at       = Column(DateTime)
    created_at       = Column(DateTime, default=datetime.now)

    pharmacy = relationship("Pharmacy", back_populates="alerts")
    medicine = relationship("Medicine", back_populates="alerts")

    __table_args__ = (
        Index("idx_alerts_pharmacy", "pharmacy_id", "is_resolved"),
        Index("idx_alerts_type",     "alert_type", "severity"),
        Index("idx_alerts_unread",   "is_read", "is_resolved"),
        Index("idx_alerts_created",  "created_at"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_id         = Column(BigInteger, ForeignKey("alerts.id"))
    user_id          = Column(Integer, ForeignKey("users.id"))
    patient_id       = Column(Integer, ForeignKey("patients.id"))
    channel          = Column(Enum(NotificationChannel), nullable=False)
    recipient        = Column(String(200), nullable=False)
    message          = Column(Text, nullable=False)
    message_amharic  = Column(Text)
    status           = Column(Enum(NotificationStatus), default=NotificationStatus.pending)
    provider         = Column(String(50))
    provider_msg_id  = Column(String(200))
    sent_at          = Column(DateTime)
    delivered_at     = Column(DateTime)
    failed_reason    = Column(Text)
    retry_count      = Column(SmallInteger, default=0)
    created_at       = Column(DateTime, default=datetime.now)

    user    = relationship("User",    back_populates="notifications")
    patient = relationship("Patient", back_populates="notifications")

    __table_args__ = (
        Index("idx_notifications_user",    "user_id", "created_at"),
        Index("idx_notifications_status",  "status"),
        Index("idx_notifications_channel", "channel"),
    )


class RedistributionSuggestion(Base):
    __tablename__ = "redistribution_suggestions"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    medicine_id         = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    source_pharmacy_id  = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    target_pharmacy_id  = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    suggested_quantity  = Column(Integer, nullable=False)
    approved_quantity   = Column(Integer)
    rationale           = Column(Text)
    urgency_score       = Column(Numeric(5, 2))
    distance_km         = Column(Numeric(8, 2))
    status              = Column(Enum(RedistributionStatus), default=RedistributionStatus.suggested)
    suggested_by        = Column(String(50), default="ai_engine")
    approved_by         = Column(Integer, ForeignKey("users.id"))
    approved_at         = Column(DateTime)
    completed_at        = Column(DateTime)
    forecast_id         = Column(BigInteger, ForeignKey("forecasts.id"))
    created_at          = Column(DateTime, default=datetime.now)

    medicine        = relationship("Medicine")
    source_pharmacy = relationship("Pharmacy", foreign_keys=[source_pharmacy_id])
    target_pharmacy = relationship("Pharmacy", foreign_keys=[target_pharmacy_id])

    __table_args__ = (
        Index("idx_redistrib_medicine", "medicine_id", "status"),
        Index("idx_redistrib_source",   "source_pharmacy_id"),
        Index("idx_redistrib_target",   "target_pharmacy_id"),
    )


class OfflineSyncLog(Base):
    __tablename__ = "offline_sync_log"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id"))
    pharmacy_id      = Column(Integer, ForeignKey("pharmacies.id"))
    device_id        = Column(String(100))
    table_name       = Column(String(100), nullable=False)
    record_id        = Column(BigInteger)
    operation        = Column(String(10), nullable=False)
    payload          = Column(JSON, nullable=False)
    synced           = Column(Boolean, default=False)
    conflict         = Column(Boolean, default=False)
    conflict_reason  = Column(Text)
    client_timestamp = Column(DateTime)
    server_timestamp = Column(DateTime, default=datetime.now)
    created_at       = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_offline_sync_user",    "user_id",    "synced"),
        Index("idx_offline_sync_pharmacy","pharmacy_id","synced"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id"))
    action     = Column(String(100), nullable=False)
    table_name = Column(String(100))
    record_id  = Column(BigInteger)
    old_values = Column(JSON)
    new_values = Column(JSON)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_audit_user",  "user_id", "created_at"),
        Index("idx_audit_table", "table_name", "record_id"),
    )


# ─── All models list (for imports elsewhere) ──────────────────
__all__ = [
    "Base", "Region", "SubCity", "Pharmacy", "Medicine",
    "Inventory", "Patient", "Prescription", "User",
    "Transaction", "WeeklyDemand", "Forecast",
    "AnomalyEvent", "Alert", "Notification",
    "RedistributionSuggestion", "OfflineSyncLog", "AuditLog",
    # Enums
    "PharmacyType", "StockStatus", "ShortageRisk", "DosageForm",
    "StorageCondition", "UserRole", "AlertType", "AlertSeverity",
    "Gender", "NotificationChannel", "NotificationStatus",
    "RedistributionStatus",
]
