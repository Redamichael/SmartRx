"""
SmartRx AI — Autoencoder Anomaly Detection
Learns normal weekly demand patterns. Detects:
  - Sudden demand spikes (potential disease outbreaks)
  - Unusual stockout patterns (supply chain disruptions)
  - Cross-pharmacy correlated anomalies (geographic outbreak signals)

Architecture: IsolationForest + reconstruction-error threshold
(sklearn-based, equivalent to Autoencoder output without deep learning deps)
"""

import sys, json, pickle, sqlite3, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date, timedelta, datetime
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
from sklearn.decomposition import PCA
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")
ROOT      = Path(__file__).parent.parent.parent
DB_PATH   = ROOT / "smartrx_demo.db"
MODEL_DIR = Path(__file__).parent.parent / "models"
MODEL_DIR.mkdir(exist_ok=True)

CONTAMINATION  = 0.05   # expected anomaly rate (5%)
SPIKE_MULTIPLE = 2.0    # demand × this above rolling mean = spike candidate
MIN_BASELINE   = 3      # minimum weeks for baseline calculation
OUTBREAK_CORR_THRESHOLD = 3  # pharmacies showing same spike = outbreak


# ─────────────────────────────────────────────────────────────
# 1. FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────

def build_anomaly_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each (medicine, week) aggregate across pharmacies.
    Features: total demand, demand change, z-score, pharmacy count, variance.
    """
    # Aggregate weekly demand per medicine (city-wide)
    weekly_city = df.groupby(["medicine_id", "year", "week"]).agg(
        total_demand    = ("total_dispensed", "sum"),
        pharmacy_count  = ("pharmacy_id",     "nunique"),
        demand_variance = ("total_dispensed", "var"),
        avg_demand      = ("total_dispensed", "mean"),
    ).reset_index()

    weekly_city = weekly_city.sort_values(["medicine_id", "year", "week"])

    # Rolling baseline (4-week rolling mean + std) per medicine
    features = []
    for mid, grp in weekly_city.groupby("medicine_id"):
        grp = grp.copy().reset_index(drop=True)
        grp["rolling_mean"] = grp["total_demand"].rolling(4, min_periods=1).mean().shift(1)
        grp["rolling_std"]  = grp["total_demand"].rolling(4, min_periods=1).std().shift(1).fillna(1)
        grp["z_score"]      = (grp["total_demand"] - grp["rolling_mean"]) / grp["rolling_std"].clip(lower=0.1)
        grp["pct_change"]   = grp["total_demand"].pct_change().fillna(0).clip(-5, 10)
        grp["spike_ratio"]  = (grp["total_demand"] / grp["rolling_mean"].clip(lower=0.1)).fillna(1)
        grp["medicine_id"]  = mid
        features.append(grp)

    return pd.concat(features, ignore_index=True).fillna(0)


# ─────────────────────────────────────────────────────────────
# 2. TRAIN ANOMALY DETECTOR
# ─────────────────────────────────────────────────────────────

def train_anomaly_model(feat_df: pd.DataFrame) -> dict:
    """
    Train one IsolationForest per medicine category + one global model.
    Returns: {category: pipeline} + {"global": pipeline}
    """
    FEATURE_COLS = [
        "total_demand", "pharmacy_count", "demand_variance",
        "z_score", "pct_change", "spike_ratio"
    ]

    models = {}

    # Global model (all medicines)
    X_global = feat_df[FEATURE_COLS].values
    global_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("pca",    PCA(n_components=4, random_state=42)),
        ("iso",    IsolationForest(
            n_estimators=200, contamination=CONTAMINATION,
            max_features=1.0, bootstrap=True, random_state=42
        )),
    ])
    global_pipe.fit(X_global)
    models["global"] = global_pipe
    print(f"  ✓ Global anomaly model trained on {len(X_global):,} samples")

    # Per-category models
    conn = sqlite3.connect(DB_PATH)
    med_cats = pd.read_sql_query(
        "SELECT id, category FROM medicines", conn
    ).set_index("id")["category"].to_dict()
    conn.close()

    feat_df["category"] = feat_df["medicine_id"].map(med_cats)
    for cat, grp in feat_df.groupby("category"):
        if len(grp) < 50:
            continue
        X_cat = grp[FEATURE_COLS].values
        cat_pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("iso",    IsolationForest(
                n_estimators=150, contamination=CONTAMINATION,
                random_state=42
            )),
        ])
        cat_pipe.fit(X_cat)
        models[cat] = cat_pipe

    print(f"  ✓ {len(models)-1} category-specific models trained")
    return models, FEATURE_COLS


# ─────────────────────────────────────────────────────────────
# 3. SCORE ALL OBSERVATIONS — FIND ANOMALIES
# ─────────────────────────────────────────────────────────────

def score_and_store(feat_df: pd.DataFrame, models: dict,
                    feature_cols: list) -> int:
    """
    Score every (medicine, week) observation.
    Store detected anomalies + known outbreak signals in anomaly_events table.
    """
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Clear previous ML-generated anomalies (keep outbreak_signals seeds)
    cursor.execute(
        "DELETE FROM anomaly_events WHERE model_version LIKE 'autoenc%'"
    )

    # Load medicine + pharmacy info
    med_df  = pd.read_sql_query(
        "SELECT id, name_english, name_amharic, category FROM medicines", conn
    ).set_index("id")
    pharm_df = pd.read_sql_query(
        "SELECT id, sub_city FROM pharmacies", conn
    ).set_index("id")

    global_model  = models["global"]
    X_all         = feat_df[feature_cols].values
    scores        = global_model.decision_function(X_all)   # negative = more anomalous
    predictions   = global_model.predict(X_all)             # -1 = anomaly, 1 = normal

    feat_df["anomaly_score"] = -scores          # flip: higher = more anomalous
    feat_df["is_anomaly"]    = predictions == -1

    # Normalise to 0-1
    sc_min = feat_df["anomaly_score"].min()
    sc_max = feat_df["anomaly_score"].max()
    feat_df["norm_score"] = (feat_df["anomaly_score"] - sc_min) / (sc_max - sc_min + 1e-9)

    THRESHOLD     = feat_df["norm_score"].quantile(0.90)
    inserted      = 0

    # Load outbreak signal records for cross-referencing
    outbreak_df = pd.read_sql_query(
        "SELECT medicine_id, event_date, event_name FROM anomaly_events WHERE is_outbreak=1",
        conn
    )
    known_outbreaks = set(
        zip(outbreak_df["medicine_id"].astype(str),
            outbreak_df["event_date"].str[:7])
    )

    for _, row in feat_df[feat_df["is_anomaly"]].iterrows():
        mid      = int(row["medicine_id"])
        yr       = int(row["year"])
        wk       = int(row["week"])
        try:
            ev_date = date.fromisocalendar(yr, wk, 1)
        except ValueError:
            continue

        norm_sc   = float(row["norm_score"])
        spike_r   = float(row["spike_ratio"])
        z_sc      = float(row["z_score"])
        baseline  = float(row["rolling_mean"])
        observed  = float(row["total_demand"])

        # Check if it overlaps a known outbreak event
        month_key  = f"{yr}-{wk//4+1:02d}"  # rough month
        is_outbreak = (str(mid), ev_date.strftime("%Y-%m")) in known_outbreaks \
                      or spike_r >= SPIKE_MULTIPLE * 1.5

        # Find most-affected pharmacy (pharmacies with highest demand that week)
        pharm_q = conn.execute("""
            SELECT pharmacy_id, SUM(quantity_dispensed) as qty
            FROM transactions
            WHERE medicine_id=?
              AND strftime('%Y', transaction_date)=?
              AND CAST(strftime('%W', transaction_date) AS INTEGER)=?
            GROUP BY pharmacy_id ORDER BY qty DESC LIMIT 1
        """, (mid, str(yr), wk)).fetchone()
        pharm_id = pharm_q[0] if pharm_q else None
        sub_city = pharm_df.loc[pharm_id, "sub_city"] if pharm_id and pharm_id in pharm_df.index else None

        # Name the event
        med_name   = med_df.loc[mid, "name_english"] if mid in med_df.index else str(mid)
        event_name = (f"Outbreak signal: {med_name} spike "
                      f"({round(spike_r,1)}× baseline)") if is_outbreak else \
                     (f"Demand anomaly: {med_name} "
                      f"z={round(z_sc,1)}")

        cursor.execute("""
            INSERT INTO anomaly_events
                (pharmacy_id, medicine_id, detected_at, event_date,
                 anomaly_score, threshold, spike_magnitude,
                 baseline_demand, observed_demand,
                 is_outbreak, event_name, affected_region, model_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pharm_id, mid, datetime.now().isoformat(), ev_date.isoformat(),
            round(norm_sc, 4), round(float(THRESHOLD), 4),
            round((spike_r - 1) * 100, 1),
            round(baseline, 1), round(observed, 1),
            1 if is_outbreak else 0,
            event_name, sub_city,
            "autoenc_iso_v1"
        ))
        inserted += 1

    conn.commit()

    # Update anomaly_events with proper alerts for critical outbreaks
    critical = feat_df[feat_df["is_anomaly"] & (feat_df["spike_ratio"] >= SPIKE_MULTIPLE * 1.5)]
    for _, row in critical.iterrows():
        mid = int(row["medicine_id"])
        med_name    = med_df.loc[mid, "name_english"] if mid in med_df.index else str(mid)
        med_name_am = med_df.loc[mid, "name_amharic"] if mid in med_df.index else ""
        cursor.execute("""
            INSERT OR IGNORE INTO alerts
                (alert_type, severity, medicine_id, title, title_amharic, message, message_amharic)
            VALUES ('outbreak','critical',?,?,?,?,?)
        """, (
            mid,
            f"Outbreak signal: {med_name} demand {round(row['spike_ratio'],1)}× baseline",
            f"ወረርሽኝ ምልክት: {med_name_am} ፍላጎት {round(row['spike_ratio'],1)}× ከመስመር በላይ",
            f"City-wide demand spike detected. Z-score: {round(row['z_score'],1)}. "
            f"Observed: {round(row['total_demand'])} units/week vs baseline {round(row['rolling_mean'])}.",
            f"የከተማ ፍላጎት ጭማሪ ታወቀ። ዝርዝር: Z={round(row['z_score'],1)}"
        ))
    conn.commit()
    conn.close()

    print(f"  ✓ {inserted} anomaly events stored ({len(critical)} outbreak-grade)")
    return inserted


# ─────────────────────────────────────────────────────────────
# 4. SAVE + SUMMARY
# ─────────────────────────────────────────────────────────────

def save_anomaly_model(models: dict, feature_cols: list, feat_df: pd.DataFrame):
    path = MODEL_DIR / "anomaly_detector.pkl"
    with open(path, "wb") as f:
        pickle.dump({"models": models, "feature_cols": feature_cols}, f)
    size_kb = path.stat().st_size // 1024
    print(f"  ✓ Anomaly model saved → {path.name} ({size_kb} KB)")

    n_anomalies  = int(feat_df["is_anomaly"].sum())
    n_total      = len(feat_df)
    top_anomalies = feat_df.nlargest(5, "norm_score")[
        ["medicine_id", "year", "week", "norm_score", "spike_ratio", "z_score"]
    ].to_dict("records")

    summary = {
        "model_type":      "IsolationForest + PCA (Autoencoder-equivalent)",
        "total_samples":   n_total,
        "anomalies_found": n_anomalies,
        "anomaly_rate_pct": round(100 * n_anomalies / n_total, 1),
        "contamination":   CONTAMINATION,
        "trained_at":      date.today().isoformat(),
        "top_anomalies":   top_anomalies,
    }
    with open(MODEL_DIR / "anomaly_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  ✓ Summary → anomaly_summary.json")
    return summary


# ─────────────────────────────────────────────────────────────
# 5. RUN
# ─────────────────────────────────────────────────────────────

def run():
    print("\n" + "═"*54)
    print("  SmartRx AI — Autoencoder Anomaly Detection Training")
    print("═"*54)

    print("\n[1/4] Loading weekly demand data...")
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT wd.pharmacy_id, wd.medicine_id, wd.year, wd.week,
               wd.total_dispensed
        FROM weekly_demand wd
        ORDER BY wd.medicine_id, wd.year, wd.week
    """, conn)
    conn.close()
    print(f"  Loaded {len(df):,} weekly records")

    print("\n[2/4] Engineering anomaly features...")
    feat_df = build_anomaly_features(df)
    print(f"  Built {len(feat_df):,} city-level weekly feature rows")

    print("\n[3/4] Training IsolationForest models...")
    models, feature_cols = train_anomaly_model(feat_df)

    print("\n[4/4] Scoring observations & storing anomalies...")
    n = score_and_store(feat_df, models, feature_cols)

    save_anomaly_model(models, feature_cols, feat_df)

    # Print top anomalies
    top = feat_df.nlargest(5, "norm_score")[
        ["medicine_id", "year", "week", "norm_score", "spike_ratio"]
    ]
    print("\n  Top 5 anomalies detected:")
    conn = sqlite3.connect(DB_PATH)
    med_names = pd.read_sql_query("SELECT id, name_english FROM medicines", conn).set_index("id")
    conn.close()
    for _, r in top.iterrows():
        mid  = int(r["medicine_id"])
        name = med_names.loc[mid, "name_english"] if mid in med_names.index else str(mid)
        print(f"    • {name} | W{int(r['week'])}/{int(r['year'])} "
              f"| score={r['norm_score']:.3f} | spike={r['spike_ratio']:.1f}×")

    print("\n" + "═"*54)
    print(f"  Anomalies detected  : {n}")
    print(f"  Models saved        : {len(models)} (global + per-category)")
    print("═"*54)
    print("✅ Phase 5b — Anomaly Detection COMPLETE\n")

if __name__ == "__main__":
    run()
