#!/usr/bin/env bash
# =============================================================================
#  Gỡ PC Agent khỏi Linux (systemd)
#
#  Dùng:
#      sudo ./uninstall_linux.sh              # giữ lại cấu hình + dữ liệu
#      sudo ./uninstall_linux.sh --purge      # xoá cả cấu hình + dữ liệu
#      sudo ./uninstall_linux.sh --keep-venv  # giữ venv (mặc định: xoá)
#
#  Mặc định KHÔNG xoá dữ liệu đo — an toàn cho dữ liệu lịch sử.
# =============================================================================
set -euo pipefail

INSTALL_DIR="/opt/smartpower"
CONFIG_DIR="/etc/smartpower"
DATA_DIR="/var/lib/smartpower"
LOG_DIR="/var/log/smartpower"
SERVICE_USER="smartpower"
UNIT_NAME="smart-power-agent"

PURGE=0
KEEP_VENV=0

usage() {
    cat <<EOF
Dùng: sudo $0 [tùy chọn]

Tùy chọn:
  --purge       Xoá cả cấu hình ($CONFIG_DIR) và dữ liệu ($DATA_DIR)
  --keep-venv   Giữ lại virtualenv trong $INSTALL_DIR/venv
  --user USER   Tài khoản service cần xoá (mặc định: $SERVICE_USER)
  -h, --help    Hiện trợ giúp
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --purge)     PURGE=1; shift ;;
        --keep-venv) KEEP_VENV=1; shift ;;
        --user)      SERVICE_USER="$2"; shift 2 ;;
        -h|--help)   usage; exit 0 ;;
        *) echo "Tham số lạ: $1" >&2; usage; exit 1 ;;
    esac
done

[[ $EUID -eq 0 ]] || { echo "Cần chạy với quyền root: sudo $0" >&2; exit 1; }

step() { echo "==> $*"; }
ok()   { echo "  ✓ $*"; }
warn() { echo "  ! $*"; }

step "Gỡ PC Agent khỏi systemd"

# --- 1. Dừng + gỡ unit -------------------------------------------------------
if systemctl list-unit-files | grep -q "^${UNIT_NAME}\.service"; then
    systemctl stop "$UNIT_NAME.service" 2>/dev/null || true
    systemctl disable "$UNIT_NAME.service" 2>/dev/null || true
    rm -f "/etc/systemd/system/${UNIT_NAME}.service"
    systemctl daemon-reload
    systemctl reset-failed "$UNIT_NAME.service" 2>/dev/null || true
    ok "Đã gỡ unit $UNIT_NAME.service"
else
    warn "Không tìm thấy unit $UNIT_NAME.service"
fi

# --- 2. Xoá code + venv -------------------------------------------------------
if [[ $KEEP_VENV -eq 1 ]]; then
    warn "Giữ lại virtualenv theo yêu cầu"
else
    rm -rf "$INSTALL_DIR"
    ok "Đã xoá $INSTALL_DIR"
fi

# --- 3. Xoá cấu hình + dữ liệu (chỉ khi --purge) -----------------------------
if [[ $PURGE -eq 1 ]]; then
    warn "Xoá cấu hình và DỮ LIỆU ĐO"
    rm -rf "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR"
    ok "Đã xoá $CONFIG_DIR, $DATA_DIR, $LOG_DIR"
else
    ok "Giữ nguyên cấu hình và dữ liệu tại $CONFIG_DIR, $DATA_DIR"
    echo "    (dùng --purge để xoá)"
fi

# --- 4. Xoá user --------------------------------------------------------------
if id -u "$SERVICE_USER" >/dev/null 2>&1; then
    userdel -r "$SERVICE_USER" 2>/dev/null || userdel "$SERVICE_USER" 2>/dev/null || true
    ok "Đã xoá tài khoản $SERVICE_USER"
fi

echo ""
echo "=============================================="
echo " Gỡ cài đặt hoàn tất"
echo "=============================================="
echo "  Kiểm tra: systemctl status $UNIT_NAME"
