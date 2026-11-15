# Kế hoạch thực thi GR2 (bản 2) — Chia 2 phần

> Lập ngày **2026-11-15** (bản 2, thay thế bản 1).
> **Thay đổi so với bản 1:**
> 1. Bỏ hẳn việc *đổi mật khẩu MQTT* khỏi phạm vi kế hoạch — người dùng sẽ báo GVHD riêng. Repo **giữ nguyên**, không tạo repo mới.
> 2. Track B chốt **ESP32-S3 N16R8** (16 MB Flash / 8 MB Octal PSRAM) — thay cho ESP32-P4/C3 trong bản 1.
> 3. Bổ sung các task còn mở đã phát hiện khi rà soát code (A-8-7 chart, A-9-1..4, A-7-6/7, A-5-5, A-4-10, D-3, D-4) và **nhóm task mới** phát sinh từ rà soát này.
> 4. Bổ sung nhóm **Track B mới** (B-4: `PowerMonitor` cho ESP32-S3, B-5: vòng lặp khép kín đo–cắt).
>
> **Cấu trúc:** Phần 1 = việc **bạn** (mua + đấu + chuẩn bị môi trường test) · Phần 2 = việc **tôi** (trợ lý) — gồm cả phần *sau khi bạn chuẩn bị xong phần cứng*.
>
> Quy ước ưu tiên: `P0` = chặn tiến độ · `P1` = làm trong GR2 nhưng sau · `P2` = nice-to-have.
> ID task dùng đúng như `ROADMAP.md` để đối chiếu khi báo cáo GVHD.

---

## PHẦN 1 — KẾ HOẠCH CHO BẠN (chuẩn bị phần cứng & môi trường test)

### 1.1. Kiểm kê: bạn ĐÃ CÓ gì (không cần mua)

| Món | Tình trạng | Ghi chú |
|---|---|---|
| **PZEM-004T V3.0** × 1 | ✅ có | Loại kẹp dây CT đóng mở. Đã đấu 220 VAC + đèn bàn, đọc được qua COM10. |
| **USB-TTL adapter** | ✅ có | CH340/CP210x. Từng gây `PermissionError(13)` do bị process khác giữ. |
| **ESP32-S3 N16R8** | ✅ có (chốt) | Controller trung tâm Track B. Xem mục 1.6 về pin map. |
| Laptop Windows | ✅ có | Máy test PC Agent (Windows Service). |
| WSL Ubuntu (systemd=true) | ✅ có | `ps -p 1 -o comm=` → `systemd`. Test systemd unit. |
| Docker Desktop 29.2.1 | ✅ có | Broker Mosquitto nội bộ (nếu thầy yêu cầu tự chủ). |
| EasyEDA Pro + skill `easyeda-api` | ✅ có | Vẽ schematic/PCB B-3. |
| ESP-IDF **5.5.3** & 5.2 | ✅ có | `D:\ProgramData\Espressif`. **Đã xác minh 5.5.3 có target `esp32s3`.** |

**Trạng thái hiện tại:** *không có thiết bị nào cắm* — COM5/COM6 đều là Bluetooth.

### 1.2. Vật tư CẦN MUA / CẦN THÊM

#### Ưu tiên 1 — Chặn Track A (làm được ngay, chi phí thấp) · **mua trước**

| Mã | Món | Spec tối thiểu | Vì sao cần | Ghi chú |
|---|---|---|---|---|
| **H-01** | PZEM-004T V3.0 dự phòng | kẹp dây CT đóng mở | Dự phòng **+ làm meter thứ 2** cho ESP32-S3 (Track B cần 2 PZEM) | **Thầy đã nói sẽ mua** → nếu thầy mua thì bỏ mục này |
| **H-02** | Bóng đèn LED ~9–12 W | — | Tải **dướ** ngưỡng → test `UNDER`/bình thường | Dùng đèn bàn sẵn có |
| **H-03** | Bóng sợi đốt 60–100 W **hoặc** bếp điện 1500–2000 W | — | Tải **vượt** ngưỡng → test `OVER_POWER`, `OVER_CURRENT` | 1 bóng sợi đốt là đủ |
| **H-04** | Ổ cắm lộ thiên (splitter) 1→2, 10 A | 10 A | Cắm PZEM + tải **cùng lúc** | Hoặc dùng cục chốt + dây riêng |
| **H-05** | Cầu dao/automat 16 A + hộp điện nhỏ | 16 A | An toàn khi đấu 220 VAC | Không bắt buộc nếu dùng ổ cắm sẵn |

#### Ưu tiên 2 — Chặn Track B (ESP32-S3 Controller) + B-3 (PCB) · **mua song song**

| Mã | Món | Spec tối thiểu | Vì sao cần |
|---|---|---|---|
| **H-06** | Module relay 1 kênh 5 V | opto-isolated, 10 A/250 VAC, **active LOW** | Điều khiển ổ cắm — thành phần thật của Controller |
| **H-07** | Module nguồn AC→DC 5 V | HLK-PM01 (5 V/3 W) hoặc LM2596 | Cấp nguồn ESP32-S3 + relay từ đường 220 V |
| **H-08** | Nút bấm 6 mm + LED 5 mm + điện trở 10 kΩ + 1 kΩ | 10 kΩ 1/4 W | Nút reset WiFi (giữ 3 s), LED trạng thái |
| **H-09** | Breadboard 830 lỗ + dây jumper + header 2.54 mm | 830 lỗ | Prototype Track B trước khi ra PCB |
| **H-10** | PCB 2 lớp (đặt **sau** khi B-3 xong) | JLCPCB/PCBWay, ~30–50 kyu/board | Board thật, đặt 3–5 mạch |

#### Ưu tiên 3 — Cho hệ thống hoàn chỉnh · **mua nếu còn ngân sách**

| Mã | Món | Vì sao cần |
|---|---|---|
| **H-11** | USB hub có nguồn hoặc cáp nối dài | Test rút/cắm USB-TTL (A-9-5) mà không làm sập laptop |
| **H-12** | Mini-PC / máy cũ (Windows hoặc Linux) | Demo PC Agent chạy 24/7 giống môi trường rack thật |

**Ngân sách ước tính:** Ưu tiên 1 ≈ 265 k · Ưu tiên 2 ≈ 165 k (chưa gồm board S3 bạn đã có) · Ưu tiên 3 ≈ 310 k.

### 1.3. Sơ đồ đấu nối PZEM-004T ← USB-TTL

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

### 1.4. Pin map ESP32-S3 N16R8 (đã xác minh từ header ESP-IDF 5.5.3)

> **Cơ sở kỹ thuật:** đã đọc `components/soc/esp32s3/include/soc/spi_pins.h` và `gpio_num.h` của ESP-IDF 5.5.3.

| Chân | Cấp | Dùng cho | Ghi chú |
|---|---|---|---|
| **GPIO 21** | ra | Relay (H-06) | Active LOW → bật relay bằng mức `LOW` |
| **GPIO 48** | ra | LED trạng thái (H-08) | GPIO 48 là **LED RGB tích hợp** trên DevKitC-1 → dùng làm chẳng hạn |
| **GPIO 0** | vào | Nút reset WiFi (H-08) | Chân BOOT, có pull-up nội; giữ 3 s → xoá WiFi + restart |
| **GPIO 18** | vào | RX ← TX của PZEM #2 | UART1 |
| **GPIO 17** | ra | TX → RX của PZEM #2 | UART1 |
| **GPIO 8 / 9** | 2 chiều | I2C (dự phòng, B-3) | Khe cắm 4 chân, pull-up 4.7 kΩ trên PCB |

⛔ **Cấm dùng:**
- **GPIO 22–37** — bus MSPI octal dùng chung flash + PSRAM (`MSPI_IOMUX_PIN_NUM_*` = 26..37). Dùng là hỏng board.
- **GPIO 19/20** — USB native (D−/D+). Tránh nếu cần cắm USB.
- **GPIO 22–25** — nằm ngoài `SOC_GPIO_VALID_GPIO_MASK`.

✅ **Dải dùng được:** 0–18, 21, 38–48.

> ℹ️ **Phân biệt với 2 project cũ (không thuộc GR2):**
> - `Smart_power_outlet_PIO/` — PlatformIO/Arduino, hỗ trợ ESP32-WROOM (relay GPIO 32),
>   ESP32-P4 (relay GPIO 20), ESP8266 (relay GPIO 5). Relay **active HIGH**.
> - `Smart_Power_Outlet_ESP/` — ESP-IDF cho **ESP32-P4** (relay GPIO 20, nút GPIO 35).
>
> Hai project này **không** chạy trên ESP32-S3 và **không** nằm trong phạm vi GR2.
> Board mới (Track B) dựng **firmware mới** bằng ESP-IDF 5.5.3 cho `esp32s3` với
> pin map ở trên (relay GPIO 21, **active LOW**). Không chuyển code từ 2 project
> cũ sang — khác framework (Arduino vs ESP-IDF) lẫn SoC.

### 1.5. Bạn cần **làm ngay** (không đợi phần cứng)

| # | Việc | Vì sao | Mức |
|---|---|---|---|
| **1** | **Mua H-02, H-03, H-04** (bóng sợi đốt + ổ lộ thiên) | Chặn Giai đoạn 2 — test thật trên máy | 🟡 |
| **2** | **Cắm PZEM + USB-TTL, bật cầu dao, báo tôi** | Tôi chạy `--exhaustive-scan` để xác nhận cổng + địa chỉ | 🟡 |
| **3** | **Chụp ảnh mặt trước + mặt sau board ESP32-S3** | Tôi cần xác nhận: devkit nào, LED RGB có thật không, chân nào đã gắn sẵn | 🔴 |
| **4** | Xác nhận **với thầy**: broker dùng chung hay tự host (mục 1.6, Q2) | Quyết định có cài Mosquitto trong Docker không | 🟡 |

### 1.6. Ba câu hỏi cần chốt với GVHD

| # | Câu hỏi | Ảnh hưởng | Khuyến nghị của tôi |
|---|---|---|---|
| **Q1** | Broker MQTT: dùng **broker công cộng** `mqtt.toolhub.app` (thầy cấp, đang dùng chung) hay **tự host** Mosquitto trong Docker? | A-10, Track B, Track C | **Tự host Mosquitto** (Docker đã có) — đồ án nói rõ "tự chủ"; broker của thầy dùng để demo |
| **Q2** | Máy chủ rack thật chạy **Windows Server** hay **Linux**? | ưu tiên A-4 vs A-5 | Làm **cả hai** (đã gần xong), nếu phải chọn một thì **Windows** — `install_service.ps1` đã hoàn chỉnh |
| **Q3** | Đồ án có yêu cầu **báo cáo tuần** (docx) trước khi hết GR2 không? | D-5, D-6 | Có — tôi sẽ soạn sẵn `.docx` ở Giai đoạn 3 |

### 1.7. Môi trường test cần chuẩn bị (theo từng task)

| Task | Bạn cần làm | Lưu ý |
|---|---|---|
| **A-4-8** (reboot + auto-start) | Chạy PowerShell **as Administrator** để cài service → **reboot máy** → báo tôi | Tôi không tự reboot được máy đang chat |
| **A-4-9** (quyền COM dưới LocalSystem) | Cắm USB-TTL + PZEM (đã đấu 220 VAC) | Nếu `Access is denied` → fallback: chạy service dưới tài khoản user |
| **A-5-4** (systemd) | Cấp quyền `usbipd` cho WSL **hoặc** cho tôi test trên máy Linux thật | WSL có systemd nhưng **không** thấy `/dev/ttyUSB*` |
| **A-7-5** (ngưỡng cảnh báo) | Cắm H-02 rồi H-03, đổi tải → quan sát | Tôi sẽ hạ ngưỡng trong config để test nhanh |
| **A-9-5** (rút/cắm) | Rút/cắm USB-TTL giữa lúc agent chạy | Nên dùng H-11 |
| **A-9-6** (PORT_BUSY) | Mở PuTTY giữ cổng | Agent phải báo `PORT_BUSY`, không báo lỗi nguồn |
| **B-4** (firmware ESP32-S3) | Cắm board S3, cắm relay H-06, cấp nguồn H-07, cắm PZEM #2 (H-01) vào UART1 | Đủ để tôi flash + test |
| **B-5** (vòng lặp khép kín) | Kết nối ESP32-S3 vào WiFi, có broker | Tôi sẽ chạy kịch bản tự động |

### 1.8. Rủi ro phần cứng cần bạn lưu ý

| Rủi ro | Dấu hiệu | Xử lý |
|---|---|---|
| PZEM mất nguồn AC | Agent báo `DEVICE_OFFLINE`, log "không phản hồi UART" | Cấp lại 220 VAC — không phải lỗi phần mềm |
| COM bị chiếm | `PORT_BUSY` | Đóng PuTTY/PlatformIO Monitor trước khi start agent |
| Đổi số COM sau khi rút/cắm | Agent vẫn tự tìm lại (đã có `usb_location`) | Không cần can thiệp |
| **Dùng nhầm GPIO 26–37 trên S3** | Board không boot / flash lỗi | Tuân thủ pin map mục 1.4 — không dùng 22–37 |
| Relay đóng cầu khi ESP32 mất điện | Ổ cắm bị mất điện | Chấp nhận (fail-safe) hoặc dùng relay NC — ghi rõ trong B-3 |
| PSRAM octal chiếm MSPI | `spi_flash` init fail lúc boot | Xác minh `sdkconfig` đúng variant N16R8 |

---

## PHẦN 2 — KẾ HOẠCH CHO TÔI (trợ lý)

> Chia 7 giai đoạn. Giai đoạn 0–2 tôi làm **ngay, không cần phần cứng**. Giai đoạn 4–5 phụ thuộc phần cứng của bạn.

### Giai đoạn 0 — Nền tảng & vệ sinh mã nguồn `P0` ✅ *đã xong ~95%*

| # | Việc | Trạng thái |
|---|---|---|
| 0.1 | Gỡ `secrets.h` khỏi git index, tạo `.example` cho 3 nơi | ✅ xong |
| 0.2 | Scrub lịch sử bằng `git filter-repo` — 4 branch public đã sạch | ✅ xong |
| 0.3 | `.gitignore` đầy đủ (JVM crash log, Gradle, Flutter, Python cache, Playwright, backup) | ✅ xong |
| 0.4 | Fix sai lệch `RELAY_GPIO` trong tài liệu (`platformio.ini` ghi 34, build flag là 32) | ✅ xong |
| 0.5 | Ghi log ký ức quyết định vào `agentmemory` | ⬜ |

**Hàng bàn giao:** `git log --all -S "<credential>"` → rỗng; `secrets.h` không còn bị track; `.gitignore` chặn đúng artifact.

> ℹ️ **Ghi chú bảo mật:** còn 1 ref `refs/pull/3/head` trên GitHub (PR đã merge, ref bị GitHub đóng băng) trỏ tới commit cũ chứa credential. **Không scrub được bằng API.** Người dùng sẽ báo GVHD đổi mật khẩu — đây là biện pháp chắc chắn. Việc này **không chặn** bất kỳ task nào trong kế hoạch này.

### Giai đoạn 1 — Track A: đóng các task `P0` còn mở `P0` ✅ *đã xong (2026-11-15)*

| # | Task | Nội dung chi tiết | Cần gì từ bạn |
|---|---|---|---|
| 1.1 | **A-8-6** | **Bắt buộc xác thực khi bind ngoài localhost.** Hiện `api_token=None` ⇒ không auth. Sửa: khi `api_host` không phải loopback → **tự sinh token** `secrets.token_urlsafe(32)`, in ra log 1 lần + ghi vào file `api_token.txt` (mode 600), **từ chối khởi động** nếu không tạo được token. So sánh token bằng `hmac.compare_digest` (chống timing attack). Thêm `--rotate-token` và `POST /api/config/token` | ✅ xong |
| 1.2 | **A-8-7** | **Biểu đồ lịch sử** 24 h / 7 d / 30 d. `web/index.html` hiện 225 dòng, **không có thư viện chart** → vẽ **Canvas/SVG thuần** (không CDN → giữ "bề mặt tấn công nhỏ", không phụ thuộc mạng). Nguồn: `/api/history?resolution=raw|hourly`. Vẽ đường P (W), V (V), I (A) | ✅ xong — 3 lane chồng nhau, đã kiểm chứng trực quan |
| 1.3 | **A-4-10** = **D-3** | `docs/operations/TROUBLESHOOTING.md` — 6 lỗi thật đã gặp: cổng bị chiếm, thiết bị bị rút, **chưa có nguồn AC**, đổi số COM, service không lên, **quyền COM dưới LocalSystem**. Kèm bảng *nguyên nhân → dấu hiệu trong log → cách xử lý* | ✅ xong |
| 1.4 | **D-4** | `docs/operations/INSTALL.md` — cài Windows Service + systemd từ đầu, 2 nền tảng, có phần *Khắc phục sự cố* dẫn sang TROUBLESHOOTING | ✅ xong |
| 1.5 | **A-7-6** | **Ngưỡng quá dòng** (`current_threshold_a`) + siết ngưỡng sụt áp theo thông số tủ rack (220 V ±10 % → 198–242 V thay vì 180–260 V). Thêm 2 field vào `AgentConfig` + `RuleEngine` + `/api/config` | ✅ xong |
| 1.6 | **A-7-7** | **Thông báo tổng hợp** khi sự kiện `critical`. Thiết kế: `notifiers/` package với interface `Notifier` + `TelegramNotifier` (webhook, `requests` stdlib urllib, timeout 5 s, **retry có backoff**). **Không** làm agent chết vì webhook lỗi → đẩy sang thread riêng + queue | ✅ xong |
| 1.7 | **A-9-1** | **Watchdog**: im lặng > 3 chu kỳ → ghi `DEVICE_OFFLINE`. Hiện `offline_after_s=30` có trong config nhưng **chưa dùng** → nối vào poller | ✅ xong |
| 1.8 | **A-9-2** | **Giới hạn tốc độ log** khi lỗi lặp: cơ chế *suppression* theo (message-signature, khoảng 60 s) → log đầy 1 lần + "còn bị chặn N lần", không spam mỗi vòng lấy mẫu | ✅ xong |
| 1.9 | **A-9-3** | **Version stamping**: `/api/health` trả version package + **git commit SHA** + build timestamp. Đọc SHA lúc build (`importlib.metadata` + file `version.txt` sinh bởi `setup.py`/`pyproject` hook), fallback `"unknown"` | ✅ xong |
| 1.10 | **A-9-4** | **Backup tự động** cấu hình + DB vào `%ProgramData%\SmartPowerOutlet\backup\`, lịch hằng ngày, **giữ 7 bản**. Ghi atomically (dùng lại `atomic_write_json`), dùng SQLite **backup API** (`conn.backup()`) chứ không copy file thô (tránh hỏng DB khi đang ghi WAL) | ✅ xong |
| 1.11 | **A-5-5** | `pc_agent/deploy/install_linux.sh` + `uninstall_linux.sh` (bash, `set -euo pipefail`, idempotent) + đoạn systemd trong INSTALL.md | ✅ xong — script đã kiểm tra syntax (`bash -n`) |
| 1.12 | **A-6-6** | Chuẩn bị **test 24 h**: script `pc_agent/tools/soak_test.py` chạy `--simulate` 24 h, đo kích thước DB/WAL theo chu kỳ, xuất báo cáo. (Phần chạy thật cần bạn để máy bật) | ✅ xong — script chạy được; **chạy 24 h thật cần máy bật** |

**Hàng bàn giao:** tất cả task `P0` trong ROADMAP đóng · `pytest` xanh (36 test) · dashboard có biểu đồ (đã kiểm chứng trực quan) · 2 file operations tồn tại · API bắt buộc auth khi bind LAN.

> 🐛 **3 lỗi production do soak test phát hiện & đã sửa (2026-11-15):**
> 1. `sqlite_store.py` — `with sqlite3.connect(...)` **không đóng connection** → rò handle → `database table is locked`. Đã dùng `contextlib.closing` qua `_session()`.
> 2. `sqlite_store.py` — `purge_expired()` **thiếu dấu phẩy** cuối tuple → `sqlite3.ProgrammingError` **mọi lần gọi** → retention **không bao giờ chạy**.
> 3. `smart-power-agent.service` — file dùng **cú pháp XML** thay vì **INI** của systemd → không load được. Đã viết lại đúng chuẩn + thêm `chmod 644`.

### Giai đoạn 2 — Test trên máy thật `P0` 🔴 *(cần bạn cắm thiết bị)*

| # | Task | Bạn cần làm | Tôi làm |
|---|---|---|---|
| 2.1 | **A-4-8** | Cài service (Admin) → **reboot** → báo lại | Kiểm tra `sc query` = RUNNING sau reboot, API healthy, kill tiến trình → SCM tự restart |
| 2.2 | **A-4-9** | Cắm USB-TTL + PZEM (có 220 VAC) | Xác minh đọc được dưới LocalSystem; nếu `Access is denied` → chuyển sang tài khoản user |
| 2.3 | **A-7-5** | Cắm H-02 / H-03, đổi tải | Hạ ngưỡng → xác nhận `events` ghi đúng + tự đóng + hiện trên `/api/events` |
| 2.4 | **A-9-5** | Rút/cắm USB-TTL giữa lúc chạy | Agent ghi `DEVICE_OFFLINE`, thử lại sau 5 s, tự nối lại khi cắm |
| 2.5 | **A-9-6** | Mở PuTTY giữ cổng | Agent báo đúng `PORT_BUSY` (không nhầm lỗi nguồn) |
| 2.6 | **A-5-4** | Cấp `usbipd` cho WSL hoặc máy Linux thật | `systemctl enable --now`, `journalctl -u`, `is-enabled` = enabled |

**Hàng bàn giao:** bảng "Test thực địa" trong `TROUBLESHOOTING.md` có **kết quả thật**, không phải mô tả lý thuyết.

### Giai đoạn 3 — Track A mở rộng + Track C + Track D `P1`

| # | Task | Nội dung |
|---|---|---|
| 3.1 | **A-10** | MQTT uplink: client `paho-mqtt` (optional dep `[mqtt]`), **mặc định tắt**. Topic `smartoutlet/rack/<rack>/meter/<meter>` + `telemetry`/`state`/`event`. Retained `online`/`offline`. Reconnect backoff luỹ thừa, agent **không** chết vì broker chết. QoS 1, `clean_session=False`. Đọc credential từ **biến môi trường**, không hardcode |
| 3.2 | **C-1** | Tách dashboard khỏi PC Agent thành **Web Server riêng**, chỉ đọc REST/MQTT — **không** mở serial (tránh tranh `exclusive-lock` COM) |
| 3.3 | **C-2…C-5** | Xác thực user + phân quyền (admin/viewer); trang tổng quan rack; trang lịch sử (lọc, `raw` vs `hourly`, xuất CSV); trang cấu hình (đổi ngưỡng, chu kỳ lấy mẫu, xem COM đã nhớ) |
| 3.4 | **C-6** | App Flutter đọc từ Web Server; tái dùng `mqtt_service.dart`, bỏ secret hardcode (đọc từ `--dart-define` / file cấu hình ngoài repo) |
| 3.5 | **D-5** | Báo cáo GR2 (`.docx`) — mô hình 3 thành phần + kết quả test service + sơ đồ |
| 3.6 | **D-6** | Cập nhật `ROADMAP.md` + `README.md` |

**Hàng bàn giao:** broker nhận telemetry; Web Server chạy độc lập, không cần serial.

### Giai đoạn 4 — Track B: ESP32-S3 Controller `P1` 🔴 *(cần H-06/H-07/H-08/H-09 + H-01)*

> **Điều kiện vào:** Giai đoạn 1–2 đạt DoD **và** bạn đã cắm board S3 + relay + nguồn.
> **Quyết định kiến trúc quan trọng:** dựng **firmware mới** cho ESP32-S3 bằng **ESP-IDF 5.5.3** (target `esp32s3`) — **không** cố chuyển code PlatformIO P4 sang S3, vì cả framework (Arduino vs ESP-IDF) lẫn SoC đều khác. Tái sử dụng *ý tưởng* từ `Smart_power_outlet_PIO/src/wifi_prov.cpp` và `Smart_Power_Outlet_ESP/main/wifi_prov.c`.

| # | Task | Nội dung | Ghi chú |
|---|---|---|---|
| 4.1 | **B-4-0** | **Khởi tạo project ESP-IDF 5.5.3** cho `esp32s3`, variant **N16R8** (16 MB flash / 8 MB octal PSRAM). `sdkconfig.defaults`: flash 16 MB, PSRAM octal, **`CONFIG_SPIRAM_MODE_OCT=y`**. Xác minh `idf.py build` pass + `idf.py size` | Phải đúng variant, nếu không PSRAM sẽ chiếm chân MSPI |
| 4.2 | **B-4-1** | **Pin map theo mục 1.4**: relay GPIO21 (active LOW), LED GPIO48, nút GPIO0, UART1 TX=17/RX=18, I2C 8/9. Tạo `board_pins.h` với `#define` + comment cấm GPIO 22–37 | |
| 4.3 | **B-1-1** | `ConfigManager` trên **NVS**: schema có `version` + CRC, ghi atomic, chỉ commit khi dirty | Refactor từ `wifi_prov.cpp` hiện có |
| 4.4 | **B-1-2** | Tối đa 5 SSID; nhớ SSID "ok" gần nhất; thử `ok` trước rồi mới xoay vòng | |
| 4.5 | **B-1-3** | Captive portal (AP + DNS) timeout 5 phút rồi thoát | |
| 4.6 | **B-1-4** | State machine `OFF/IDLE/CONNECTING/CONNECTED/PORTAL`, **tuyệt đối không `delay()`** — task FreeRTOS tách nhau | Hiện `delay(10)` ở `loop()` → phải bỏ |
| 4.7 | **B-4-2** | **`PowerMonitor`**: đọc PZEM-004T qua UART1 (Modbus-RTU, CRC-16), decode RMS/công suất/PF/kWh. **Tách lớp transport ↔ protocol** y hệt cách `drivers/pzem004t.py` tách 2 tầng — đó là bài học thầy nói *"Serial là hạ tầng vật lý, Modbus chỉ là giao thức"* | **Module mới, độc lập phần cứng** |
| 4.8 | **B-4-3** | Task FreeRTOS riêng cho sampling → publish qua **queue** sang task MQTT | Không block lẫn nhau |
| 4.9 | **B-4-4** | **MQTT client** (esp-mqtt) + **điều khiển relay** theo lệnh từ broker + **cắt relay khi quá nhiệt / quá tải** (ngưỡng cấu hình được) | |
| 4.10 | **B-1-5** | `arduino-lint --compliance strict` + `library.properties` → publish Arduino Library Registry | Có thể làm sau nếu hết thời gian |

**Hàng bàn giao:** ESP32-S3 cấu hình WiFi qua điện thoại, đọc được PZEM #2, điều khiển relay qua MQTT, tự cắt khi quá tải.

### Giai đoạn 5 — Track B-5: vòng lặp khép kín + Track B-3 PCB `P2`

> **Điều kiện vào:** Giai đoạn 4 cho thấy thiết kế điện tử ổn định.

| # | Task | Nội dung |
|---|---|---|
| 5.1 | **B-5-1** | **Kịch bản khép kín:** bật tải → ESP32-S3 đo → publish MQTT → PC Agent nhận → ghi SQLite → dashboard hiện → **ESP32 tự cắt relay khi vượt ngưỡng** → PZEM #1 thấy công suất về 0. **Đây là mốc tích hợp quan trọng nhất của GR2** |
| 5.2 | **B-3-1** | Schematic EasyEDA: 220 VAC → HLK-PM01 → LDO 3V3; **ESP32-S3 module** (header + nguồn); relay + driver active LOW; nút BOOT/RESET; LED trạng thái; 2 cổng UART (PZEM #2 + debug) |
| 5.3 | **B-3-2** | Khe cắm **I2C** đánh dấu rõ trên silkscreen `3V3 / GND / SDA / SCL`, nhãn "I2C", pull-up 4.7 kΩ |
| 5.4 | **B-3-3** | Creepage/clearance ≥ 3 mm giữa cao áp và logic; test point 3V3/GND/SDA/SCL; chạy DRC trong EasyEDA |
| 5.5 | **B-3-4** | BOM + Gerber + đặt 1 lô 5 board (H-10) |

**Hàng bàn giao:** Gerber + BOM; board đầu tiên về tay; **vòng lặp khép kín đã chạy trên bàn**.

### Giai đoạn 6 — Tích hợp, demo, báo cáo `P1`

| # | Việc |
|---|---|
| 6.1 | Kịch bản demo end-to-end: mất nguồn AC → agent ghi `DEVICE_OFFLINE` → có lại → auto-reconnect → dashboard hiện đồ thị + sự kiện |
| 6.2 | Kịch bản quá tải: bật tải lớn → `OVER_POWER` **ở PC Agent** **và** relay tự cắt **ở ESP32-S3** → xác nhận cả hai đồng thời |
| 6.3 | Soạn báo cáo GR2 cuối kỳ (`.docx`) + cập nhật ROADMAP/README |
| 6.4 | Ghi ký ức quyết định cuối cùng vào `agentmemory` |

---

## TỔNG HỢP — Ai làm gì, khi nào

| Hạng mục | Bạn | Tôi |
|---|---|---|
| Mua/thu vật tư H-01…H-12 | ✅ | — |
| Cắm PZEM + USB-TTL, bật 220 VAC | ✅ | ✅ Giai đoạn 2 (scan + đọc) |
| Chụp ảnh board ESP32-S3 | ✅ | — |
| Đóng task P0 còn mở (A-8-6/7, A-9-1..4, A-7-6/7, A-5-5, A-6-6) | — | ✅ Giai đoạn 1 |
| Viết TROUBLESHOOTING.md + INSTALL.md | — | ✅ Giai đoạn 1 |
| Xác thực service thật, reboot, rút/cắm | ✅ | ✅ Giai đoạn 2 |
| Test systemd | ✅ (usbipd) | ✅ Giai đoạn 2 |
| MQTT uplink (A-10) | — | ✅ Giai đoạn 3 |
| Web Server độc lập + trang (C-1…C-5) | — | ✅ Giai đoạn 3 |
| App Flutter (C-6) | — | ✅ Giai đoạn 3 |
| Firmware ESP32-S3 (B-1, B-4) | ✅ (cắm board + relay) | ✅ Giai đoạn 4 |
| Vòng lặp khép kín (B-5) | ✅ (kết nối WiFi + broker) | ✅ Giai đoạn 5 |
| PCB EasyEDA (B-3) | ✅ (đặt mạch) | ✅ Giai đoạn 5 |
| Báo cáo (D-5, D-6) | — | ✅ Giai đoạn 3 + 6 |

## Rủi ro & đối sách

| Rủi ro | Mức | Đối sách |
|---|---|---|
| **Credential broker còn đọc được qua `refs/pull/3/head`** (ref GitHub đóng băng) | Trung bình | Đã scrub 4 branch public; người dùng báo GVHD đổi mật khẩu. **Không chặn** task nào ở đây |
| Web Server bị yêu cầu cắm serial trực tiếp | Cao | Trao đổi lại ở buỉi GR2: Windows chỉ cho 1 tiến trình giữ COM → đề xuất "serial ↔ HTTP bridge" nếu thầy vẫn muốn |
| Service không đọc được COM dưới LocalSystem | Cao | Test sớm ở Giai đoạn 2.2; fallback → chạy dưới tài khoản user |
| **ESP32-S3 N16R8 PSRAM octal chiếm MSPI → chân 26–37 hỏng** | Cao | Đã xác minh từ header ESP-IDF; chốt pin map ở mục 1.4 + `board_pins.h` |
| Firmware S3 viết lại từ đầu (không tái dùng code P4) | Trung bình | Chấp nhận — dùng ESP-IDF 5.5.3 target `esp32s3`, tái sử dụng *ý tưởng* `wifi_prov` |
| Broker công cộng bị giới hạn/sập, lộ dữ liệu rack | Trung bình | Q1 → Mosquitto tự host trong Docker (đã có) |
| Hết thời gian GR2 | Trung bình | Cắt theo thứ tự: A-10 → C-2…C-6 → B-3. **Track A + B-4** vẫn đủ để báo cáo |
| Không kịp mua phần cứng Track B | Trung bình | Làm B-4 (firmware) trên board mô phỏng — không phụ thuộc PCB; test UART bằng PC thay PZEM #2 |

## Câu hỏi cần trả lời để bắt đầu Giai đoạn 1

1. Bạn mua **H-02, H-03, H-04** ngay hôm nay được chứ? (chặn Giai đoạn 2)
2. Bạn cắm được **PZEM + USB-TTL** để tôi scan không? (chặn A-4-9, A-7-5, A-9-5, A-9-6)
3. Board **ESP32-S3 của bạn là devkit nào** — ESP32-S3-DevKitC-1 N16R8 hay board khác? (tôi cần sơ đồ chân chính xác)
4. Cho tôi **chạy Giai đoạn 1 ngay** chứ? (12 task P0, không cần phần cứng)
