<#
.SYNOPSIS
    Gỡ PC Agent khỏi Windows Service.

.DESCRIPTION
    Dừng service, gỡ đăng ký khỏi SCM, và (tuỳ chọn) xoá dữ liệu.

.EXAMPLE
    .\uninstall_service.ps1
    .\uninstall_service.ps1 -RemoveData
#>
[CmdletBinding()]
param(
    [switch]$RemoveData,
    [switch]$KeepFiles
)

$ErrorActionPreference = "Stop"

$ServiceName  = "SmartPowerOutletAgent"
$InstallDir   = "C:\SmartPowerOutlet"
$ConfigDir    = Join-Path $env:ProgramData "SmartPowerOutlet"
$SvcScript    = Join-Path $InstallDir "pc_agent\src\pc_agent\deploy\windows_service.py"

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " Gỡ PC Agent Windows Service" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

# --- Kiểm tra quyền admin ---------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    throw "Cần chạy PowerShell với quyền Administrator để gỡ service."
}

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

if ($svc) {
    Write-Host "[1/3] Dừng service..." -ForegroundColor Yellow
    if ($svc.Status -ne "Stopped") {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }

    Write-Host "[2/3] Gỡ đăng ký khỏi SCM..." -ForegroundColor Yellow
    # Ưu tiên gỡ qua wrapper (đúng đường dẫn đã đăng ký)
    $PyExe = Join-Path $InstallDir "venv\Scripts\python.exe"
    if ((Test-Path $PyExe) -and (Test-Path $SvcScript)) {
        & $PyExe $SvcScript remove 2>$null
    }
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        & sc.exe delete $ServiceName | Out-Null
    }
    Write-Host "      Đã gỡ service '$ServiceName'."
} else {
    Write-Host "[1/3] Service không tồn tại — bỏ qua." -ForegroundColor Yellow
}

# --- Dọn dẹp ---------------------------------------------------------------
if ($RemoveData -and -not $KeepFiles) {
    Write-Host "[3/3] Xoá dữ liệu $ConfigDir ..." -ForegroundColor Yellow
    if (Test-Path $ConfigDir) {
        Remove-Item $ConfigDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $InstallDir) {
        Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "[3/3] Giữ lại dữ liệu tại $ConfigDir" -ForegroundColor Yellow
    Write-Host "      (xoá thủ công nếu cần, hoặc chạy lại với -RemoveData)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Đã gỡ xong." -ForegroundColor Green
