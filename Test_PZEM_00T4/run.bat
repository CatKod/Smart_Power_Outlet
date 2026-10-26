@echo off
REM ============================================================
REM  Chay web doc thong so PZEM-004T tu cong serial
REM
REM  Usage : run.bat [COM_PORT] [WEB_PORT]
REM  Vd    : run.bat              -> COM10, web 8000
REM          run.bat COM10 8000
REM
REM  Luu y: PZEM-004T V3.0 phai duoc cap nguon luoi AC 220V
REM          (chan L/N) moi phan hoi tren UART.
REM ============================================================
setlocal
cd /d "%~dp0"

set "SERIAL_PORT=%~1"
if "%SERIAL_PORT%"=="" set "SERIAL_PORT=COM10"

set "WEB_PORT=%~2"
if "%WEB_PORT%"=="" set "WEB_PORT=8000"

echo ==========================================
echo  PZEM-004T Web Monitor
echo ==========================================
echo  Serial port : %SERIAL_PORT%
echo  Web port    : %WEB_PORT%
echo  Mo trinh duyet tai: http://127.0.0.1:%WEB_PORT%/
echo.
echo  Nhac: PZEM-004T can nguon luoi AC 220V (chan L/N).
echo        Neu thay "Khong nhan duoc phan hoi", kiem tra nguon + day TX/RX.
echo.

python server.py --port %SERIAL_PORT% --web-port %WEB_PORT%
if errorlevel 1 (
    echo.
    echo Loi chay server. Hay chay: pip install pyserial
    pause
)
endlocal
