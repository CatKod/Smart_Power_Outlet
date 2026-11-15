# Checklist chuẩn bị phần cứng — Smart Power Outlet

> Bổ sung cho [`docs/PLAN_GR2.md`](../PLAN_GR2.md). Đây là **bảng mua + bảng đấu + bảng test** để bạn chuẩn bị trước, kịp thời gian test sau khi tôi viết xong phần mềm.
>
> **Cập nhật 2026-11-15** — sau khi chốt: Controller dùng **ESP32-S3 N16R8**; broker MQTT do GVHD cung cấp (`mqtt.toolhub.app`).

---

## 0. Tóm tắt: mua gì, tốn bao nhiêu, mua ở đâu

| Mã | Món | SL | Ước giá | Ghi chú |
|---|---|---|---|---|
| **H-01** | PZEM-004T V3.0 (kẹp dây CT) | 1 | ~120 k | **Dự phòng + làm meter thứ 2 cho ESP32-S3** (xem mục 3.2) |
| **H-02** | Bóng LED ~9–12 W | 1 | 15 k | Tải **dưới** ngưỡng |
| **H-03** | Bóng sợi đốt 60–100 W | 1 | 20 k | Tải **vượt** ngưỡng → test `OVER_POWER` |
| **H-04** | Ổ cắm lộ thiên 1→2 (10 A) | 2 | 60 k | Ổ cho PC + ổ cho ESP32-S3 |
| **H-05** | Module relay 1 kênh 5 V opto (active LOW) | 1 | 30 k | **Mua sẵn, dùng ở Giai đoạn 4** |
| **H-06** | Module nguồn AC→DC 5 V (HLK-PM01) | 1 | 45 k | Cho ESP32-S3 + relay |
| **H-07** | Nút bấm 6 mm + LED 5 mm + điện trở 10 kΩ + 1 kΩ | 1 bộ | 15 k | Nút reset WiFi + LED trạng thái |
| **H-08** | Breadboard 830 lỗ + dây jumper + header 2.54 mm | 1 bộ | 60 k | Prototype Track B |
| **H-09** | USB hub có nguồn | 1 | 250 k | Test rút/cắm USB-TTL (A-9-5) |
| **H-10** | PCB 2 lớp | 5 board | ~150 k | Chỉ đặt **sau** khi xong B-3 (mục 6) |

**Tổng ngân sách ≈ 770 k** (không gồm board ESP32-S3 bạn đã có).

**Mua ngay (H-02…H-04)**: chặn Giai đoạn 2 — test thật trên máy.
**Mua sau (H-05…H-08)**: chặn Giai đoạn 4 — Track B.

---

## 1. Bạn ĐÃ có — không cần mua

| Món | Dùng để |
|---|---|
| **PZEM-004T V3.0** × 1 | Meter **cấp rack** cho PC Agent (đo tổng công suất cụm server) |
| **USB-TTL adapter** | Kết nối PZEM ↔ PC Agent qua `Modbus-RTU 9600 8N1` |
| **ESP32-S3 N16R8** | Central IoT Controller (WiFi provisioning + đo điện + relay) |
| **Laptop Windows** | Máy chạy PC Agent dưới dạng Windows Service |
| **WSL Ubuntu (systemd)** | Test systemd unit |
| **Docker Desktop** | Broker Mosquitto dự phòng (nếu thầy yêu cầu) |
| **EasyEDA Pro + skill `easyeda-api`** | Vẽ schematic/PCB B-3 |
| **ESP-IDF 5.5.3 / 5.2** | Build firmware ESP32-S3 |

---

## 2. Yêu cầu điện — đọc trước khi đấu

### 2.1. Ba nguyên tắc bắt buộc

1. **PZEM-004T không phản hồi UART khi mất 220 VAC.** Quang họp của nó nằm trên phía AC. Thiếu điện lưới → UART im → tưởng hỏng máy. Luôn cấp điện cho L/N trước khi kết luận.
2. **Adapter USB-TTL phải 3.3 V tolerant.** PZEM V3.0 dùng mức logic 3.3 V. Adapter 5 V-only sẽ hỏng hoặc đọc sai.
3. **Mọi đấu nối 220 VAC phải qua cầu dao/aptomat và ổ cắm lộ thiên.** Không cắt trực tiếp dây nguồn. Bật/tắt cầu dao để thao tác.

### 2.2. Sơ đồ đấu PZEM ↔ USB-TTL (dùng cho PC Agent)

```
            ┌───────────────────────┐
   220 VAC  │  L ────┐              │
      ──────┤        │   ┌──────┐   │      ┌──────────────────┐
            │  N ─┐  │   │ CT   │   │      │  USB-TTL adapter │
            │     │  └───┤PZEM  │   │      │  (CH340/CP210x)  │
            │     │      │  TX  ├───┼──────┤ RX               │
            │     │      │  RX  ├───┼──────┤ TX               │
            │     │      │  VCC ├───┼──5V──┤ VCC              │
            │     │      │  GND ├───┼──GND─┤ GND              │
            │     └──────┴─────┘   │      └──────────────────┘
            │                      │
            │      ┌───────────────┴──────────┐
            │      │  TẢI (H-02 hoặc H-03)   │
            └──────┴──────────────────────────┘
```

> **Lưu ý CT:** dây điện phải xuyên qua khe CT **đúng chiều 1 lần** (đi vào 1 cửa, ra 1 cửa). Dây đi xuyên 2 lần → đọc sai.

### 2.3. Quy trình cấp nguồn (làm đúng thứ tự)

```
1. Tắt cầu dao
2. Cắm USB-TTL vào laptop
3. Đấu PZEM ↔ USB-TTL (TX↔RX, RX↔TX, GND↔GND)
4. Cắm tải (đèn) vào ổ lộ thiên
5. Bật cầu dao  → PZEM có 220 VAC
6. Mở terminal: python -m pc_agent --exhaustive-scan
```

---

## 3. Chuẩn bị cho từng giai đoạn test (theo đúng thứ tự tôi sẽ yêu cầu)

### 3.1. Giai đoạn 2 — Test PC Agent trên máy thật (cần H-02, H-03, H-04)

| Bước | Bạn làm | Tôi làm | Kết quả cần đạt |
|---|---|---|---|
| **B1** | Cắm PZEM + tải H-02, bật cầu dao | Chạy `--exhaustive-scan` → xác nhận tìm thấy đúng COM + địa chỉ | In ra `FOUND port=COMxx address=0x01` |
| **B2** | *Không làm gì* | `install_service.ps1` (Admin) → reboot máy | `sc query` = `RUNNING` **không ai đăng nhập**; `/api/health` = `healthy` |
| **B3** | *Không làm gì* | Kill tiến trình | SCM tự restart sau 5 s |
| **B4** | Đổi tải H-02 → H-03 (vượt ngưỡng) | Hạ ngưỡng `power_threshold_w`, theo dõi `/api/events` | Có bản ghi `OVER_POWER`, tự đóng khi bỏ tải |
| **B5** | Rút/cắm USB-TTL giữa lúc chạy (dùng H-09) | Theo dõi log | Ghi `DEVICE_OFFLINE`, tự reconnect khi cắm lại |
| **B6** | Mở PuTTY giữ cổng COM rồi start agent | Kiểm tra log | Báo đúng `PORT_BUSY`, **không** báo lỗi nguồn |

### 3.2. Giai đoạn 4 — Track B, ESP32-S3 (cần H-01, H-05, H-06, H-07, H-08)

> **Bốn thứ bạn phải làm đúng:** (1) cấp nguồn ESP32-S3 từ 220 VAC qua H-06, (2) đấu relay H-05, (3) nốt PZEM thứ 2 (H-01) vào UART của ESP32-S3, (4) **đo đường 220 VAC qua CT của PZEM-004T thứ 2**.

**Sơ đồ tổng thể — mô hình 3 thành phần:**

```
┌──────── MÁY CHỦ GIÁM SÁT (tủ rack) ─────────┐
│  PC Agent (Windows Service)                  │
│    ├─ Modbus-RTU 9600 8N1 ──► PZEM #1 (rack)│
│    ├─ SQLite WAL (14 ngày raw / 365 năm h)  │
│    ├─ Rule Engine (OVER_POWER, OVER_VOLT…)  │
│    └─ REST API 127.0.0.1:8000 ──► Web Server│
└──────────────┬───────────────────────────────┘
               │ MQTT (broker của thầy)
               ▼
┌──────── CENTRAL IoT CONTROLLER (ESP32-S3) ──┐
│  ├─ WiFi provisioning (captive portal)        │
│  ├─ PowerMonitor: RMS / P / PF / kWh / NTC   │
│  │     └─ UART1 ──► PZEM #2 (H-01)           │
│  ├─ MQTT client (sub cmd / pub status)        │
│  └─ GPIO21 ──► Relay (H-05) ──► Ổ cắm       │
│  GPIO48 ──► LED (H-07)                        │
│  GPIO0  ──► Nút giữ 3 s = xoá WiFi (H-07)    │
└───────────────────────────────────────────────┘
```

**Sơ đồ nguồn cho khối ESP32-S3:**

```
        220 VAC ──┬──► HLK-PM01 (H-06) ──► 5 V ──┬──► ESP32-S3 5V pin
                  │                                ├──► Relay coil (H-05)
                  │                                └──► LED + điện trở 1 kΩ (H-07)
                  │
                  └──► [CT của PZEM #2] ──► 220 VAC ──► Relay NO ──► TẢI (H-02/H-03)
```

**Sơ đồ tín hiệu:**

| Tín hiệu | ESP32-S3 | Đến | Ghi chú |
|---|---|---|---|
| Relay | **GPIO 21** | Chân IN của relay | Active LOW → code bật relay bằng `LOW` |
| LED trạng thái | **GPIO 48** | R + LED + 1 kΩ → GND | GPIO 48 là LED RGB tích hợp trên DevKitC-1 → dùng làm chẳng hạn |
| Nút reset WiFi | **GPIO 0** | Nút bấm → GND | GPIO 0 = nút BOOT, có pull-up nội; giữ 3 s → xoá WiFi + restart |
| PZEM #2 TX | **GPIO 17** | RX của PZEM #2 | UART1 |
| PZEM #2 RX | **GPIO 18** | TX của PZEM #2 | UART1 |
| I2C (dự phòng) | GPIO 8 / 9 | Khe cắm 4 chân | Có pull-up 4.7 kΩ (sẽ có trên PCB B-3) |

> ⚠️ **GPIO 22–37 KHÔNG dùng được** trên ESP32-S3 N16R8: bus MSPI dùng chung cho flash + PSRAM octal (đã xác minh trong `soc/spi_pins.h` của ESP-IDF 5.5.3). GPIO 19/20 là USB native — tránh nếu cần cắm USB.

### 3.3. Giai đoạn 5 — PCB (chỉ đặt mạch khi tôi báo)

Tôi sẽ gửi bạn: file **Gerber** + **BOM** + sơ đồ lắp. Bạn đặt 5 board (H-10) ở JLCPCB/PCBWay.

**Yêu cầu thiết kế tôi sẽ tuân thủ:**
- Khoảng cách creepage/clearance ≥ 3 mm giữa phần 220 VAC và phần logic
- Khe cắm I2C ghi rõ trên silkscreen: `3V3 / GND / SDA / SCL` + nhãn "I2C", có pull-up 4.7 kΩ
- Test point cho `3V3 / GND / SDA / SCL`
- Jack 220 VAC, relay, nguồn HLK-PM01, ESP32-S3 module, 2 cổng UART, 2 nút (BOOT + RESET)

---

## 4. Việc bạn làm ngay, KHÔNG cần phần cứng

| # | Việc | Vì sao | Mức |
|---|---|---|---|
| **1** | **Báo thầy đổi mật khẩu broker MQTT** (tài khoản thầy cấp, xem `Smart_power_outlet_PIO/include/secrets.h`) | Credential đã nằm trong repo **PUBLIC** (`github.com/CatKod/Smart_Power_Outlet`) → bất kỳ ai cũng đọc được | 🔴 Khẩn |
| **2** | `pip install git-filter-repo` | Tôi cần để gỡ secret khỏi **toàn bộ lịch sử git** (không chỉ commit hiện tại) | 🔴 Khẩn |
| **3** | Mua H-02, H-03, H-04 | Chặn Giai đoạn 2 | 🟡 |
| **4** | Xác nhận: **ESP32-S3 của bạn là devkit nào?** (ESP32-S3-DevKitC-1 N16R8 hay board khác) | Tôi cần đúng sơ đồ chân + LED RGB đã tích hợp hay chưa | 🟡 |

---

## 5. Bảng theo dõi nhanh

| Tôi cần | Bạn cung cấp | Trạng thái |
|---|---|---|
| Test A-4-8 (reboot) | Thao tác cài service + reboot | ⬜ |
| Test A-4-9 (quyền COM) | PZEM cắm sẵn, có 220 VAC | ⬜ |
| Test A-7-5 (ngưỡng) | H-02 + H-03 + H-04 | ⬜ |
| Test A-9-5 (rút/cắm) | H-09 USB hub | ⬜ |
| Test A-9-6 (PORT_BUSY) | PuTTY | ⬜ |
| Test A-5-4 (systemd) | `usbipd` trong WSL hoặc máy Linux thật | ⬜ |
| Test B-2 (Track B) | H-01 + H-05 + H-06 + H-07 + H-08 | ⬜ |
| Test B-3 (PCB) | Đặt 5 board | ⬜ |
