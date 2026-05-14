"""
SmartRx AI — Flask Application Factory
Run: python app.py
"""
import sys, os
from pathlib import Path
from flask import Flask, jsonify, request, g, send_from_directory
from datetime import datetime

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

# Auto-create package structure and copy files if needed
def _bootstrap():
    dirs = [
        ROOT/"backend"/"api", ROOT/"backend"/"database",
        ROOT/"backend"/"services",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    for pkg in [ROOT/"backend", ROOT/"backend"/"api",
                ROOT/"backend"/"database", ROOT/"backend"/"services"]:
        init = pkg/"__init__.py"
        if not init.exists(): init.write_text("# SmartRx AI\n")

    import shutil
    copies = [
        ("routes_auth.py",          ROOT/"backend"/"api"/"routes_auth.py"),
        ("routes_medicines.py",     ROOT/"backend"/"api"/"routes_medicines.py"),
        ("routes_pharmacies.py",    ROOT/"backend"/"api"/"routes_pharmacies.py"),
        ("routes_prescriptions.py", ROOT/"backend"/"api"/"routes_prescriptions.py"),
        ("routes_dashboard.py",     ROOT/"backend"/"api"/"routes_dashboard.py"),
        ("auth_utils.py",           ROOT/"backend"/"api"/"auth_utils.py"),
        ("db.py",                   ROOT/"backend"/"database"/"db.py"),
        ("sms_service.py",          ROOT/"backend"/"services"/"sms_service.py"),
    ]
    for src_name, dst_path in copies:
        src = ROOT/src_name
        if src.exists() and not dst_path.exists():
            shutil.copy2(src, dst_path)

    # Fix DB_PATH in db.py to absolute path
    db_py = ROOT/"backend"/"database"/"db.py"
    if db_py.exists():
        txt = db_py.read_text(encoding="utf-8")
        db_file = ROOT/"smartrx_demo.db"
        new_lines = []
        for line in txt.splitlines(keepends=True):
            if line.strip().startswith("DB_PATH"):
                new_lines.append(f'DB_PATH = Path(r"{db_file}")\n')
            else:
                new_lines.append(line)
        db_py.write_text("".join(new_lines), encoding="utf-8")

_bootstrap()

from backend.api.routes_auth          import auth_bp
from backend.api.routes_medicines     import medicines_bp
from backend.api.routes_pharmacies    import pharmacies_bp
from backend.api.routes_prescriptions import prescriptions_bp
from backend.api.routes_dashboard     import (
    dashboard_bp, alerts_bp, forecasts_bp,
    redistribution_bp, analytics_bp
)

def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"]     = False
    app.config["JSON_AS_ASCII"]      = False

    @app.after_request
    def add_cors(response):
        response.headers["Access-Control-Allow-Origin"]  = "*"
        response.headers["Access-Control-Allow-Headers"] = \
            "Content-Type, Authorization, X-Device-ID, X-Offline-Mode"
        response.headers["Access-Control-Allow-Methods"] = \
            "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return response

    @app.before_request
    def handle_options():
        if request.method == "OPTIONS":
            return jsonify({}), 200

    @app.before_request
    def detect_offline():
        g.offline_mode = request.headers.get("X-Offline-Mode","false").lower() == "true"
        g.device_id    = request.headers.get("X-Device-ID")

    for bp in [auth_bp, medicines_bp, pharmacies_bp, prescriptions_bp,
               dashboard_bp, alerts_bp, forecasts_bp,
               redistribution_bp, analytics_bp]:
        app.register_blueprint(bp)

    @app.get("/api/health")
    def health():
        from backend.database.db import query
        try:
            counts = {
                "pharmacies":   query("SELECT COUNT(*) as n FROM pharmacies",  one=True)["n"],
                "medicines":    query("SELECT COUNT(*) as n FROM medicines",   one=True)["n"],
                "transactions": query("SELECT COUNT(*) as n FROM transactions",one=True)["n"],
            }
            db_ok = True
        except Exception as e:
            counts = {}; db_ok = False
        return jsonify({
            "status":    "healthy" if db_ok else "degraded",
            "version":   "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "database":  "connected" if db_ok else "error",
            "counts":    counts,
            "features": {
                "amharic_support":    True,
                "offline_mode":       True,
                "ocr_extraction":     True,
                "demand_forecasting": "LSTM GBR v1",
                "anomaly_detection":  "IsolationForest v1",
                "sms_notifications":  "Africa's Talking (demo)",
            }
        })

    @app.get("/api")
    def api_index():
        return jsonify({
            "name":       "SmartRx AI API",
            "version":    "1.0.0",
            "endpoints": {
                "auth":          "/api/auth/*",
                "medicines":     "/api/medicines",
                "pharmacies":    "/api/pharmacies",
                "prescriptions": "/api/prescriptions",
                "dashboard":     "/api/dashboard/*",
                "alerts":        "/api/alerts",
                "forecasts":     "/api/forecasts",
                "redistribution":"/api/redistribution",
                "analytics":     "/api/analytics/*",
                "health":        "/api/health",
            }
        })

    @app.get("/")
    def frontend_index():
        return send_from_directory(ROOT / "frontend", "index.html")

    @app.get("/<path:filename>")
    def frontend_assets(filename: str):
        if filename.startswith("api/"):
            return jsonify({"error": "Not found", "code": 404}), 404
        return send_from_directory(ROOT / "frontend", filename)

    @app.get("/api/docs")
    def api_docs():
        return jsonify({
            "medicines":  {
                "GET /api/medicines":                   "Search (q=Amharic or English)",
                "GET /api/medicines/<id>/availability": "Stock at all pharmacies",
                "GET /api/medicines/<id>/alternatives": "Generic alternatives",
            },
            "pharmacies": {
                "GET /api/pharmacies/nearby": "lat, lon, radius_km",
                "GET /api/pharmacies/<id>/inventory": "Full inventory",
            },
            "prescriptions": {
                "POST /api/prescriptions": "Upload text/image → AI extraction",
            },
            "forecasts": {
                "GET /api/forecasts": "LSTM shortage predictions",
                "GET /api/forecasts/at-risk": "Critical medicines",
            },
            "analytics": {
                "GET /api/analytics/outbreak-signals": "Autoencoder anomalies",
                "GET /api/analytics/availability-rate": "Coverage by sub-city",
            }
        })

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found", "code": 404}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error", "code": 500}), 500

    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\nSmartRx AI API → http://localhost:{port}/api\n")
    app.run(host="0.0.0.0", port=port, debug=True)
