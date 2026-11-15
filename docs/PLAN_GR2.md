# Kế hoạch thực thi GR2 — Chia 2 phần

> Lập ngày **2026-11-15**, sau khi khảo sát toàn bộ repo + phần cứng hiện có.
> Nguồn: `ROADMAP.md`, `docs/architecture/ARCHITECTURE.md`, phản hồi GVHD (Thầy Nguyễn Đức Tiến).
>
> **Cấu trúc:** Phần 1 = việc **bạn** (người dùng) phải chuẩn bị phần cứng + môi trường test.
> Phần 2 = việc **tôi** (trợ lý) phải làm — gồm cả phần *sau khi bạn chuẩn bị xong phần cứng*.
>
> Quy ước ưu tiên: `P0` = chặn tiến độ · `P1` = làm trong GR2 nhưng sau · `P2` = nice-to-have.
> ID task dùng đúng như `ROADMAP.md` để đối chiếu khi báo cáo GVHD.

---

## PHẦN 1 — KẾ HOẠCH CHO BẠN (chuẩn bị phần cứng & môi trường test)

### 1.1. Kiểm kê: bạn ĐÃ CÓ gì (không cần mua)

| Món | Tình trạng | Ghi chú |
|---|---|---|
| PZEM-004T V3.0 × 1 | ✅ có | Loại kẹp dây CT đóng mở. Đã đấu 220 VAC + đèn bàn, đọc được qua COM10. |
| USB-TTL adapter | ✅ có | CH340/CP210x. Từng gây lỗi `PermissionError(13)` do bị process khác giữ. |
| ESP32-P4 rev 0.1 + ESP32-C6 coprocessor | ✅ có | Board JC-ESP32P4-M3. Flash được bằng ESP-IDF **5.5** (`CONFIG_ESP32P4_REV_MIN_100=y`). |
| Laptop Windows | ✅ có | Dùng làm máy test PC Agent. |
| WSL Ubuntu (systemd=true) | ✅ có | `ps -p 1 -o comm=` → `systemd`. Dùng test systemd unit. |
| Docker Desktop 29.2.1 | ✅ có | Có thể chạy Mosquitto/EMQX làm broker nội bộ. |
| EasyEDA Pro client + `easyeda-api` skill | ✅ có | Bridge server + extension `run-api-gateway` đã cài. |
| ESP-IDF 5.5.3 & 5.2 | ✅ có | Tại `D:\ProgramData\Espressif`. |

**Trạng thái hiện tại (đã kiểm tra):** *không có thiết bị nào cắm* — COM5/COM6 đều là Bluetooth. Không thấy USB-TTL hay ESP32.

### 1.2. Vật tư CẦN MUA / CẦN THÊM

#### Ưu tiên 1 — Chặn Track A (làm được ngay, chi phí thấp)

| Mã | Món | Spec tối thiểu | Vì sao cần | Ghi chú |
|---|---|---|---|---|
| **H-01** | PZEM-004T V3.0 dự phòng | kẹp dây CT đóng mở | Dự phòng + test 2 meter | **Thầy đã nói sẽ mua** → nếu thầy mua thì bỏ mục này |
| **H-02** | Bóng đèn LED ~9–12 W | — | Tạo tải **dưới** ngưỡng để test `UNDER`/bình thường | Có thể dùng đèn bàn sẵn có |
| **H-03** | Bóng sợi đốt 60–100 W **hoặc** bếp điện 1500–2000 W | — | Tạo tải **vượt** ngưỡng → test `OVER_POWER`, `OVER_CURRENT`, load factor | 1 bóng sợi đốt là đủ |
| **H-04** | Ổ cắm lộ thiên (splitter) 1→2, 10 A | 10 A | Cắm PZEM + tải **cùng lúc** | Hoặc dùng cục chốt + dây riêng |
| **H-05** | Cầu dao/automat 16 A + hộp điện nhỏ | 16 A | An toàn khi đấu 220 VAC | Không bắt buộc nếu dùng ổ cắm sẵn |

#### Ưu tiên 2 — Chặn Track B (ESP32 Controller) + B-3 (PCB)

| Mã | Món | Spec tối thiểu | Vì sao cần |
|---|---|---|---|
| **H-06** | **ESP32-C3 SuperMini** hoặc **ESP32-WROOM-32 devkit** | 4 MB flash, WiFi onboard, USB-TTL on-board | ⚠️ Xem mục 1.6 — P4 cần coprocessor C6 (ESP-Hosted) rất dễ lỗi; board WiFi-onboard đơn giản hơn nhiều cho GR2 |
| **H-07** | Module relay 1 kênh 5 V | opto-isolated, 10 A/250 VAC, **active LOW** | Điều khiển ổ cắm — thành phần thật của Controller |
| **H-08** | Module nguồn AC→DC 5 V | HLK-PM01 (5 V/3 W) hoặc LM2596 | Cấp nguồn ESP32 + relay từ đường 220 V |
| **H-09** | Nút bấm + LED + điện trở pull-up 10 kΩ + header 2.54 mm | 10 kΩ 1/4 W | Nút reset WiFi (giữ 3 s), LED trạng thái |
| **H-10** | Breadboard + dây jumper | 830 lỗ | Prototype trước khi ra PCB |
| **H-11** | PCB 2 lớp (đặt sau khi B-3 xong) | JLCPCB/PCBWay, ~30–50 kyu/board | Board thật, đặt 3–5 mạch |

#### Ưu tiên 3 — Cho hệ thống hoàn chỉnh

| Mã | Món | Vì sao cần |
|---|---|---|
| **H-12** | USB hub có nguồn hoặc cáp nối dài | Test rút/cắm USB-TTL (A-9-5) mà không làm sập laptop |
| **H-13** | Mini-PC / máy cũ (Windows hoặc Linux) | Demo PC Agent chạy 24/7 giống môi trường rack thật |

### 1.3. Sơ đồ đấu nối PZEM-004T ← USB-TTL (bạn tự làm theo)

```
        ┌──────────────────┐              ┌─────────────────┐
 220VAC │  L ──────┐       │              │  USB-TTL adapter│
        │          [CT] PZEM-004T V3.0    │  (CH340/CP210x) │
        │  N ──┐   │  TX ──┼──────────────┤ RX              │
        │      │   │  RX ──┼──────────────┤ TX              │
        │      │   │  VCC ─┼─── 5V ───────┤ 5V              │
        └──────┴───┤  GND ─┼─── GND ──────┤ GND             │
                   └───────┘              └─────────────────┘
                     ↑
              tải (đèn/bếp) nối qua đây
```

⚠️ **Hai điều kiện tiên quyết đã được kiểm chứng:**
1. **PZEM phải có 220 VAC ở chân L/N** mới phản hồi trên UART (quang họp không dẫn qua khi mất điện lưới).
2. Adapter USB-TTL phải **3.3 V tolerant** (PZEM V3.0 dùng mức logic 3.3 V).

### 1.4. Môi trường test cần chuẩn bị (theo từng task)

| Task | Bạn cần làm | Lưu ý |
|---|---|---|
| **A-4-8** (reboot + auto-start) | Chạy PowerShell **as Administrator** để cài service → **reboot máy** → báo lại tôi để kiểm tra | Tôi không tự reboot được máy đang chat |
| **A-4-9** (quyền COM dưới LocalSystem) | Cắm USB-TTL + PZEM (đã đấu 220 VAC) | Nếu bị `Access is denied` → fallback: chạy service dưới tài khoản user |
| **A-5-4** (systemd) | Cấp quyền `usbipd` cho WSL **hoặc** cho tôi test trên máy Linux thật | WSL có systemd nhưng **không** thấy `/dev/ttyUSB*` |
| **A-7-5** (ngưỡng cảnh báo) | Cắm H-02 rồi H-03, đổi tải → quan sát | Tôi sẽ hạ ngưỡng trong config để test nhanh |
| **A-9-5** (rút/cắm) | Rút/cắm USB-TTL giữa lúc agent chạy | Nên dùng H-12 |
| **B-2** (firmware ESP32) | Cắm board H-06, cắm relay H-07, cấp nguồn H-08 | Sẽ chốt board sau khi bạn hỏi thầy (mục 1.6) |

### 1.5. Bạn cần **làm ngay** (không đợi phần cứng)

| # | Việc | Vì sao |
|---|---|---|
| **1** | **Đổi mật khẩu MQTT** trên broker `mqtt.toolhub.app` (tài khoản `REDACTED_MQTT_USERNAME`) | Thông tin đã nằm trong repo **PUBLIC** → phải rotate ngay |
| **2** | Cài `git-filter-repo`: `pip install git-filter-repo` | Tôi cần để gỡ secret khỏi lịch sử git |
| **3** | Xác nhận 3 câu hỏi với thầy (mục 1.6) | Quyết định thiết kế Track B + A-5 |
| **4** | Cho tôi biết bạn có **ESP32-WROOM-32 / ESP8266** hay chưa | Tránh mua trùng H-06 |

### 1.6. Ba câu hỏi cần chốt với GVHD (bạn hỏi, tôi phụ thuận)

| # | Câu hỏi | Ảnh hưởng | Khuyến nghị của tôi |
|---|---|---|---|
| **Q1** | Track B dùng board nào: **ESP32-P4** (đã có, cần coprocessor C6/ESP-Hosted — dễ lỗi, build chậm) hay **ESP32-C3/WROOM** (WiFi onboard, đơn giản)? | B-1, B-2, B-3, phần cứng H-06 | **C3/WROOM** cho GR2 — giảm rủi ro; P4 giữ làm hướng nghiên cứu |
| **Q2** | Broker MQTT: dùng **broker công cộng** `mqtt.toolhub.app` (đang dùng, dùng chung — rủi ro lộ dữ liệu rack) hay **tự host** Mosquitto/EMQX trong Docker? | A-10, Track B, Track C | **Tự host Mosquitto** (Docker đã có sẵn) — đồ án nói rõ "tự chủ"; broker public chỉ dùng để demo |
| **Q3** | Máy chủ rack thật chạy **Windows Server** hay **Linux**? | ưu tiên A-4 vs A-5 | Làm **cả hai** (đã gần xong), nhưng nếu phải chọn một thì **Windows** — đã có `install_service.ps1` hoàn chỉnh |

### 1.7. Rủi ro phần cứng cần bạn lưu ý

| Rủi ro | Dấu hiệu | Xử lý |
|---|---|---|
| PZEM mất nguồn AC | Agent báo `DEVICE_OFFLINE`, log "không phản hồi UART" | Cấp lại 220 VAC — không phải lỗi phần mềm |
| COM bị chiếm | `PORT_BUSY` | Đóng PuTTY/PlatformIO Monitor trước khi start agent |
| Đổi số COM sau khi rút/cắm | Agent vẫn tự tìm lại (đã có `usb_location`) | Không cần can thiệp |
| Relay đóng cầu khi ESP32 mất điện | Ổ cắm bị mất điện | Chấp nhận (fail-safe) hoặc dùng relay NC — sẽ ghi rõ trong B-3 |

---

## PHẦN 2 — KẾ HOẠCH CHO TÔI (trợ lý)

> Chia 7 giai đoạn. Mỗi giai đoạn có **điều kiện vào** rõ ràng và **hàng bàn giao** kiểm chứng được.
> Giai đoạn 0–2 tôi làm được ngay. Giai đoạn 4–5 **phụ thuộc phần cứng của bạn**.

### Giai đoạn 0 — Nền tảng & vệ sinh mã nguồn `P0` *(làm ngay, không cần phần cứng)*

| # | Việc | Chi tiết | Ưu tiên |
|---|---|---|---|
| 0.1 | **Gỡ secret khỏi git** | `git rm --cached Smart_power_outlet_PIO/include/secrets.h`; tạo `secrets.h.example`; dùng `git filter-repo` xoá khỏi toàn bộ lịch sử; push lại các branch | **P0 — khẩn** |
| 0.2 | Chuyển secret sang cơ chế **nạp lúc chạy** | `secrets.h` → biến môi trường / file ngoài repo; `Smart_Power_Outlet_ESP/main/secrets.h` và `app/.../secret.dart` cũng chuyển sang mẫu `.example` | P0 |
| 0.3 | Fix **sai lệch `RELAY_GPIO`** trong tài liệu | `platformio.ini` comment ghi GPIO 34 nhưng build flag là **32**; `main.cpp` docstring ghi GPIO 20 (chỉ đúng cho P4) | P1 |
| 0.4 | **Ghi log ký ức** quyết định | Lưu plan này + kết quả khảo sát vào `agentmemory` | P1 |
| 0.5 | Tách nhánh & commit sạch | Đang ở `feature/gr2-pc-agent-service`; stage đúng file, không lẫn build artifact | P1 |

**Hàng bàn giao:** `git grep -i "MQTT_PASSWORD" $(git rev-list --all)` → rỗng; `secrets.h` không còn bị track; repo public không còn secret.

### Giai đoạn 1 — Track A: đóng các task `P0` còn mở `P0`

| # | Task | Nội dung | Cần gì từ bạn |
|---|---|---|---|
| 1.1 | **A-8-6** | Bật xác thực **bắt buộc** khi bind ngoài `127.0.0.1` (hiện tuỳ chọn → lỗ hổng). Tự sinh token ngẫu nhiên lần đầu, in ra log, hỗ trợ `POST /api/config` đổi token | — |
| 1.2 | **A-8-7** | Biểu đồ lịch sử 24 h / 7 d / 30 d trên dashboard. `web/index.html` hiện **không có** thư viện chart → vẽ bằng Canvas/SVG thuần (không thêm CDN, giữ "bề mặt tấn công nhỏ") | — |
| 1.3 | **A-4-10** = **D-3** | `docs/operations/TROUBLESHOOTING.md`: cổng bị chiếm, thiết bị bị rút, chưa có nguồn AC, đổi số COM, service không lên, quyền COM dưới LocalSystem | — |
| 1.4 | **D-4** | `docs/operations/INSTALL.md`: cài Windows Service + systemd từ đầu, cả 2 nền tảng | — |
| 1.5 | **A-7-6** | Ngưỡng **quá dòng** (`current_a`) + siết ngưỡng sụt áp theo thông số tủ rack; thêm ngưỡng cấu hình được | — |
| 1.6 | **A-9-1** | Health check + watchdog: im lặng > 3 chu kỳ → ghi `DEVICE_OFFLINE` | — |
| 1.7 | **A-9-2** | Giới hạn tốc độ log khi lỗi lặp (tránh đầy ổ đĩa khi cổng hỏng) | — |
| 1.8 | **A-9-3** | Version stamping: `/api/health` trả version package + **git commit** + thời điểm build | — |
| 1.9 | **A-9-4** | Backup tự động cấu hình + DB (`%ProgramData%\SmartPowerOutlet`), giữ 7 bản | — |
| 1.10 | **A-6-6** | Test 24 h: không rò rỉ disk, DB ổn định, WAL không phình | — |
| 1.11 | **A-5-5** | `install_linux.sh` (còn thiếu) + `uninstall` + tài liệu | — |
| 1.12 | **A-7-7** | Gửi thông báo tổng hợp khi sự kiện `critical` (Telegram webhook — có sẵn MCP `telegram_notify`) | — |

**Hàng bàn giao:** tất cả task `P0` trong ROADMAP đóng; `pytest` xanh; dashboard có biểu đồ; 2 file operations tồn tại.

### Giai đoạn 2 — Test trên máy thật `P0` *(cần bạn cắm thiết bị)*

| # | Task | Bạn cần làm | Tôi làm |
|---|---|---|---|
| 2.1 | **A-4-8** | Cài service (Admin) → **reboot** → báo lại | Kiểm tra `sc query` = RUNNING sau reboot, API healthy, kill tiến trình → SCM tự restart |
| 2.2 | **A-4-9** | Cắm USB-TTL + PZEM (có 220 VAC) | Xác minh đọc được dưới LocalSystem; nếu `Access is denied` → chuyển sang chạy dưới tài khoản user |
| 2.3 | **A-7-5** | Cắm H-02 / H-03, đổi tải | Hạ ngưỡng → xác nhận `events` ghi đúng + tự đóng + hiện trên `/api/events` |
| 2.4 | **A-9-5** | Rút/cắm USB-TTL giữa lúc chạy | Agent ghi `DEVICE_OFFLINE`, thử lại sau 5 s, tự nối lại khi cắm |
| 2.5 | **A-9-6** | Mở PuTTY giữ cổng | Agent báo đúng `PORT_BUSY` (không nhầm lỗi nguồn) |
| 2.6 | **A-5-4** | Cấp `usbipd` cho WSL hoặc máy Linux thật | `systemctl enable --now`, `journalctl -u`, `is-enabled` = enabled |

**Hàng bàn giao:** bảng "Test thực địa" trong `docs/operations/TROUBLESHOOTING.md` có kết quả thật (không phải mô tả lý thuyết).

### Giai đoạn 3 — Track A mở rộng + Track C + Track D `P1`

| # | Task | Nội dung |
|---|---|---|
| 3.1 | **A-10** | MQTT uplink: client `paho-mqtt` (optional dep `[mqtt]`), mặc định tắt. Topic `smartoutlet/rack/<rack>/meter/<meter>` + `telemetry`/`state`/`event`. Retained `online`/`offline`. Reconnect backoff luỹ thừa, agent **không** chết vì broker chết. QoS 1, `clean_session=False` |
| 3.2 | **C-1** | Tách dashboard khỏi PC Agent thành **Web Server riêng**, chỉ đọc REST/MQTT — **không** mở serial (tránh tranh `exclusive-lock` COM) |
| 3.3 | **C-2…C-5** | Xác thực user + phân quyền; trang tổng quan rack; trang lịch sử (lọc, `raw` vs `hourly`, xuất CSV); trang cấu hình (đổi ngưỡng, chu kỳ lấy mẫu, xem COM đã nhớ) |
| 3.4 | **C-6** | App Flutter đọc từ Web Server; tái dùng `mqtt_service.dart`, bỏ secret hardcode |
| 3.5 | **D-5** | Báo cáo GR2 Tuần 2 (`.docx`) — mô hình 3 thành phần + kết quả test service |
| 3.6 | **D-6** | Cập nhật `ROADMAP.md` + `README.md` |

**Hàng bàn giao:** broker nhận được telemetry từ agent; Web Server chạy độc lập, không cần serial.

### Giai đoạn 4 — Track B: ESP32 Controller `P1` *(cần H-06/H-07/H-08)*

> **Điều kiện vào:** Giai đoạn 1–2 đạt DoD **và** bạn đã chốt Q1 (board) + có relay + nguồn.
> **Còn nằm trong GR2** (ưu tiên P1, làm sau Track A) — không chuyển sang GR3.

| # | Task | Nội dung | Ghi chú |
|---|---|---|---|
| 4.1 | **B-1-1** | `ConfigManager` trên NVS: schema có `version` + CRC, ghi atomic, chỉ commit khi dirty | Code `wifi_prov.cpp` hiện có nền tảng — refactor thành thư viện độc lập |
| 4.2 | **B-1-2** | Tối đa 5 SSID; nhớ SSID "ok" gần nhất; thử `ok` trước rồi mới xoay vòng | |
| 4.3 | **B-1-3** | Captive portal (AP + DNS) timeout 5 phút rồi thoát | Đã có HTML portal — bổ sung timeout |
| 4.4 | **B-1-4** | State machine `OFF/IDLE/CONNECTING/CONNECTED/PORTAL`, tuyệt đối không `delay()` | Hiện `delay(10)` ở `loop()` → thay bằng task tách |
| 4.5 | **B-1-5** | `arduino-lint --compliance strict` + `library.properties` → publish Arduino Library Registry | |
| 4.6 | **B-2-1** | `PowerMonitor`: RMS, công suất, PF, điện năng, NTC — **API độc lập phần cứng** | Module mới, tách khỏi WiFi/MQTT |
| 4.7 | **B-2-2** | Task FreeRTOS riêng cho sampling → publish qua queue | |
| 4.8 | **B-2-3** | MQTT client + điều khiển relay + **cắt relay khi quá nhiệt/quá tải** | |
| 4.9 | Test phần cứng | Flash board thật + relay thật, đo vòng lặp: **PC Agent → broker → ESP32 → relay → PZEM thấy công suất đổi** | Mốc tích hợp quan trọng nhất của GR2 |

**Hàng bàn giao:** ESP32 cấu hình WiFi qua điện thoại, điều khiển relay qua MQTT, đo điện và cắt relay khi quá tải — **vòng lặp khép kín** với PC Agent.

### Giai đoạn 5 — Track B-3: Phần cứng EasyEDA `P2`

> **Điều kiện vào:** Giai đoạn 4 cho thấy thiết kế điện tử ổn định.
> **Hiện trạng:** project EasyEDA `hardware/smart-power-outlet.eprj2` có cấu trúc Board1/Schematic1/P1/PCB1 nhưng **`source` rỗng, `documents` = 0** → phải vẽ từ đầu.

| # | Task | Nội dung |
|---|---|---|
| 5.1 | **B-3-1** | Schematic: 220 VAC → HLK-PM01 → LDO 3V3; ESP32-C3/WROOM; relay + driver (active LOW); nút BOOT/RESET; LED trạng thái |
| 5.2 | **B-3-2** | Khe cắm **I2C** đánh dấu rõ trên silkscreen `3V3 / GND / SDA / SCL`, có nhãn "I2C", pull-up 4.7 kΩ |
| 5.3 | **B-3-3** | Creepage/clearance ≥ 3 mm giữa cao áp và logic; test point 3V3/GND/SDA/SCL; run DRC trong EasyEDA |
| 5.4 | **B-3-4** | BOM + Gerber + đặt 1 lô 5 board (H-11) |

**Hàng bàn giao:** file Gerber + BOM; board đầu tiên về tay.

### Giai đoạn 6 — Tích hợp, demo, báo cáo `P1`

| # | Việc |
|---|---|
| 6.1 | Kịch bản demo end-to-end: mất nguồn AC → agent ghi `DEVICE_OFFLINE` → khi có lại → auto-reconnect → Web Server hiện đồ thị + sự kiện |
| 6.2 | Kịch bản quá tải: bật tải lớn → `OVER_POWER` ở PC Agent **và** relay tự cắt ở ESP32 |
| 6.3 | Soạn báo cáo GR2 cuối kỳ (`.docx`) + cập nhật ROADMAP/README |
| 6.4 | Ghi ký ức quyết định cuối cùng vào `agentmemory` |

---

## TỔNG HỢP — Ai làm gì, khi nào

| Hạng mục | Bạn | Tôi |
|---|---|---|
| Mua/thu vật tư H-01…H-13 | ✅ | — |
| Đổi mật khẩu MQTT broker | ✅ (ưu tiên cao) | — |
| Gỡ secret khỏi git | — | ✅ Giai đoạn 0 |
| Xác thực service thật, reboot, rút/cắm | ✅ | ✅ Giai đoạn 2 |
| Test systemd | ✅ (usbipd) | ✅ Giai đoạn 2 |
| Đóng task P0 còn mở (A-8-6/7, A-9-1..4, A-5-5, A-7-6/7) | — | ✅ Giai đoạn 1 |
| Viết TROUBLESHOOTING.md + INSTALL.md | — | ✅ Giai đoạn 1 |
| MQTT uplink (A-10) | — | ✅ Giai đoạn 3 |
| Web Server độc lập + trang (C-1…C-5) | — | ✅ Giai đoạn 3 |
| App Flutter (C-6) | — | ✅ Giai đoạn 3 |
| Firmware ESP32 (B-1, B-2) | ✅ (cắm board + relay) | ✅ Giai đoạn 4 |
| PCB EasyEDA (B-3) | ✅ (đặt mạch) | ✅ Giai đoạn 5 |
| Báo cáo (D-5) | — | ✅ Giai đoạn 3 + 6 |

## Rủi ro & đối sách

| Rủi ro | Mức | Đối sách |
|---|---|---|
| **Secret MQTT đã lộ trong repo public** | **Cao** | Giai đoạn 0 (gỡ + filter-repo) **và** bạn đổi mật khẩu ngay |
| Web Server bị yêu cầu cắm serial trực tiếp | Cao | Trao đổi lại ở buổi GR2: Windows chỉ cho 1 tiến trình giữ COM → đề xuất "serial ↔ HTTP bridge" nếu thầy vẫn muốn |
| Service không đọc được COM dưới LocalSystem | Cao | Test sớm ở Giai đoạn 2.2; fallback → chạy dưới tài khoản user |
| Broker công cộng bị giới hạn/sập, lộ dữ liệu rack | Trung bình | Q2 → Mosquitto tự host trong Docker (đã có Docker) |
| P4 + ESP-Hosted build lỗi, mất thời gian | Trung bình | Q1 → ưu tiên C3/WROOM; nếu giữ P4 thì dùng đường ESP-IDF sẵn có (`Smart_Power_Outlet_ESP`) |
| Hết thời gian GR2 | Trung bình | Cắt theo thứ tự: A-10 → C-2…C-6 → B-3. **Track A + B-1/B-2** vẫn đủ để báo cáo |
| Không có phần cứng Track B kịp | Trung bình | Làm B-1 (thư viện WiFi provisioning) + B-2 (firmware) trên board mô phỏng — không phụ thuộc PCB |

## Câu hỏi cần trả lời để bắt đầu Giai đoạn 1

1. Bạn đã **đổi mật khẩu MQTT** chưa? (chặn Giai đoạn 0)
2. Bạn có **ESP32-WROOM-32 / ESP8266** sẵn không? (tránh mua trùng H-06)
3. Bạn muốn tôi bắt đầu **Giai đoạn 0 + 1** ngay không, hay chờ bạn hỏi thầy Q1–Q3 xong?
