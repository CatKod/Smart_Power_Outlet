# Khắc phục sự cố vận hành — PC Agent

> Bổ sung cho [`docs/operations/INSTALL.md`](INSTALL.md).
> Tài liệu này ghi lại **các lỗi thật đã gặp** trong quá trình phát triển và
> test, không phải mô tả lý thuyết.
>
> **Cập nhật: 2026-11-15** — sau khi đóng các task Giai đoạn 1 của GR2.

---

## 0. Bảng tra cứu nhanh

| Triệu chứng | Nguyên nhân thường gặp | Mục |
|---|---|---|
| `DEVICE_OFFLINE` liên tục, log "không phản hồi UART" | **PZEM chưa có nguồn 220 VAC** ở chân L/N | [1.1](#11-pzem-khong-phan-hoi-uart) |
| `PORT_BUSY` / "Access is denied" | Tiến trình khác (PuTTY, PlatformIO Monitor) đang giữ cổng | [1.2](#12-port_busy--access-is-denied) |
| "Cổng serial không tồn tại" | USB-TTL bị rút | [1.3](#13-thiet-bi-bi-rut-khoi-cong) |
| Agent tìm được cổng nhưng đổi số COM mỗi lần cắm | Windows đổi số COM theo cổng USB | [1.4](#14-doi-so-com-sau-khi-rut-cam) |
| Service không lên sau reboot | Chưa cài đúng, hoặc lỗi quyền | [1.5](#15-service-khong-len) |
| Service lên nhưng không đọc được cổng COM | Quyền COM dưới LocalSystem | [1.6](#16-service-chay-duoi-localsystem-khong-doc-duoc-com) |
| API trả `401 Unauthorized` | Chưa gửi token | [1.7](#17-api-tra-401-unauthorized) |
| API trả `401` dù đã lưu token | Token bị xoay / sai file | [1.8](#18-token-bi-xoay-hoac-sai) |
| Log đầy ổ đĩa, lặp lại cùng 1 lỗi | Chưa bật rate-limit (đã có A-9-2) | [1.9](#19-log-day-ung-dia) |
| DB phình to bất thường | Retention chưa chạy | [1.10](#110-db-phinh-to) |
| `python.exe` không tìm thấy khi service khởi động | Venv bị xoá / Python nâng cấp | [1.11](#111-service-khong-chay-duoc-python-khong-tim-thay) |

---

## 1. Các lỗi đã biết

### 1.1 PZEM không phản hồi UART

**Dấu hiệu:**
```
[WARNING] pc_agent.poller: Chưa tìm thấy PZEM-004T — sẽ thử lại sau 5s
[CRITICAL] DEVICE_OFFLINE — Không nhận được dữ liệu trong 30s
```
Log của `discovery` có thêm: `SILENT — Cổng mở được nhưng thiết bị không phản hồi`.

**Nguyên nhân (quan trọng nhất, hay bị nhầm là lỗi phần mềm):**
> **PZEM-004T V3.0 KHÔNG phản hồi trên UART khi chưa có nguồn lưới AC 220 V ở chân L/N.**
> Quang họp ( opto-isolator ) của nó nằm ở phía AC. Mất điện lưới → UART im lặng → tưởng hỏng máy.

**Cách kiểm tra (theo thứ tự):**

| Bước | Kiểm tra | Kết quả mong đợi |
|---|---|---|
| 1 | Cầu dao/ổ cắm có cấp 220 V cho PZEM không? | Đèn PZEM sáng, màn hình hiện ~220 V |
| 2 | Dây **TX của PZEM → RX của USB-TTL** (chéo) | — |
| 3 | Dây **RX của PZEM → TX của USB-TTL** | — |
| 4 | GND chung giữa PZEM và USB-TTL | Bắt buộc |
| 5 | Adapter USB-TTL **3.3 V tolerant** | Adapter 5 V-only sẽ đọc sai |
| 6 | Địa chỉ slave đúng `0x01`? | PZEM mặc định `0x01` |

**Lệnh chẩn đoán:**
```powershell
cd pc_agent
python -m pc_agent --exhaustive-scan
```
Kết quả mong đợi: `FOUND port=COM10 address=0x01 location=...`

**Nếu vẫn không thấy:** thử tắt/bật cầu dao vài lần (PZEM cần vài giây để khởi tạo), rồi chạy lại lệnh trên.

---

### 1.2 `PORT_BUSY` / Access is denied

**Dấu hiệu:**
```
[WARNING] pc_agent.poller: Cổng đang bị chiếm: Cổng COM10 đang bị tiến trình khác chiếm (Access is denied)...
```

**Nguyên nhân:** Windows chỉ cho **một** tiến trình giữ một cổng COM tại một thời điểm. Đây là hệ quả trực tiếp của yêu cầu *"Các tiến trình máy chủ phải viết service"* — PC Agent là tiến trình **duy nhất** được giữ cổng.

**Cách xử lý:**

```powershell
# 1. Tìm tiến trình nào đang giữ cổng
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "COM10" } |
  Select-Object ProcessId, Name, CommandLine

# 2. Liệt kê handle
Get-Process | Where-Object { $_.ProcessName -match "putty|platformio|python|arduino" } |
  Select-Object Id, ProcessName
```

Đóng: PuTTY, PlatformIO Serial Monitor, Arduino Serial Monitor, mọi cửa sổ `python -m pc_agent` khác.

**⚠️ Đây KHÔNG phải lỗi nguồn hay lỗi dây.** Agent đã phân loại đúng:
`PORT_BUSY` (tiến trình khác giữ) ≠ `PORT_MISSING` (thiết bị bị rút) ≠ `SILENT` (không có nguồn AC).

---

### 1.3 Thiết bị bị rút khỏi cổng

**Dấu hiệu:**
```
[WARNING] pc_agent.poller: Thiết bị đã bị rút khỏi cổng — sẽ quét lại khi cắm lại.
```
hoặc `PORT_MISSING — Cổng serial không tồn tại`.

**Cách xử lý:** cắm lại USB-TTL. Agent tự quét lại sau 5 giây, **không cần** can thiệp tay.

**Lưu ý khi test:** rút/cắm nhanh có thể làm ổ USB mất nguồn và làm sập laptop. Nên dùng **USB hub có nguồn** (H-11) hoặc cáp nối dài.

---

### 1.4 Đổi số COM sau khi rút/cắm

**Hiện tượng:** cắm vào cổng USB khác → Windows cấp số COM khác (COM10 → COM12).

**Cơ chế đã xử lý:** agent lưu **cả** `usb_location` (vd `1-4:x.3`) trong cấu hình. `usb_location` ổn định theo vị trí cổng USB, không đổi theo số COM. Khi quét, agent ưu tiên cổng có `usb_location` khớp → tự tìm lại đúng thiết bị.

**Kiểm tra cấu hình đã nhớ:**
```powershell
Get-Content "$env:ProgramData\SmartPowerOutlet\config.json"
```
```json
{
  "port": "COM10",
  "usb_location": "1-4:x.3",
  "slave_address": 1
}
```

**Chính sách chống flapping:** cấu hình **chỉ** được ghi đè sau khi đã *xác minh được thiết bị thật* (đúng function code `0x04`, CRC hợp lệ, điện áp 80–260 V, tần số 45–65 Hz). Cổng hỏng / bị chiếm / chưa có nguồn AC → **không** ghi đè cấu hình đã nhớ.

---

### 1.5 Service không lên

**Chẩn đoán:**
```powershell
sc query SmartPowerOutletAgent
# STATE : 1  STOPPED / 4  RUNNING
```

| `STATE` | Nguyên nhân | Xử lý |
|---|---|---|
| `STOPPED` ngay sau reboot | Chưa bật auto-start, hoặc service lỗi ngay khi khởi động | Xem log + kiểm tra `FailureActions` |
| `START_PENDING` kẹt | Tiến trình treo (thường do quét cổng lâu) | `sc stop`, xem log |
| Không có service trong danh sách | Chưa cài | Chạy lại `install_service.ps1` (Administrator) |

**Cấu hình auto-start:**
```powershell
sc qc SmartPowerOutletAgent | Select-String "START_TYPE"
# START_TYPE : 2 -- AUTO_START (DELAYED)
```

**Cấu hình tự khởi động lại khi chết:**
```powershell
sc qfailure SmartPowerOutletAgent
# FAILURE_ACTIONS: RESTART/5000 RESTART/10000 RESTART/30000
sc qfailureflag SmartPowerOutletAgent
# FAILURE_FLAG : 1  (failure actions enabled)
```

**Xem log:**
```powershell
Get-Content "$env:ProgramData\SmartPowerOutlet\logs\agent.log" -Tail 50
```

---

### 1.6 Service chạy dưới LocalSystem không đọc được COM

**Dấu hiệu:**
```
[WARNING] pc_agent.poller: Cổng đang bị chiếm: ... Access is denied
```
**nhưng** khi chạy `python -m pc_agent` ở foreground thì lại đọc được bình thường.

**Nguyên nhân:** Service chạy ở **Session 0** dưới tài khoản `LocalSystem`. Tài khoản này có quyền khác với tài khoản user thông thường đối với cổng COM, và **không** có quyền truy cập USB/serial theo cách user được.

**Cách xử lý (theo thứ tự ưu tiên):**

**Cách 1 — Chạy service dưới tài khoản user thay vì LocalSystem:**
```powershell
# Cài lại với tài khoản cụ thể
python pc_agent\src\pc_agent\deploy\windows_service.py --username=".\YOUR_USER" --password="..." install
sc start SmartPowerOutletAgent
```
> Tài khoản này phải **đã đăng nhập ít nhất một lần** để Windows tạo profile (cần cho `%ProgramData%` và registry).

**Cách 2 — Thêm quyền cho LocalSystem trên cổng COM:**
Dùng `DevCon` (`devcon.exe`) hoặc công cụ quản lý quyền của thiết bị USB-Serial trong Device Manager → Properties → Permissions → thêm `SYSTEM`.

**Cách 3 — Chấp nhận chạy foreground (chỉ dùng để debug):**
```powershell
python -m pc_agent
```

> ⚠️ Yêu cầu của GVHD là *"Các tiến trình máy chủ phải viết service, không có chuyện phải bấm Enter mới chạy"* → **Cách 1 là hướng đúng cho sản phẩm**, Cách 2 là phương án dự phòng.

---

### 1.7 API trả `401 Unauthorized`

**Dấu hiệu:** trình duyệt hiện "Cần xác thực", `curl` trả 401.

**Nguyên nhân:** API đang lắng nghe **ngoài localhost** (`api_host` ≠ `127.0.0.1`) → xác thực là bắt buộc (A-8-6).

**Cách xử lý:**

```powershell
# 1. Đọc token
Get-Content "$env:ProgramData\SmartPowerOutlet\api_token.txt"

# 2. Gọi API kèm token
$token = (Get-Content "$env:ProgramData\SmartPowerOutlet\api_token.txt").Trim()
curl.exe -H "Authorization: Bearer $token" http://192.168.1.50:8000/api/metrics

# 3. Hoặc dùng query string (tiện cho trình duyệt)
curl.exe "http://192.168.1.50:8000/api/metrics?token=$token"
```

Mở dashboard trong trình duyệt:
```
http://192.168.1.50:8000/?token=<token>
```

> `/api/health` là endpoint **công khai** (không cần token) — để monitor kiểm tra sống mà không phải giữ token.

---

### 1.8 Token bị xoay hoặc sai

**Triệu chứng:** trước đó dùng được, giờ 401.

**Cách xử lý — xoay token:**
```powershell
python -m pc_agent --rotate-token
```
Hoặc qua API (cần token cũ):
```powershell
curl.exe -X POST -H "Authorization: Bearer $token" http://127.0.0.1:8000/api/config/token
```

Token mới ghi vào `%ProgramData%\SmartPowerOutlet\api_token.txt`.

> **Lưu ý:** `--rotate-token` sẽ làm mọi client đang dùng token cũ mất truy cập. Cần cập nhật lại link/token cho Web Server và app Flutter.

---

### 1.9 Log đầy ổ đĩa

**Hiện trạng:** đã có cơ chế chống (A-9-2) — `RateLimitFilter` gom các log lặp lại theo chữ ký thông điệp trong cửa sổ 60 s. Log đầy 1 lần, các lần sau bị chặn và đếm số lần.

**Nếu vẫn thấy log lặp:** kiểm tra xem có logger nào tự gắn handler riêng (bỏ qua bộ lọc ở root) hay không.

**Dung lượng log tối đa:** 10 MB × 10 file = 100 MB trong `%ProgramData%\SmartPowerOutlet\logs\`.

```powershell
Get-ChildItem "$env:ProgramData\SmartPowerOutlet\logs" | Measure-Object -Sum Length
```

---

### 1.10 DB phình to

**Kiểm tra:**
```powershell
Get-ChildItem "$env:ProgramData\SmartPowerOutlet\data"
# telemetry.db, telemetry.db-wal, telemetry.db-shm
```

**Cơ chế retention (đã có):**
- `telemetry_raw` — giữ **14 ngày**, dọn mỗi giờ
- `telemetry_hourly` — giữ **365 ngày**
- Tổng hợp theo giờ chạy mỗi 5 phút

**Đổi thời hạn:** sửa `raw_retention_days` / `hourly_retention_days` trong `config.json`, rồi restart service.

**Nén DB sau khi dọn:**
```powershell
python -c "import sqlite3; c=sqlite3.connect(r'%ProgramData%\SmartPowerOutlet\data\telemetry.db'); c.execute('VACUUM'); c.close()"
```
> VACUUM cần service đang **dừng** (khóa file DB).

---

### 1.11 Service không chạy được — Python không tìm thấy

**Dấu hiệu trong Event Viewer:**
```
The service process could not connect to the service controller.
```
hoặc log: `FileNotFoundError: ... python.exe`

**Nguyên nhân:** `ImagePath` của service trỏ tới `python.exe` trong venv. Nếu venv bị xoá hoặc Python được nâng cấp → đường dẫn không còn hợp lệ.

**Cách xử lý:** cài lại service (script sẽ ghi `ImagePath` mới):
```powershell
# Gỡ bỏ
python pc_agent\src\pc_agent\deploy\windows_service.py remove
# Cài lại (Administrator)
powershell -ExecutionPolicy Bypass -File pc_agent\src\pc_agent\deploy\install_service.ps1
```

---

## 2. Test thực địa

> Bảng này điền **kết quả thật** sau khi chạy test trên máy. Trạng thái hiện tại: chưa có thiết bị nào cắm.

| Mã | Kịch bản | Cách chạy | Kết quả mong đợi | Kết quả thật |
|---|---|---|---|---|
| **A-4-8** | Cài service → reboot → service tự lên | `install_service.ps1` (Admin) → reboot → `sc query` | `STATE : 4 RUNNING` ngay sau reboot, không ai đăng nhập | ⬜ chờ |
| **A-4-9** | Đọc COM dưới LocalSystem | Cắm PZEM + USB-TTL (có 220 VAC) → `sc query` | Có mẫu đo trong `/api/metrics` | ⬜ chờ |
| **A-7-5** | Ngưỡng cảnh báo | Cắm H-02 (LED), rồi H-03 (bóng sợi đốt) | `OVER_POWER`/`OVER_CURRENT` vào `events`, tự đóng khi bỏ tải | ⬜ chờ |
| **A-9-5** | Rút/cắm USB-TTL giữa lúc chạy | Rút rồi cắm lại | Ghi `DEVICE_OFFLINE` → tự reconnect → ghi tiếp | ⬜ chờ |
| **A-9-6** | Cổng bị chiếm | Mở PuTTY giữ cổng | Agent báo `PORT_BUSY` (không báo lỗi nguồn) | ⬜ chờ |
| **A-5-4** | systemd | `systemctl enable --now` | `is-enabled` = `enabled`, tự lên sau reboot | ⬜ chờ |
| **B-4** | Firmware ESP32-S3 | Flash board + relay + PZEM #2 | Cấu hình WiFi qua điện thoại, đọc được PZEM #2 | ⬜ chờ |
| **B-5** | Vòng lặp khép kín | Bật tải vượt ngưỡng | ESP32 cắt relay → PZEM #1 thấy P → 0 | ⬜ chờ |

---

## 3. Lệnh chẩn đoán tổng hợp

```powershell
# --- Trạng thái service ---
sc query SmartPowerOutletAgent
Get-Content "$env:ProgramData\SmartPowerOutlet\logs\agent.log" -Tail 50

# --- Cấu hình đang dùng ---
Get-Content "$env:ProgramData\SmartPowerOutlet\config.json"

# --- Quét thiết bị (chẩn đoán cổng) ---
cd pc_agent
python -m pc_agent --exhaustive-scan

# --- Chạy foreground để xem log console ---
python -m pc_agent --no-console-log:$false

# --- Chạy thử không cần phần cứng ---
python -m pc_agent --simulate

# --- API ---
$token = (Get-Content "$env:ProgramData\SmartPowerOutlet\api_token.txt" -EA SilentlyContinue).Trim()
curl.exe http://127.0.0.1:8000/api/health
curl.exe -H "Authorization: Bearer $token" http://127.0.0.1:8000/api/status

# --- Dung lượng ---
Get-ChildItem "$env:ProgramData\SmartPowerOutlet" -Recurse | Measure-Object -Sum Length
```

### Linux

```bash
systemctl status smart-power-agent
journalctl -u smart-power-agent -n 100 --no-pager
systemctl is-enabled smart-power-agent
cat ~/.config/smartpoweroutlet/config.json
```

---

## 4. Khi nào cần nâng lên GVHD

| Triệu chứng | Vì sao cần hỏi thầy |
|---|---|
| Yêu cầu Web Server đọc serial **trực tiếp** | Xung đột với mô hình 3 thành phần (mục 1 của `ROADMAP.md`) — Windows chỉ cho 1 tiến trình giữ COM. Đề xuất phương án "serial ↔ HTTP bridge" |
| Thầy yêu cầu nhiều PZEM trong 1 rack | Cần thêm 1 cổng serial + `meter_id` — kiến trúc đã hỗ trợ, cần mở rộng poller |
| Yêu cầu xuất CSV / báo cáo định kỳ | Có thể làm bằng `GET /api/history` + `resolution=hourly` |
| Thầy muốn Web Server trên máy khác (không phải máy chủ rack) | Cần mở API ra LAN → **bắt buộc** xác thức bằng token (đã có) |
