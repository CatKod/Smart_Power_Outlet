# Smart Power Outlet — Lộ trình công việc

> **Cập nhật: 2026-11-15** · Trạng thái: **GR2 Tuần 2** · Lần sửa này viết lại toàn bộ lộ trình theo phản hồi của GVHD (Thầy Nguyễn Đức Tiến) trong buổi nộp báo cáo GR2 Tuần 1.
>
> **Thay đổi lớn so với lộ trình cũ:** trọng tâm chuyển từ *thư viện Arduino WiFi* sang **Electronic PC Agent** — một dịch vụ nền (Windows Service / Linux daemon) chạy 24/7 trên máy chủ, giám sát năng lượng PZEM-004T cho một tổ hợp máy chủ trong tủ rack. Phần ESP32 vẫn nằm trong **phạm vi GR2** nhưng bị **lùi xuống sau** (ưu tiên `P1`, làm sau khi Track A đạt DoD) theo chỉ đạo *"em có thì hoãn cái esp32 lại"* của thầy.

---

## 0. Phản hồi của GVHD và cách đáp ứng

| # | Thầy yêu cầu / nhận xét | Cách đáp ứng | Trạng thái |
|---|---|---|---|
| 1 | Coi PZEM-004T là một **tính năng**: cần **PC Agent** chạy trên máy tính | Xây dựng `pc_agent/` — package Python chuyên dụng cho PC Agent | **Đã có khung, đang hoàn thiện** |
| 2 | Lý giải: PC Agent cài lên **máy chủ**, giám sát năng lượng **1 tổ hợp máy chủ trong tủ rack** | Mô hình hoá `site_id` → `rack_id` → `meter_id` trong cấu hình và trong bảng telemetry | **Đã có trong schema** |
| 3 | Trên Windows: lập trình **service** chạy 24/24 **không cần đăng nhập**; trên Linux dùng **daemon/service** | `pc_agent/src/pc_agent/deploy/windows_service.py` (pywin32) + `pc_agent/deploy/smart-power-agent.service` (systemd) | **Đã có, chưa test trên máy thật** |
| 4 | Service **không có giao diện**, phải **tự detect cổng COM**, **gửi thử lệnh** xem cổng trả lời đúng không | `discovery.py`: 4 bậc dò, xác minh frame + CRC + giá trị điện lưới hợp lý | **Đã có** |
| 5 | **Tự lưu cổng COM đúng** để lần sau khỏi mất thời gian | Anti-Flapping Cache trong `%ProgramData%\SmartPowerOutlet\config.json` | **Đã có** |
| 6 | "Các tiến trình máy chủ phải viết service, **không có chuyện phải bấm Enter mới chạy**" | Cơ chế SCM auto-start (delayed) + `FailureActions` tự khởi động lại 5s/10s/30s | **Đã có** |
| 7 | Thiếu **mô hình tổng quát** — thầy cần hình dung 3 thành phần | Mô hình 3 thành phần (mục 1) + `docs/architecture/ARCHITECTURE.md` | **Đã có** |
| 8 | "**Serial là hạ tầng vật lý, Modbus chỉ là giao thức**" | Tách rõ 2 tầng trong `drivers/pzem004t.py` (transport serial ↔ frame Modbus) | **Đã có** |
| 9 | "**Hoãn cái ESP32 lại**" | Track B (ESP32) **vẫn thuộc phạm vi GR2** nhưng **lùi xuống sau Track A** — ưu tiên `P1`, không phải việc gấp | **Đã sắp lại thứ tự, vẫn nằm trong GR2** |
| 10 | "Các sự cố phát hiện được và ghi lại là rất tốt" | Bảng `events` + `RuleEngine` ghi cảnh báo quá tải / quá áp / sụt áp / offline | **Đã có** |

**Quy ước ưu tiên:** `P0` = chặn tiến độ, phải xong trong GR2 · `P1` = vẫn làm trong GR2 nhưng làm **sau** các việc `P0` · `P2` = nice-to-have, làm nếu còn thời gian.
**DoD** = Definition of Done. ID task dạng `A-3` để đối chiếu khi báo cáo GVHD.

---

## 1. Mô hình hệ thống — 3 thành phần

```
                    ┌──────────────────────────────────────────────┐
                    │  MÁY CHỦ GIÁM SÁT TRONG TỦ RACK             │
                    │  (Windows Server hoặc Linux host)            │
                    │                                              │
                    │  ┌────────────────────────────────────────┐  │
                    │  │ 1. ELECTRONIC PC AGENT                │  │
                    │  │    Windows Service / systemd daemon    │  │
                    │  │    chạy 24/7, headless, không GUI     │  │
                    │  │    Modbus-RTU + COM auto-discovery     │  │
                    │  │    + SQLite WAL + REST API             │  │
                    │  └───────────────┬────────────────────────┘  │
                    └──────────────────┼───────────────────────────┘
                                       │ USB-TTL, Modbus-RTU 9600 8N1
                                       ▼
                            ┌─────────────────────┐
                            │  PZEM-004T V3.0     │
                            │  đo 1 pha 220 V AC  │
                            └─────────────────────┘

   ┌───────────────────┐   MQTT / REST   ┌──────────────────────────┐
   │ 3. WEB SERVER     │◄────────────────┤ 1. ELECTRONIC PC AGENT   │
   │  giao diện + API  │                 └────────────┬─────────────┘
   └───────────────────┘                              │ MQTT
                                                     ▼
                                        ┌────────────────────────────┐
                                        │ 2. CENTRAL IOT CONTROLLER │
                                        │    ESP32 / ESP32-P4        │
                                        │    (P1 — LÀM SAU TRACK A)  │
                                        │    WiFi provisioning,      │
                                        │    điều khiển relay         │
                                        └─────────────┬──────────────┘
                                                      ▼
                                             ┌────────────────┐
                                             │  RELAY Ổ CẮM   │
                                             └────────────────┘
```

| # | Thành phần | Chạy trên | Trách nhiệm | Giao tiếp | Trạng thái |
|---|---|---|---|---|---|
| **1** | **Electronic PC Agent** | Máy chủ giám sát trong tủ rack | Đọc PZEM-004T liên tục, tự dò COM, lưu trữ time-series, đánh giá ngưỡng, phục vụ API nội bộ | **Nhận:** Modbus-RTU qua USB-TTL · **Cung cấp:** REST API `127.0.0.1:8000` · **Gửi (sau):** MQTT | **P0 — đang làm** |
| **2** | **Central IoT Controller** | Vi điều khiển ESP32 / ESP32-P4 | Cấu hình & duy trì WiFi, subscriber MQTT, điều khiển relay, giám sát an toàn | Nhận MQTT qua WiFi · Điều khiển GPIO relay | **P1 — làm sau Track A, vẫn trong GR2** |
| **3** | **Web Server** | Máy chủ web trung tâm | Giao diện web + API người dùng, báo cáo, lịch sử sự kiện | Nhận REST/MQTT từ PC Agent — **không** cắm serial trực tiếp | **P1 — đang dựng dần** |

> **Vì sao Web Server không cắm serial trực tiếp?** Windows cho phép **chỉ một** tiến trình giữ cổng COM tại một thời điểm (tiến trình thứ hai nhận `Access is denied`). PC Agent là tiến trình duy nhất sống 24/7 và giữ phiên serial. Nếu Web Server mở cùng cổng, giám sát sẽ bị gián đoạn. Vì vậy ranh giới bắt buộc là: **PC Agent = tầng thiết bị (edge)**, **Web Server = tầng trình diễn (application)**.

Tài liệu chi tiết + sơ đồ: [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md).

---

## 2. Track A — Electronic PC Agent  `P0` *(đang làm, ưu tiên tuyệt đối)*

Thư mục: `pc_agent/`. Đây là sản phẩm chính của GR2.

### 2.1 A-1 — Đóng gói & cấu trúc project  `P0` ✅ *gần xong*

- [x] **A-1-1** Chuẩn `src/` layout: `pc_agent/src/pc_agent/` + `pyproject.toml` (PEP 621).
- [x] **A-1-2** Tách `drivers/` (Modbus) · `core/` (poller, rules, state) · `storage/` (SQLite) · `api/` (HTTP) · `deploy/` (service wrappers) · `tools/` (probe).
- [x] **A-1-3** Entry point `python -m pc_agent` (foreground) — **không fork mã nguồn** so với chế độ service.
- [x] **A-1-4** Phụ thuộc cốt lõi chỉ `pyserial`; `pywin32` là optional (`[service]`); `paho-mqtt` là optional (`[mqtt]`).
- [x] **A-1-5** `web/index.html` là dashboard tĩnh, đóng gói bằng `package-data`.

**DoD:** `pip install -e pc_agent` chạy được; `pc-agent --help` in ra usage.

### 2.2 A-2 — Modbus-RTU Engine  `P0` ✅ *đã hiện thực & kiểm chứng*

- [x] **A-2-1** CRC-16 Modbus (poly phản chiếu `0xA001`, init `0xFFFF`, **byte thấp gửi trước**).
- [x] **A-2-2** Frame đọc: `01 04 00 00 00 0A 70 0D` → đối chiếu **khớp chính xác** với frame mẫu trong `PZEM-004T_Huong_Dan_Giao_Thuc.docx`.
- [x] **A-2-3** Giải mã 20 byte → 10 đại lượng (U, I, P, W, f, PF, alarm).
- [x] **A-2-4** Xử lý **sentinel `0xFFFF`** (chưa có tải) → hiển thị `0`, không hiện số rác.
- [x] **A-2-5** Ghép 32-bit đúng thứ tự: thanh ghi **thấp trước, cao sau** (`0x0001` = 16 bit thấp, `0x0002` = 16 bit cao) → `value = (high << 16) | low`. Đối chiếu bằng frame mẫu trong `PZEM-004T_Huong_Dan_Giao_Thuc.docx`.
- [x] **A-2-6** Test tự động `pc_agent/tests/test_decode.py` — 4 ca (CRC tài liệu / frame mẫu / giá trị thực tế / no-load).

**DoD:** toàn bộ test decode pass; giá trị đo thực tế khớp ampe kìm trong ±2 %.

### 2.3 A-3 — COM Auto-Discovery & Anti-Flapping Cache  `P0` ✅ *đã hiện thực*

Đây là yêu cầu trực tiếp của thầy (mục 4 & 5 ở bảng phản hồi).

- [x] **A-3-1** **Bậc 1 — Fast path:** thử cổng đã nhớ + địa chỉ đã nhớ. Không quét → khởi động nhanh.
- [x] **A-3-2** **Bậc 2 — Ưu tiên theo topology:** nếu adapter không có serial number (CH340 không có), Windows đổi số COM khi cắm cổng khác → dùng `location` (`1-4:x.3`) để khớp lại.
- [x] **A-3-3** **Bậc 3 — Quét cổng ứng viên:** xếp hạng theo VID/PID (CH340 / CP210x / FTDI / PL2303 tier 1; USB chung tier 2; legacy tier 3); thử địa chỉ `0x01` → `0xF8` → địa chỉ đã nhớ.
- [x] **A-3-4** **Bậc 4 — Quét toàn bộ:** `0x01..0xF7` (chỉ khi `--exhaustive-scan`).
- [x] **A-3-5** **Xác minh 5 bậc trước khi công nhận:** đúng function code `0x04` → đúng byte count → **CRC hợp lệ** → **điện áp 80–260 V** → **tần số 45–65 Hz**.
- [x] **A-3-6** **Anti-Flapping:** chỉ ghi đè cấu hình khi đã **xác minh được thiết bị thật**. Cổng hỏng / bị chiếm / chưa có nguồn AC → **không** xoá cấu hình đã nhớ.
- [x] **A-3-7** Ghi cấu hình **nguyên tử** (ghi file tạm → `fsync` → `os.replace`) — không mất cấu hình khi mất điện giữa lúc ghi.
- [x] **A-3-8** Phân loại lỗi rõ ràng: `PORT_BUSY` (tiến trình khác giữ cổng) vs `PORT_MISSING` (thiết bị bị rút) vs `IO_ERROR` — **không** nhầm lỗi dây/nguồn.
- [x] **A-3-9** Nhắc nhở nguyên nhân hay gặp: PZEM **không phản hồi UART nếu chưa có nguồn lưới AC** ở chân L/N.

**DoD:** rút/cắm lại USB-TTL, đổi cổng USB → agent tự tìm lại đúng thiết bị mà không cần sửa tay; cấu hình file không bao giờ bị ghi đè bằng giá trị rác.

### 2.4 A-4 — Windows Service (SCM)  `P0` 🔶 *code xong, cần test trên máy thật*

- [x] **A-4-1** `SmartPowerOutletAgentService` (pywin32 `ServiceFramework`) với `_svc_name_`, `_svc_display_name_`, `_svc_description_`.
- [x] **A-4-2** **Không dùng `pythonservice.exe`** — nó link cứng `pythonXY.dll` của Python gốc và **không** đọc `pyvenv.cfg` → service chạy sai Python, mất `pyserial`. Thay bằng: `python.exe` của venv làm host trực tiếp (`ImagePath = venv\Scripts\python.exe "...\windows_service.py"`).
- [x] **A-4-3** Vòng đời SCM: `Initialize()` → `PrepareToHostSingle(cls)` → `StartServiceCtrlDispatcher()` → `SvcDoRun()` → `SvcStop()`.
- [x] **A-4-4** **Logging an toàn Session 0:** luôn ghi file xoay vòng (`RotatingFileHandler` 10 MB × 10); chỉ gắn handler console khi stdout thực sự dùng được.
- [x] **A-4-5** **Auto-start trễ** (`SERVICE_DELAYED_AUTO_START_INFO`) — không tranh chấp I/O lúc boot.
- [x] **A-4-6** **Crash recovery:** `sc.exe failure ... restart/5000/restart/10000/restart/30000`, `reset= 86400`, `failureflag 1`.
- [x] **A-4-7** Script `deploy/install_service.ps1` (tạo venv, copy package, ghi config ban đầu, đăng ký, cấu hình recovery, mở firewall nếu bind ngoài localhost) và `deploy/uninstall_service.ps1`.
- [ ] **A-4-8** ⚠️ **Test trên máy thật:** cài → reboot → service tự lên → đọc dữ liệu → kill tiến trình → SCM tự khởi động lại. **Chưa làm.**
- [ ] **A-4-9** ⚠️ **Xác minh quyền đọc cổng COM khi chạy dưới LocalSystem** (Session 0). **Chưa làm.**
- [ ] **A-4-10** ⚠️ Viết **sự cố đã biết** vào `docs/operations/TROUBLESHOOTING.md`: cổng bị chiếm, thiết bị bị rút, chưa có nguồn AC, đổi số COM.

**DoD:** sau khi cài, `sc query SmartPowerOutletAgent` = `RUNNING` ngay sau reboot mà **không ai phải đăng nhập**; API trả `{"status":"healthy"}`.

### 2.5 A-5 — Linux systemd daemon  `P0` 🔶 *unit file xong, chưa test*

- [x] **A-5-1** `deploy/smart-power-agent.service`: `Type=simple`, `Restart=always`, `RestartSec=10`.
- [x] **A-5-2** `ConfigurationDirectory=` / `StateDirectory=` / `LogsDirectory=` (đường dẫn XDG tương ứng).
- [x] **A-5-3** `DeviceAllow=/dev/ttyUSB0 rw` + hardening (`NoNewPrivileges`, `ProtectSystem`, `PrivateTmp`).
- [ ] **A-5-4** ⚠️ Test trên máy Linux (VM hoặc Raspberry Pi): `systemctl enable --now`, `journalctl -u`.
- [ ] **A-5-5** ⚠️ Script cài đặt systemd (`install_linux.sh`) + tài liệu tương ứng.

**DoD:** `systemctl is-enabled` = `enabled`; agent tự lên sau reboot.

### 2.6 A-6 — Lưu trữ time-series (SQLite WAL)  `P0` ✅ *đã hiện thực*

- [x] **A-6-1** Bảng `telemetry_raw` (mẫu thô 1 Hz, giữ **14 ngày**) — index `(meter_id, timestamp DESC)`.
- [x] **A-6-2** Bảng `telemetry_hourly` (tổng hợp theo giờ, giữ **365 ngày**): min/max/avg U, I, P, PF, chênh lệch điện năng, **load factor**, số lần alarm.
- [x] **A-6-3** Bảng `events` (cảnh báo / sự cố) với `resolved_at` để biết sự kiện nào đang mở.
- [x] **A-6-4** Chế độ **WAL** + `synchronous=NORMAL` → đọc được đồng thời khi đang ghi.
- [x] **A-6-5** Tổng hợp theo giờ chạy mỗi 5 phút; dọn dữ liệu cũ mỗi giờ.
- [ ] **A-6-6** ⚠️ Test: chạy 24 h liên tục, không rò rỉ disk, kích thước DB ổn định.

**DoD:** DB 1 file, tự dọn theo retention, đọc/ghi song song không lỗi.

### 2.7 A-7 — Rule Engine & ghi nhận sự cố  `P0` ✅ *đã hiện thực*

Thầy nói rõ: *"Các sự cố phát hiện được và ghi lại là rất tốt."* → đây là điểm cần làm kỹ.

- [x] **A-7-1** Ngưỡng trong tiến trình: `OVER_POWER`, `OVER_VOLTAGE`, `UNDER_VOLTAGE`, `DEVICE_ALARM` (cảnh báo tích hợp của PZEM, thanh ghi `0x0009 = 0xFFFF`).
- [x] **A-7-2** `DEVICE_OFFLINE` khi mất kết nối.
- [x] **A-7-3** **Tự đóng sự kiện** khi trở lại bình thường (`resolved_at`) — không spam log.
- [x] **A-7-4** Đánh giá **trong tiến trình**, không đẩy lên broker: độ trễ < 1 ms, và cảnh báo vẫn kêu được khi mất mạng (đúng tình huống máy chủ rack).
- [ ] **A-7-5** ⚠️ **Test ngưỡng thực tế:** dùng bóng đèn/tải biến thiên vượt ngưỡng → xác nhận sự kiện ghi vào DB và hiện trên API.
- [ ] **A-7-6** ⚠️ Thêm ngưỡng **quá dòng** và **sụt áp nghiêm ngặt hơn** theo thông số thực tế của tủ rack.
- [ ] **A-7-7** ⚠️ Gửi **thông báo tổng hợp** (email/Telegram webhook) khi có sự kiện mức `critical`.

**DoD:** mỗi loại sự cố đều sinh đúng 1 bản ghi `events`, tự đóng khi hết, và xuất hiện trong `/api/events`.

### 2.8 A-8 — REST API & dashboard  `P0` ✅ *đã hiện thực*

- [x] **A-8-1** `http.server` chuẩn Python — **không framework** (bề mặt tấn công nhỏ cho service 24/7).
- [x] **A-8-2** Endpoint: `/`, `/api/health`, `/api/status`, `/api/metrics`, `/api/history`, `/api/events`, `/api/config`.
- [x] **A-8-3** Mặc định bind `127.0.0.1`; mở ra LAN là **tuy chọn có chủ đích** (`--host 0.0.0.0` + firewall rule).
- [x] **A-8-4** Bearer token tùy chọn (`api_token`) — hiện chưa bật mặc định.
- [x] **A-8-5** Dashboard tĩnh `web/index.html` — hiện số đo trực tiếp, trạng thái kết nối, sự kiện.
- [ ] **A-8-6** ⚠️ **Bật xác thực mặc định** khi bind ngoài localhost (bắt buộc — hiện là tuỳ chọn).
- [ ] **A-8-7** ⚠️ Biểu đồ lịch sử (24 h / 7 ngày / 30 ngày) — dùng `/api/history` với `resolution=raw|hourly`.

**DoD:** dashboard mở được từ máy khác trong LAN; `/api/health` trả `healthy` trong < 50 ms.

### 2.9 A-9 — Bền vững vận hành (Production hardening)  `P1`

- [ ] **A-9-1** Health check + watchdog: agent im lặng > 3 chu kỳ → ghi sự kiện `DEVICE_OFFLINE`.
- [ ] **A-9-2** Giới hạn tốc độ log khi lỗi lặp (tránh làm đầy ổ đĩa khi cổng hỏng).
- [ ] **A-9-3** **Version stamping**: `/api/health` trả version của package + git commit.
- [ ] **A-9-4** **Backup** cấu hình + DB (`%ProgramData%\SmartPowerOutlet`), lịch tự động.
- [ ] **A-9-5** Test **rút/cắm USB-TTL giữa lúc đang chạy**: agent phải tự ghi `DEVICE_OFFLINE`, thử lại sau 5 s, và **tự kết nối lại** khi cắm lại.
- [ ] **A-9-6** Test **cổng bị chiếm** bởi PuTTY/PlatformIO: agent phải báo đúng `PORT_BUSY` (không phải lỗi nguồn).

**DoD:** agent chạy 7×24 không cần can thiệp tay.

### 2.10 A-10 — MQTT uplink  `P1` *(nối Track B & C)*

- [ ] **A-10-1** Client `paho-mqtt` (optional dependency `[mqtt]`), mặc định **tắt**.
- [ ] **A-10-2** Topic `smartoutlet/rack/<rack_id>/meter/<meter_id>` + sub-topic `telemetry` / `state` / `event`.
- [ ] **A-10-3** Publish trạng thái **kết nối** lên broker (`online`/`offline` retained) — để Web Server biết agent còn sống.
- [ ] **A-10-4** Reconnect tự động với backoff luỹ thừa; agent **không** chết vì broker chết.
- [ ] **A-10-5** QoS 1, `clean_session=False`, keepalive 60 s.

**DoD:** broker mất rồi có lại → agent tự kết nối lại và tiếp tục ghi dữ liệu.

---

## 3. Track B — Central IoT Controller (ESP32)  `P1` *(làm sau Track A, **vẫn trong phạm vi GR2**)*

> **Thầy đã yêu cầu hoãn:** *"em có thì hoãn cái esp32 lại"*. → Track B **không bị đẩy sang GR3**; nó vẫn là một phần của GR2, chỉ **lùi xuống sau** Track A (ưu tiên `P1`) cho tới khi PC Agent đạt DoD.
> Việc cần giữ lại từ lộ trình cũ (để không mất hiểu biết): thư viện WiFi provisioning, state machine duy trì kết nối, đo điện trên vi điều khiển, phần cứng EasyEDA.
> **Điều kiện mở:** Track A (A-1 → A-9) đạt DoD → GVHD duyệt → làm Track B trong **cùng GR2**. Nếu hết thời gian GR2 thì phần dở dang đó mới chuyển sang đầu GR3 (xem mục 7 — rủi ro thời gian).

### 3.1 B-1 — Thư viện WiFi provisioning (Arduino)  `P1` *giữ nguyên thiết kế cũ*

- [ ] **B-1-1** `ConfigManager` trên NVS/LittleFS: schema có `version` + CRC, ghi atomic, chỉ commit khi dirty.
- [ ] **B-1-2** Tối đa 5 SSID + mật khẩu; nhớ SSID "ok" gần nhất; thử `ok` trước rồi mới xoay vòng.
- [ ] **B-1-3** Captive portal (AP + DNS) cho cấu hình qua điện thoại; timeout 5 phút rồi thoát.
- [ ] **B-1-4** State machine `OFF/IDLE/CONNECTING/CONNECTED/PORTAL` — tuyệt đối không `delay()`.
- [ ] **B-1-5** Phát hành lên Arduino Library Registry (`arduino-lint --compliance strict`).

### 3.2 B-2 — Firmware đo điện & điều khiển relay  `P1`

- [ ] **B-2-1** `PowerMonitor` (API độc lập phần cứng): RMS, công suất, PF, điện năng, NTC.
- [ ] **B-2-2** Task FreeRTOS riêng cho sampling; publish qua queue.
- [ ] **B-2-3** MQTT client (`smartoutlet/<dev_id>/...`), điều khiển relay, cắt relay khi quá nhiệt/quá tải.

### 3.3 B-3 — Phần cứng EasyEDA  `P2`

- [ ] **B-3-1** Schematic EasyEDA (nguồn 220 VAC → HLK-PM01 → LDO 3V3; relay + driver; ESP32-C3; nút BOOT/RESET).
- [ ] **B-3-2** Khe cắm **I2C** đánh dấu rõ trên silkscreen: `3V3 / GND / SDA / SCL`, có nhãn "I2C", pull-up 4.7 kΩ.
- [ ] **B-3-3** Khoảng cách creepage/clearance ≥ 3 mm giữa phần cao áp và phần logic; test point cho 3V3/GND/SDA/SCL.
- [ ] **B-3-4** BOM + Gerber + đặt 1 lô 5 board.

---

## 4. Track C — Web Server  `P1` *(đang dựng dần)*

> Thầy gợi ý *"Máy chủ web sẽ cắm trực tiếp serial để đọc số liệu"* — **ta chọn không làm vậy** (lý do ở mục 1). Nếu GVHD vẫn muốn theo hướng đó, cần trao đổi lại ở buổi báo cáo GR2.

- [ ] **C-1** Tách dashboard hiện tại khỏi PC Agent thành **Web Server riêng**, đọc dữ liệu qua REST/MQTT.
- [ ] **C-2** Xác thực người dùng + phân quyền (admin / viewer).
- [ ] **C-3** Trang **tổng quan rack**: công suất tức thời, biểu đồ 24 h, sự kiện đang mở.
- [ ] **C-4** Trang **lịch sử**: lọc theo khoảng thời gian, `raw` vs `hourly`, xuất CSV.
- [ ] **C-5** Trang **cấu hình**: đổi ngưỡng cảnh báo, chu kỳ lấy mẫu, hiển thị trạng thái COM đã nhớ.
- [ ] **C-6** App Flutter (`smart_power_outlet_app/`) đọc từ Web Server — tái dùng service `mqtt_service.dart` đã có.

**DoD:** Web Server không cần quyền truy cập serial; chỉ cần HTTP client tới PC Agent.

---

## 5. Track D — Tài liệu & báo cáo  `P1` *(chạy song song)*

- [ ] **D-1** `docs/architecture/ARCHITECTURE.md` — mô hình 3 thành phần, luồng dữ liệu, ánh xạ thư mục. ✅ *đã tạo*
- [ ] **D-2** `docs/architecture/diagrams/` — sơ đồ Mermaid + ASCII (kiến trúc tổng thể, nội bộ agent, vòng đời service). ✅ *đã tạo*
- [ ] **D-3** `docs/operations/TROUBLESHOOTING.md` — lỗi thường gặp của service (đang là A-4-10).
- [ ] **D-4** `docs/operations/INSTALL.md` — cài Windows Service + Linux daemon từ đầu.
- [ ] **D-5** Báo cáo tiến độ GR2 Tuần 2 (docx) — mô hình 3 thành phần + kết quả test service.
- [ ] **D-6** Cập nhật `ROADMAP.md` + `README.md` mỗi cuối tuần.

---

## 6. Lịch dự kiến GR2 (4 tuần)

| Tuần | Nội dung | Mốc bàn giao |
|---|---|---|
| **Tuần 2** | A-4-8, A-4-9 (test service thật), A-4-10, A-5-4, A-5-5, A-7-5, A-8-6, A-8-7, D-3, D-4 | **Service chạy 24/7 thật trên máy** + tài liệu vận hành |
| **Tuần 3** | A-9 (hardening), A-10 (MQTT), C-1 (tách Web Server), D-5 | **MQTT uplink + Web Server tách riêng** |
| **Tuần 4** | Test 24 h, C-2…C-5, D-6 | **Báo cáo GR2 + demo** |
| **Trong GR2, sau Tuần 3** | **B-1** (thư viện WiFi provisioning) → **B-2** (firmware đo điện & relay) | Controller ESP32 chạy được, nối MQTT với PC Agent |
| **Trong GR2, nếu còn thời gian** | B-3 (phần cứng EasyEDA) | Board đầu tiên về đến tay |
| **Phần dở dang (nếu hết thời gian GR2)** | Phần chưa xong của Track B chuyển sang đầu **GR3** | Không mất gì — phần đã làm giữ nguyên |

---

## 7. Rủi ro & đối sách

| Rủi ro | Mức | Đối sách |
|---|---|---|
| GVHD vẫn muốn Web Server cắm serial trực tiếp | Cao | **Trao đổi lại ở buổi GR2**, trình bày rõ xung đột exclusive-lock của COM; đề xuất phương án "serial ↔ HTTP bridge" nếu thầy vẫn muốn |
| Service không đọc được COM dưới LocalSystem (Session 0) | Cao | Test sớm (A-4-9); nếu vướng → chạy service dưới **tài khoản người dùng** (`--username/--password` trong `HandleCommandLine`) hoặc dùng `LocalService` |
| Thiết bị mất nguồn AC → im lặng, không phản hồi UART | Trung bình | Đã có thông báo nguyên nhân trong log (A-3-9) + `DEVICE_OFFLINE` event |
| Đổi số COM sau mỗi lần rút/cắm | Trung bình | Đã xử lý bằng `usb_location` (A-3-2) |
| Số lượng PZEM tăng lên (thầy sẽ mua thêm 1 module dự phòng) | Trung bình | Thiết kế `meter_id` đã hỗ trợ nhiều meter; giai đoạn 2 sẽ cho agent quét nhiều cổng song song |
| Dừng ESP32 quá lâu → GVHD mất dấu hướng | Trung bình | Track B **vẫn nằm trong GR2** (chỉ lùi sau Track A) → không bị "biến mất" khỏi báo cáo; giữ nguyên thiết kế để làm tiếp ngay |
| Hết thời gian GR2 | Trung bình | Cắt theo thứ tự: A-10 (MQTT) → C-2…C-6 → B-3 (phần cứng). **Track A + B-1/B-2** vẫn đủ để báo cáo; phần dở dang của Track B mới chuyển sang GR3 |

---

## 8. Câu hỏi cần chốt với GVHD

1. **Mô hình 3 thành phần** — thầy xác nhận mô hình này đúng ý chưa? Đặc biệt: Web Server **không** cắm serial mà đọc từ PC Agent.
2. **Phạm vi GR2** — thầy có cần thêm tính năng gì cho PC Agent trong GR2 không (ví dụ: xuất CSV, gửi email cảnh báo, hỗ trợ nhiều PZEM)?
3. **Cách chạy thực tế** — trong tủ rack, PC Agent chạy trên **Windows Server** hay **Linux**? (Ảnh hưởng việc hoàn thiện A-4 hay A-5 trước.)
4. **ESP32 trong GR2** — em định làm Track B **sau Track A** (B-1 thư viện WiFi → B-2 firmware đo điện & relay → B-3 phần cứng), vẫn kịp trong GR2. Thầy thấy thứ tự này ổn chứ?
5. **Bảo mật API** — có yêu cầu đặt mật khẩu cho dashboard / API không?
6. **Báo cáo GR2 Tuần 2** — thầy muốn nhấn mạnh phần nào: tính "service" hay tính "mô hình tổng thể"?
