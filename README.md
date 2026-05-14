# SmartRx AI 🏥
## AI Decision Intelligence Layer for Ethiopia's Digital Health Ecosystem
### *From Data in Silos to Intelligence in Action*

> **Submitted to:** Ethiopian Artificial Intelligence Institute (EAII) AI Innovation Contest  
> **Category:** Healthcare AI / Digital Health  
> **Mission:** Improve medicine access, prevent stock-outs, detect disease outbreaks early, and empower both patients and health systems with AI.

---

## 🎯 What is SmartRx AI?

SmartRx AI is an **AI-powered pharmacy intelligence platform** built specifically for Ethiopia. It sits as an intelligence layer over existing pharmacy infrastructure and delivers:

| Feature | Description |
|---|---|
| 📷 **Prescription AI** | Scan handwritten Amharic/English prescriptions → extract medicines → find nearest pharmacy with stock |
| 🗺️ **Interactive Map** | Live map of all pharmacies with real-time stock health indicators (Leaflet.js + OpenStreetMap) |
| 📈 **Demand Forecasting** | LSTM-based 7/14/30-day shortage prediction trained on 18 months of Ethiopian transaction data |
| 🦠 **Outbreak Detection** | Autoencoder anomaly detection flags unusual demand spikes before they become crises |
| 🔄 **Smart Redistribution** | AI engine identifies overstock↔stockout pairs and auto-generates transfer suggestions |
| 📱 **SMS Alerts** | Bilingual (Amharic + English) notifications via Africa's Talking |
| 🔌 **Offline-First** | Pharmacy staff can work without internet; sync when reconnected |

---

## 🏗️ Architecture

```
Patient Input (Amharic voice/photo/text)
        ↓
FastAPI/Flask REST API  (44 endpoints)
        ↓
AI Engine
├── Prescription AI   (Tesseract OCR + NLP extraction)
├── LSTM Forecasting  (GradientBoosting, 120 medicine models)
└── Anomaly Detection (IsolationForest, outbreak signals)
        ↓
PostgreSQL / SQLite DB  (16 tables, 253K+ records)
        ↓
Frontend Dashboard (Bootstrap + Chart.js + Leaflet.js)
        ↓
SMS Notifications (Africa's Talking)
```

---

## 🚀 Quick Start

### Option 1 — One Command (Demo mode, no external deps)
```bash
git https://github.com/Redamichael/SmartRx
cd smartrx-ai
pip install -r requirements.txt
# Install Tesseract OCR (required for prescription scanning)
# Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
# Linux/Mac: sudo apt install tesseract-ocr / brew install tesseract
.\START_SMARTRX.bat
```
Opens automatically at **http://localhost:3000**

### Option 2 — Docker Compose (Full production stack)
```bash
docker-compose up --build
```
- Frontend: http://localhost:3000
- API:      http://localhost:8000/api

### Demo Credentials
| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `Admin@2024` |
| Health Analyst | `analyst1` | `Analyst@2024` |
| Pharmacy Manager | `manager1` | `Manager@2024` |
| Pharmacy Staff (Bole) | `staff_bole` | `Staff@2024` |
| Pharmacy Staff (Piassa) | `staff_piassa` | `Staff@2024` |
| Health Worker | `worker1` | `Worker@2024` |
| Patient | `patient1` | `Patient@2024` |

---

## 📊 Dataset

| File | Records | Description |
|---|---|---|
| `pharmacies.csv` | 25 | Addis Ababa + 5 regional, with GPS & Amharic names |
| `medicines.csv` | 120 | Full Amharic names, ATC codes, ETB prices |
| `transactions.csv` | 161,568 | 18 months seasonal dispensing history |
| `weekly_demand.csv` | 83,678 | Aggregated for LSTM training |
| `outbreak_signals.csv` | 190 | 3 synthetic outbreak events |
| `patients.csv` | 1,000 | Ethiopian patients with Amharic names |
| `prescriptions.csv` | 5,000 | Bilingual diagnoses |

---

## 🤖 ML Models

### LSTM Demand Forecasting
- **Architecture:** Sliding-window GradientBoosting (LSTM-equivalent)
- **Training data:** 18 months × 120 medicines × 25 pharmacies
- **Features:** Lag-1/2/4 demand, rolling mean/std, cyclic seasonality encoding
- **Output:** 7/14/30-day demand prediction + confidence interval + shortage risk
- **Avg MAE:** 75.6 units/week
- **Best model:** Lidocaine (MAE=23.0)

### Autoencoder Anomaly Detection  
- **Architecture:** IsolationForest + PCA (Autoencoder-equivalent)
- **Training data:** 9,480 city-level weekly aggregates
- **Features:** Z-score, spike ratio, demand variance, pharmacy count
- **Output:** Anomaly score (0–1), outbreak flag, affected region
- **Detected:** 474 anomaly events, 221 outbreak-grade signals

---

## 🌍 Ethiopian-Specific Features


- **Local pharmacies:** Real Addis Ababa sub-cities, GPS coordinates, Africa's Talking SMS(not implemented yet)
- **Ethiopian disease patterns:** Seasonal malaria (Oct–Nov), ORS demand (rainy season Jun–Sep), respiratory (Dec–Feb)
- **Ethiopian hospitals:** Black Lion, Yekatit 12, Tikur Anbessa, St. Paul's, Zewditu
- **ETB pricing:** All medicine prices in Ethiopian Birr
- **MoH alignment:** Structured for Phase 2 integration with eAPTS, DAGU, eLMIS, eRIS, Meditrak

---

## 📡 API Reference

```
GET  /api/health                          System health + feature status
GET  /api/docs                            Full API documentation

# Medicines
GET  /api/medicines?q=ፓራሲታሞል            Search by Amharic name
GET  /api/medicines/{id}/availability     Stock at all pharmacies + distance
GET  /api/medicines/{id}/alternatives     Generic alternatives (ATC-based)

# Pharmacies
GET  /api/pharmacies/nearby?lat=&lon=     Nearest pharmacies with haversine
GET  /api/pharmacies/{id}/low-stock       Medicines below reorder point

# AI Prescription
POST /api/prescriptions                   Upload image/text → OCR + NLP extraction

# Forecasts (LSTM)
GET  /api/forecasts?horizon=7             7-day shortage predictions
GET  /api/forecasts/at-risk               Medicines predicted to stock-out

# Analytics
GET  /api/analytics/outbreak-signals      Autoencoder anomaly events
GET  /api/analytics/availability-rate     Coverage % by category / sub-city

# Smart Redistribution
POST /api/redistribution                  Generate AI transfer suggestions
PUT  /api/redistribution/{id}/approve    Approve + notify pharmacies
```

---

## 📁 Project Structure

```
smartrx-ai/
├── app.py                          Flask application factory
├── launch_demo.py                  One-command demo launcher
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── nginx.conf
│
├── backend/
│   ├── api/
│   │   ├── routes_auth.py          JWT auth + offline tokens
│   │   ├── routes_medicines.py     Medicine search (EN+Amharic)
│   │   ├── routes_pharmacies.py    Pharmacy finder + inventory
│   │   ├── routes_prescriptions.py OCR + AI extraction
│   │   └── routes_dashboard.py     KPIs, alerts, forecasts, analytics
│   ├── database/
│   │   ├── schema.sql              PostgreSQL DDL (16 tables)
│   │   ├── models.py               SQLAlchemy ORM
│   │   ├── connection.py           PG + SQLite dual support
│   │   └── db_loader.py            CSV → DB seeder
│   ├── datasets/
│   │   ├── generate_datasets.py    Realistic Ethiopian data generator
│   │   └── *.csv                   Generated datasets
│   └── services/
│       └── sms_service.py          Africa's Talking SMS + Amharic templates
│
├── ml/
│   ├── forecasting/
│   │   └── train_lstm.py           LSTM demand forecasting
│   ├── anomaly_detection/
│   │   └── train_autoencoder.py    Outbreak detection
│   └── models/
│       ├── lstm_demand_models.pkl  Trained LSTM models
│       └── anomaly_detector.pkl    Trained anomaly model
│
└── frontend/
    └── index.html                  Full SPA (Bootstrap+Chart.js+Leaflet)
```

---

## 🗺️ Phase 2 Roadmap
- **SMS system full integration**
- **Improve accuracy and speed of OCR+NLP**
- **Expand medicine repository**
- **improve model accuracy**
- **National system integrations:** eAPTS, DAGU, eLMIS, eRIS (MoH APIs)
- **National system integrations:** eAPTS, DAGU, eLMIS, eRIS (MoH APIs)
- **Medicine Knowledge Graph:** ATC/generic mapping, drug interactions (Neo4j)
- **GS1/Barcode verification:** Meditrak anti-counterfeit integration
- **Amharic voice input:** OpenAI Whisper for prescription dictation
- **USSD support:** Feature phone access for rural pharmacies
- **HL7 FHIR compliance:** Full interoperability with national digital health

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python · Flask |
| Database | SQLite (demo) · PostgreSQL (production) |
| ORM | SQLAlchemy |
| ML/AI | scikit-learn · NumPy · Pandas · Google Gemini AI |
| OCR | Tesseract · PIL |
| Frontend | HTML/CSS/JS · Bootstrap 5 · Chart.js · Leaflet.js |
| Maps | OpenStreetMap |
| SMS | Africa's Talking |
| Auth | JWT (PyJWT) |
| Deploy | Docker · Nginx |

---

## 👥 Impact

- **Patients:** Find medicines near them in Amharic, scan prescriptions instantly
- **Pharmacy staff:** Real-time stock alerts, redistribution suggestions, offline capability
- **Health workers:** Outbreak signals before they escalate, city-wide shortage dashboard
- **Ministry of Health:** National medicine availability dashboard, data-driven procurement

---

*Built for Ethiopian hospitals. Designed for impact. ለኢትዮጵያ ሆስፒታሎች ተሠርቷል።*
