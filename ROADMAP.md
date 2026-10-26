# Smart Power Outlet — Roadmap công việc

> Tài liệu này sắp xếp lại toàn bộ nội dung đã trao đổi với GVHD thành các **workstream (W)**, có **thứ tự ưu tiên**, **phụ thuộc**, **Definition of Done** và **ghi chú kỹ thuật**.
> Cập nhật lần cuối: 2026-10-26 · Trạng thái tổng: **GR2 ~70 %**

---

## 0. Mục tiêu & tài sản hiện có

**Mục tiêu sản phẩm**

- Một **thư viện Arduino** (và bản ESP-IDF component) dùng để **cấu hình + duy trì WiFi** cho thiết bị IoT, phát hành công khai lên **Arduino Library Registry** (và/hoặc **ESP Component Registry**), có thể tái sử dụng cho mọi đồ án khác.
- Một **module đo điện** (dòng tiêu thụ 2 dạng mạch, điện áp, nhiệt độ NTC) + **mạch in EasyEDA** hoàn chỉnh, đánh dấu rõ khe cắm I2C.
- Ứng dụng điều khiển ổ cắm thông minh (Flutter) dùng lại 2 thành phần trên.

**Tài sản đã có trong repo**

| Đường dẫn | Nội dung | Trạng thái |
| --- | --- | --- |
| `WiFiConf/` | Sample thư viện `WiFiSetting` v3.0.0 (`ConfigManager`, `WiFiManager`, `WiFiSelfEnroll`, `WiFiEnrollBySerial`) | Nền để fork/refactor |
| `Smart_power_outlet_PIO/` | Firmware Arduino (ESP32-WROOM / ESP32-P4 / ESP8266), `wifi_prov.*` + MQTT relay | Đang chạy được, `wifi_prov` còn sơ khai |
| `Smart_Power_Outlet_ESP/` | Firmware ESP-IDF (để nhắm ESP Component Registry) | Song song, cần đồng bộ API |
| `smart_power_outlet_app/` | App Flutter (Android/iOS/Windows) | Đã có khung |
| `hardware/smart_outlet/` | Schematic KiCad + tool ERC (`hardware/tools/*.py`) | Sơ bộ, chưa có PCB EasyEDA |

**Quy ước**

- `P0` = chặn tiến độ / phải xong trước · `P1` = bắt buộc cho GR3 · `P2` = nice-to-have.
- Mỗi task có ID dạng `W1-3` để báo cáo với GVHD.
- "DoD" = Definition of Done (điều kiện được coi là hoàn thành).

---

## 1. Bảng tổng hợp ưu tiên

| ID | Workstream | Ưu tiên | Phụ thuộc | Ước lượng | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| **W0** | Chuẩn hoá repo & quy ước phát hành | P0 | — | 1–2 ngày | Chưa |
| **W1** | Thư viện WiFi cấu hình — **bản lõi (Arduino)** | P0 | W0 | 6–8 ngày | ~50 % (có sample) |
| **W2** | Cấu hình qua **WiFi Adhoc / Captive Portal** | P0 | W1 | 3–4 ngày | ~60 % (có sample) |
| **W3** | Cấu hình qua **Serial** (thư viện riêng) | P1 | W1 | 3 ngày | ~30 % |
| **W4** | **Duy trì kết nối** non-blocking (xoay SSID, tự phục hồi) | P0 | W1 | 3 ngày | ~40 % |
| **W5** | **MAC spoofing** + ghi chú giới hạn | P1 | W1 | 1–2 ngày | ~70 % |
| **W6** | **Phát hành** lên Arduino Library Registry | P0 | W1–W5 | 3–5 ngày | 0 % |
| **W7** | (Tuỳ chọn) Phát hành **ESP Component Registry** / PlatformIO | P2 | W1–W5 | 3 ngày | 0 % |
| **W8** | Firmware **đo dòng/áp/NTC** | P0 | W1 (dùng chung config) | 5–7 ngày | 0 % |
| **W9** | Đo dòng **2 dạng mạch** + hiệu chuẩn | P1 | W8 | 4–5 ngày | 0 % |
| **W10** | Phần cứng **EasyEDA** + khe cắm I2C | P0 | W8, W9 | 5–7 ngày | ~15 % (KiCad sơ bộ) |
| **W11** | Tích hợp end-to-end + demo GR2/GR3 | P0 | tất cả | 3–4 ngày | — |

**Thứ tự thực thi đề xuất**

```
W0 → W1 → (W2 ∥ W4) → W3 → W5 → W6 → W7
                     ↘ W8 → W9 → W10 → W11
```

Lý do: W1 là "hợp đồng" dữ liệu/API mà mọi thứ khác (portal, serial, đo điện, app) đều phụ thuộc. W6 (publish) chỉ nên làm **sau** khi API chốt, vì registry gắn cứng URL repo và version.

---

## 2. W0 — Chuẩn hoá repo & quy ước phát hành  `P0`

Chưa có bước này thì `arduino-lint --compliance strict` sẽ fail ngay.

- [ ] **W0-1** Tách thư viện ra **repo riêng** (ví dụ `SmartOutlet_WiFiConf`), không nhúng trong `Smart_Power_Outlet`.
      Lý do: registry yêu cầu repo public hợp lệ, đổi URL sau khi publish là gần như không được.
- [ ] **W0-2** Cấu trúc chuẩn Arduino 1.5:
      ```
      /library.properties
      /keywords.txt
      /LICENSE              (MIT)
      /README.md
      /src/                 *.h + *.cpp (phẳng, không lồng sâu)
      /examples/<Tên>/<Tên>.ino
      /extras/              (sơ đồ, ảnh, datasheet)
      ```
- [ ] **W0-3** `.gitignore` chặn: `.pio/`, `.vscode/`, `logs/`, `secrets.h`, `build/`, `*.kicad_prl`.
- [ ] **W0-4** CI GitHub Actions:
      - `arduino-lint --compliance strict --library-manager submit`
      - ma trận compile: `arduino-cli compile -b esp32:esp32:esp32` + `esp8266:esp8266:nodemcuv2` (+ `esp32c3`, `esp32p4` nếu core hỗ trợ)
- [ ] **W0-5** Quy ước version: **SemVer**. Tag git **phải trùng** `version=` trong `library.properties`.
- [ ] **W0-6** Chốt tên thư viện (duy nhất, không trùng registry) — gợi ý: `WiFiConf`, `SOICT_WiFiConf`.

**DoD:** repo mới public, CI xanh, `arduino-lint` strict pass, có tag `v4.0.0` (hoặc bản beta `-beta`).

---

## 3. W1 — Thư viện lõi: lưu trữ cấu hình bền vững  `P0`

Đây là phần "trái tim": **một data object duy nhất** lưu trong flash, dùng chung cho cả WiFi và module đo điện.

### 3.1 Schema cấu hình (chốt sớm, có version + CRC)

```json
{
  "v": 2,
  "net": [
    {"s": "Home_WiFi", "p": "88888888"},
    {"s": "HUST_B1",   "p": ""},
    {"s": "SOICT_LAB","p": "12345678"}
  ],
  "ok": "HUST_B1",
  "mac": "24:24:B7:D0:B6:1C",
  "dev_id": "mydevice",
  "wifi_en": true,
  "meas": { "shunt_mohm": 10, "v_div": 5.0, "ntc_beta": 3950 }
}
```

| Field | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `net[5]` | Tối đa **5 cặp SSID/password** (bắt buộc theo yêu cầu) | Cho phép `p=""` (mạng mở, ví dụ `HUST_B1`) |
| `ok` | SSID **gần nhất thành công** | Khi kết nối: **thử `ok` trước**, thất bại mới thử mạng liền sau |
| `mac` | MAC dùng để spoof | Bỏ trống → dùng MAC gốc |
| `dev_id` | ID thiết bị do người dùng đặt | Dùng cho MQTT client-id, topic |
| `wifi_en` | Bật/tắt WiFi | `false` → tắt radio, tiết kiệm pin |
| `meas` | Hệ số hiệu chuẩn đo điện | Thêm mới — tận dụng luôn store này cho W8 |

- [ ] **W1-1** `ConfigManager` (hoặc `OutletConfig`) thao tác trên struct `PersistentParams`, **không** để người dùng đụng JSON thô.
- [ ] **W1-2** Ghi **atomic**: ghi file tạm → `rename` → tránh mất cấu hình khi mất điện giữa lúc `save()`.
- [ ] **W1-3** Có `version` + `CRC32`; nâng cấp schema tự động (`migrate()`), nếu CRC sai → dùng default + cảnh báo.
- [ ] **W1-4** Giới hạn ghi: chỉ `commit()` khi dirty, tránh mài mòn flash (đặc biệt khi rotate SSID mỗi 60 s — **không** được ghi `ok` mỗi lần thử).
- [ ] **W1-5** Backend lưu trữ:
      - ESP32/ESP32-C3/C6/P4: `Preferences` (NVS) hoặc `LittleFS` JSON
      - ESP8266: `LittleFS` (khuyến nghị) hoặc EEPROM giả lập
      - Bọc sau interface `IConfigStore` để test trên host.
- [ ] **W1-6** API công khai tối giản:
      ```cpp
      bool  begin();
      bool  load();  bool save();
      void  setWifiEnabled(bool);
      void  setDeviceId(const char*);
      void  setMac(const char*);            // "AA:BB:CC:DD:EE:FF", "" = bỏ spoof
      bool  upsertNetwork(const char* ssid, const char* pass);
      void  setLastOkSsid(const char*);
      ```
- [ ] **W1-7** Unit test trên host (PlatformIO `env:native`) cho: parse/serialize, migrate v1→v2, CRC sai, danh sách đầy 5 phần tử.

**DoD:** reboot 100 lần liên tiếp không mất cấu hình; test native pass; schema có tài liệu trong README.

---

## 4. W2 — Cấu hình qua WiFi Adhoc / Captive Portal  `P0`

- [ ] **W2-1** Phát AP: SSID mặc định `WIFI_ADHOC` (đổi được qua tham số `setup(adhoc_ssid, pass)`), **mặc định nên có password** (hiện đang `""` — rủi ro).
- [ ] **W2-2** Captive portal DNS: mọi request → `192.168.4.1` (ESP32: `DNSServer`, ESP8266: `DNSServer` của core).
- [ ] **W2-3** Web UI (LittleFS): trang chủ (danh sách 5 SSID, chọn mạng "ok"), trang scan, trang nhập `dev_id` / `mac` / `wifi_en`, nút Reboot.
- [ ] **W2-4** REST API dùng chung cho app Flutter: `GET /api/scan`, `GET/POST /api/config`, `POST /api/reboot`, `GET /api/status`.
- [ ] **W2-5** **Non-blocking**: `portal.loop()` gọi từ `loop()` chính. Hiện sample gọi `myWiFi->setup()` lặp lại trong `loop()` → tạo AP nhiều lần, phải sửa.
- [ ] **W2-6** Timeout an toàn: tự thoát portal + reboot sau **5 phút** (đã có `ADHOC_STATION_DURATION`) để không kẹt AP khi mất điện.
- [ ] **W2-7** Bảo vệ: giới hạn 1 client đồng thời, chống POST rỗng, validate MAC regex.

**DoD:** điện thoại vào AP → nhập 5 mạng + dev_id + mac → reboot → kết nối đúng mạng `ok`. Không block `loop()`.

---

## 5. W4 — Duy trì kết nối non-blocking  `P0`

Hàm mục tiêu:

```cpp
bool WiFiManager::checkAndEstablishWiFiConnection(
        unsigned long reconnect_interval,
        unsigned int  ssid_interval);
```

### 5.1 Vấn đề của code sample hiện tại (đã đọc `WiFiConf/src/WiFiManager.cpp`)

| # | Vấn đề | Hệ quả |
| --- | --- | --- |
| 1 | `WiFi.begin()` gọi lại mỗi tick throttle, không có state `CONNECTING` | Reset liên tục, **không bao giờ** kết nối được |
| 2 | Ngay sau `WiFi.begin()` lại `if (WiFi.status() == WL_CONNECTED)` | `true` gần như không bao giờ xảy ra → nhánh cập nhật `ok` là **dead code** |
| 3 | Không có timeout cho 1 lần thử | Kẹt ở 1 SSID vô hạn |
| 4 | `ssid_interval == 0` → chỉ thử đúng `ok`, không fallback | Không đáp ứng "thử mạng liền sau" |
| 5 | Đếm `attemptsOnCurrentSsid` theo số tick, không theo thời gian | Hành vi phụ thuộc `reconnect_interval` |
| 6 | Xoá/tắt WiFi bằng `WiFi.disconnect()` + `wifiStatus=false` nhưng không `mode(WIFI_OFF)` | Vẫn ăn dòng |

### 5.2 Thiết kế lại: state machine

```
OFF ──(wifi_en=true)──► IDLE ──tick──► CONNECTING(idx, deadline)
 ▲                        ▲                     │
 │                        │        timeout / CONNECT_FAILED
 │                   rotate idx ◄───────────────┘
 │                        │
 │                   (hết 1 vòng 5 mạng, N lần)
 │                        ▼
 └──────────────────── PORTAL (W2)  hoặc backoff luỹ thừa
CONNECTED ──(LOST)──► IDLE
```

- [ ] **W4-1** Enum `State { OFF, IDLE, CONNECTING, CONNECTED, PORTAL }` + `loop()` xử lý, **tuyệt đối không `delay()`**.
- [ ] **W4-2** Timeout/lần thử cấu hình được (mặc định 15 s), `ssid_interval` = **số lần thử trên 1 SSID** (chốt ngữ nghĩa với GVHD, hiện đang mơ hồ).
- [ ] **W4-3** Thứ tự thử: `ok` trước → vòng các mạng còn lại.
- [ ] **W4-4** Khi kết nối thành công: cập nhật `ok` **một lần** rồi mới commit flash.
- [ ] **W4-5** Exponential backoff khi hết 1 vòng (15 s → 30 s → 60 s → 120 s, trần 5 phút).
- [ ] **W4-6** Callback: `onConnected(IP)`, `onDisconnected()`, `onPortalStarted()`, `onConfigChanged()`.
- [ ] **W4-7** Kiểm tra "internet thật" (DNS probe) — **tách khỏi** "đã vào WiFi", trả 2 trạng thái riêng.
- [ ] **W4-8** `shutdownWiFi()` → `WiFi.mode(WIFI_OFF)` (+ `forceSleepBegin()` trên ESP8266); `wakeupWiFi()` khôi phục STA.
- [ ] **W4-9** "Tự khởi động lại nếu chết": watchdog mềm — nếu `CONNECTED` nhưng 3 lần DNS probe fail liên tiếp → reconnect; nếu 5 lần reconnect thất bại → **restart** (có đếm trong RTC/NVS để tránh loop restart vô hạn: quá 5 restart/giờ → vào portal).

**DoD:** test kịch bản (a) mất điện router 5 phút → tự vào lại; (b) đổi vị trí sang mạng thứ 2 → xoay vòng và vào được; (c) `wifi_en=false` → dòng tiêu thụ giảm rõ rệt; (d) 2 giờ chạy liên tục không rò rỉ heap.

---

## 6. W3 — Thư viện cấu hình qua **Serial**  `P1`

Yêu cầu: *"Thư viện tương tự như (1) nhưng qua đường serial"*. Hai hướng — cần chốt với GVHD:

| Hướng | Mô tả | Ưu/nhược |
| --- | --- | --- |
| **A. Cùng thư viện, thêm transport** | `WifiConf` có `setTransport(Serial/USB)`, dùng chung `ConfigManager` | Ít trùng lặp, publish 1 lần |
| **B. Thư viện riêng `WiFiConfSerial`** | Repo/library riêng, chỉ phụ thuộc `WiFiConf` | Đúng câu chữ "thư viện tương tự", nhưng 2 lần publish |

Khuyến nghị **A** (thêm `#include <WiFiConfSerial.h>` như module mở rộng, vẫn có `library.properties` riêng nếu cần).

- [ ] **W3-1** Giao thức **line-based, non-blocking**, timeout 10 s/lệnh:
      ```
      net.add=<ssid>,<pass>      net.ok=<ssid>      net.list
      net.del=<ssid>             dev.id=<name>      mac=<AA:BB:..|off>
      wifi.en=<0|1>              show               save
      reset                      reboot             help
      ```
- [ ] **W3-2** Hỗ trợ thêm `--json` mode (`{"cmd":"net.add","ssid":"..","pass":".."}`) để app desktop gửi.
- [ ] **W3-3** Không echo password ra serial; che dạng `****`.
- [ ] **W3-4** Parser chịu lỗi: dòng quá dài, ký tự rác, `\r\n` vs `\n`, escape dấu phẩy trong password.
- [ ] **W3-5** Hàm blocking cũ (`EnrollBySerial()` đang chặn luồng) → thay bằng `serial.poll()` không chặn, hoặc giữ blocking nhưng có timeout thoát tự động.
- [ ] **W3-6** Example `RegisterBySerial.ino` + script Python mẫu (`tools/enroll.py`) để cấu hình hàng loạt.
- [ ] **W3-7** Ghi tài liệu **bảng lệnh** trong README (đây là thứ app Flutter sẽ dùng).

**DoD:** cấu hình 5 mạng + `dev_id` + `mac` qua serial trong < 30 s; script Python chạy được; không block quá 10 s.

---

## 7. W5 — MAC spoofing  `P1`

- [ ] **W5-1** API: `setNewMac(const char*)` — validate `XX:XX:XX:XX:XX:XX` (**hiện chỉ hỗ trợ dấu `:`**, cần nhận cả `-` và dạng liền `AABBCCDDEEFF`).
- [ ] **W5-2** Thứ tự bắt buộc: `WiFi.mode(WIFI_STA)` → `esp_wifi_set_mac(WIFI_IF_STA, mac)` / `wifi_set_macaddr(STATION_IF, mac)` → **rồi mới** `WiFi.begin()`.
- [ ] **W5-3** Kiểm tra mã trả về, log rõ ràng khi fail; **fallback** dùng MAC gốc, không treo.
- [ ] **W5-4** Đọc MAC gốc 1 lần (`WiFi.macAddress()` trước khi đổi) và lưu lại để có thể "khôi phục".
- [ ] **W5-5** OUI: byte đầu **phải chẵn** (unicast) và **không** đặt bit local-admin tuỳ tiện; cấm `FF:FF:FF:...`, cấm trùng MAC của AP.
- [ ] **W5-6** **Ghi chú giới hạn vào README** (quan trọng, GVHD đã nêu):
      > MAC thực chất **không đổi** trong phần cứng. Ta chỉ ghi đè **biến/tham số MAC** mà driver WiFi dùng để dựng frame và khai báo trong quá trình association — tức là đánh lừa hệ thống quản lý mạng ở tầng phần mềm.
      > **Ngoại lệ: Windows và card mạng Intel cấm ghi đè MAC** (driver/vendor lock) — nên kịch bản "đổi MAC của máy tính để vượt chặn" **không** khả thi trên các nền tảng này.
      > Bối cảnh: `HUST_B1` có thể chặn theo MAC → thư viện cho phép mỗi board tự mang một MAC riêng.
- [ ] **W5-7** Cảnh báo pháp lý/đạo đức ngắn trong README: chỉ dùng cho thiết bị của mình / lab được phép.

**DoD:** router/AP thấy MAC mới; khôi phục MAC gốc được; MAC sai định dạng không làm board treo.

---

## 8. W6 — Phát hành lên **Arduino Library Registry**  `P0`

Quy trình (fork + PR):

- [ ] **W6-1** `library.properties` sạch và **nhất quán với tên repo**:
      ```properties
      name=WiFiConf
      version=4.0.0
      author=...
      maintainer=... <email>
      sentence=Một câu mô tả (<= 80 ký tự).
      paragraph=Đoạn mô tả dài hơn (<= 200 ký tự).
      category=Communication
      url=https://github.com/<user>/<repo>
      architectures=esp32,esp8266
      includes=WiFiConf.h
      depends=ArduinoJson
      ```
      ⚠️ Sample hiện tại có 3 lỗi sẽ fail lint:
      - `includes=siot_core_lib.h` — file **không tồn tại** trong `src/`
      - `depends=WiFi,Preferences` — `Preferences` **không phải** thư viện; `WiFi` là core API, không khai báo
      - thiếu `depends=ArduinoJson` (đang dùng `ArduinoJson.h`), thiếu `LittleFS` (core)
- [ ] **W6-2** `keywords.txt` (tab-separated: `KEYWORD1`/`KEYWORD2`/`LITERAL1`).
- [ ] **W6-3** `LICENSE` (MIT) + header license trong từng file nguồn.
- [ ] **W6-4** Ít nhất **2 examples** compile được trên cả `esp32` và `esp8266`.
- [ ] **W6-5** Chạy local: `arduino-lint --compliance strict --library-manager submit --recursive`.
- [ ] **W6-6** Tạo **GitHub Release** với tag `4.0.0` (khớp `version=`), ghi release notes.
- [ ] **W6-7** Fork [`arduino/library-registry`](https://github.com/arduino/library-registry) → thêm **một dòng URL repo** vào file danh sách theo hướng dẫn trong README của registry (hiện là `repositories.txt`) → commit → **Pull Request**.
      Lưu ý: PR cần URL **ổn định vĩnh viễn**; đừng đổi tên repo sau khi merge.
- [ ] **W6-8** Theo dõi CI của registry (arduino-lint + kiểm tra trùng tên); xử lý feedback của maintainer.
- [ ] **W6-9** Sau khi merge: kiểm chứng bằng `arduino-cli lib search WiFiConf` và `lib install WiFiConf`.
- [ ] **W6-10** (Song song) publish **PlatformIO Registry** nếu muốn dùng ngay trong `platformio.ini`:
      `pio pkg publish --owner <user> --type library` (cần `platformio.ini`/manifest + token).
- [ ] **W6-11** Gắn **badge** (build, lint, version) + hướng dẫn cài trong README.

**DoD:** `arduino-cli lib search <name>` thấy thư viện; `lib install` + compile example OK trên 2 kiến trúc.

---

## 9. W7 — (Tuỳ chọn) ESP Component Registry  `P2`

Dùng cho nhánh firmware `Smart_Power_Outlet_ESP/` (ESP-IDF thuần).

- [ ] **W7-1** Đóng gói `components/wifi_conf/` với `idf_component.yml` (`version`, `dependencies`, `targets`).
- [ ] **W7-2** Viết **shim** để dùng chung logic: tách phần "thuần C++ không phụ thuộc Arduino" (`ConfigStore`, state machine) thành `wifi_conf_core`; Arduino và IDF chỉ là 2 lớp adapter.
      → Đây là cách duy nhất tránh maintain 2 bản logic song song.
- [ ] **W7-3** `compote component upload --namespace <ns> --name wifi_conf --version 4.0.0` (cần token từ `idf.py`/espressif.com).
- [ ] **W7-4** Cập nhật `idf_component.yml` của project để kéo component từ registry thay vì path local.
- [ ] **W7-5** Kiểm tra hiển thị trên <https://components.espressif.com>.

**DoD:** project IDF build sạch khi `idf_component.yml` trỏ registry.

---

## 10. W8 — Firmware đo điện: dòng, áp, nhiệt độ  `P0`

**Phạm vi:** đo **dòng tiêu thụ** (2 dạng mạch), **điện áp**, **nhiệt độ qua NTC**.

- [ ] **W8-1** Chốt **dải đo & độ phân giải** với GVHD:
      | Đại lượng | Dải dự kiến | Sai số mục tiêu |
      | --- | --- | --- |
      | Dòng | 0–10 A (AC 220 V) | ±2 % |
      | Áp | 0–260 V AC (hoặc 0–30 V DC) | ±1 % |
      | Nhiệt độ | −20…+125 °C (NTC 10 k, B=3950) | ±1 °C |
      ⚠️ Nếu đo **AC 220 V** thì **bắt buộc cách ly** (CT + optocoupler) — không dùng shunt trực tiếp.
- [ ] **W8-2** Lớp `PowerMonitor` (API độc lập phần cứng):
      ```cpp
      bool  begin(const MeasConfig& cfg);   // lấy từ ConfigManager (W1)
      void  loop();                          // lấy mẫu, tính RMS, không block
      float currentRms();   float voltageRms();
      float activePower();  float powerFactor();   // nếu đo AC
      float energyWh();                          // tích luỹ, lưu flash mỗi 5 phút
      float temperatureC();
      ```
- [ ] **W8-3** Lấy mẫu: 1 kHz+, cửa sổ **≥ 10 chu kỳ** lưới (200 ms @50 Hz) để RMS ổn định; đồng bộ zero-cross nếu có.
- [ ] **W8-4** Hiệu chuẩn ADC: ESP32 → dùng `esp_adc_cal`/`analogReadMilliVolts`, tránh `analogRead` thô; oversample + trung bình trượt.
- [ ] **W8-5** Lưu **hệ số hiệu chuẩn** vào `ConfigManager.params.meas` (không hard-code).
- [ ] **W8-6** NTC: công thức **Beta** (`1/T = 1/T0 + (1/B)·ln(R/R0)`), có bảng tra/`Steinhart-Hart` nếu cần; xử lý chia 0 khi NTC hở/ngắn → trả `NAN` + cờ lỗi.
- [ ] **W8-7** Task FreeRTOS riêng cho sampling (core 1 trên ESP32), publish giá trị qua queue — không gọi ADC trong `loop()` chính.
- [ ] **W8-8** Báo cáo: MQTT topic `home/socket/telemetry` (JSON), và API `/api/meas` cho app.
- [ ] **W8-9** Cảnh báo: quá áp / quá dòng / quá nhiệt → auto ngắt relay (an toàn) + event.

**DoD:** so sánh với đồng hồ vạn năng/ampe kìm: sai số trong ngưỡng W8-1; chạy 24 h không trôi; nhiệt độ khớp nhiệt kế ±1 °C.

---

## 11. W9 — Hai dạng mạch đo dòng + hiệu chuẩn  `P1`

- [ ] **W9-1** **Dạng 1 — Shunt + IC công suất (INA219/INA226), DC, high-side**
      Ưu: chính xác, sẵn I2C, đo cả V/I/P. Nhược: chỉ DC, cần cách ly nếu đặt phía sơ cấp.
- [ ] **W9-2** **Dạng 2 — Cảm biến Hall (ACS712/ACS758) hoặc CT (SCT-013)**, AC/DC tuỳ chọn
      Ưu: **cách ly galvanic** (CT), đo AC. Nhược: cần op-amp khuếch đại + offset 2.5 V, nhiễu.
- [ ] **W9-3** Cùng 1 API (`PowerMonitor`), chọn backend bằng `build_flags`:
      `-D MEAS_BACKEND=INA226 | ACS712 | CT_ZMPT`
- [ ] **W9-4** Script hiệu chuẩn (`tools/calibrate.py`): cho nhập 2 điểm chuẩn (0 A và 5 A) → tính hệ số → ghi vào config.
- [ ] **W9-5** Bảng so sánh 2 dạng mạch (giá, dải đo, cách ly, sai số, độ phức tạp) để đưa vào báo cáo.
- [ ] **W9-6** Test: tải điện trở (bóng đèn/quạt) ở 3 mức, ghi lại số đo vs ampe kìm.

**DoD:** 2 backend cùng chạy, cùng API, có bảng so sánh + dữ liệu hiệu chuẩn.

---

## 12. W10 — Phần cứng **EasyEDA** + khe cắm I2C  `P0`

Hiện repo mới có KiCad schematic sơ bộ (`hardware/smart_outlet/smart_outlet.kicad_sch`) + tool ERC.

- [ ] **W10-1** Vẽ lại **schematic EasyEDA** (yêu cầu của GVHD: "mạch in EasyEDA"), gồm:
      - Nguồn: 220 VAC → HLK-PM01/PS 5 V → LDO 3.3 V (kèm fuse, MOV, X2 cap)
      - Relay + driver (optocoupler/MOSFET) + snubber
      - ESP32-C3/WROOM module, anten, nút BOOT/RESET
      - Header nạp (UART) + header I2C
- [ ] **W10-2** **Đề danh (silkscreen) rõ khe cắm I2C**: connector 4 chân chuẩn `3V3 / GND / SDA / SCL`, ghi nhãn **"I2C"** + đánh số chân + chiều (GND ở pin 1), dùng JST-XH 2.54 mm hoặc XH 1.25 mm.
- [ ] **W10-3** Kéo 2 điện trở **pull-up 4.7 kΩ** cho SDA/SCL (hoặc jumper chọn), thêm **TVS/ESD** bảo vệ đường I2C.
- [ ] **W10-4** Bố trí: khoảng cách **creepage/clearance ≥ 3 mm** giữa phần cao áp và低压; slot cắt trên PCB nếu cần; không route I2C dưới relay.
- [ ] **W10-5** Chừa **test point** cho: 3V3, GND, SDA, SCL, relay coil, ADC in.
- [ ] **W10-6** 2 biến thể bo đo (dạng 1 / dạng 2) dùng chung connector I2C để cắm rời.
- [ ] **W10-7** BOM + giá thành, chọn linh kiện **có sẵn ở VN** (hoặc JLCPCB basic parts).
- [ ] **W10-8** Kiểm tra ERC/DRC, xuất Gerber + BOM + Pick&Place, đặt thử 1 lô 5 board.
- [ ] **W10-9** Đồng bộ lại KiCad ↔ EasyEDA (chọn 1 nguồn sự thật duy nhất, tránh 2 bản lệch).

**DoD:** Gerber pass DRC, board mẫu hàn xong chạy được, silkscreen đọc được "I2C".

---

## 13. W11 — Tích hợp & demo  `P0`

- [ ] **W11-1** Thay `wifi_prov.*` trong `Smart_power_outlet_PIO` bằng thư viện mới (`lib_deps` trỏ git/tag).
- [ ] **W11-2** App Flutter: màn hình cấu hình WiFi (qua portal + serial), màn hình telemetry (I, U, P, °C).
- [ ] **W11-3** Đồng bộ ESP-IDF (`Smart_Power_Outlet_ESP`) dùng chung core (W7-2).
- [ ] **W11-4** Kịch bản demo GR2/GR3:
      1. Board mới → tự phát AP → nhập 5 mạng + `dev_id` + `mac`
      2. Rút router → tự reconnect, xoay SSID
      3. Bật tải → app hiện dòng/áp/nhiệt
      4. Quá nhiệt giả lập → tự ngắt relay
      5. Reset 3 s (giữ nút) → xoá cấu hình → về AP
- [ ] **W11-5** README tổng + sơ đồ khối + video demo.

---

## 14. Câu hỏi cần chốt với GVHD

1. **W3**: "thư viện tương tự nhưng qua serial" là **repo/thư viện riêng** hay **module mở rộng** của cùng thư viện?
2. **W1**: `ssid_interval` trong `checkAndEstablishWiFiConnection()` — là *số lần thử/1 SSID* hay *số giây/1 SSID*? (code hiện tại đếm theo tick, không rõ nghĩa)
3. **W8**: đo **AC 220 V** hay **DC**? (quyết định có cần cách ly / CT hay không)
4. **W9**: 2 dạng mạch đo dòng cụ thể là gì — *shunt+INA226* vs *Hall/CT*, hay GVHD đã chỉ định linh kiện khác?
5. **W10**: "mạch in easylab" — là **EasyEDA** (web, JLC) hay **EasyLab** của trường? Có ràng buộc kích thước/linh kiện kho trường?
6. Deadline từng mốc GR2 / GR3 để xếp lịch.
7. Có cần **bảo mật** cho AP cấu hình (password) hay để mở cho tiện demo?

---

## 15. Rủi ro & đối sách

| Rủi ro | Mức | Đối sách |
| --- | --- | --- |
| Registry từ chối PR vì tên/`library.properties`/lint | Cao | W0 + W6 chạy `arduino-lint` strict trước khi tạo PR; chuẩn bị sẵn 1–2 vòng sửa |
| ESP32-P4 không có WiFi native (qua C6 ESP-Hosted) | Cao | Xác nhận sớm; nếu vướng thì **P4 chỉ làm board đo**, WiFi dùng WROOM/C3 |
| Dính 220 V khi prototype | Cao | Cách ly, cầu chì, hộp nhựa, không hàn khi cắm điện; dùng biến áp cách ly khi test |
| Trôi hệ số hiệu chuẩn theo nhiệt độ | TB | Hiệu chuẩn 2 điểm + bù nhiệt, ghi log để phát hiện trôi |
| Viết 2 bản logic Arduino/IDF lệch nhau | TB | Tách `wifi_conf_core` thuần C++ (W7-2) |
| Mài mòn flash do ghi `ok` liên tục | TB | Chỉ commit khi dirty (W1-4) |
| Hết thời gian trước GR3 | TB | Ưu tiên P0 trước; W7/W9-5/W10-6 có thể cắt |

---

## 16. Lịch đề xuất (6 tuần)

| Tuần | Nội dung | Mốc |
| --- | --- | --- |
| 1 | W0, W1 (schema + store + test native) | Repo thư viện sạch, CI xanh |
| 2 | W4 (state machine) + W2 (portal) | WiFi tự phục hồi ổn định 24 h |
| 3 | W3 (serial) + W5 (MAC) | Cấu hình được 2 đường |
| 4 | W6 (publish) + demo nội bộ | **PR registry** + tag 4.0.0 |
| 5 | W8 + W9 (đo điện, 2 backend) | Số đo khớp ampe kìm |
| 6 | W10 (EasyEDA, gerber) + W11 (tích hợp) | **GR3 demo** |

> Ghi chú: phần nào GVHD đánh giá cao hơn (ví dụ mạch in) thì dời W10 lên tuần 4 và lùi W6 lại — W6 không phụ thuộc phần cứng.
