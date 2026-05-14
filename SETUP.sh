#!/bin/bash
echo ""
echo "============================================"
echo " SmartRx AI - Setup"
echo " Ethiopia Digital Health AI System"
echo "============================================"
echo ""

echo "[1/3] Installing required Python packages..."
pip3 install -r requirements.txt

echo ""
echo "[2/3] Checking files..."
if [ ! -f "smartrx_demo.db" ]; then
    echo "ERROR: smartrx_demo.db is missing!"
    exit 1
fi

echo ""
echo "[3/3] Starting SmartRx AI..."
echo ""
echo "Frontend: http://localhost:3000"
echo "API:      http://localhost:8000/api"
echo ""
python3 launch_demo.py
