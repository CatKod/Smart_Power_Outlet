# Smart Power Outlet — Lộ trình công việc

> **Cập nhật: 2026-11-17** · Trạng thái: **GR2 Tuần 2 — Giai đoạn 1 đóng, chờ test máy thật** · Lần sửa trước (2026-11-15) viết lại toàn bộ lộ trình theo phản hồi của GVHD (Thầy Nguyễn Đức Tiến) trong buổi nộp báo cáo GR2 Tuần 1.
>
> **Thay đổi lớn so với lộ trình cũ:** trọng tâm chuyển từ *thư viện Arduino WiFi* sang **Electronic PC Agent** — một dịch vụ nền (Windows Service / Linux daemon) chạy 24/7 trên máy chủ, giám sát năng lượng PZEM-004T cho một tổ hợp máy chủ trong tủ rack. Phần ESP32 vẫn nằm trong **phạm vi GR2** nhưng bị **lùi xuống sau** (ưu tiên `P1`, làm sau khi Track A đạt DoD) theo chỉ đạo *"em có thì hoãn cái esp32 lại"* của thầy.
>
> 📌 **Cập nhật 2026-11-17 — nhánh thư viện dùng chung đã ra mắt.** Thư viện C99 **`embedded-iot-toolkit`** (repo riêng `CatKod/embedded-iot-toolkit`) đã được **đăng ký thành công trên cả hai registry**: [Arduino Library Manager](https://www.arduinolibraries.info/libraries/embedded-io-t-toolkit) và [ESP-IDF Component Registry](https://components.espressif.com/components/catkod/embedded-iot-toolkit/versions/1.0.0). Xem **Track E — mục 5**.
>
> 📌 **Cập nhật 2026-11-17 — Giai đoạn 1 đã đóng.** Toàn bộ 12 task `P0` của Giai đoạn 1 đã xong (A-4-10, A-5-5, A-6-6, A-7-6/7, A-8-6/7, A-9-1..4, D-3, D-4). Phần còn lại của Tuần 2 là **Giai đoạn 2 — test trên máy thật** (A-4-8/9, A-7-5, A-9-5/6, A-5-4), vốn **phụ thuộc phần cứng** (cắm USB-TTL, reboot máy). Báo cáo: [`docs/reports/report_week2.docx`](docs/reports/report_week2.docx).

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
| **2** | **Central IoT Controller** | Vi điều khiển **ESP32-S3 N16R8** (16 MB Flash / 8 MB Octal PSRAM) | Cấu hình & duy trì WiFi, subscriber MQTT, điều khiển relay, giám sát an toàn | Nhận MQTT qua WiFi · Điều khiển GPIO relay · Đọc PZEM #2 qua UART1 | **P1 — làm sau Track A, vẫn trong GR2** |
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
- [x] **A-4-10** ⚠️ Viết **sự cố đã biết** vào `docs/operations/TROUBLESHOOTING.md`: cổng bị chiếm, thiết bị bị rút, chưa có nguồn AC, đổi số COM.

**DoD:** sau khi cài, `sc query SmartPowerOutletAgent` = `RUNNING` ngay sau reboot mà **không ai phải đăng nhập**; API trả `{"status":"healthy"}`.

### 2.5 A-5 — Linux systemd daemon  `P0` 🔶 *unit file xong, chưa test*

- [x] **A-5-1** `deploy/smart-power-agent.service`: `Type=simple`, `Restart=always`, `RestartSec=10`.
- [x] **A-5-2** `ConfigurationDirectory=` / `StateDirectory=` / `LogsDirectory=` (đường dẫn XDG tương ứng).
- [x] **A-5-3** `DeviceAllow=/dev/ttyUSB0 rw` + hardening (`NoNewPrivileges`, `ProtectSystem`, `PrivateTmp`).
- [ ] **A-5-4** ⚠️ Test trên máy Linux (VM hoặc Raspberry Pi): `systemctl enable --now`, `journalctl -u`.
- [x] **A-5-5** ⚠️ Script cài đặt systemd (`install_linux.sh` + `uninstall_linux.sh`, bash, `set -euo pipefail`, idempotent) + tài liệu.

**DoD:** `systemctl is-enabled` = `enabled`; agent tự lên sau reboot.

### 2.6 A-6 — Lưu trữ time-series (SQLite WAL)  `P0` ✅ *đã hiện thực*

- [x] **A-6-1** Bảng `telemetry_raw` (mẫu thô 1 Hz, giữ **14 ngày**) — index `(meter_id, timestamp DESC)`.
- [x] **A-6-2** Bảng `telemetry_hourly` (tổng hợp theo giờ, giữ **365 ngày**): min/max/avg U, I, P, PF, chênh lệch điện năng, **load factor**, số lần alarm.
- [x] **A-6-3** Bảng `events` (cảnh báo / sự cố) với `resolved_at` để biết sự kiện nào đang mở.
- [x] **A-6-4** Chế độ **WAL** + `synchronous=NORMAL` → đọc được đồng thời khi đang ghi.
- [x] **A-6-5** Tổng hợp theo giờ chạy mỗi 5 phút; dọn dữ liệu cũ mỗi giờ.
- [ ] **A-6-6** ⚠️ Test: chạy 24 h liên tục, không rò rỉ disk, kích thước DB ổn định. Có script `pc_agent/tools/soak_test.py` chạy `--simulate` 24 h, đo kích thước DB/WAL theo chu kỳ. 🔶 *script + tham số ngưỡng đã xong; **còn lại: chạy 24 h thật**.*

**DoD:** DB 1 file, tự dọn theo retention, đọc/ghi song song không lỗi.

> 📌 **2026-11-15 — script soak đã viết & đã chạy thử (45 s), phát hiện 3 lỗi production đã sửa:**
> 1. `sqlite_store.py` — `with sqlite3.connect(...)` chỉ quản lý transaction, **không đóng connection** → rò handle → `database table is locked`. Đã thêm `_session()` dùng `contextlib.closing`.
> 2. `sqlite_store.py` — `purge_expired()` thiếu dấu phẩy cuối tuple → `sqlite3.ProgrammingError` **mọi lần gọi** → retention (dọn dữ liệu cũ) **không bao giờ chạy**. Đã sửa + tách `PRAGMA wal_checkpoint` ra connection riêng (PRAGMA không chạy được trong transaction).
> 3. `deploy/smart-power-agent.service` — file viết theo **cú pháp XML** thay vì **INI** của systemd → `systemd` không load được. Đã viết lại đúng chuẩn.
>
> Kết quả sau khi sửa: DB/WAL/SHM ổn định, WAL được truncate về 0, RSS phẳng (+0.3 %).
>
> ✅ **2026-11-17 — phần mềm của A-6-6 đã xong:** script `soak_test.py` đã có đủ cờ ngưỡng để tự kết luận PASS/FAIL — `--db-max-mb`, `--wal-max-mb`, `--total-max-mb`, `--rss-max-mb`, `--rss-growth-pct` — và xuất báo cáo JSON + CSV.
>
> 🔶 **Còn lại — chạy 24 h thật** (cần máy bật liên tục, chưa làm):
> `python pc_agent/tools/soak_test.py --duration 86400 --interval 300`
>
> **Phần còn lại:** chạy thật 24 h cần máy bật liên tục → `python pc_agent/tools/soak_test.py --duration 86400 --interval 300`.

### 2.7 A-7 — Rule Engine & ghi nhận sự cố  `P0` ✅ *đã hiện thực*

Thầy nói rõ: *"Các sự cố phát hiện được và ghi lại là rất tốt."* → đây là điểm cần làm kỹ.

- [x] **A-7-1** Ngưỡng trong tiến trình: `OVER_POWER`, `OVER_VOLTAGE`, `UNDER_VOLTAGE`, `DEVICE_ALARM` (cảnh báo tích hợp của PZEM, thanh ghi `0x0009 = 0xFFFF`).
- [x] **A-7-2** `DEVICE_OFFLINE` khi mất kết nối.
- [x] **A-7-3** **Tự đóng sự kiện** khi trở lại bình thường (`resolved_at`) — không spam log.
- [x] **A-7-4** Đánh giá **trong tiến trình**, không đẩy lên broker: độ trễ < 1 ms, và cảnh báo vẫn kêu được khi mất mạng (đúng tình huống máy chủ rack).
- [ ] **A-7-5** ⚠️ **Test ngưỡng thực tế:** dùng bóng đèn/tải biến thiên vượt ngưỡng → xác nhận sự kiện ghi vào DB và hiện trên API.
- [x] **A-7-6** ⚠️ Thêm ngưỡng **quá dòng** (`current_threshold_a`) + **siết ngưỡng sụt áp** theo thông số tủ rack (220 V ±10 % → 198–242 V, thay vì 180–260 V hiện tại). Thêm field vào `AgentConfig` + `RuleEngine` + `/api/config`.
- [x] **A-7-7** ⚠️ Gửi **thông báo tổng hợp** khi có sự kiện mức `critical`. Thiết kế: package `notifiers/` với interface `Notifier` + `TelegramNotifier` (webhook, timeout 5 s, retry backoff). **Agent không được chết vì webhook lỗi** → thread riêng + queue.

**DoD:** mỗi loại sự cố đều sinh đúng 1 bản ghi `events`, tự đóng khi hết, và xuất hiện trong `/api/events`.

### 2.8 A-8 — REST API & dashboard  `P0` ✅ *đã hiện thực*

- [x] **A-8-1** `http.server` chuẩn Python — **không framework** (bề mặt tấn công nhỏ cho service 24/7).
- [x] **A-8-2** Endpoint: `/`, `/api/health`, `/api/status`, `/api/metrics`, `/api/history`, `/api/events`, `/api/config`.
- [x] **A-8-3** Mặc định bind `127.0.0.1`; mở ra LAN là **tuy chọn có chủ đích** (`--host 0.0.0.0` + firewall rule).
- [x] **A-8-4** Bearer token tùy chọn (`api_token`) — hiện chưa bật mặc định.
- [x] **A-8-5** Dashboard tĩnh `web/index.html` — hiện số đo trực tiếp, trạng thái kết nối, sự kiện.
- [x] **A-8-6** ⚠️ **Bắt buộc xác thực khi bind ngoài localhost.** Khi `api_host` không phải loopback → tự sinh token `secrets.token_urlsafe(32)`, in ra log 1 lần + ghi `api_token.txt` (mode 600), **từ chối khởi động** nếu không tạo được token. So sánh bằng `hmac.compare_digest`. Thêm `--rotate-token` + `POST /api/config/token`.
- [x] **A-8-7** ⚠️ Biểu đồ lịch sử (24 h / 7 ngày / 30 ngày) — dùng `/api/history` với `resolution=raw|hourly`. Vẽ **Canvas/SVG thuần** (không CDN, giữ "bề mặt tấn công nhỏ"): đường P (W), V (V), I (A).

**DoD:** dashboard mở được từ máy khác trong LAN; `/api/health` trả `healthy` trong < 50 ms.

### 2.9 A-9 — Bền vững vận hành (Production hardening)  `P1`

- [x] **A-9-1** Health check + watchdog: agent im lặng > 3 chu kỳ → ghi sự kiện `DEVICE_OFFLINE`. (`offline_after_s` đã có trong config nhưng **chưa dùng**.)
- [x] **A-9-2** Giới hạn tốc độ log khi lỗi lặp (suppression theo message-signature, ~60 s → log 1 lần + đếm số lần bị chặn).
- [x] **A-9-3** **Version stamping**: `/api/health` trả version package + **git commit SHA** + thời điểm build (fallback `"unknown"`).
- [x] **A-9-4** **Backup** cấu hình + DB vào `%ProgramData%\SmartPowerOutlet\backup\`, lịch hằng ngày, giữ 7 bản. Dùng SQLite **backup API** (`conn.backup()`) chứ không copy file thô (tránh hỏng DB khi đang ghi WAL).
- [ ] **A-9-5** Test **rút/cắm USB-TTL giữa lúc đang chạy**: agent phải tự ghi `DEVICE_OFFLINE`, thử lại sau 5 s, và **tự kết nối lại** khi cắm lại.
- [ ] **A-9-6** Test **cổng bị chiếm** bởi PuTTY/PlatformIO: agent phải báo đúng `PORT_BUSY` (không phải lỗi nguồn).

**DoD:** agent chạy 7×24 không cần can thiệp tay.

### 2.10 A-10 — MQTT uplink  `P1` *(nối Track B & C)*

- [ ] **A-10-1** Client `paho-mqtt` (optional dependency `[mqtt]`), mặc định **tắt**. Credential đọc từ **biến môi trường**, không hardcode.
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

> **Board đã chốt: ESP32-S3 N16R8.** Firmware viết mới bằng **ESP-IDF 5.5.3** (target `esp32s3`) — *không* chuyển code PlatformIO P4 sang S3 vì framework (Arduino vs ESP-IDF) lẫn SoC đều khác. Tái sử dụng *ý tưởng* từ `Smart_power_outlet_PIO/src/wifi_prov.cpp` và `Smart_Power_Outlet_ESP/main/wifi_prov.c`.
>
> ⚠️ **Pin map đã xác minh từ header ESP-IDF 5.5.3** (`components/soc/esp32s3/include/soc/spi_pins.h`):
> relay = **GPIO 21** (active LOW) · LED = **GPIO 48** · nút reset WiFi = **GPIO 0** · UART1 TX=**17**/RX=**18** · I2C = **8/9**.
> **Cấm GPIO 22–37** (bus MSPI octal dùng chung flash + PSRAM) và **19/20** (USB native).

- [ ] **B-4-0** Project ESP-IDF 5.5.3 cho `esp32s3` variant **N16R8**; `sdkconfig.defaults`: flash 16 MB, `CONFIG_SPIRAM_MODE_OCT=y`. Xác minh `idf.py build` + `idf.py size`.
- [ ] **B-4-1** `board_pins.h` định nghĩa pin map + comment cấm GPIO 22–37.
- [ ] **B-2-1** `PowerMonitor` (API độc lập phần cứng): RMS, công suất, PF, điện năng, NTC. **Tách lớp transport ↔ protocol** y hệt `drivers/pzem004t.py` (bài học: *"Serial là hạ tầng vật lý, Modbus chỉ là giao thức"*).
- [ ] **B-2-2** Task FreeRTOS riêng cho sampling; publish qua queue sang task MQTT.
- [ ] **B-2-3** MQTT client (`smartoutlet/<dev_id>/...`), điều khiển relay, cắt relay khi quá nhiệt/quá tải.

### 3.3 B-5 — Vòng lặp khép kín `P2`

- [ ] **B-5-1** Kịch bản tích hợp quan trọng nhất của GR2: bật tải → ESP32-S3 đo → publish MQTT → PC Agent nhận → ghi SQLite → dashboard hiện → **ESP32 tự cắt relay khi vượt ngưỡng** → PZEM #1 thấy công suất về 0.

### 3.3 B-3 — Phần cứng EasyEDA  `P2`

- [ ] **B-3-1** Schematic EasyEDA (nguồn 220 VAC → HLK-PM01 → LDO 3V3; **ESP32-S3**; relay + driver active LOW; nút BOOT/RESET; 2 cổng UART).
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

- [x] **D-1** `docs/architecture/ARCHITECTURE.md` — mô hình 3 thành phần, luồng dữ liệu, ánh xạ thư mục.
- [x] **D-2** `docs/architecture/diagrams/` — sơ đồ Mermaid + ASCII (kiến trúc tổng thế, nội bộ agent, vòng đời service).
- [x] **D-3** `docs/operations/TROUBLESHOOTING.md` — lỗi thường gặp của service (đang là A-4-10).
- [x] **D-4** `docs/operations/INSTALL.md` — cài Windows Service + Linux daemon từ đầu.
- [x] **D-5** Báo cáo tiến độ GR2 Tuần 2 (docx) — mô hình 3 thành phần + kết quả test service. ✅ *đã tạo:* [`docs/reports/report_week2.docx`](docs/reports/report_week2.docx)
- [x] **D-6** Cập nhật `ROADMAP.md` + `README.md` mỗi cuối tuần. ✅ *đã cập nhật 2026-11-17*
- [x] **D-7** `docs/operations/HARDWARE_PREP.md` — chuẩn bị phần cứng & môi trường test cho Giai đoạn 2 (A-4-8/9, A-7-5, A-9-5/6, A-5-4).

---

## 5.1 Track E — Thư viện dùng chung `embedded-iot-toolkit`  `P1` ✅ *đã phát hành v1.0.0*

> **Vì sao tách thành track riêng:** bài toán "giao thức lặp lại" (đọc thanh ghi, checksum, timer không chặn, codec) là **giống nhau** giữa PC Agent (Python), firmware ESP32 (C) và tầng Web/Flutter (Dart). Thay vì viết lại 3 lần, tách ra **thư viện C99 thuần** để dùng lại ở mọi tầng. Thư viện nằm ở repo riêng: [`CatKod/embedded-iot-toolkit`](https://github.com/CatKod/embedded-iot-toolkit).

### 5.1.1 E-1 — Đăng ký trên cả 2 registry  `P1` ✅ *đã xong (2026-11-16)*

- [x] **E-1-1** Cấu trúc theo **Arduino Library Specification 1.5** (Rev 2.2): `library.properties`, `keywords.txt`, `src/` (umbrella header `EmbeddedIoTToolkit.h`), `examples/*.ino`.
- [x] **E-1-2** Tuân thủ **ESP-IDF Component Registry**: `idf_component.yml` (`version: "1.0.0"`, `dependencies`, `targets`, `files.exclude`).
- [x] **E-1-3** Kiểm tra tuân thủ: `arduino-lint --compliance strict --library-manager submit` → **0 ERROR**.
- [x] **E-1-4** PR đăng ký Arduino: [`arduino/library-registry#9655`](https://github.com/arduino/library-registry/pull/9655) → **MERGED** (2026-11-16 02:45 UTC).
- [x] **E-1-5** Publish ESP-IDF: `compote component upload --name embedded-iot-toolkit --namespace CatKod` → **thành công**.
- [x] **E-1-6** Kiểm chứng end-to-end: dựng project ESP-IDF mới, khai báo `catkod/embedded-iot-toolkit: "^1.0.0"`, `idf.py build` (target `esp32s3`) → **PASS**, `dependencies.lock` xác nhận `source: {type: service, registry_url: https://components.espressif.com/}`.

### 5.1.2 E-2 — Nội dung thư viện  `P1` ✅ *đã xong*

| Module | Nội dung | Cổng |
|---|---|---|
| `ekt_soft_timer` | Timer không chặn, không `delay()` | `src/ekt_soft_timer.c` |
| `ekt_frame` | Giao thức khung serial có checksum XOR, an toàn ISR | `src/ekt_frame.c` |
| `ekt_can_codec` | Codec định danh CAN 2.0B (11/29 bit) | `src/ekt_can_codec.c` |
| `ekt_sensor` | Trợ giúp cảm biến + phát hiện dữ liệu cũ (stale) | `src/ekt_sensor.c` |

- [x] **E-2-1** Lõi thuần C99: **không header nhà cung cấp**, **không cấp phát động**, không phụ thuộc RTOS.
- [x] **E-2-2** Tầng port: `port/posix` (test trên PC) · `port/esp32` (ESP-IDF) · `port/stm32` · `src/port_arduino` (Arduino, tự biên dịch đệ quy).
- [x] **E-2-3** Bố cục **không nhân bản header**: header công khai ở `src/*.h`, chỉ phần khác biệt nằm trong port.
- [x] **E-2-4** `files.exclude` trong `idf_component.yml` loại `.ino` của Arduino + port Arduino khỏi gói ESP-IDF (vì ESP-IDF tự dò `examples/` theo thư mục → `.ino` sẽ làm hỏng).

### 5.1.3 E-3 — CI & phát hành  `P1` ✅ *đã xong*

- [x] **E-3-1** 4 job GitHub Actions, tất cả **xanh**: `Host unit tests (gcc)` · `Host unit tests (clang)` · `Arduino Library Specification` · `ESP-IDF component build`.
- [x] **E-3-2** Cờ `-std=c99 -Wall -Wextra -Wpedantic -Werror` → cả 2 compiler đều **không cảnh báo**.
- [x] **E-3-3** Job ESP-IDF clone `v5.5.3`, `install.sh esp32s3`, build example `esp32_timer`.
- [x] **E-3-4** Tag `v1.0.0` + GitHub Release `v1.0.0` (cần cho Arduino indexer nhận repo).
- [x] **E-3-5** Lỗi CI đã sửa: `_POSIX_C_SOURCE` cho `clock_gettime`/`nanosleep` dưới `-std=c99` · `arduino-lint` phải truyền đường dẫn tuyệt đối (`$GITHUB_WORKSPACE`) · `espressif/setup-esp@v2` không tồn tại → clone ESP-IDF trực tiếp.

**Kết quả:**
- Arduino Library Manager → https://www.arduinolibraries.info/libraries/embedded-io-t-toolkit
- ESP-IDF Component Registry → https://components.espressif.com/components/catkod/embedded-iot-toolkit/versions/1.0.0

**DoD:** cài được từ cả 2 registry bằng 1 dòng lệnh, build sạch trên ≥ 2 toolchain, không cần sửa tay.

### 5.1.4 E-4 — Hướng tiếp theo  `P2`

- [ ] **E-4-1** Dùng `ekt_frame` cho **giao thức giữa PC Agent ↔ ESP32** (thay vì giao thức riêng).
- [ ] **E-4-2** Dùng `ekt_soft_timer` cho task FreeRTOS trong firmware ESP32-S3 (thay vì `vTaskDelay` rời rạc).
- [ ] **E-4-3** Thêm module `ekt_modbus` vào thư viện (CRC-16 Modbus hiện nằm trong PC Agent bằng Python → cần bản C cho firmware).
- [ ] **E-4-4** Phát hành `v1.1.0` khi Track B (firmware ESP32-S3) bắt đầu dùng thư viện.

---

## 6. Lịch dự kiến GR2 (4 tuần)

| Tuần | Nội dung | Mốc bàn giao |
|---|---|---|
| **Tuần 2** 🔶 *đã xong phần mềm* | Giai đoạn 1 (12 task P0: A-8-6/7, A-9-1..4, A-7-6/7, A-5-5, A-6-6, A-4-10, D-4) + Giai đoạn 2 (A-4-8/9, A-7-5, A-9-5/6, A-5-4) | **Service chạy 24/7 thật trên máy** + tài liệu vận hành + dashboard có biểu đồ |
| **Tuần 3** | A-10 (MQTT), C-1 (tách Web Server), D-5 | **MQTT uplink + Web Server tách riêng** |
| **Tuần 4** | Test 24 h, C-2…C-5, D-6, **B-4-0…B-4-4** (firmware ESP32-S3) | **Báo cáo GR2 + demo** + firmware S3 chạy được |
| **Trong GR2, sau Tuần 4** | **B-5** (vòng lặp khép kín) → **B-3** (phần cứng EasyEDA) | Controller điều khiển relay qua MQTT, đo được PZEM #2 |
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
4. **ESP32 trong GR2** — em định làm Track B **sau Track A** (B-4 firmware ESP32-S3 → B-5 vòng lặp khép kín → B-3 phần cứng), vẫn kịp trong GR2. Thầy thấy thứ tự này ổn chứ?
5. **Bảo mật API** — có yêu cầu đặt mật khẩu cho dashboard / API không?
6. **Báo cáo GR2 Tuần 2** — thầy muốn nhấn mạnh phần nào: tính "service" hay tính "mô hình tổng thể"?
