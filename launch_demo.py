#!/usr/bin/env python3
"""
SmartRx AI — One-Command Demo Launcher (Windows-compatible, flat directory)
============================================================================
Run: python launch_demo.py

All files must be in the SAME folder as this script.
"""

import sys, os, time, json, threading, webbrowser, traceback
import http.server, socketserver
from functools import partial
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))
API_ERROR = None

def ensure_structure():
    dirs = [
        ROOT/"backend"/"api", ROOT/"backend"/"database",
        ROOT/"backend"/"services", ROOT/"backend"/"datasets",
        ROOT/"frontend", ROOT/"ml"/"models",
        ROOT/"ml"/"forecasting", ROOT/"ml"/"anomaly_detection",
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
        ("index.html",              ROOT/"frontend"/"index.html"),
        ("train_lstm.py",           ROOT/"ml"/"forecasting"/"train_lstm.py"),
        ("train_autoencoder.py",    ROOT/"ml"/"anomaly_detection"/"train_autoencoder.py"),
    ]
    for src_name, dst_path in copies:
        src = ROOT/src_name
        if src.exists() and not dst_path.exists():
            shutil.copy2(src, dst_path)
            print(f"    Copied {src_name}")
        elif not src.exists() and not dst_path.exists():
            print(f"  WARNING: Missing file: {src_name}")

    # Fix DB_PATH in db.py
    db_py = ROOT/"backend"/"database"/"db.py"
    if db_py.exists():
        txt = db_py.read_text(encoding="utf-8")
        db_abs = str(ROOT/"smartrx_demo.db").replace("\\","\\\\")
        new_lines = []
        for line in txt.splitlines(keepends=True):
            if line.strip().startswith("DB_PATH"):
                new_lines.append(f'DB_PATH = Path(r"{ROOT / "smartrx_demo.db"}")\n')
            else:
                new_lines.append(line)
        db_py.write_text("".join(new_lines), encoding="utf-8")

def check_db():
    import sqlite3
    db = ROOT/"smartrx_demo.db"
    if not db.exists():
        print("  ERROR: smartrx_demo.db not found in this folder!")
        return False
    conn = sqlite3.connect(str(db))
    txns  = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    fcast = conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
    conn.close()
    print(f"  DB OK: {txns:,} transactions, {fcast:,} forecasts")
    return True

def check_models():
    lstm = ROOT/"ml"/"models"/"lstm_demand_models.pkl"
    anom = ROOT/"ml"/"models"/"anomaly_detector.pkl"
    if not lstm.exists():
        print("  NOTE: LSTM model not found - forecasts use heuristic fallback (still works)")
    else:
        print(f"  LSTM model: OK ({lstm.stat().st_size//1024//1024} MB)")
    if not anom.exists():
        print("  NOTE: Anomaly model not found - using seeded outbreak data (still works)")
    else:
        print(f"  Anomaly model: OK ({anom.stat().st_size//1024//1024} MB)")

class SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin","*")
        super().end_headers()

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

def start_frontend(port=3000):
    handler = partial(SilentHandler, directory=str(ROOT/"frontend"))
    with ThreadedTCPServer(("",port), handler) as h:
        h.serve_forever()

def start_api(port=8000):
    global API_ERROR
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("app", str(ROOT/"app.py"))
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.create_app().run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as exc:
        API_ERROR = exc
        print("\n\n  ERROR: API failed to start.")
        print(f"  {type(exc).__name__}: {exc}")
        traceback.print_exc()

def main():
    print("""
╔═══════════════════════════════════════════════╗
║      SmartRx AI — Demo Launcher               ║
║  Ethiopia AI Health System / ኢትዮጵያ ጤና AI    ║
╚═══════════════════════════════════════════════╝
""")
    print("[1/4] Setting up folder structure...")
    ensure_structure()

    print("\n[2/4] Checking database...")
    if not check_db():
        input("Press Enter to exit"); return

    print("\n[3/4] Checking ML models...")
    check_models()

    print("\n[4/4] Starting servers...")
    threading.Thread(target=start_frontend, args=(3000,), daemon=True).start()
    print("  Frontend: http://localhost:3000")
    threading.Thread(target=start_api, args=(8000,), daemon=True).start()
    print("  API starting: http://localhost:8000/api")

    print("\n  Waiting for API", end="", flush=True)
    for _ in range(40):
        time.sleep(1); print(".", end="", flush=True)
        if API_ERROR is not None:
            print("\n\n  SmartRx AI could not start because the API crashed.")
            input("Press Enter to exit")
            return
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:8000/api/health", timeout=1)
            break
        except: pass
    else:
        print("\n\n  ERROR: API did not respond at http://localhost:8000/api/health")
        input("Press Enter to exit")
        return
    print(" Ready!")

    print("""
╔═══════════════════════════════════════════════╗
║  SmartRx AI is RUNNING!                       ║
╠═══════════════════════════════════════════════╣
║  Frontend:  http://localhost:3000             ║
║  API:       http://localhost:8000/api         ║
║  API Docs:  http://localhost:8000/api/docs    ║
╠═══════════════════════════════════════════════╣
║  Login: admin / Admin@2024                    ║
║  Press Ctrl+C to stop                         ║
╚═══════════════════════════════════════════════╝
""")
    try: webbrowser.open("http://localhost:3000")
    except: pass
    try:
        while True: time.sleep(10)
    except KeyboardInterrupt:
        print("\nSmartRx AI stopped.")

if __name__ == "__main__":
    main()
