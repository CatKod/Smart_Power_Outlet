<#
.SYNOPSIS
    Cài PC Agent thành Windows Service (chạy 24/7, không cần đăng nhập).

.DESCRIPTION
    Script này dùng `pywin32` (pure Python) làm cơ chế chính, vì:
      - không cần tải binary ngoài (WinSW/NSSM);
      - không bị EDR/Defender gắn cờ (NSSM bị coi là HackTool);
      - chạy được với `venv\Scripts\python.exe` (xem giải thích bên dưới).

    **Vì sao không dùng `pythonservice.exe` (wrapper mặc định của pywin32)?**
    `pythonservice.exe` được link cứng với `pythonXY.dll` của bản Python gốc và
    KHÔNG đọc `pyvenv.cfg` → nó sẽ chạy service bằng Python gốc (mất `pyserial`
    đã cài trong venv) và không nạp được DLL → service không chạy.
    Pywin32 hỗ trợ cách khác: **để `python.exe` của venv làm host trực tiếp**
    (chính source pywin32 ghi: *"it is now possible for python.exe to directly
    host services"*). Script này làm đúng vậy — ImagePath trỏ thẳng vào
    `venv\Scripts\python.exe` + file `windows_service.py`.

    Service được đăng ký với:
      - Startup: DELAYED (khởi động trễ sau khi hệ thống ổn định, tránh tranh
        chấp I/O với các service khác lúc boot);
      - Recovery: tự khởi động lại 5s / 10s / 30s nếu tiến trình chết;
      - Account: LocalSystem (mặc định) — có quyền truy cập cổng COM.

.PARAMETER Port
    Cổng HTTP của API/dashboard (mặc định 8000).

.PARAMETER ApiHost
    Địa chỉ lắng nghe API (mặc định 127.0.0.1 — chỉ trong máy).

.PARAMETER InstallDir
    Thư mục cài đặt (mặc định C:\SmartPowerOutlet).

.EXAMPLE
    .\install_service.ps1
    .\install_service.ps1 -ApiHost 0.0.0.0 -Port 8000
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "C:\SmartPowerOutlet",
    [string]$ApiHost    = "127.0.0.1",
    [int]$ApiPort       = 8000,
    [switch]$SkipRecovery
)

$ErrorActionPreference = "Stop"

$ServiceName = "SmartPowerOutletAgent"
$RepoRoot    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # ...\Smart_Power_Outlet
$PkgDir      = Join-Path $RepoRoot "pc_agent"

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " Cài PC Agent thành Windows Service" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  Thư mục cài đặt : $InstallDir"
Write-Host "  API             : http://${ApiHost}:${ApiPort}/"
Write-Host ""

# --- 0. Kiểm tra quyền admin -------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    throw "Cần chạy PowerShell với quyền Administrator (Run as Administrator) để đăng ký service."
}

if (-not (Test-Path $PkgDir)) {
    throw "Không tìm thấy package tại $PkgDir. Chạy script từ trong repo."
}

# --- 1. Sao chép mã nguồn ----------------------------------------------------
Write-Host "[1/6] Sao chép mã nguồn vào $InstallDir ..." -ForegroundColor Yellow
$DestPkg = Join-Path $InstallDir "pc_agent"
if (Test-Path $DestPkg) { Remove-Item $DestPkg -Recurse -Force }
Copy-Item $PkgDir $DestPkg -Recurse -Force
New-Item -ItemType Directory -Path "$InstallDir\logs" -Force | Out-Null

# --- 2. Tạo virtualenv ------------------------------------------------------
Write-Host "[2/6] Tạo virtualenv + cài phụ thuộc..." -ForegroundColor Yellow
$VenvDir = Join-Path $InstallDir "venv"
if (-not (Test-Path "$VenvDir\Scripts\python.exe")) {
    python -m venv $VenvDir
}
$PyExe = Join-Path $VenvDir "Scripts\python.exe"
& $PyExe -m pip install --upgrade pip --quiet
& $PyExe -m pip install "pyserial>=3.5" "pywin32>=306" --quiet
& $PyExe -m pip install -e $DestPkg --quiet
Write-Host "      Python: $PyExe"

# Đường dẫn script sẽ là ImagePath của service
$SvcScript = Join-Path $DestPkg "src\pc_agent\deploy\windows_service.py"

# --- 3. Ghi cấu hình ban đầu ------------------------------------------------
Write-Host "[3/6] Ghi cấu hình..." -ForegroundColor Yellow
$ConfigDir = Join-Path $env:ProgramData "SmartPowerOutlet"
New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null

$ConfigPath = Join-Path $ConfigDir "config.json"
if (-not (Test-Path $ConfigPath)) {
    $initial = @{
        schema_version         = 1
        site_id                = "site-01"
        rack_id                = "rack-01"
        meter_id               = "pdu-01"
        port                   = $null
        usb_location           = $null
        slave_address          = 1
        baudrate               = 9600
        poll_interval_s        = 1.0
        power_threshold_w      = 25000
        voltage_min_v          = 180.0
        voltage_max_v          = 260.0
        offline_after_s        = 30.0
        api_host               = $ApiHost
        api_port               = $ApiPort
        api_token              = $null
        mqtt_host              = $null
        mqtt_port              = 1883
        mqtt_username          = $null
        mqtt_password          = $null
        raw_retention_days     = 14
        hourly_retention_days  = 365
        last_verified_utc      = $null
        extra                  = @{}
    }
    $initial | ConvertTo-Json -Depth 5 | Set-Content -Path $ConfigPath -Encoding UTF8
    Write-Host "      Đã tạo $ConfigPath"
} else {
    Write-Host "      Cấu hình đã tồn tại, giữ nguyên: $ConfigPath"
}

# --- 4. Đăng ký service -----------------------------------------------------
Write-Host "[4/6] Đăng ký service '$ServiceName'..." -ForegroundColor Yellow

# Dừng & gỡ bản cũ nếu có (để script chạy lại được)
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "      Service đã tồn tại — dừng và gỡ bản cũ."
    if ($existing.Status -ne "Stopped") {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    }
    & $PyExe $SvcScript remove 2>$null
    Start-Sleep -Seconds 2
}

# --startup=delayed : SERVICE_DELAYED_AUTO_START_INFO
& $PyExe $SvcScript --startup=delayed install
if ($LASTEXITCODE -ne 0) { throw "Đăng ký service thất bại (exit $LASTEXITCODE)." }

# --- 5. Cấu hình recovery ----------------------------------------------------
if (-not $SkipRecovery) {
    Write-Host "[5/6] Cấu hình tự khởi động lại khi lỗi..." -ForegroundColor Yellow
    & sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null
    & sc.exe failureflag $ServiceName 1 | Out-Null
}

# --- 6. Firewall (chỉ khi bind ngoài localhost) -----------------------------
if ($ApiHost -ne "127.0.0.1" -and $ApiHost -ne "localhost") {
    Write-Host "[6/6] Mở firewall cho cổng $ApiPort..." -ForegroundColor Yellow
    $ruleName = "Smart Power Outlet Agent API ($ApiPort)"
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName `
            -Direction Inbound -LocalPort $ApiPort -Protocol TCP -Action Allow | Out-Null
    }
} else {
    Write-Host "[6/6] API chỉ bind localhost — không cần rule firewall." -ForegroundColor Yellow
}

# --- Khởi động ---------------------------------------------------------------
Write-Host ""
Write-Host "Đang khởi động service..." -ForegroundColor Yellow
Start-Service -Name $ServiceName
Start-Sleep -Seconds 3

$svc = Get-Service -Name $ServiceName
Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " Cài đặt thành công" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host "  Trạng thái  : $($svc.Status)"
Write-Host "  API        : http://${ApiHost}:${ApiPort}/"
Write-Host "  Log        : $ConfigDir\logs\agent.log"
Write-Host "  Cấu hình   : $ConfigPath"
Write-Host ""
Write-Host "  Kiểm tra   : sc.exe query $ServiceName"
Write-Host "  Gỡ bỏ      : .\uninstall_service.ps1"
