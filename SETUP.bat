@echo off
setlocal
cd /d "%~dp0"
set "SMART_RX_PACKAGES=%~dp0.smart_rx_packages"

echo.
echo ============================================
echo  SmartRx AI - Windows Setup
echo   Ethiopia Digital Health AI System
echo ============================================
echo.

set "PYTHON_CMD="

if defined CONDA_PREFIX (
    if /I "%CONDA_DEFAULT_ENV%"=="eda" (
        if exist "%CONDA_PREFIX%\python.exe" set "PYTHON_CMD=%CONDA_PREFIX%\python.exe"
    ) else (
        if /I not "%CONDA_DEFAULT_ENV%"=="base" (
            if exist "%CONDA_PREFIX%\python.exe" set "PYTHON_CMD=%CONDA_PREFIX%\python.exe"
        )
    )
)

if not defined PYTHON_CMD (
    if defined _CONDA_ROOT (
        if exist "%_CONDA_ROOT%\envs\eda\python.exe" set "PYTHON_CMD=%_CONDA_ROOT%\envs\eda\python.exe"
    )
)

if not defined PYTHON_CMD (
    if exist "C:\ProgramData\anaconda3\envs\eda\python.exe" (
        set "PYTHON_CMD=C:\ProgramData\anaconda3\envs\eda\python.exe"
    )
)

if not defined PYTHON_CMD (
    if exist "%USERPROFILE%\.conda\envs\eda\python.exe" (
        set "PYTHON_CMD=%USERPROFILE%\.conda\envs\eda\python.exe"
    )
)

if not defined PYTHON_CMD (
    if defined VIRTUAL_ENV (
        if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON_CMD=%VIRTUAL_ENV%\Scripts\python.exe"
    )
)

if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py"
)

if not defined PYTHON_CMD (
    echo ERROR: Python was not found on PATH.
    echo Install Python 3, then run this file again.
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo Using Python:
%PYTHON_CMD% -c "import sys; print('  ' + sys.executable)"

set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
if exist "%SMART_RX_PACKAGES%" (
    if defined PYTHONPATH (
        set "PYTHONPATH=%SMART_RX_PACKAGES%;%PYTHONPATH%"
    ) else (
        set "PYTHONPATH=%SMART_RX_PACKAGES%"
    )
)

echo [1/3] Installing required Python packages...
%PYTHON_CMD% -s -m pip install --target "%SMART_RX_PACKAGES%" Flask==3.1.3 PyJWT==2.10.1 Pillow==12.2.0 pytesseract==0.3.13 python-dotenv==1.0.0 werkzeug==3.1.3 click==8.1.7 itsdangerous==2.2.0 blinker==1.9.0 jinja2==3.1.4 markupsafe==3.0.2 packaging==26.2
if errorlevel 1 (
    echo.
    echo ERROR: Could not install required Python packages.
    pause
    exit /b 1
)

echo.
echo [2/3] Checking files...
if not exist "smartrx_demo.db" (
    echo ERROR: smartrx_demo.db is missing from this folder!
    echo Make sure all downloaded files are in the same folder.
    pause
    exit /b 1
)
if not exist "app.py" (
    echo ERROR: app.py is missing from this folder!
    pause
    exit /b 1
)

echo.
echo [3/3] Starting SmartRx AI...
echo.
echo Frontend will open at: http://localhost:3000
echo API will be at:        http://localhost:8000/api
echo.
%PYTHON_CMD% launch_demo.py

pause
