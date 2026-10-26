# Test_PZEM_00T4 — Web hiển thị thông số PZEM-004T

Giao diện web đơn giản hiển thị trực tiếp các thông số đo được từ đồng hồ đo
năng lượng **PZEM-004T V3.0**, đọc qua cổng nối tiếp TTL-USB của máy tính.

## 1. Cấu trúc thư mục

```
Test_PZEM_00T4/
├── pzem004t.py        # Driver giao tiếp Modbus-RTU với PZEM-004T
├── server.py          # Web server + API JSON + luồng đọc nền
├── run.bat            # Script chạy nhanh trên Windows
├── web/
│   └── index.html     # Giao diện dashboard
├── tools/
│   ├── test_decode.py        # Kiểm thử giải mã theo frame ví dụ trong tài liệu
│   ├── scan_pzem.py          # Dò địa chỉ slave / function code
│   ├── probe_exhaustive.py   # Dò rộng baud x parity x địa chỉ
│   └── check_crc.py          # Đối chiếu thuật toán CRC với tài liệu
└── README.md
```

## 2. Yêu cầu cài đặt

```bash
pip install pyserial
```

Chỉ cần đúng một thư viện ngoài (`pyserial`), phần còn lại dùng thư viện chuẩn
của Python.

## 3. Chạy

```bash
# Mặc định: cổng COM10, web ở http://127.0.0.1:8000/
python server.py

# Hoặc dùng script
run.bat                      # tương đương python server.py --port COM10
run.bat COM10 8000
```

Các tham số khác:

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `--port` | `COM10` | Cổng COM của TTL-USB |
| `--baud` | `9600` | Tốc độ baud |
| `--address` | `0xF8` | Địa chỉ Modbus slave |
| `--web-port` | `8000` | Cổng web server |
| `--interval` | `1.0` | Chu kỳ lấy mẫu (giây) |
| `--simulate` | — | Chế độ mô phỏng, **không** đọc phần cứng thật |

Mở trình duyệt tại <http://127.0.0.1:8000/>.

## 4. Nối dây

| Chân PZEM-004T | Nối vào |
|---|---|
| `5V` | 5V của USB-TTL (chỉ cấp cho mạch logic) |
| `GND` | GND của USB-TTL |
| `TX` | **RX** của USB-TTL |
| `RX` | **TX** của USB-TTL |
| `L`, `N` | **Nguồn lưới AC 220V** (bắt buộc) |

> ### ⚠ Yêu cầu quan trọng: phải cấp nguồn lưới AC
>
> PZEM-004T V3.0 **không phản hồi trên UART nếu chưa được cấp nguồn lưới AC**.
> Cấp 5V qua USB-TTL chỉ đủ cho mạch logic, nhưng mạch đo và giao tiếp UART
> chỉ hoạt động khi có điện lưới nối vào chân `L`/`N`.
>
> Nếu web báo *"Không nhận được phản hồi từ PZEM"*, hãy kiểm tra:
> 1. Đã cấp 220V AC vào chân `L`/`N` chưa?
> 2. Dây `TX`/`RX` có bị đảo không?
> 3. Đã cắm chung GND chưa?

Ngoài ra, nếu PZEM của bạn đã được đổi địa chỉ slave khác `0xF8`, hãy truyền
`--address` tương ứng. Dùng `tools/scan_pzem.py` để dò địa chỉ.

## 5. Giao thức

Tài liệu tham chiếu: `PZEM-004T_Huong_Dan_Giao_Thuc.docx` (ở thư mục gốc repo).

**Tầng vật lý:** UART — 9600 bps, 8 data bits, 1 stop bit, no parity.

**Tầng ứng dụng:** Modbus-RTU.

### Đọc kết quả đo (function code `0x04`)

Master → Slave (8 byte):

```
[addr] 04 00 00 00 0A <crc_lo> <crc_hi>
```

Ví dụ với địa chỉ `0x01`: `01 04 00 00 00 0A 70 0D`

Slave → Master (25 byte):

```
[addr] 04 14 <20 byte dữ liệu> <crc_lo> <crc_hi>
```

### CRC-16 Modbus

Đa thức phản chiếu `0xA001`, khởi tạo `0xFFFF`. **Byte thấp gửi trước, byte cao
gửi sau.** Thư viện chuẩn `mandulaj/PZEM-004T-v30` dùng đúng thuật toán này và
frame ví dụ trong tài liệu khớp chính xác (kiểm chứng bởi `tools/test_decode.py`).

### Bảng thanh ghi đo

| Địa chỉ | Ý nghĩa | Độ phân giải |
|---|---|---|
| `0x0000` | Điện áp | 0.1 V |
| `0x0001` | Dòng điện — 16 bit thấp | 0.001 A |
| `0x0002` | Dòng điện — 16 bit cao | (ghép thành 32 bit) |
| `0x0003` | Công suất — 16 bit thấp | 0.1 W |
| `0x0004` | Công suất — 16 bit cao | (ghép thành 32 bit) |
| `0x0005` | Điện năng — 16 bit thấp | 1 Wh |
| `0x0006` | Điện năng — 16 bit cao | (ghép thành 32 bit) |
| `0x0007` | Tần số | 0.1 Hz |
| `0x0008` | Hệ số công suất | 0.01 |
| `0x0009` | Trạng thái cảnh báo | `0xFFFF` = đang báo động, `0x0000` = bình thường |

> **Lưu ý thứ tự ghép 32 bit:** thanh ghi **cao** đứng **trước**, thanh ghi
> **thấp** đứng **sau**, tức `giá trị = (cao << 16) | thấp`. Đây là điểm dễ
> sai nhất — `tools/test_decode.py` có test riêng cho nó.

### Địa chỉ slave

- Dải hợp lệ: `0x01` … `0xF7`
- `0x00`: địa chỉ quảng bá (slave **không** trả lời)
- `0xF8`: địa chỉ chung, dùng khi chỉ có **một** slave — **đây là mặc định**

### Khi chưa cắm tải

PZEM trả giá trị sentinel `0xFFFF` (16 bit) / `0xFFFFFFFF` (32 bit) cho các
đại lượng không đo được. Driver giải mã chuyển các giá trị này thành `0` để
hiển thị đúng, tránh ra các con số rác như `655.3 A`.

## 6. API

### `GET /api/metrics`

```json
{
  "connected": true,
  "error": null,
  "samples": 42,
  "last_update": 1793028946.25,
  "port": "COM10",
  "baud": 9600,
  "address": 248,
  "simulate": false,
  "metrics": {
    "voltage": 220.0,
    "current": 1.0,
    "power": 220.0,
    "energy": 0.0,
    "energy_kwh": 0.0,
    "frequency": 50.0,
    "power_factor": 1.0,
    "alarm": 0,
    "timestamp": 1793028946.25
  }
}
```

Khi mất kết nối, `connected` là `false` và `error` chứa thông báo lỗi.

## 7. Kiểm thử

```bash
python tools/test_decode.py        # kiểm thử giải mã (không cần phần cứng)
python tools/scan_pzem.py COM10    # dò địa chỉ slave / function code
python tools/probe_exhaustive.py COM10
```

`test_decode.py` dùng đúng frame ví dụ trong tài liệu làm chuẩn đối chiếu:

| Kiểm thử | Kết quả mong đợi |
|---|---|
| CRC frame mẫu | `01 04 00 00 00 0A 70 0D` — khớp tài liệu |
| Giải mã frame mẫu | 220.0 V, 1.000 A, 220.0 W, 0 Wh, 50.0 Hz, PF 1.00 |
| Giá trị thực tế | 220.5 V, 1.234 A, 271.4 W, 1500 Wh, 50.0 Hz, PF 0.95 |
| Chưa có tải (sentinel) | tất cả bằng 0 |

## 8. Chế độ mô phỏng

Khi chưa có phần cứng, dùng `--simulate` để kiểm thử giao diện:

```bash
python server.py --simulate --web-port 8010
```

Giao diện sẽ hiện **băng cảnh báo màu vàng "CHẾ ĐỘ MÔ PHỎNG"** để không nhầm
với số liệu đo thật.
