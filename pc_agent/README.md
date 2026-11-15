# PC Agent — Electronic PC Agent (Smart Power Outlet)

Tiến trình nền giám sát năng lượng bằng **PZEM-004T V3.0** (Modbus-RTU) cho một tổ hợp máy chủ trong tủ rack.

Chạy như **Windows Service** hoặc **Linux systemd daemon**: tự khởi động cùng máy, **không cần đăng nhập người dùng**, không GUI, tự dò cổng COM và tự phục hồi khi thiết bị bị rút/cắm lại.

> Kiến trúc tổng thể 3 thành phần: [`docs/architecture/ARCHITECTURE.md`](../docs/architecture/ARCHITECTURE.md)

---

## 1. Yêu cầu

- Python **3.9+**
- `pyserial` (phụ thuộc bắt buộc duy nhất)
- `pywin32` — chỉ khi chạy dưới dạng Windows Service
- Phần cứng: USB-TTL adapter + **PZEM-004T V3.0** đã cấp nguồn lưới AC

## 2. Cài đặt

```powershell
cd pc_agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[service]"
```

Không dùng venv:

```powershell
pip install pyserial
pip install pywin32        # chỉ cần cho Windows Service
```

## 3. Chạy

### 3.1. Foreground (phát triển)

```powershell
python -m pc_agent                 # tự dò COM, API 127.0.0.1:8000
python -m pc_agent --port COM10    # ép cổng
python -m pc_agent --simulate      # không cần phần cứng
python -m pc_agent --exhaustive-scan   # quét toàn bộ dải địa chỉ slave (chậm)
```

Hoặc dùng script: `deploy\run_dev.bat [COM_PORT] [API_PORT]`.

### 3.2. Windows Service (sản xuất)

```powershell
# PowerShell với quyền Administrator
cd pc_agent\deploy
.\install_service.ps1
.\install_service.ps1 -ApiHost 0.0.0.0 -ApiPort 8000    # mở cho mạng LAN
```

Script sẽ: copy package vào `C:\SmartPowerOutlet`, tạo venv, cài phụ thuộc, ghi cấu hình ban đầu, đăng ký service (**delayed auto-start**), cấu hình **crash recovery** (5 s / 10 s / 30 s) và mở firewall rule nếu bind ngoài localhost.

Kiểm tra:

```powershell
sc.exe query SmartPowerOutletAgent
Get-Content "$env:ProgramData\SmartPowerOutlet\logs\agent.log" -Tail 50
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Gỡ bỏ:

```powershell
.\uninstall_service.ps1
.\uninstall_service.ps1 -PurgeData     # xoá luôn %ProgramData%\SmartPowerOutlet
```

### 3.3. Linux daemon

```bash
sudo cp deploy/smart-power-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smart-power-agent
journalctl -u smart-power-agent -f
```

## 4. Cấu trúc thư mục

```
pc_agent/
├── pyproject.toml                    # PEP 621, entry points: pc-agent, pc-agent-service
├── src/pc_agent/
│   ├── __main__.py                   # CLI + AgentRuntime (chung foreground & service)
│   ├── config.py                     # AgentConfig, đường dẫn, ghi atomic
│   ├── discovery.py                  # COM Auto-Discovery 4 bậc + Anti-Flapping Cache
│   ├── logging_setup.py              # logging an toàn cho Session 0
│   ├── drivers/pzem004t.py           # driver Modbus-RTU (CRC, frame, giải mã)
│   ├── core/
│   │   ├── poller.py                 # thread lấy mẫu 1 Hz + tự phục hồi
│   │   ├── rules.py                  # Rule Engine (ngưỡng cảnh báo → events)
│   │   └── state.py                  # StateStore (trạng thái dùng chung)
│   ├── storage/sqlite_store.py       # TelemetryStore (SQLite WAL)
│   ├── api/server.py                 # REST API (http.server chuẩn Python)
│   ├── web/index.html                # dashboard tĩnh
│   ├── deploy/windows_service.py     # pywin32 ServiceFramework
│   └── tools/                        # probe_bus, probe_exhaustive, dump_settings
├── deploy/
│   ├── install_service.ps1
│   ├── uninstall_service.ps1
│   ├── smart-power-agent.service
│   └── run_dev.bat
└── tests/
    ├── test_decode.py                # test giải mã theo frame mẫu trong tài liệu
    ├── verify_frame.py               # kiểm chứng CRC + frame thật từ thiết bị
    └── check_crc.py                  # đối chiếu thuật toán CRC với tài liệu
```

## 5. Cấu hình

Vị trí:

| Nền tảng | Cấu hình | Dữ liệu | Log |
|---|---|---|---|
| Windows | `%ProgramData%\SmartPowerOutlet\config.json` | `...\data\telemetry.db` | `...\logs\agent.log` |
| Linux | `$XDG_CONFIG_HOME/smartpoweroutlet/config.json` (hoặc `~/.config/…`) | `$XDG_DATA_HOME/smartpoweroutlet/` | `~/.config/smartpoweroutlet/logs/` |

Ghi đè bằng biến môi trường: `SMARTPOWER_CONFIG_DIR`, `SMARTPOWER_DATA_DIR`, `SMARTPOWER_LOG_DIR`.

Các trường quan trọng:

| Trường | Mặc định | Ý nghĩa |
|---|---|---|
| `site_id` / `rack_id` / `meter_id` | `site-01` / `rack-01` / `pdu-01` | Định danh hiện trường — ánh xạ "1 tủ rack" |
| `port` | `null` | Cổng COM đã dò & xác minh |
| `usb_location` | `null` | Đường dẫn USB vật lý (ổn định hơn số COM) |
| `slave_address` | `0x01` | Địa chỉ Modbus slave đã xác minh |
| `baudrate` | `9600` | 9600 8N1 |
| `poll_interval_s` | `1.0` | Chu kỳ lấy mẫu |
| `power_threshold_w` | `25000` | Ngưỡng quá công suất |
| `voltage_min_v` / `voltage_max_v` | `180` / `260` | Ngưỡng sụt / quá áp |
| `api_host` / `api_port` | `127.0.0.1` / `8000` | Địa chỉ API |
| `api_token` | `null` | Bearer token — **bắt buộc** khi bind ngoài localhost |
| `mqtt_host` | `null` | Broker MQTT (giai đoạn sau; để trống = tắt) |
| `raw_retention_days` / `hourly_retention_days` | `14` / `365` | Thời hạn lưu dữ liệu |

**Ghi đè bằng tay bị chặn có chủ đích:** agent chỉ ghi đè `port` / `slave_address` / `usb_location` sau khi **xác minh được thiết bị thật** (đúng function code → đúng byte count → CRC hợp lệ → U ∈ [80,260] V → f ∈ [45,65] Hz). Nếu không tìm thấy, cấu hình cũ **giữ nguyên**.

## 6. API

| Endpoint | Trả về |
|---|---|
| `GET /` | Dashboard |
| `GET /api/health` | `status`, `version`, `uptime_s`, thống kê DB |
| `GET /api/status` | Trạng thái kết nối, cổng, địa chỉ, số mẫu, lỗi cuối |
| `GET /api/metrics` | Số đo mới nhất |
| `GET /api/history?from=&to=&resolution=raw\|hourly&limit=` | Lịch sử |
| `GET /api/events?active_only=true` | Sự cố |
| `GET /api/config` | Cấu hình hiện tại |

Ví dụ:

```json
{
  "connected": true,
  "port": "COM10",
  "metrics": {
    "voltage_v": 233.8, "current_a": 0.075, "power_w": 9.7,
    "energy_wh": 2.0, "energy_kwh": 0.002, "frequency_hz": 50.1,
    "power_factor": 0.55, "alarm_active": false
  }
}
```

## 7. Nối dây

| Chân PZEM-004T | Nối vào |
|---|---|
| `5V` | 5 V của USB-TTL (chỉ cấp cho mạch logic) |
| `GND` | GND của USB-TTL |
| `TX` | **RX** của USB-TTL |
| `RX` | **TX** của USB-TTL |
| `L`, `N` | **Nguồn lưới AC 220 V** (bắt buộc) |

> ⚠️ **PZEM-004T V3.0 không phản hồi trên UART nếu chưa có nguồn lưới AC.** Cấp 5 V qua USB-TTL chỉ đủ cho mạch logic. Nếu agent báo *"Cổng mở được nhưng thiết bị im lặng"*, kiểm tra ngay nguồn 220 V ở chân `L`/`N`.

## 8. Giao thức

**Tầng vật lý:** UART 9600 8N1 · **Tầng ứng dụng:** Modbus-RTU, slave `0x01`, function `0x04`.

```
Master → Slave : 01 04 00 00 00 0A 70 0D
Slave → Master : 01 04 14 <20 byte dữ liệu> <crc_lo> <crc_hi>
```

**CRC-16 Modbus:** poly phản chiếu `0xA001`, init `0xFFFF`, **byte thấp gửi trước**.

Bảng thanh ghi đo:

| Địa chỉ | Ý nghĩa | Độ phân giải |
|---|---|---|
| `0x0000` | Điện áp | 0.1 V |
| `0x0001`–`0x0002` | Dòng điện (16 bit thấp + 16 bit cao) | 0.001 A |
| `0x0003`–`0x0004` | Công suất (16 bit thấp + 16 bit cao) | 0.1 W |
| `0x0005`–`0x0006` | Điện năng (16 bit thấp + 16 bit cao) | 1 Wh |
| `0x0007` | Tần số | 0.1 Hz |
| `0x0008` | Hệ số công suất | 0.01 |
| `0x0009` | Cảnh báo | `0xFFFF` = đang báo động |

Hai điểm dễ sai nhất (đã có test riêng):
1. **Ghép 32 bit:** `value = (high << 16) | low` — thanh ghi **thấp** (`0x0001`) đứng trước trong frame, thanh ghi **cao** (`0x0002`) đứng sau.
2. **Sentinel `0xFFFF`:** chưa có tải → PZEM trả `0xFFFF`, driver chuyển thành `0`.

Nguồn: `PZEM-004T_Huong_Dan_Giao_Thuc.docx`.

## 9. Kiểm thử

```powershell
pip install -e ".[dev]"
pytest pc_agent/tests -v
python pc_agent/tests/check_crc.py       # đối chiếu thuật toán CRC
python pc_agent/src/pc_agent/tools/probe_bus.py        # dò cổng + địa chỉ
```

| Kiểm thử | Mong đợi |
|---|---|
| CRC frame mẫu | `01 04 00 00 00 0A 70 0D` — khớp tài liệu |
| Giải mã frame mẫu | 220.0 V, 1.000 A, 220.0 W, 0 Wh, 50.0 Hz, PF 1.00 |
| Giá trị thực tế | 220.5 V, 1.234 A, 271.4 W, 1500 Wh, 50.0 Hz, PF 0.95 |
| Chưa có tải (sentinel) | tất cả bằng 0 |

## 10. Kết quả đo thực tế

PZEM-004T V3.0 thật (COM10, đèn bàn LED ~10 W):

```
Điện áp   : 233.8 V
Dòng điện : 0.075 A
Công suất : 9.7 W
Điện năng : 2.0 Wh (0.002 kWh)
Tần số    : 50.1 Hz
Hệ số CS  : 0.55
```

Đối chiếu `P = V × I × PF` = 233.8 × 0.075 × 0.55 = **9.64 W** ≈ **9.7 W** đo được → giải mã chính xác.

## 11. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| `Access is denied` / `PORT_BUSY` | Tiến trình khác đang giữ cổng (PuTTY, PlatformIO, monitor) | Đóng tiến trình đó — **không phải** lỗi dây/nguồn |
| `PORT_MISSING` / không tìm thấy cổng | USB-TTL bị rút | Cắm lại; agent tự dò lại sau 5 s |
| Cổng mở được nhưng thiết bị im lặng | PZEM **chưa có nguồn lưới AC** ở chân L/N | Cấp 220 V AC |
| Số COM đổi sau khi rút/cắm | Adapter không có serial number (CH340) | Agent tự khớp lại theo `usb_location` |
| `IMPLAUSIBLE` (U/f ngoài dải) | Cổng khác trả lời, hoặc nhiễu | Bỏ qua cổng đó, tiếp tục quét |
| Service không lên sau reboot | Chưa cài venv / script lỗi | `Get-Content %ProgramData%\SmartPowerOutlet\logs\agent.log -Tail 50` |
