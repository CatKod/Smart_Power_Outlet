# Cài đặt & vận hành — PC Agent

> Tài liệu này hướng dẫn cài PC Agent thành **dịch vụ nền chạy 24/7**.
> Khi gặp sự cố → xem [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).
>
> **Cập nhật: 2026-11-15**

---

## 0. Yêu cầu tiên quyết

| Hạng mục | Yêu cầu | Ghi chú |
|---|---|---|
| Hệ điều hành | Windows 10/11 **hoặc** Debian/Ubuntu/Raspberry Pi OS | Có hai bản cài đặt song song |
| Python | **3.9+** | Trên Windows: `py -3.11 -m venv` |
| Phần cứng | USB-TTL adapter + **PZEM-004T V3.0** | PZEM **phải** có nguồn lưới AC 220 V |
| Driver | CH340 / CP2102 / FTDI cho USB-TTL | Xem [`HARDWARE_PREP.md`](HARDWARE_PREP.md) |
| Quyền | Administrator (Windows) / sudo (Linux) | Bắt buộc để đăng ký service |

> ⚠️ **Điều kiện tiên quyết quan trọng nhất:** PZEM-004T **không phản hồi UART
> khi chưa có nguồn lưới AC 220 V** ở chân L/N. Thiếu nguồn → agent báo
> `SILENT` / `DEVICE_OFFLINE` dù mọi thứ khác đều đúng.

---

## 1. Chọn nhánh cài đặt

```
                    ┌─────────────────────────────────────┐
                    │  PC Agent cần đọc PZEM qua USB-TTL │
                    └──────────────┬──────────────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │                                         │
      Máy chủ rack Windows                     Máy chủ Linux / Pi
      (rack-01)                                (edge-01)
              │                                         │
     §2 Windows Service                       §3 systemd
     install_service.ps1                      install_linux.sh
```

---

## 2. Windows — cài thành Windows Service

### 2.1. Chuẩn bị

```powershell
# Cài Python 3.11+ nếu chưa có: https://www.python.org/downloads/
python --version
```

Kiểm tra driver USB-TTL: mở **Device Manager** → Ports (COM & LPT) → thấy
`USB-SERIAL CH340 (COM10)` hoặc tương tự.

### 2.2. Cài đặt

```powershell
# PowerShell với quyền Administrator (Start → gõ "PowerShell" → Run as administrator)
cd D:\GitHub\Smart_Power_Outlet\pc_agent\deploy
.\install_service.ps1
```

Hoặc mở API ra mạng LAN (cho Web Server / app Flutter truy cập từ máy khác):

```powershell
.\install_service.ps1 -ApiHost 0.0.0.0 -ApiPort 8000
```

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `-InstallDir` | `C:\SmartPowerOutlet` | Thư mục cài đặt |
| `-ApiHost` | `127.0.0.1` | Địa chỉ lắng nghe API |
| `-ApiPort` | `8000` | Cổng HTTP |
| `-SkipRecovery` | (tắt) | Không cấu hình tự khởi động lại khi lỗi |

### 2.3. Script làm gì

```
[1/6] Sao chép mã nguồn vào C:\SmartPowerOutlet
[2/6] Tạo virtualenv + cài pyserial, pywin32
[3/6] Ghi cấu hình ban đầu vào %ProgramData%\SmartPowerOutlet\config.json
[4/6] Đăng ký service (Delayed Auto-Start)
[5/6] Cấu hình crash recovery: restart 5s / 10s / 30s
[6/6] Mở firewall rule (chỉ khi bind ngoài localhost)
```

### 2.4. Xác minh

```powershell
sc query SmartPowerOutletAgent
# STATE : 4  RUNNING

curl.exe http://127.0.0.1:8000/api/health
```

Kết quả mong đợi (chứa version + git commit + build time):

```json
{
  "status": "ok",
  "version": {
    "package": "1.0.0",
    "git_commit": "a1b2c3d",
    "build_timestamp": "2026-11-15T13:20:00Z",
    "python": "3.11.9 (64-bit)"
  }
}
```

### 2.5. Vị trí file sau khi cài

| Đường dẫn | Nội dung |
|---|---|
| `C:\SmartPowerOutlet\pc_agent\` | Mã nguồn đã copy |
| `C:\SmartPowerOutlet\venv\` | Virtualenv + thư viện |
| `%ProgramData%\SmartPowerOutlet\config.json` | Cấu hình |
| `%ProgramData%\SmartPowerOutlet\api_token.txt` | Token xác thực API |
| `%ProgramData%\SmartPowerOutlet\data\telemetry.db` | CSDL telemetry |
| `%ProgramData%\SmartPowerOutlet\logs\agent.log` | Log (xoay vòng 10 MB × 10) |
| `%ProgramData%\SmartPowerOutlet\backup\` | Bản sao lưu tự động (giữ 7 bản) |

### 2.6. Chạy dưới tài khoản riêng (khuyến nghị)

Service mặc định chạy dưới `LocalSystem` (Session 0). Một số máy chủ **chặn
LocalSystem** đọc cổng COM. Nếu gặp lỗi *"Access is denied"* khi service
đọc cổng (nhưng chạy foreground thì được) → cài lại với tài khoản user:

```powershell
# Tài khoản phải đã đăng nhập ít nhất 1 lần
python C:\SmartPowerOutlet\pc_agent\src\pc_agent\deploy\windows_service.py `
    --username=".\TEN_DANG_NHAP" --password="MAT_KHAU" install
sc start SmartPowerOutletAgent
```

Chi tiết: [`TROUBLESHOOTING.md` §1.6](TROUBLESHOOTING.md#16-service-chạy-dưới-localsystem-không-đọc-được-com).

### 2.7. Gỡ cài đặt

```powershell
cd C:\SmartPowerOutlet\pc_agent\deploy
.\uninstall_service.ps1
```

---

## 3. Linux — cài thành systemd service

### 3.1. Cài đặt

```bash
cd /path/to/Smart_Power_Outlet/pc_agent/deploy
sudo ./install_linux.sh
```

Mở API ra LAN:

```bash
sudo ./install_linux.sh --api-host 0.0.0.0 --api-port 8000
```

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `--install-dir DIR` | `/opt/smartpower` | Thư mục cài đặt |
| `--api-host HOST` | `127.0.0.1` | Địa chỉ lắng nghe API |
| `--api-port PORT` | `8000` | Cổng HTTP |
| `--user USER` | `smartpower` | Tài khoản service |
| `--no-start` | (tắt) | Cài nhưng không start |

### 3.2. Script làm gì

```
1. Tạo user system `smartpower` + thêm vào nhóm `dialout` (đọc cổng serial)
2. Copy mã nguồn vào /opt/smartpower
3. Tạo virtualenv + cài pyserial
4. Ghi /etc/smartpower/config.json
5. Cài unit systemd (Restart=always, hardening, DeviceAllow cho /dev/ttyUSB*)
6. Mở firewall (ufw/firewalld) nếu bind ra LAN
7. enable + start
```

### 3.3. Xác minh

```bash
systemctl status smart-power-agent
systemctl is-enabled smart-power-agent     # → enabled
curl -s http://127.0.0.1:8000/api/health
journalctl -u smart-power-agent -f          # log trực tiếp
```

### 3.4. Vị trí file sau khi cài

| Đường dẫn | Nội dung |
|---|---|
| `/opt/smartpower/` | Mã nguồn + venv |
| `/etc/smartpower/config.json` | Cấu hình |
| `/var/lib/smartpower/telemetry.db` | CSDL telemetry |
| `/var/log/smartpower/` | Log |
| journal | `journalctl -u smart-power-agent` |

### 3.5. Gỡ cài đặt

```bash
sudo ./uninstall_linux.sh              # giữ cấu hình + dữ liệu
sudo ./uninstall_linux.sh --purge      # xoá cả cấu hình + dữ liệu
```

---

## 4. Cấu hình

File cấu hình: `%ProgramData%\SmartPowerOutlet\config.json` (Windows) hoặc
`/etc/smartpower/config.json` (Linux).

```json
{
  "schema_version": 1,
  "site_id": "site-01",
  "rack_id": "rack-01",
  "meter_id": "pdu-01",

  "port": "COM10",
  "usb_location": "1-4:x.3",
  "slave_address": 1,
  "baudrate": 9600,
  "poll_interval_s": 1.0,

  "power_threshold_w": 25000,
  "current_threshold_a": 10.0,
  "voltage_min_v": 198.0,
  "voltage_max_v": 242.0,
  "offline_after_s": 30.0,

  "api_host": "127.0.0.1",
  "api_port": 8000,
  "mqtt_host": null,
  "raw_retention_days": 14,
  "hourly_retention_days": 365
}
```

### 4.1. Các ngưỡng cảnh báo

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `power_threshold_w` | 25 000 W | Vượt → sự kiện `OVER_POWER` |
| `current_threshold_a` | 10.0 A | Vượt → sự kiện `OVER_CURRENT` |
| `voltage_min_v` / `voltage_max_v` | 198 / 242 V | Ngoài dải → `OVER_VOLTAGE` / `UNDER_VOLTAGE` |
| `offline_after_s` | 30 s | Im lặng quá → `DEVICE_OFFLINE` |

> Ngưỡng điện áp được siết về **198–242 V** (220 V ± 10%) theo yêu cầu
> đặc tả tủ rack. Biên rộng hơn (180–260 V) sẽ bỏ lọt sự cố điện áp lệch.

### 4.2. Cổng serial tự động

Agent **không** ghi đè cấu hình cổng trừ khi đã **xác minh được thiết bị
thật** (đúng function code `0x04`, CRC hợp lệ, điện áp 80–260 V, tần số
45–65 Hz). Cổng hỏng / bị chiếm / PZEM chưa có nguồn AC → giữ nguyên cấu
hình đã nhớ.

Ngoài ra agent ghi nhớ **`usb_location`** (VD `1-4:x.3`) — ổn định theo vị
trí cổng USB, không đổi khi Windows cấp lại số COM.

### 4.3. Xác thực API

Khi `api_host` **không phải** `127.0.0.1` / `localhost`, API **bắt buộc**
xác thực:

```powershell
# Token được sinh tự động ở lần chạy đầu
Get-Content "$env:ProgramData\SmartPowerOutlet\api_token.txt"
```

```bash
cat /etc/smartpower/api_token.txt
```

Dùng token:

```bash
curl -H "Authorization: Bearer $TOKEN" http://192.168.1.50:8000/api/status
curl "http://192.168.1.50:8000/api/status?token=$TOKEN"     # cho trình duyệt
```

Xoay token (làm mất truy cập cho client dùng token cũ):

```powershell
python -m pc_agent --rotate-token
```

---

## 5. Nâng cấp

### 5.1. Windows

```powershell
# 1. Dừng service
Stop-Service SmartPowerOutletAgent

# 2. Cài lại (script tự dừng + gỡ bản cũ)
cd D:\GitHub\Smart_Power_Outlet\pc_agent\deploy
.\install_service.ps1

# 3. Kiểm tra
sc query SmartPowerOutletAgent
```

> Script giữ nguyên `config.json` và `data/` — nâng cấp **không** mất dữ liệu.

### 5.2. Linux

```bash
cd /path/to/Smart_Power_Outlet/pc_agent/deploy
sudo ./install_linux.sh          # script tự dừng service cũ trước khi copy code
systemctl status smart-power-agent
```

### 5.3. Kiểm tra phiên bản đang chạy

```bash
curl -s http://127.0.0.1:8000/api/health | python -m json.tool
```

Trường `version.git_commit` cho biết đúng commit nào đang chạy — dùng khi
báo cáo lỗi để GVHD đối chiếu.

---

## 6. Kiểm tra sau cài đặt (checklist)

| # | Bước | Lệnh | Mong đợi |
|---|---|---|---|
| 1 | Service đang chạy | `sc query SmartPowerOutletAgent` | `STATE : 4 RUNNING` |
| 2 | API sống | `curl http://127.0.0.1:8000/api/health` | `"status": "ok"` + version |
| 3 | Tự lên sau reboot | reboot → lặp lại bước 1 | `RUNNING` (không ai đăng nhập) |
| 4 | Thấy thiết bị | `python -m pc_agent --exhaustive-scan` | `FOUND port=COM10 address=0x01` |
| 5 | Có số đo | `curl -H "Authorization: Bearer $TOKEN" .../api/metrics` | `voltage_v` ≈ 220 |
| 6 | Dashboard | mở `http://127.0.0.1:8000/` | 6 thẻ số + biểu đồ |
| 7 | Ghi DB | xem `telemetry.db` tăng dần | số dòng `telemetry_raw` tăng |
| 8 | Backup tự động | `Get-ChildItem ...\backup` | có file `.db` mới |
| 9 | Token (nếu mở LAN) | `curl .../api/status` không token | `401` |

> Bước 3 là **bắt buộc** theo yêu cầu GVHD: *"Các tiến trình máy chủ phải viết
> service, không có chuyện phải bấm Enter mới chạy"*.

---

## 7. Bảo trì định kỳ

| Việc | Tần suất | Cách làm |
|---|---|---|
| Kiểm tra log | hàng ngày | `Get-Content ...\logs\agent.log -Tail 50` |
| Kiểm tra dung lượng | hàng tuần | `Get-ChildItem ...\SmartPowerOutlet -Recurse | Measure-Object -Sum Length` |
| Nén DB | hàng tháng | dừng service → `VACUUM` → start lại |
| Kiểm tra backup | hàng tuần | xem thư mục `backup/` có 7 bản mới nhất |
| Xoay token | mỗi 6 tháng | `python -m pc_agent --rotate-token` |

### 7.1. Soak test (kiểm tra rò rỉ dài hạn)

```powershell
cd pc_agent
python tools\soak_test.py --duration 86400 --interval 300
```

Tool này đo kích thước `telemetry.db` / `-wal` / `-shm`, RSS bộ nhớ, số dòng
raw, và so với ngân sách đề ra. Xem [`TROUBLESHOOTING.md` §1.10](TROUBLESHOOTING.md#110-db-phinh-to).

---

## 8. Gỡ cài đặt

### Windows

```powershell
cd C:\SmartPowerOutlet\pc_agent\deploy
.\uninstall_service.ps1
```

### Linux

```bash
sudo ./uninstall_linux.sh              # giữ dữ liệu
sudo ./uninstall_linux.sh --purge      # xoá cả dữ liệu
```
