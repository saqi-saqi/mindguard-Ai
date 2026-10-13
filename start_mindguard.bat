@echo off
chcp 65001 >nul
title MindGuard Launcher
cd /d "%~dp0"

echo =====================================================
echo   MindGuard - AI Mental Health Support Chatbot
echo   One-click launcher (backend + frontend)
echo =====================================================
echo.

REM ---------- 1. Prerequisite checks ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found on PATH. Install Python 3.10+ first.
    pause
    exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found on PATH. Install Node 18+ first.
    pause
    exit /b 1
)

REM ---------- 2. First-run installs (skipped when already done) ----------
if not exist "client\node_modules" (
    echo [SETUP] Installing frontend dependencies ^(first run only^)...
    pushd client
    call npm install
    popd
)
python -c "import flask" >nul 2>nul
if errorlevel 1 (
    echo [SETUP] Installing backend dependencies ^(first run only^)...
    pip install -r server\requirements.txt
)

REM ---------- 3. MongoDB detection ----------
netstat -an | findstr /C:":27017" | findstr /C:"LISTENING" >nul 2>nul
if errorlevel 1 (
    echo [INFO] MongoDB not detected on :27017 - using in-memory DB ^(mongomock^).
    goto backend_nomongo
)
echo [INFO] MongoDB detected on :27017.
goto backend_mongo

:backend_nomongo
echo [START] Backend  -^> http://127.0.0.1:5000  (window: MindGuard Backend, in-memory DB)
start "MindGuard Backend" cmd /k "set USE_MONGOMOCK=true&& py server\app.py"
goto frontend

:backend_mongo
echo [START] Backend  -^> http://127.0.0.1:5000  (window: MindGuard Backend)
start "MindGuard Backend" cmd /k "py server\app.py"

:frontend
REM ---------- 4. Launch frontend ----------
echo [START] Frontend -^> http://localhost:5173  (window: MindGuard Frontend)
cd /d "%~dp0client"
start "MindGuard Frontend" cmd /k "cd /d %~dp0client && npm run dev"
cd /d "%~dp0"

REM ---------- 6. Open the app ----------
echo.
echo Waiting for the frontend to come up...
timeout /t 10 >nul
start "" http://localhost:5173

echo.
echo =====================================================
echo   MindGuard is running.
echo     App      : http://localhost:5173
echo     API      : http://127.0.0.1:5000/api/health
echo   To stop: close BOTH "MindGuard Backend" and
echo   "MindGuard Frontend" windows.
echo =====================================================
pause
