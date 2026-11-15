@echo off
REM ============================================================
REM  PC Agent - chay foreground (development)
REM
REM  Usage : run_dev.bat [COM_PORT] [API_PORT]
REM  Vd    : run_dev.bat              -> tu do COM, API 8000
REM          run_dev.bat COM10 8000
REM
REM  Luu y: PZEM-004T V3.0 phai duoc cap nguon luoi AC 220V
REM          (chan L/N) moi phan hoi tren UART.
REM ============================================================
setlocal
cd /d "%~dp0\.."

set "SERIAL_PORT=%~1"
set "API_PORT=%~2"

set "EXTRA="
if not "%SERIAL_PORT%"=="" set "EXTRA=--port %SERIAL_PORT%"
if not "%API_PORT%"=="" set "EXTRA=%EXTRA% --api-port %API_PORT%"

echo ==========================================
echo  PC Agent - Electronic PC Agent
echo ==========================================
if not "%SERIAL_PORT%"=="" echo  Serial port : %SERIAL_PORT% (ep)
echo  API         : http://127.0.0.1:%API_PORT%% 
echo.
echo  Nhac: PZEM-004T can nguon luoi AC 220V (chan L/N).
echo        Neu thay "thiet bi im lang", kiem tra nguon + day TX/RX.
echo.

REM Dung python trong venv neu co, nguoc lai dung python he thong.
set "PY=python"
if exist ".\.venv\Scripts\python.exe" set "PY=.\.venv\Scripts\python.exe"

%PY% -m pc_agent %EXTRA%
if errorlevel 1 (
    echo.
    echo Loi chay PC Agent. Hay chay: pip install -e ".[service]"
    pause
)
endlocal
