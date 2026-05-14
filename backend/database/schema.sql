-- =============================================================
-- SmartRx AI — PostgreSQL Database Schema
-- Version: 1.0.0
-- Description: AI Decision Intelligence Layer for Ethiopia's
--              Digital Health Ecosystem
-- =============================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- fuzzy text search (medicine names)
CREATE EXTENSION IF NOT EXISTS "unaccent";       -- accent-insensitive search

-- =============================================================
-- ENUM TYPES
-- =============================================================

CREATE TYPE pharmacy_type        AS ENUM ('private', 'government', 'ngo', 'hospital_pharmacy');
CREATE TYPE stock_status         AS ENUM ('out', 'critical', 'low', 'adequate', 'overstock');
CREATE TYPE shortage_risk        AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE dosage_form          AS ENUM (
    'Tablet', 'Capsule', 'Syrup', 'Injection', 'IV Bag',
    'Inhaler', 'Eye Drop', 'Eye Oint', 'Cream', 'Lotion',
    'Solution', 'Sachet', 'Vial', 'Suppository', 'Patch'
);
CREATE TYPE storage_condition    AS ENUM ('Room temperature', 'Refrigerate', 'Freeze', 'Below 25C');
CREATE TYPE user_role            AS ENUM ('admin', 'pharmacy_staff', 'health_worker', 'analyst', 'patient');
CREATE TYPE alert_type           AS ENUM ('stockout', 'low_stock', 'expiry', 'outbreak', 'redistribution');
CREATE TYPE alert_severity       AS ENUM ('info', 'warning', 'critical');
CREATE TYPE gender               AS ENUM ('M', 'F', 'Other');
CREATE TYPE notification_channel AS ENUM ('sms', 'email', 'push', 'in_app');
CREATE TYPE notification_status  AS ENUM ('pending', 'sent', 'delivered', 'failed');
CREATE TYPE redistribution_status AS ENUM ('suggested', 'approved', 'in_transit', 'completed', 'rejected');

-- =============================================================
-- 1. REGIONS & LOCATIONS  (lookup tables)
-- =============================================================

CREATE TABLE regions (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    name_am     VARCHAR(200),                -- Amharic name
    code        VARCHAR(10) UNIQUE NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sub_cities (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    name_am     VARCHAR(200),
    region_id   INT REFERENCES regions(id),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- =============================================================
-- 2. PHARMACIES
-- =============================================================

CREATE TABLE pharmacies (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(200)   NOT NULL,
    name_amharic     VARCHAR(300),
    sub_city         VARCHAR(100),
    woreda           VARCHAR(20),
    latitude         DECIMAL(10,7)  NOT NULL,
    longitude        DECIMAL(10,7)  NOT NULL,
    address          TEXT,
    phone            VARCHAR(20),
    email            VARCHAR(150),
    type             pharmacy_type  NOT NULL DEFAULT 'private',
    license_number   VARCHAR(50)    UNIQUE,
    region           VARCHAR(100)   DEFAULT 'Addis Ababa',
    open_24h         BOOLEAN        DEFAULT FALSE,
    is_active        BOOLEAN        DEFAULT TRUE,
    -- operational metadata
    total_capacity   INT,           -- max stock units
    last_inspection  DATE,
    facility_code    VARCHAR(30),   -- eAPTS / MoH facility code (Phase 2 linkage)
    created_at       TIMESTAMP      DEFAULT NOW(),
    updated_at       TIMESTAMP      DEFAULT NOW()
);

-- Spatial index for pharmacy proximity queries
CREATE INDEX idx_pharmacies_location ON pharmacies (latitude, longitude);
CREATE INDEX idx_pharmacies_sub_city ON pharmacies (sub_city);
CREATE INDEX idx_pharmacies_active   ON pharmacies (is_active);

-- =============================================================
-- 3. MEDICINES
-- =============================================================

CREATE TABLE medicines (
    id                     SERIAL PRIMARY KEY,
    name_english           VARCHAR(200) NOT NULL,
    name_amharic           VARCHAR(300),          -- ፓራሲታሞል etc.
    name_amharic_alt       VARCHAR(300),          -- alternative Amharic spelling
    generic_name           VARCHAR(300) NOT NULL,
    brand_names            TEXT[],                -- array of known brands
    category               VARCHAR(100) NOT NULL,
    atc_code               VARCHAR(20),           -- WHO ATC classification
    strength               VARCHAR(50)  NOT NULL,
    dosage_form            dosage_form  NOT NULL,
    unit_price_etb         DECIMAL(10,2),
    is_essential           BOOLEAN      DEFAULT FALSE,  -- WHO/MoH essential list
    requires_prescription  BOOLEAN      DEFAULT FALSE,
    storage_condition      storage_condition DEFAULT 'Room temperature',
    shelf_life_months      INT          DEFAULT 24,
    -- drug properties (for knowledge graph — Phase 2)
    atc_level1             VARCHAR(5),            -- e.g. 'N' (Nervous system)
    atc_level2             VARCHAR(10),           -- e.g. 'N02' (Analgesics)
    controlled_substance   BOOLEAN      DEFAULT FALSE,
    is_active              BOOLEAN      DEFAULT TRUE,
    created_at             TIMESTAMP    DEFAULT NOW(),
    updated_at             TIMESTAMP    DEFAULT NOW()
);

-- Full-text + trigram search on both English and Amharic names
CREATE INDEX idx_medicines_name_trgm ON medicines USING GIN (name_english gin_trgm_ops);
CREATE INDEX idx_medicines_atc       ON medicines (atc_code);
CREATE INDEX idx_medicines_category  ON medicines (category);
CREATE INDEX idx_medicines_essential ON medicines (is_essential);

-- =============================================================
-- 4. INVENTORY  (pharmacy ↔ medicine stock)
-- =============================================================

CREATE TABLE inventory (
    id                SERIAL PRIMARY KEY,
    pharmacy_id       INT          NOT NULL REFERENCES pharmacies(id) ON DELETE CASCADE,
    medicine_id       INT          NOT NULL REFERENCES medicines(id)  ON DELETE CASCADE,
    quantity          INT          NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    stock_status      stock_status NOT NULL DEFAULT 'adequate',
    reorder_point     INT          DEFAULT 20,
    reorder_quantity  INT          DEFAULT 100,    -- recommended order qty
    unit_cost_etb     DECIMAL(10,2),              -- purchase cost (vs retail price)
    batch_number      VARCHAR(100),
    expiry_date       DATE,
    last_reorder_date DATE,
    last_counted_date DATE,                       -- physical stock-count date
    -- computed / ML fields
    avg_daily_demand  DECIMAL(8,2),               -- rolling 30-day average
    days_of_stock     INT,                        -- qty / avg_daily_demand
    shortage_risk     shortage_risk DEFAULT 'low',
    updated_at        TIMESTAMP    DEFAULT NOW(),
    UNIQUE (pharmacy_id, medicine_id, batch_number)
);

CREATE INDEX idx_inventory_pharmacy    ON inventory (pharmacy_id);
CREATE INDEX idx_inventory_medicine    ON inventory (medicine_id);
CREATE INDEX idx_inventory_status      ON inventory (stock_status);
CREATE INDEX idx_inventory_expiry      ON inventory (expiry_date);
CREATE INDEX idx_inventory_risk        ON inventory (shortage_risk);

-- =============================================================
-- 5. TRANSACTIONS  (dispensing log — core time-series)
-- =============================================================

CREATE TABLE transactions (
    id                  BIGSERIAL    PRIMARY KEY,
    pharmacy_id         INT          NOT NULL REFERENCES pharmacies(id),
    medicine_id         INT          NOT NULL REFERENCES medicines(id),
    patient_id          INT          REFERENCES patients(id),   -- nullable (anonymous)
    prescription_id     INT          REFERENCES prescriptions(id),
    quantity_dispensed  INT          NOT NULL CHECK (quantity_dispensed > 0),
    unit_price_etb      DECIMAL(10,2),
    total_price_etb     DECIMAL(10,2),
    transaction_date    DATE         NOT NULL DEFAULT CURRENT_DATE,
    transaction_time    TIME         DEFAULT CURRENT_TIME,
    month               SMALLINT     GENERATED ALWAYS AS (EXTRACT(MONTH FROM transaction_date)::SMALLINT) STORED,
    year                SMALLINT     GENERATED ALWAYS AS (EXTRACT(YEAR  FROM transaction_date)::SMALLINT) STORED,
    day_of_week         SMALLINT     GENERATED ALWAYS AS (EXTRACT(DOW   FROM transaction_date)::SMALLINT) STORED,
    is_weekend          BOOLEAN      GENERATED ALWAYS AS (EXTRACT(DOW FROM transaction_date) IN (0,6)) STORED,
    prescription_required BOOLEAN    DEFAULT FALSE,
    dispensed_by        INT          REFERENCES users(id),
    notes               TEXT,
    created_at          TIMESTAMP    DEFAULT NOW()
);

-- Time-series indexes (critical for LSTM queries)
CREATE INDEX idx_transactions_date        ON transactions (transaction_date DESC);
CREATE INDEX idx_transactions_pharmacy    ON transactions (pharmacy_id, transaction_date DESC);
CREATE INDEX idx_transactions_medicine    ON transactions (medicine_id, transaction_date DESC);
CREATE INDEX idx_transactions_pharm_med   ON transactions (pharmacy_id, medicine_id, transaction_date DESC);
CREATE INDEX idx_transactions_month_year  ON transactions (year, month);

-- =============================================================
-- 6. PATIENTS
-- =============================================================

CREATE TABLE patients (
    id                   SERIAL PRIMARY KEY,
    name_amharic         VARCHAR(300),
    name_english         VARCHAR(200),
    age                  SMALLINT     CHECK (age BETWEEN 0 AND 130),
    gender               gender,
    sub_city             VARCHAR(100),
    phone                VARCHAR(20)  UNIQUE,
    email                VARCHAR(150),
    has_chronic_condition BOOLEAN     DEFAULT FALSE,
    -- privacy: no national ID stored in Phase 1
    -- eRIS linkage in Phase 2
    is_active            BOOLEAN      DEFAULT TRUE,
    created_at           TIMESTAMP    DEFAULT NOW(),
    updated_at           TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX idx_patients_phone    ON patients (phone);
CREATE INDEX idx_patients_sub_city ON patients (sub_city);

-- =============================================================
-- 7. PRESCRIPTIONS
-- =============================================================

CREATE TABLE prescriptions (
    id                     SERIAL PRIMARY KEY,
    patient_id             INT         REFERENCES patients(id),
    diagnosis_english      VARCHAR(200),
    diagnosis_amharic      VARCHAR(300),
    -- scanned prescription data (from OCR AI module)
    prescription_image_url TEXT,
    ocr_raw_text           TEXT,        -- raw Tesseract output
    ai_extracted_medicines JSONB,       -- [{medicine_id, name, confidence, dosage}]
    extraction_confidence  DECIMAL(5,4), -- 0.0 – 1.0
    extraction_model       VARCHAR(50),  -- 'gemini-pro', 'whisper', etc.
    -- prescription details
    primary_medicine_id    INT         REFERENCES medicines(id),
    additional_medicine_ids INT[],
    prescribing_facility   VARCHAR(200),
    prescribing_doctor     VARCHAR(200),
    prescribed_date        DATE,
    valid_until            DATE,
    filled                 BOOLEAN      DEFAULT FALSE,
    filled_at              TIMESTAMP,
    filled_pharmacy_id     INT         REFERENCES pharmacies(id),
    -- Amharic support
    language_detected      VARCHAR(20)  DEFAULT 'amharic',
    created_at             TIMESTAMP    DEFAULT NOW(),
    updated_at             TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX idx_prescriptions_patient   ON prescriptions (patient_id);
CREATE INDEX idx_prescriptions_filled    ON prescriptions (filled);
CREATE INDEX idx_prescriptions_date      ON prescriptions (prescribed_date DESC);
CREATE INDEX idx_prescriptions_ai_data   ON prescriptions USING GIN (ai_extracted_medicines);

-- =============================================================
-- 8. USERS & AUTHENTICATION
-- =============================================================

CREATE TABLE users (
    id               SERIAL PRIMARY KEY,
    username         VARCHAR(100) UNIQUE NOT NULL,
    email            VARCHAR(150) UNIQUE NOT NULL,
    password_hash    VARCHAR(255) NOT NULL,
    full_name        VARCHAR(200),
    full_name_am     VARCHAR(300),       -- Amharic name
    role             user_role    NOT NULL DEFAULT 'patient',
    pharmacy_id      INT          REFERENCES pharmacies(id),  -- for pharmacy_staff
    phone            VARCHAR(20),
    is_active        BOOLEAN      DEFAULT TRUE,
    is_verified      BOOLEAN      DEFAULT FALSE,
    last_login       TIMESTAMP,
    -- offline support token
    offline_token    VARCHAR(500),
    offline_token_expires TIMESTAMP,
    -- JWT / session
    refresh_token    VARCHAR(500),
    created_at       TIMESTAMP    DEFAULT NOW(),
    updated_at       TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX idx_users_email      ON users (email);
CREATE INDEX idx_users_role       ON users (role);
CREATE INDEX idx_users_pharmacy   ON users (pharmacy_id);

-- =============================================================
-- 9. WEEKLY DEMAND AGGREGATES  (pre-computed for LSTM)
-- =============================================================

CREATE TABLE weekly_demand (
    id               BIGSERIAL    PRIMARY KEY,
    pharmacy_id      INT          NOT NULL REFERENCES pharmacies(id),
    medicine_id      INT          NOT NULL REFERENCES medicines(id),
    year             SMALLINT     NOT NULL,
    week             SMALLINT     NOT NULL,   -- ISO week 1-53
    total_dispensed  INT          NOT NULL DEFAULT 0,
    avg_daily        DECIMAL(8,2),
    days_recorded    SMALLINT,
    -- ML label
    shortage_risk    shortage_risk DEFAULT 'low',
    -- LSTM feature columns
    prev_week_qty    INT,         -- lag-1
    prev_2week_qty   INT,         -- lag-2
    prev_4week_qty   INT,         -- lag-4 (monthly)
    rolling_4wk_avg  DECIMAL(8,2),
    is_outbreak_week BOOLEAN      DEFAULT FALSE,
    created_at       TIMESTAMP    DEFAULT NOW(),
    UNIQUE (pharmacy_id, medicine_id, year, week)
);

CREATE INDEX idx_weekly_demand_pharm_med ON weekly_demand (pharmacy_id, medicine_id);
CREATE INDEX idx_weekly_demand_risk      ON weekly_demand (shortage_risk);
CREATE INDEX idx_weekly_demand_week      ON weekly_demand (year, week);

-- =============================================================
-- 10. ML FORECASTS  (LSTM output store)
-- =============================================================

CREATE TABLE forecasts (
    id                   BIGSERIAL    PRIMARY KEY,
    pharmacy_id          INT          NOT NULL REFERENCES pharmacies(id),
    medicine_id          INT          NOT NULL REFERENCES medicines(id),
    forecast_date        DATE         NOT NULL,   -- date prediction was generated
    target_date          DATE         NOT NULL,   -- date being predicted
    horizon_days         SMALLINT     NOT NULL,   -- 3, 7, 14, 30
    predicted_demand     DECIMAL(10,2) NOT NULL,
    confidence_lower     DECIMAL(10,2),
    confidence_upper     DECIMAL(10,2),
    predicted_risk       shortage_risk DEFAULT 'low',
    model_version        VARCHAR(50),
    model_accuracy_mae   DECIMAL(8,4), -- Mean Absolute Error on validation set
    created_at           TIMESTAMP    DEFAULT NOW(),
    UNIQUE (pharmacy_id, medicine_id, forecast_date, target_date)
);

CREATE INDEX idx_forecasts_pharmacy    ON forecasts (pharmacy_id, target_date);
CREATE INDEX idx_forecasts_medicine    ON forecasts (medicine_id, target_date);
CREATE INDEX idx_forecasts_risk        ON forecasts (predicted_risk, target_date);

-- =============================================================
-- 11. ANOMALY DETECTION  (Autoencoder alerts)
-- =============================================================

CREATE TABLE anomaly_events (
    id                BIGSERIAL    PRIMARY KEY,
    pharmacy_id       INT          REFERENCES pharmacies(id),  -- NULL = system-wide
    medicine_id       INT          NOT NULL REFERENCES medicines(id),
    detected_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    event_date        DATE         NOT NULL,
    anomaly_score     DECIMAL(8,4) NOT NULL,  -- reconstruction error
    threshold         DECIMAL(8,4) NOT NULL,
    spike_magnitude   DECIMAL(8,2),           -- % above baseline
    baseline_demand   DECIMAL(8,2),
    observed_demand   DECIMAL(8,2),
    is_outbreak       BOOLEAN      DEFAULT FALSE,
    event_name        VARCHAR(200),           -- e.g. 'Diarrhea_Bole_Jul2024'
    affected_region   VARCHAR(100),
    model_version     VARCHAR(50),
    resolved_at       TIMESTAMP,
    notes             TEXT,
    created_at        TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX idx_anomaly_medicine  ON anomaly_events (medicine_id, event_date DESC);
CREATE INDEX idx_anomaly_outbreak  ON anomaly_events (is_outbreak, event_date DESC);
CREATE INDEX idx_anomaly_region    ON anomaly_events (affected_region);

-- =============================================================
-- 12. ALERTS  (system-wide alert queue)
-- =============================================================

CREATE TABLE alerts (
    id               BIGSERIAL      PRIMARY KEY,
    alert_type       alert_type     NOT NULL,
    severity         alert_severity NOT NULL DEFAULT 'warning',
    pharmacy_id      INT            REFERENCES pharmacies(id),
    medicine_id      INT            REFERENCES medicines(id),
    anomaly_id       BIGINT         REFERENCES anomaly_events(id),
    forecast_id      BIGINT         REFERENCES forecasts(id),
    title            VARCHAR(300)   NOT NULL,
    title_amharic    VARCHAR(400),
    message          TEXT,
    message_amharic  TEXT,
    metadata         JSONB,          -- flexible extra data
    is_read          BOOLEAN        DEFAULT FALSE,
    is_resolved      BOOLEAN        DEFAULT FALSE,
    resolved_by      INT            REFERENCES users(id),
    resolved_at      TIMESTAMP,
    expires_at       TIMESTAMP,
    created_at       TIMESTAMP      DEFAULT NOW()
);

CREATE INDEX idx_alerts_pharmacy   ON alerts (pharmacy_id, is_resolved);
CREATE INDEX idx_alerts_type       ON alerts (alert_type, severity);
CREATE INDEX idx_alerts_unread     ON alerts (is_read, is_resolved);
CREATE INDEX idx_alerts_created    ON alerts (created_at DESC);

-- =============================================================
-- 13. NOTIFICATIONS  (SMS / Email / Push delivery log)
-- =============================================================

CREATE TABLE notifications (
    id               BIGSERIAL          PRIMARY KEY,
    alert_id         BIGINT             REFERENCES alerts(id),
    user_id          INT                REFERENCES users(id),
    patient_id       INT                REFERENCES patients(id),
    channel          notification_channel NOT NULL,
    recipient        VARCHAR(200)       NOT NULL,  -- phone / email
    message          TEXT               NOT NULL,
    message_amharic  TEXT,
    status           notification_status DEFAULT 'pending',
    provider         VARCHAR(50),                  -- 'africas_talking', 'sendgrid'
    provider_msg_id  VARCHAR(200),
    sent_at          TIMESTAMP,
    delivered_at     TIMESTAMP,
    failed_reason    TEXT,
    retry_count      SMALLINT           DEFAULT 0,
    created_at       TIMESTAMP          DEFAULT NOW()
);

CREATE INDEX idx_notifications_user    ON notifications (user_id, created_at DESC);
CREATE INDEX idx_notifications_status  ON notifications (status);
CREATE INDEX idx_notifications_channel ON notifications (channel);

-- =============================================================
-- 14. REDISTRIBUTION SUGGESTIONS  (Decision Intelligence Engine)
-- =============================================================

CREATE TABLE redistribution_suggestions (
    id                   BIGSERIAL            PRIMARY KEY,
    medicine_id          INT                  NOT NULL REFERENCES medicines(id),
    source_pharmacy_id   INT                  NOT NULL REFERENCES pharmacies(id),
    target_pharmacy_id   INT                  NOT NULL REFERENCES pharmacies(id),
    suggested_quantity   INT                  NOT NULL,
    approved_quantity    INT,
    rationale            TEXT,                -- AI explanation
    urgency_score        DECIMAL(5,2),        -- 0-100
    distance_km          DECIMAL(8,2),
    status               redistribution_status DEFAULT 'suggested',
    suggested_by         VARCHAR(50)          DEFAULT 'ai_engine',
    approved_by          INT                  REFERENCES users(id),
    approved_at          TIMESTAMP,
    completed_at         TIMESTAMP,
    forecast_id          BIGINT               REFERENCES forecasts(id),
    created_at           TIMESTAMP            DEFAULT NOW()
);

CREATE INDEX idx_redistrib_medicine  ON redistribution_suggestions (medicine_id, status);
CREATE INDEX idx_redistrib_source    ON redistribution_suggestions (source_pharmacy_id);
CREATE INDEX idx_redistrib_target    ON redistribution_suggestions (target_pharmacy_id);

-- =============================================================
-- 15. OFFLINE SYNC LOG  (for offline-first support)
-- =============================================================

CREATE TABLE offline_sync_log (
    id               BIGSERIAL    PRIMARY KEY,
    user_id          INT          REFERENCES users(id),
    pharmacy_id      INT          REFERENCES pharmacies(id),
    device_id        VARCHAR(100),
    table_name       VARCHAR(100) NOT NULL,
    record_id        BIGINT,
    operation        VARCHAR(10)  NOT NULL,   -- 'INSERT','UPDATE','DELETE'
    payload          JSONB        NOT NULL,
    synced           BOOLEAN      DEFAULT FALSE,
    conflict         BOOLEAN      DEFAULT FALSE,
    conflict_reason  TEXT,
    client_timestamp TIMESTAMP,
    server_timestamp TIMESTAMP    DEFAULT NOW(),
    created_at       TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX idx_offline_sync_user    ON offline_sync_log (user_id, synced);
CREATE INDEX idx_offline_sync_pharmacy ON offline_sync_log (pharmacy_id, synced);

-- =============================================================
-- 16. AUDIT LOG
-- =============================================================

CREATE TABLE audit_log (
    id           BIGSERIAL    PRIMARY KEY,
    user_id      INT          REFERENCES users(id),
    action       VARCHAR(100) NOT NULL,
    table_name   VARCHAR(100),
    record_id    BIGINT,
    old_values   JSONB,
    new_values   JSONB,
    ip_address   VARCHAR(45),
    user_agent   TEXT,
    created_at   TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX idx_audit_user    ON audit_log (user_id, created_at DESC);
CREATE INDEX idx_audit_table   ON audit_log (table_name, record_id);

-- =============================================================
-- VIEWS  (pre-built for dashboard queries)
-- =============================================================

-- Stock overview per pharmacy
CREATE VIEW v_stock_overview AS
SELECT
    p.id          AS pharmacy_id,
    p.name        AS pharmacy_name,
    p.name_amharic,
    p.sub_city,
    p.latitude,
    p.longitude,
    COUNT(*)                                                   AS total_medicines,
    COUNT(*) FILTER (WHERE i.stock_status = 'out')            AS stockout_count,
    COUNT(*) FILTER (WHERE i.stock_status = 'critical')       AS critical_count,
    COUNT(*) FILTER (WHERE i.stock_status = 'low')            AS low_count,
    COUNT(*) FILTER (WHERE i.stock_status = 'adequate')       AS adequate_count,
    COUNT(*) FILTER (WHERE i.expiry_date < NOW() + INTERVAL '90 days') AS expiring_soon,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE i.stock_status IN ('adequate','overstock'))
        / NULLIF(COUNT(*), 0), 1
    )                                                          AS availability_pct
FROM pharmacies p
LEFT JOIN inventory i ON p.id = i.pharmacy_id
WHERE p.is_active = TRUE
GROUP BY p.id, p.name, p.name_amharic, p.sub_city, p.latitude, p.longitude;

-- Medicine availability across all pharmacies
CREATE VIEW v_medicine_availability AS
SELECT
    m.id          AS medicine_id,
    m.name_english,
    m.name_amharic,
    m.category,
    m.atc_code,
    m.is_essential,
    COUNT(DISTINCT i.pharmacy_id)                             AS pharmacies_stocking,
    SUM(i.quantity)                                           AS total_units_available,
    COUNT(*) FILTER (WHERE i.stock_status = 'out')            AS stockout_pharmacies,
    COUNT(*) FILTER (WHERE i.stock_status IN ('critical','low')) AS low_stock_pharmacies,
    MAX(f.predicted_risk)                                     AS max_forecast_risk
FROM medicines m
LEFT JOIN inventory i  ON m.id = i.medicine_id
LEFT JOIN forecasts f  ON m.id = f.medicine_id
    AND f.target_date = CURRENT_DATE + INTERVAL '7 days'
WHERE m.is_active = TRUE
GROUP BY m.id, m.name_english, m.name_amharic, m.category, m.atc_code, m.is_essential;

-- Active shortage alerts
CREATE VIEW v_active_alerts AS
SELECT
    a.id, a.alert_type, a.severity,
    a.title, a.title_amharic,
    a.message, a.message_amharic,
    p.name   AS pharmacy_name,
    p.name_amharic AS pharmacy_name_am,
    p.sub_city,
    m.name_english AS medicine_name,
    m.name_amharic AS medicine_name_am,
    a.created_at
FROM alerts a
LEFT JOIN pharmacies p ON a.pharmacy_id = p.id
LEFT JOIN medicines  m ON a.medicine_id  = m.id
WHERE a.is_resolved = FALSE
  AND (a.expires_at IS NULL OR a.expires_at > NOW())
ORDER BY
    CASE a.severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END,
    a.created_at DESC;

-- =============================================================
-- FUNCTIONS & TRIGGERS
-- =============================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pharmacies_updated   BEFORE UPDATE ON pharmacies   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_medicines_updated    BEFORE UPDATE ON medicines     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_inventory_updated    BEFORE UPDATE ON inventory     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_patients_updated     BEFORE UPDATE ON patients      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_prescriptions_updated BEFORE UPDATE ON prescriptions FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Auto-compute stock_status when inventory quantity changes
CREATE OR REPLACE FUNCTION compute_stock_status()
RETURNS TRIGGER AS $$
BEGIN
    NEW.stock_status = CASE
        WHEN NEW.quantity = 0                          THEN 'out'
        WHEN NEW.quantity <= NEW.reorder_point * 0.5  THEN 'critical'
        WHEN NEW.quantity <= NEW.reorder_point         THEN 'low'
        WHEN NEW.quantity > NEW.reorder_point * 5      THEN 'overstock'
        ELSE                                                'adequate'
    END;

    -- Compute days_of_stock
    IF NEW.avg_daily_demand IS NOT NULL AND NEW.avg_daily_demand > 0 THEN
        NEW.days_of_stock = (NEW.quantity / NEW.avg_daily_demand)::INT;
    END IF;

    -- Shortage risk from days_of_stock
    NEW.shortage_risk = CASE
        WHEN NEW.days_of_stock IS NULL OR NEW.days_of_stock <= 3  THEN 'critical'
        WHEN NEW.days_of_stock <= 7                               THEN 'high'
        WHEN NEW.days_of_stock <= 14                              THEN 'medium'
        ELSE                                                           'low'
    END;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_inventory_stock_status
    BEFORE INSERT OR UPDATE OF quantity, reorder_point, avg_daily_demand
    ON inventory
    FOR EACH ROW EXECUTE FUNCTION compute_stock_status();

-- Auto-generate alert when inventory hits critical/out
CREATE OR REPLACE FUNCTION auto_generate_alert()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.stock_status IN ('out', 'critical')
       AND (OLD.stock_status IS NULL OR OLD.stock_status NOT IN ('out','critical')) THEN

        INSERT INTO alerts (alert_type, severity, pharmacy_id, medicine_id, title, title_amharic, message, metadata)
        SELECT
            CASE WHEN NEW.stock_status = 'out' THEN 'stockout'::alert_type ELSE 'low_stock'::alert_type END,
            CASE WHEN NEW.stock_status = 'out' THEN 'critical'::alert_severity ELSE 'warning'::alert_severity END,
            NEW.pharmacy_id,
            NEW.medicine_id,
            CASE WHEN NEW.stock_status = 'out'
                THEN 'Stock-out: ' || m.name_english || ' at ' || p.name
                ELSE 'Critical stock: ' || m.name_english || ' at ' || p.name
            END,
            CASE WHEN NEW.stock_status = 'out'
                THEN 'ክምችት አለቀ: ' || COALESCE(m.name_amharic, m.name_english)
                ELSE 'ወሳኝ ክምችት: ' || COALESCE(m.name_amharic, m.name_english)
            END,
            'Quantity: ' || NEW.quantity || ' units. Reorder point: ' || NEW.reorder_point,
            jsonb_build_object(
                'quantity', NEW.quantity,
                'reorder_point', NEW.reorder_point,
                'batch', NEW.batch_number
            )
        FROM medicines m, pharmacies p
        WHERE m.id = NEW.medicine_id AND p.id = NEW.pharmacy_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auto_alert
    AFTER INSERT OR UPDATE OF stock_status ON inventory
    FOR EACH ROW EXECUTE FUNCTION auto_generate_alert();

-- =============================================================
-- SEED: Reference data (Regions)
-- =============================================================

INSERT INTO regions (name, name_am, code) VALUES
    ('Addis Ababa',       'አዲስ አበባ',   'AA'),
    ('Oromia',            'ኦሮሚያ',       'OR'),
    ('Amhara',            'አማራ',        'AM'),
    ('Tigray',            'ትግራይ',       'TI'),
    ('SNNPR',             'ደቡብ ብሔሮች',  'SN'),
    ('Somali',            'ሶማሌ',        'SO'),
    ('Afar',              'አፋር',         'AF'),
    ('Dire Dawa',         'ድሬ ዳዋ',      'DD'),
    ('Harari',            'ሐረሪ',         'HA'),
    ('Benishangul-Gumuz', 'ቤኒሻንጉል',    'BG');
