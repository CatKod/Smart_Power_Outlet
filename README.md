# Smart Power Outlet

Hệ thống giám sát năng lượng cho **tổ hợp máy chủ trong tủ rack**, dùng đồng hồ đo điện **PZEM-004T V3.0** (Modbus-RTU).

## Mô hình hệ thống — 3 thành phần

| # | Thành phần | Chạy trên | Trách nhiệm | Trạng thái |
|---|---|---|---|---|
| **1** | **Electronic PC Agent** | Máy chủ giám sát trong tủ rack | Đọc PZEM-004T liên tục, tự dò COM, lưu time-series, đánh giá ngưỡng & ghi sự cố, phục vụ REST API | **P0 — Giai đoạn 1 xong, chờ test máy thật** |
| **2** | **Central IoT Controller** | Vi điều khiển **ESP32-S3 N16R8** (ESP-IDF 5.5.3) | Cấu hình & duy trì WiFi, subscriber MQTT, điều khiển relay, đo điện PZEM #2, giám sát an toàn | **P1 — làm sau Track A, vẫn trong GR2** |
| **3** | **Web Server** | Máy chủ web trung tâm | Giao diện web + API người dùng, báo cáo, lịch sử sự kiện | **P1 — đang dựng dần** |

Sơ đồ kiến trúc: [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) · [`docs/architecture/diagrams/`](docs/architecture/diagrams/)

> **Điểm cốt lõi:** PC Agent chạy như **Windows Service** / **Linux daemon** — tự khởi động cùng máy, **không cần đăng nhập**, không GUI, tự dò cổng COM và tự phục hồi khi thiết bị bị rút/cắm lại. Đây là điểm GVHD yêu cầu ưu tiên trong buổi báo cáo GR2 Tuần 1.

## Cấu trúc repo

```
Smart_Power_Outlet/
├── pc_agent/                  ← THÀNH PHẦN 1: Electronic PC Agent (P0 — đang làm)
│   ├── src/pc_agent/          # package Python (drivers / core / storage / api / deploy)
│   ├── deploy/                # install_service.ps1, smart-power-agent.service, run_dev.bat
│   └── tests/                 # test giải mã & CRC theo tài liệu PZEM-004T
├── Smart_power_outlet_PIO/    ← THÀNH PHẦN 2: firmware Arduino (P1 — làm sau Track A)
├── Smart_Power_Outlet_ESP/    ← THÀNH PHẦN 2: firmware ESP-IDF (P1 — làm sau Track A)
├── smart_power_outlet_app/    ← app Flutter (client của thành phần 3)
├── hardware/                  ← EasyEDA / KiCad cho thành phần 2
├── docs/architecture/         ← tài liệu kiến trúc + sơ đồ
└── ROADMAP.md                 ← lộ trình công việc theo workstream
```

## Bắt đầu nhanh

```powershell
cd pc_agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[service]"

python -m pc_agent            # foreground, tự dò COM, API 127.0.0.1:8000
python -m pc_agent --simulate # không cần phần cứng
```

Chạy như Windows Service (cần PowerShell quyền Administrator):

```powershell
cd pc_agent\deploy
.\install_service.ps1
```

Chi tiết: [`pc_agent/README.md`](pc_agent/README.md)

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [`ROADMAP.md`](ROADMAP.md) | Lộ trình theo workstream, ưu tiên, phụ thuộc, DoD, lịch GR2 |
| [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) | Mô hình 3 thành phần, kiến trúc nội bộ PC Agent, cơ chế service, ánh xạ thư mục |
| [`docs/architecture/diagrams/`](docs/architecture/diagrams/) | Sơ đồ Mermaid + bản ASCII (kiến trúc tổng thể, nội bộ agent, vòng đời service) |
| [`pc_agent/README.md`](pc_agent/README.md) | Hướng dẫn cài đặt, cấu hình, API, xử lý sự cố |
| [`docs/operations/INSTALL.md`](docs/operations/INSTALL.md) | Cài PC Agent thành Windows Service / systemd daemon từ đầu |
| [`docs/operations/TROUBLESHOOTING.md`](docs/operations/TROUBLESHOOTING.md) | 11 lỗi thường gặp + lệnh chẩn đoán |
| [`docs/operations/HARDWARE_PREP.md`](docs/operations/HARDWARE_PREP.md) | Chuẩn bị phần cứng cho Giai đoạn 2 (test máy thật) |
| [`docs/reports/report_week2.docx`](docs/reports/report_week2.docx) | Báo cáo GR2 Tuần 2 — Giai đoạn 1 (hardening) + đăng ký thư viện |
| `PZEM-004T_Huong_Dan_Giao_Thuc.docx` | Tài liệu gốc của module đo điện |

## Thư viện dùng chung — `embedded-iot-toolkit`

Thư viện C99 thuần tách ra để dùng lại ở nhiều tầng (PC Agent, firmware ESP32, tầng Web):
timer không chặn, giao thức khung serial có checksum, codec CAN 2.0B, trợ giúp cảm biến.

| Registry | Địa chỉ |
|---|---|
| Arduino Library Manager | https://www.arduinolibraries.info/libraries/embedded-io-t-toolkit |
| ESP-IDF Component Registry | https://components.espressif.com/components/catkod/embedded-iot-toolkit/versions/1.0.0 |
| Mã nguồn | https://github.com/CatKod/embedded-iot-toolkit |

## Phần cứng

- **PZEM-004T V3.0** — đồng hồ đo điện 1 pha 220 V AC, giao thức Modbus-RTU
- **USB-TTL adapter** — CH340 / CP210x / FTDI (9600 8N1)
- ⚠️ PZEM **không phản hồi UART nếu chưa được cấp nguồn lưới AC** ở chân `L`/`N`
