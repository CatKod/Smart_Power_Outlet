#!/usr/bin/env bash
# =============================================================================
#  Cài PC Agent thành systemd service trên Linux (Debian/Ubuntu/Raspberry Pi OS)
#
#  Dùng:
#      sudo ./install_linux.sh
#      sudo ./install_linux.sh --api-host 0.0.0.0 --api-port 8000
#
#  Script sẽ:
#      1. Tạo user `smartpower` (không login) + thêm vào nhóm `dialout`
#      2. Copy mã nguồn vào /opt/smartpower
#      3. Tạo virtualenv + cài phụ thuộc
#      4. Ghi cấu hình khởi tạo vào /etc/smartpower/config.json
#      5. Cài unit systemd (Restart=always, hardening)
#      6. enable + start
#
#  Gỡ bỏ:  sudo ./uninstall_linux.sh
# =============================================================================
set -euo pipefail

# --- Tham số ------------------------------------------------------------------
INSTALL_DIR="/opt/smartpower"
CONFIG_DIR="/etc/smartpower"
DATA_DIR="/var/lib/smartpower"
LOG_DIR="/var/log/smartpower"
SERVICE_USER="smartpower"
SERVICE_GROUP="dialout"
UNIT_NAME="smart-power-agent"
API_HOST="127.0.0.1"
API_PORT="8000"

usage() {
    cat <<EOF
Dùng: sudo $0 [tùy chọn]

Tùy chọn:
  --install-dir DIR   Thư mục cài đặt (mặc định: $INSTALL_DIR)
  --api-host HOST     Địa chỉ lắng nghe API (mặc định: $API_HOST)
  --api-port PORT     Cổng HTTP API (mặc định: $API_PORT)
  --user USER         Tài khoản service (mặc định: $SERVICE_USER)
  --no-start          Cài nhưng không start service
  -h, --help          Hiện trợ giúp
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        --api-host)    API_HOST="$2";    shift 2 ;;
        --api-port)    API_PORT="$2";    shift 2 ;;
        --user)        SERVICE_USER="$2"; shift 2 ;;
        --no-start)    NO_START=1;       shift ;;
        -h|--help)     usage; exit 0 ;;
        *) echo "Tham số lạ: $1" >&2; usage; exit 1 ;;
    esac
done

# --- Màu log ------------------------------------------------------------------
if [[ -t 1 ]]; then
    C_CYAN=$'\033[36m'; C_YELLOW=$'\033[33m'; C_GREEN=$'\033[32m'; C_RED=$'\033[31m'; C_OFF=$'\033[0m'
else
    C_CYAN=""; C_YELLOW=""; C_GREEN=""; C_RED=""; C_OFF=""
fi
step() { echo "${C_CYAN}==>${C_OFF} $*"; }
ok()   { echo "${C_GREEN}  ✓${C_OFF} $*"; }
warn() { echo "${C_YELLOW}  !${C_OFF} $*"; }
die()  { echo "${C_RED}LỖI:${C_OFF} $*" >&2; exit 1; }

step "Cài PC Agent thành systemd service"
echo "  Thư mục cài đặt : $INSTALL_DIR"
echo "  API             : http://${API_HOST}:${API_PORT}/"

# --- 0. Kiểm tra điều kiện tiên quyết ----------------------------------------
[[ $EUID -eq 0 ]] || die "Cần chạy với quyền root: sudo $0"
command -v systemctl >/dev/null 2>&1 || die "Không tìm thấy systemd (máy này dùng init khác?)."
command -v python3   >/dev/null 2>&1 || die "Không tìm thấy python3. Cài: apt install python3 python3-venv"

# Thư mục chứa script này = gốc repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PKG_DIR="$REPO_ROOT/pc_agent"
[[ -d "$PKG_DIR" ]] || die "Không tìm thấy package tại $PKG_DIR. Chạy script từ trong repo."

# --- 1. Tạo user -------------------------------------------------------------
step "Tạo tài khoản service '$SERVICE_USER'"
if id -u "$SERVICE_USER" >/dev/null 2>&1; then
    ok "Tài khoản đã tồn tại"
else
    useradd --system --create-home --home-dir "/home/$SERVICE_USER" \
            --shell /usr/sbin/nologin "$SERVICE_USER"
    ok "Đã tạo tài khoản system"
fi

# Nhóm dialout = quyền đọc/ghi cổng serial
if getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
    usermod -aG "$SERVICE_GROUP" "$SERVICE_USER"
    ok "Đã thêm vào nhóm '$SERVICE_GROUP' (đọc cổng serial)"
else
    warn "Nhóm '$SERVICE_GROUP' không tồn tại — cần tạo thủ công: groupadd $SERVICE_GROUP"
fi

# --- 2. Copy mã nguồn ---------------------------------------------------------
step "Sao chép mã nguồn vào $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
if [[ -d "$INSTALL_DIR/pc_agent" ]]; then
    rm -rf "$INSTALL_DIR/pc_agent"
fi
cp -r "$PKG_DIR" "$INSTALL_DIR/pc_agent"
mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR"

# --- 3. Virtualenv + phụ thuộc ------------------------------------------------
step "Tạo virtualenv + cài phụ thuộc"
VENV_DIR="$INSTALL_DIR/venv"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3 -m venv "$VENV_DIR" || die "Không tạo được venv (cần python3-venv)."
fi
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install "pyserial>=3.5" --quiet
"$VENV_DIR/bin/pip" install -e "$INSTALL_DIR/pc_agent" --quiet
ok "Python: $("$VENV_DIR/bin/python" --version)"

# --- 4. Cấu hình khởi tạo ------------------------------------------------------
step "Ghi cấu hình khởi tạo"
CONFIG_PATH="$CONFIG_DIR/config.json"
if [[ -f "$CONFIG_PATH" ]]; then
    ok "Cấu hình đã tồn tại, giữ nguyên: $CONFIG_PATH"
else
    cat > "$CONFIG_PATH" <<EOF
{
  "schema_version": 1,
  "site_id": "site-01",
  "rack_id": "rack-01",
  "meter_id": "pdu-01",
  "port": null,
  "usb_location": null,
  "slave_address": 1,
  "baudrate": 9600,
  "poll_interval_s": 1.0,
  "power_threshold_w": 25000,
  "current_threshold_a": 10.0,
  "voltage_min_v": 198.0,
  "voltage_max_v": 242.0,
  "offline_after_s": 30.0,
  "api_host": "$API_HOST",
  "api_port": $API_PORT,
  "api_token": null,
  "mqtt_host": null,
  "mqtt_port": 1883,
  "mqtt_username": null,
  "mqtt_password": null,
  "raw_retention_days": 14,
  "hourly_retention_days": 365,
  "last_verified_utc": null,
  "extra": {}
}
EOF
    ok "Đã tạo $CONFIG_PATH"
fi

# --- 5. Unit systemd ----------------------------------------------------------
step "Cài unit systemd '$UNIT_NAME'"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME.service"
cp "$SCRIPT_DIR/smart-power-agent.service" "$UNIT_PATH"
# systemd từ chối unit world-writable/executable → siết quyền.
chmod 644 "$UNIT_PATH"

# Bảo đảm unit khớp với các đường dẫn đã chọn
sed -i "s#^WorkingDirectory=.*#WorkingDirectory=$INSTALL_DIR#" "$UNIT_PATH"
sed -i "s#^ExecStart=.*#ExecStart=$VENV_DIR/bin/python -m pc_agent --no-console-log#" "$UNIT_PATH"
sed -i "s#^User=.*#User=$SERVICE_USER#" "$UNIT_PATH"
sed -i "s#^Group=.*#Group=$SERVICE_GROUP#" "$UNIT_PATH"
sed -i "s#^Environment=SMARTPOWER_CONFIG_DIR=.*#Environment=SMARTPOWER_CONFIG_DIR=$CONFIG_DIR#" "$UNIT_PATH"
sed -i "s#^Environment=SMARTPOWER_DATA_DIR=.*#Environment=SMARTPOWER_DATA_DIR=$DATA_DIR#" "$UNIT_PATH"
sed -i "s#^Environment=SMARTPOWER_LOG_DIR=.*#Environment=SMARTPOWER_LOG_DIR=$LOG_DIR#" "$UNIT_PATH"

systemctl daemon-reload
systemctl enable "$UNIT_NAME.service" >/dev/null 2>&1
ok "Unit đã cài và enable"

# --- 6. Firewall (nếu bind ra LAN) -------------------------------------------
if [[ "$API_HOST" != "127.0.0.1" && "$API_HOST" != "localhost" ]]; then
    step "Mở firewall cho cổng $API_PORT"
    if command -v ufw >/dev/null 2>&1; then
        ufw allow "$API_PORT/tcp" >/dev/null 2>&1 && ok "ufw: đã mở cổng $API_PORT"
    elif command -v firewall-cmd >/dev/null 2>&1; then
        firewall-cmd --permanent --add-port="$API_PORT/tcp" >/dev/null 2>&1
        firewall-cmd --reload >/dev/null 2>&1
        ok "firewalld: đã mở cổng $API_PORT"
    else
        warn "Không tìm thấy ufw/firewalld — mở cổng $API_PORT thủ công nếu cần."
    fi
fi

# --- 7. Start -----------------------------------------------------------------
if [[ "${NO_START:-0}" != "1" ]]; then
    step "Khởi động service"
    systemctl restart "$UNIT_NAME.service"
    sleep 3
    STATUS="$(systemctl is-active "$UNIT_NAME.service" || true)"
    if [[ "$STATUS" == "active" ]]; then
        ok "Service đang chạy"
    else
        warn "Service chưa active (=$STATUS). Xem: journalctl -u $UNIT_NAME -n 50"
    fi
fi

cat <<EOF

${C_GREEN}==============================================${C_OFF}
${C_GREEN} Cài đặt thành công${C_OFF}
${C_GREEN}==============================================${C_OFF}
  Trạng thái  : systemctl status $UNIT_NAME
  API         : http://${API_HOST}:${API_PORT}/
  Cấu hình    : $CONFIG_PATH
  Log         : journalctl -u $UNIT_NAME -f
  Dữ liệu    : $DATA_DIR

  Bật tự khởi động: systemctl is-enabled $UNIT_NAME
  Gỡ bỏ          : sudo ./uninstall_linux.sh
EOF
