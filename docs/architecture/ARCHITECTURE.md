# Kiến trúc hệ thống Smart Power Outlet

> Tài liệu kiến trúc cấp hệ thống, bám theo mô hình **3 thành phần** mà GVHD đã đề xuất trong buổi báo cáo GR2 Tuần 1.
> Cập nhật: 2026-11-09 · Liên kết: [`ROADMAP.md`](../../ROADMAP.md)

---

## 1. Bối cảnh & vấn đề cần giải

**Bài toán gốc:** đồng hồ đo điện **PZEM-004T V3.0** là thiết bị **Modbus slave** kết nối qua **USB-TTL**. Nó *bắt buộc* phải có máy tính ở giữa.

**Lý giải sản phẩm (theo GVHD):** PC Agent được cài lên **một máy chủ**, và máy chủ đó giám sát năng lượng tiêu thụ của **một tổ hợp máy chủ trong tủ rack**. Đây là một tình huống thực tế rất phổ biến: mỗi tủ rack có một PDU đo tổng công suất, và bạn muốn biết tủ đó đang tải bao nhiêu, có vượt ngưỡng không, và sự cố xảy ra lúc nào.

**Hệ quả thiết kế:** vì PC Agent phải giữ phiên serial liên tục trong thời gian dài, nó **không được là một script chạy tay**. Nó phải là:

- một **tiến trình nền** tự khởi động cùng máy, **không cần đăng nhập người dùng**;
- **headless** — không GUI, chạy trong **Session 0**;
- **tự phục hồi** — chịu được việc USB-TTL bị rút, cổng bị chiếm, hay tiến trình crash;
- **tự dò** cổng COM và **ghi nhớ** cổng đúng để lần sau khởi động tức thì.

---

## 2. Mô hình 3 thành phần

| # | Thành phần | Chạy trên | Trách nhiệm | Giao tiếp | Trạng thái |
|---|---|---|---|---|---|
| **1** | **Electronic PC Agent** | Máy chủ giám sát trong tủ rack (Windows Server hoặc Linux host) | Đọc PZEM-004T liên tục; tự dò COM; lưu time-series; đánh giá ngưỡng & ghi sự cố; phục vụ API nội bộ | **Nhận:** Modbus-RTU qua USB-TTL (`\\.\COMx`) · **Cung cấp:** REST API `127.0.0.1:8000` · **Gửi (sau):** MQTT | **P0 — đang làm** |
| **2** | **Central IoT Controller** | Vi điều khiển **ESP32-S3 N16R8** (ESP-IDF 5.5.3, target `esp32s3`) | Cấu hình & duy trì WiFi; subscriber MQTT; điều khiển relay; đo điện qua PZEM #2 (UART1); giám sát an toàn (quá nhiệt / quá tải → cắt relay) | Nhận MQTT qua WiFi · Điều khiển GPIO relay · UART1 ↔ PZEM #2 | **P1 — làm sau Track A, vẫn trong GR2** |
| **3** | **Web Server** | Máy chủ web trung tâm | Giao diện web + API người dùng; báo cáo; lịch sử sự kiện; cấu hình | Nhận REST / MQTT từ PC Agent | **P1 — đang dựng dần** |

Sơ đồ: [`diagrams/system-architecture.md`](diagrams/system-architecture.md) (Mermaid + ASCII bản in).

### 2.1. Vì sao Web Server **không** cắm trực tiếp serial?

GVHD gợi ý: *"Máy chủ web sẽ cắm trực tiếp seria để đọc số liệu từ thiết bị"*. Ta **không** làm theo hướng đó, vì:

1. **Exclusive lock của cổng COM trên Windows.** Chỉ một tiến trình được giữ handle cổng serial tại một thời điểm. Tiến trình thứ hai nhận `PermissionError(13) / Access is denied`. Nếu cả PC Agent lẫn Web Server đều mở cổng, một trong hai sẽ phải giành nhau liên tục.
2. **PC Agent là tiến trình duy nhất sống 24/7.** Nó là chủ sở hữu của phiên serial. Nếu Web Server giữ cổng, mỗi lần Web Server restart sẽ làm gián đoạn giám sát — và ngược lại, PC Agent sẽ không dò được thiết bị.
3. **Tách bạch tầng.** PC Agent = tầng thiết bị (edge). Web Server = tầng trình diễn (application). Một máy chủ web có thể phục vụ **nhiều** tủ rack; nó không nên biết gì về COM.

> **Nếu GVHD vẫn muốn Web Server đọc serial trực tiếp:** phương án thay thế là biến PC Agent thành **serial ↔ HTTP bridge** (một endpoint `/api/measure` trả về số đo mới nhất), để Web Server vẫn "đọc từ thiết bị" một cách gián tiếp mà không tranh chấp cổng. Cần trao đổi lại ở buổi báo cáo GR2.

---

## 3. Kiến trúc bên trong Electronic PC Agent

```
                      ┌──────────────────────────────────────────┐
   USB-TTL  ────────►│  drivers/pzem004t.py                    │
   (\\.\COMx)        │  • CRC-16 Modbus                        │
   Modbus-RTU        │  • build_read_frame / build_write_single │
   9600 8N1          │  • Pzem004T._decode → PzemMetrics      │
   FC 0x04           └──────────────┬───────────────────────────┘
                                     │
        ┌────────────────────────────▼────────────────────────────┐
        │  discovery.py — COM Auto-Discovery (4 bậc)             │
        │  ① fast-path cổng đã nhớ  ② ưu tiên theo usb_location  │
        │  ③ quét cổng USB-TTL       ④ quét 0x01..0xF7            │
        │  Xác minh: func code + CRC + U/f hợp lý                │
        │  Anti-Flapping: chỉ ghi đè khi đã xác minh              │
        └────────────────────────────┬────────────────────────────┘
                                     │ config.json (atomic write)
                                     ▼
        ┌──────────────────────────────────────────────────────────┐
        │  core/poller.py — ModbusPoller (thread, chu kỳ 1 Hz)     │
        └───┬─────────────────────┬──────────────────┬───────────┘
            │                     │                  │
            ▼                     ▼                  ▼
   core/state.py          core/rules.py     storage/sqlite_store.py
   StateStore              RuleEngine        TelemetryStore
   (mẫu mới nhất,          (ngưỡng cảnh báo)  • telemetry_raw (14 n)
    trạng thái, khóa)      → bảng events       • telemetry_hourly (365 n)
            │                     │                  │
            └─────────────────────┴─────────┬────────┘
                                            ▼
                              api/server.py — AgentServer
                              http.server, 127.0.0.1:8000
                              /  /api/health  /api/status  /api/metrics
                              /api/history  /api/events  /api/config
```

Sơ đồ chi tiết + vòng đời service: [`diagrams/agent-internals.md`](diagrams/agent-internals.md).

### 3.1. Tầng giao thức — hai tầng tách biệt

GVHD nhấn mạnh: *"Serial là hạ tầng vật lý, còn Modbus chỉ là giao thức qui định làm gì nói gì thôi."* — đúng, và code phản ánh đúng điều đó:

| Tầng | Trách nhiệm | Nơi hiện thực |
|---|---|---|
| **Hạ tầng vật lý (serial)** | Mở/đóng cổng, baud, timeout, framing byte | `pyserial.Serial` trong `drivers/pzem004t.py` |
| **Giao thức (Modbus-RTU)** | CRC-16, dựng frame, kiểm tra frame, giải mã thanh ghi | `crc16_modbus`, `build_read_frame`, `Pzem004T._decode` |
| **Hệ thống (agent)** | Dò cổng, lịch lấy mẫu, lưu trữ, cảnh báo, API | `discovery.py`, `core/`, `storage/`, `api/` |

Hệ quả thực tế: thay đổi **thiết bị** (PZEM-004T → thiết bị Modbus khác) chỉ đụng tầng 2–3. Đổi **hạ tầng** (USB-TTL → RS-485 adapter công nghiệp) chỉ đụng tầng 1.

### 3.2. Giao thức PZEM-004T V3.0 (đã kiểm chứng)

**Tầng vật lý:** UART 9600 bps, 8 data bits, 1 stop bit, no parity.
**Tầng ứng dụng:** Modbus-RTU, slave address `0x01` (thiết bị thật trong dự án), function code `0x04` (đọc input register).

| Mã | Ý nghĩa |
|---|---|
| `01 04 00 00 00 0A 70 0D` | Master → Slave: đọc 10 input register từ `0x0000` |
| `01 04 14 <20 byte> <crc_lo> <crc_hi>` | Slave → Master |

**CRC-16 Modbus:** đa thức phản chiếu `0xA001`, init `0xFFFF`, **byte thấp gửi trước, byte cao gửi sau**.

**Bảng thanh ghi đo:**

| Địa chỉ | Ý nghĩa | Độ phân giải |
|---|---|---|
| `0x0000` | Điện áp | 0.1 V |
| `0x0001`–`0x0002` | Dòng điện (16 bit thấp + 16 bit cao) | 0.001 A |
| `0x0003`–`0x0004` | Công suất (16 bit thấp + 16 bit cao) | 0.1 W |
| `0x0005`–`0x0006` | Điện năng (16 bit thấp + 16 bit cao) | 1 Wh |
| `0x0007` | Tần số | 0.1 Hz |
| `0x0008` | Hệ số công suất | 0.01 |
| `0x0009` | Cảnh báo | `0xFFFF` = đang báo động, `0x0000` = bình thường |

Hai điểm dễ sai nhất, đã có test riêng:
1. **Ghép 32 bit:** `value = (high << 16) | low` — trong frame, thanh ghi **thấp** (`0x0001`) đứng trước, thanh ghi **cao** (`0x0002`) đứng sau.
2. **Sentinel `0xFFFF`:** khi chưa có tải, PZEM trả `0xFFFF` → phải hiển thị `0`, không phải `655.3 A`.

Nguồn: `PZEM-004T_Huong_Dan_Giao_Thuc.docx` (mục 2.3) — frame mẫu `01 04 00 00 00 0A 70 0D` được dùng làm chuẩn đối chiếu trong `pc_agent/tests/test_decode.py`.

### 3.3. COM Auto-Discovery — 4 bậc

```
        ┌──────────────────────────────────────────────────────────┐
        │  ① FAST PATH: cổng đã nhớ + địa chỉ đã nhớ             │
        │     (không quét → khởi động trong ~60 ms)               │
        └───────────────┬──────────────────────────────────────────┘
                        │ thất bại
        ┌───────────────▼──────────────────────────────────────────┐
        │  ② TOPOLOGY: quét cổng, ưu tiên cổng có usb_location   │
        │     khớp với cổng đã nhớ (adapter không có serial no.)  │
        └───────────────┬──────────────────────────────────────────┘
                        │ thất bại
        ┌───────────────▼──────────────────────────────────────────┐
        │  ③ QUÉT ỨNG VIÊN: tier 1 = CH340/CP210x/FTDI/PL2303,   │
        │     tier 2 = USB serial khác, tier 3 = legacy            │
        │     địa chỉ thử: đã nhớ → 0x01 → 0xF8                   │
        └───────────────┬──────────────────────────────────────────┘
                        │ thất bại
        ┌───────────────▼──────────────────────────────────────────┐
        │  ④ QUÉT TOÀN BỘ: 0x01..0xF7 (chỉ khi --exhaustive-scan)│
        └──────────────────────────────────────────────────────────┘

        Mọi bậc đều qua XÁC MINH 5 bước trước khi công nhận:
          function code đúng → byte count đúng → CRC hợp lệ
          → U ∈ [80, 260] V → f ∈ [45, 65] Hz
```

**Vì sao phải nhớ `usb_location` chứ không chỉ số COM?** Adapter CH340 giá rẻ **không có** serial number riêng (không có EEPROM), nên Windows gán lại số COM mỗi khi cắm vào cổng USB khác. Đường dẫn USB vật lý (`1-4:x.3`) thì ổn định.

**Anti-Flapping — luật bất di bất dịch:** chỉ ghi đè `config.json` khi đã **xác minh được thiết bị thật**. Cổng hỏng, cổng bị chiếm, hay PZEM chưa có nguồn AC đều **không** được xoá cấu hình đã nhớ — nếu không, agent sẽ "ghi nhớ" giá trị rác rồi không bao giờ quay lại đúng cổng cũ.

Ghi cấu hình **nguyên tử**: ghi file tạm cùng thư mục → `flush()` → `fsync()` → `os.replace()`.

### 3.4. Lưu trữ time-series

| Bảng | Nội dung | Retention | Ghi |
|---|---|---|---|
| `telemetry_raw` | Mẫu thô theo chu kỳ lấy mẫu (1 Hz) | 14 ngày | Mỗi chu kỳ |
| `telemetry_hourly` | Tổng hợp theo giờ: min/max/avg U, I, P, PF; chênh lệch điện năng; **load factor**; số lần alarm | 365 ngày | Mỗi 5 phút (rollup giờ trước) |
| `events` | Cảnh báo & sự cố, kèm `resolved_at` | Không tự xoá | Khi có vi phạm ngưỡng |

SQLite ở chế độ **WAL** + `synchronous=NORMAL` → đọc được đồng thời trong lúc ghi (API đọc không bị chặn bởi vòng ghi 1 Hz). File DB nằm ở `%ProgramData%\SmartPowerOutlet\data\telemetry.db` (Windows) hoặc `$XDG_DATA_HOME/smartpoweroutlet/` (Linux).

### 3.5. Rule Engine — đánh giá trong tiến trình

| Sự kiện | Ngưỡng mặc định | Mức |
|---|---|---|
| `OVER_POWER` | `power_threshold_w` = 25000 W (max của PZEM V3.0) | critical |
| `OVER_VOLTAGE` | > 260 V | critical |
| `UNDER_VOLTAGE` | < 180 V | warning |
| `DEVICE_ALARM` | thanh ghi `0x0009 = 0xFFFF` (alarm phần cứng của PZEM) | critical |
| `DEVICE_OFFLINE` | mất kết nối serial | critical |

Đánh giá **trong tiến trình** chứ không đẩy lên broker: độ trễ < 1 ms, không phụ thuộc mạng, và cảnh báo vẫn kêu được khi broker MQTT chết hoặc router mất mạng — đúng tình huống của một máy chủ rack. Sự kiện tự đóng (`resolved_at`) khi trở lại bình thường để không spam log.

---

## 4. Chạy như một dịch vụ

### 4.1. Windows Service (SCM)

| Thuộc tính | Giá trị |
|---|---|
| Tên service | `SmartPowerOutletAgent` |
| Tên hiển thị | `Smart Power Outlet PC Agent` |
| Tài khoản | `LocalSystem` (mặc định) |
| Startup | **Delayed auto-start** (`SERVICE_DELAYED_AUTO_START_INFO`) |
| Recovery | `restart/5000` → `restart/10000` → `restart/30000`, `reset= 86400`, `failureflag 1` |
| ImagePath | `<venv>\Scripts\python.exe "<install>\pc_agent\src\pc_agent\deploy\windows_service.py"` |

**Vì sao không dùng `pythonservice.exe`?** Wrapper mặc định của pywin32 được **link cứng** với `pythonXY.dll` của bản Python gốc và **không** đọc `pyvenv.cfg`. Hệ quả: service chạy bằng Python gốc (mất `pyserial` đã cài trong venv) và không nạp được DLL → không chạy. Pywin32 hỗ trợ cách khác — `python.exe` **trực tiếp** làm host (source pywin32 ghi rõ: *"it is now possible for python.exe to directly host services"*). Ta làm đúng vậy: `ImagePath` trỏ thẳng vào `venv\Scripts\python.exe`.

**Vì sao `pywin32` chứ không phải WinSW / NSSM?**

- **Không cần binary ngoài** → cài đặt chỉ cần `pip install pywin32`.
- **Không bị EDR/Defender gắn cờ** → NSSM đã ngừng phát hành từ 2014 và hay bị coi là "HackTool".
- **Chạy được với `venv`** (xem trên).
- Vẫn giữ được ưu điểm của wrapper ngoài: tự cấu hình `FailureActions` để SCM tự khởi động lại khi tiến trình chết.

**Session 0 — bẫy cần tránh:** service chạy trong Session 0, không có console; `sys.stdout`/`sys.stderr` có thể là `None` và làm `print()` ném `AttributeError`. Vì vậy `logging_setup.setup_logging()`:
- **luôn** ghi log ra file với `RotatingFileHandler` (10 MB × 10 bản) — an toàn trong Session 0;
- **chỉ** gắn handler console khi `_console_available()` xác nhận stdout dùng được.

**Cài đặt:**

```powershell
# Chạy PowerShell với quyền Administrator
cd pc_agent\deploy
.\install_service.ps1                 # mặc định API 127.0.0.1:8000
.\install_service.ps1 -ApiHost 0.0.0.0 -ApiPort 8000   # mở cho LAN (tự thêm firewall rule)
.\uninstall_service.ps1               # gỡ bỏ
```

### 4.2. Linux daemon (systemd)

Unit file: `pc_agent/deploy/smart-power-agent.service`.

```ini
[Unit]
Description=Smart Power Outlet PC Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/smartpower/venv/bin/pc-agent --no-console-log
Restart=always
RestartSec=10

ConfigurationDirectory=smartpower
StateDirectory=smartpower
LogsDirectory=smartpower
DeviceAllow=/dev/ttyUSB0 rw

NoNewPrivileges=true
ProtectSystem=strict
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Cấu hình nằm ở `$XDG_CONFIG_HOME/smartpoweroutlet/config.json` (hoặc `~/.config/smartpoweroutlet/`), dữ liệu ở `$XDG_DATA_HOME/smartpoweroutlet/`.

### 4.3. Cùng một codebase, hai chế độ

Nguyên tắc: **không fork mã nguồn**.

| Chế độ | Lệnh | Ai chịu trách nhiệm dừng |
|---|---|---|
| Foreground (dev) | `python -m pc_agent` | `SIGINT` (Ctrl+C) → `stop_event` |
| Windows Service | `pc-agent-service` / `windows_service.py` | `SvcStop()` → `runtime.stop()` → `stop_event` |
| Linux daemon | `systemd` → `python -m pc_agent` | `SIGTERM` → `stop_event` |

Cả ba đều gọi chung `run_agent()` / `AgentRuntime`. `install_signal_handlers()` ánh xạ `SIGINT`/`SIGTERM`/`SIGBREAK` vào `threading.Event`; thread `ModbusPoller` thoát êm ái, đóng phiên serial, `shutdown()` HTTP server.

---

## 5. Ánh xạ thư mục ↔ thành phần

```
Smart_Power_Outlet/
├── pc_agent/                          ← THÀNH PHẦN 1: Electronic PC Agent
│   ├── pyproject.toml                  # PEP 621, entry points pc-agent / pc-agent-service
│   ├── src/pc_agent/
│   │   ├── __main__.py                 # CLI + AgentRuntime + run_agent()
│   │   ├── config.py                   # AgentConfig, đường dẫn, ghi atomic
│   │   ├── discovery.py                # COM Auto-Discovery 4 bậc + Anti-Flapping
│   │   ├── logging_setup.py            # logging an toàn Session 0
│   │   ├── drivers/pzem004t.py         # TẦNG 1+2: serial + Modbus-RTU
│   │   ├── core/poller.py              # vòng lấy mẫu 1 Hz, tự phục hồi
│   │   ├── core/rules.py               # Rule Engine (ngưỡng, sự kiện)
│   │   ├── core/state.py               # StateStore (trạng thái dùng chung)
│   │   ├── storage/sqlite_store.py     # TelemetryStore (WAL, raw/hourly/events)
│   │   ├── api/server.py               # AgentServer (http.server, REST)
│   │   ├── web/index.html              # dashboard tĩnh
│   │   ├── deploy/windows_service.py   # pywin32 ServiceFramework
│   │   └── tools/                      # probe_bus, probe_exhaustive, dump_settings
│   ├── deploy/
│   │   ├── install_service.ps1         # cài Windows Service
│   │   ├── uninstall_service.ps1       # gỡ Windows Service
│   │   ├── smart-power-agent.service   # systemd unit
│   │   └── run_dev.bat                 # chạy foreground nhanh
│   └── tests/                          # test_decode, verify_frame, check_crc
│
├── Smart_power_outlet_PIO/             ← THÀNH PHẦN 2: firmware Arduino (P1 — làm sau Track A)
├── Smart_Power_Outlet_ESP/             ← THÀNH PHẦN 2: firmware ESP-IDF (P1 — làm sau Track A)
├── smart_power_outlet_app/             ← app Flutter (client của thành phần 3)
├── hardware/                           ← EasyEDA / KiCad cho thành phần 2
└── docs/architecture/                   ← tài liệu kiến trúc (file này)
```

---

## 6. API của PC Agent (hợp đồng với Web Server)

| Endpoint | Method | Trả về | Ý nghĩa |
|---|---|---|---|
| `/` | GET | HTML | Dashboard tĩnh |
| `/api/health` | GET | JSON | `status`, `version`, `uptime_s`, thống kê DB |
| `/api/status` | GET | JSON | Trạng thái kết nối, cổng, địa chỉ, số mẫu, lỗi cuối |
| `/api/metrics` | GET | JSON | Số đo mới nhất (U, I, P, Wh, kWh, Hz, PF, alarm) |
| `/api/history` | GET | JSON | Lịch sử; `?from=&to=&resolution=raw\|hourly&limit=` |
| `/api/events` | GET | JSON | Sự cố; `?active_only=true&limit=` |
| `/api/config` | GET | JSON | Cấu hình hiện tại (cổng đã nhớ, ngưỡng, chu kỳ) |

Mặc định bind `127.0.0.1`. Khi bind ngoài localhost **phải** bật `api_token` (Bearer) — hiện là tuỳ chọn, đã ghi vào roadmap (A-8-6).

---

## 7. Câu hỏi kiến trúc đang mở

| # | Câu hỏi | Trạng thái | Người quyết |
|---|---|---|---|
| 1 | Web Server có cắm serial trực tiếp theo gợi ý của GVHD không? | Ta chọn **không** (lý do §2.1); đề xuất phương án bridge | **Cần GVHD xác nhận ở GR2** |
| 2 | PC Agent trong tủ rack chạy Windows Server hay Linux? | Cả hai đều đã có, nhưng mức độ test khác nhau (A-4-8 vs A-5-4) | **Cần GVHD / bố trí thực tế** |
| 3 | Một agent nhiều PZEM hay nhiều agent một PZEM? | Schema đã có `meter_id`; hiện là 1 agent : 1 meter | Giai đoạn 2 |
| 4 | Có cần thông báo cảnh báo ra ngoài (email / Telegram) không? | Đã đưa vào A-7-7 | Chờ GVHD |
| 5 | Bao lâu giữ dữ liệu thô? | Đang để 14 ngày raw / 365 ngày hourly | Có thể chỉnh theo yêu cầu lưu trữ của kỷ luật |
