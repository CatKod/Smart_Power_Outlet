"""
Driver cho PZEM-004T V3.0 (đồng hồ đo năng lượng AC) qua cổng nối tiếp TTL.

Tuân thủ tài liệu "PZEM-004T V3.0 User Manual & Communication Protocol":
  https://www.cdebyte.com/products/PZEM-004T-10A_20A_100A.html

Tầng vật lý : UART, 9600 bps, 8 data bits, 1 stop bit, no parity
Tầng ứng dụng: Modbus-RTU

Bảng thanh ghi đo (đọc bằng function code 0x04 - Read Input Register,
bắt đầu từ 0x0000, đọc 10 thanh ghi):

    0x0000  Điện áp            0.1 V      (16 bit)
    0x0001  Dòng điện thấp     0.001 A    (16 bit thấp)
    0x0002  Dòng điện cao      (16 bit cao -> ghép thành 32 bit)
    0x0003  Công suất thấp     0.1 W      (16 bit thấp)
    0x0004  Công suất cao      (16 bit cao -> ghép thành 32 bit)
    0x0005  Điện năng thấp     1 Wh       (16 bit thấp)
    0x0006  Điện năng cao      (16 bit cao -> ghép thành 32 bit)
    0x0007  Tần số             0.1 Hz     (16 bit)
    0x0008  Hệ số công suất    0.01       (16 bit)
    0x0009  Trạng thái cảnh báo             (16 bit, 0xFFFF = báo động)

Frame yêu cầu (8 byte):
    [addr] 04 00 00 00 0A <crc_lo> <crc_hi>      (CRC: low byte trước)
"""

from __future__ import annotations

import struct
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

import serial

# --- Hằng số theo tài liệu ---
# Địa chỉ mặc định của PZEM-004T V3.0 là 0xF8 (địa chỉ chung, dùng khi chỉ có
# 1 slave). Tuy nhiên nhiều thiết bị bán sẵn để ở 0x01 - đo được trên thiết bị
# thật là 0x01, nên dùng 0x01 làm mặc định và có cơ chế tự dò.
PZEM_DEFAULT_ADDRESS = 0x01
PZEM_GENERAL_ADDRESS = 0xF8
PZEM_DEFAULT_BAUD = 9600
PZEM_MIN_ADDRESS = 0x01
PZEM_MAX_ADDRESS = 0xF7
PZEM_BROADCAST_ADDRESS = 0x00

CMD_READ_HOLDING = 0x03   # Đọc thanh ghi lưu trữ / tham số cài đặt
CMD_READ_INPUT = 0x04     # Đọc kết quả đo điện
CMD_WRITE_SINGLE = 0x06   # Ghi 1 thanh ghi
CMD_RESET_ENERGY = 0x42   # Xóa bộ đếm điện năng

REG_MEASURE_BASE = 0x0000
REG_COUNT = 0x000A
REG_ALARM_THRESHOLD = 0x0001
REG_SLAVE_ADDRESS = 0x0002

ALARM_ACTIVE = 0xFFFF
INVALID = 0xFFFF        # Giá trị 16 bit không hợp lệ
INVALID32 = 0xFFFFFFFF  # Giá trị 32 bit không hợp lệ


def crc16_modbus(data: bytes, init: int = 0xFFFF) -> int:
    """CRC-16 Modbus: đa thức phản chiếu 0xA001, khởi tạo 0xFFFF.

    Byte thấp được gửi trước, byte cao gửi sau (theo tài liệu mục 2.7).
    """
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def build_read_frame(address: int, function: int, start: int, count: int) -> bytes:
    """Dựng frame Modbus-RTU đọc thanh ghi (8 byte)."""
    body = bytes([address, function]) + struct.pack(">HH", start, count)
    crc = crc16_modbus(body)
    return body + bytes([crc & 0xFF, crc >> 8])


def build_write_single(address: int, register: int, value: int) -> bytes:
    """Dựng frame Modbus-RTU ghi 1 thanh ghi (8 byte)."""
    body = bytes([address, CMD_WRITE_SINGLE]) + struct.pack(">HH", register, value)
    crc = crc16_modbus(body)
    return body + bytes([crc & 0xFF, crc >> 8])


@dataclass
class PzemMetrics:
    """Một mẫu đo được chuẩn hoá."""

    voltage: Optional[float] = None        # V
    current: Optional[float] = None        # A
    power: Optional[float] = None          # W
    energy: Optional[float] = None         # Wh
    energy_kwh: Optional[float] = None     # kWh
    frequency: Optional[float] = None      # Hz
    power_factor: Optional[float] = None   # 0..1
    alarm: Optional[int] = None            # 0 = bình thường, 0xFFFF = báo động
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class PzemError(RuntimeError):
    """Lỗi giao tiếp với PZEM-004T."""


class Pzem004T:
    """Giao tiếp với một cổng serial gắn PZEM-004T.

    Sử dụng:
        with Pzem004T("COM10", address=0xF8) as pzem:
            print(pzem.read())
    """

    def __init__(
        self,
        port: str,
        baudrate: int = PZEM_DEFAULT_BAUD,
        address: int = PZEM_DEFAULT_ADDRESS,
        timeout: float = 1.0,
        bytesize: int = serial.EIGHTBITS,
        parity: str = serial.PARITY_NONE,
        stopbits: float = serial.STOPBITS_ONE,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.address = address
        self.timeout = timeout
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits

        self._ser: Optional[serial.Serial] = None

    # ------------------------------------------------------------------ #
    # Kết nối
    # ------------------------------------------------------------------ #
    def open(self) -> None:
        """Mở cổng serial."""
        self.close()
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
        except Exception as exc:  # noqa: BLE001
            raise PzemError(f"Không mở được cổng {self.port}: {exc}") from exc

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:  # noqa: BLE001
                pass
            self._ser = None

    def __enter__(self) -> "Pzem004T":
        self.open()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # ------------------------------------------------------------------ #
    # Đọc dữ liệu
    # ------------------------------------------------------------------ #
    def read(self) -> PzemMetrics:
        """Đọc một mẫu đo. Ném PzemError nếu giao tiếp lỗi."""
        if not self.is_open:
            raise PzemError("Cổng serial chưa mở")
        return self._read_registers(CMD_READ_INPUT)

    def probe(self) -> bool:
        """Kiểm tra slave có phản hồi ở địa chỉ hiện tại không (không ném lỗi)."""
        if not self.is_open:
            return False
        request = build_read_frame(self.address, CMD_READ_INPUT, REG_MEASURE_BASE, REG_COUNT)
        self._ser.reset_input_buffer()
        self._ser.write(request)
        self._ser.flush()
        time.sleep(0.15)
        resp = self._ser.read(64)
        return bool(resp) and len(resp) >= 3 and resp[1] == CMD_READ_INPUT

    def auto_detect_address(self) -> Optional[int]:
        """Tự dò địa chỉ slave nếu địa chỉ cấu hình không phản hồi.

        Trả về địa chỉ tìm thấy, hoặc None nếu không có slave nào phản hồi.
        """
        if not self.is_open:
            raise PzemError("Cổng serial chưa mở")
        if self.probe():
            return self.address

        # Thử địa chỉ chung 0xF8 trước, rồi quét các địa chỉ phổ biến
        candidates = [PZEM_GENERAL_ADDRESS] + list(range(0x01, 0x11))
        for address in candidates:
            if address == self.address:
                continue
            self.address = address
            if self.probe():
                return address

        # Quét toàn bộ dải hợp lệ
        for address in range(PZEM_MIN_ADDRESS, PZEM_MAX_ADDRESS + 1):
            if address in candidates:
                continue
            self.address = address
            if self.probe():
                return address

        self.address = PZEM_DEFAULT_ADDRESS
        return None

    def read_settings(self) -> dict:
        """Đọc tham số slave bằng function 0x03.

        Bố cục thanh ghi holding thực tế (đã kiểm chứng trên thiết bị):
            0x0000  (không tài liệu)
            0x0001  Ngưỡng cảnh báo công suất (W)
            0x0002  Địa chỉ Modbus-RTU của slave
            0x0003  Tốc độ baud
        """
        if not self.is_open:
            raise PzemError("Cổng serial chưa mở")
        response = self._transact(
            build_read_frame(self.address, CMD_READ_HOLDING, REG_ALARM_THRESHOLD, 0x0003)
        )
        if response is None:
            raise PzemError("Không nhận được phản hồi khi đọc tham số slave")

        # Phản hồi lỗi
        if len(response) >= 3 and response[1] == (CMD_READ_HOLDING | 0x80):
            raise PzemError(f"PZEM báo lỗi 0x{response[2]:02X} khi đọc tham số")

        body = response[:-2]
        rx_crc = response[-2] | (response[-1] << 8)
        if crc16_modbus(body) != rx_crc:
            raise PzemError("CRC phản hồi tham số không hợp lệ")

        data = response[3:3 + response[2]]

        def u16(i: int) -> int:
            return (data[i] << 8) | data[i + 1]

        settings = {
            "power_alarm_threshold": u16(0),   # 0x0001
            "slave_address": u16(2),           # 0x0002
        }
        if len(data) >= 6:
            settings["baudrate"] = u16(4)      # 0x0003
        return settings

    def set_alarm_threshold(self, watts: int) -> None:
        """Đặt ngưỡng cảnh báo công suất (tối đa 25000 W)."""
        watts = min(max(int(watts), 0), 25000)
        response = self._transact(
            build_write_single(self.address, REG_ALARM_THRESHOLD, watts)
        )
        if response is None:
            raise PzemError("Không nhận được phản hồi khi đặt ngưỡng cảnh báo")

    def reset_energy(self) -> None:
        """Xóa bộ đếm điện năng về 0 (function 0x42, 4 byte)."""
        if not self.is_open:
            raise PzemError("Cổng serial chưa mở")
        body = bytes([self.address, CMD_RESET_ENERGY])
        crc = crc16_modbus(body)
        frame = body + bytes([crc & 0xFF, crc >> 8])
        self._ser.write(frame)
        self._ser.flush()
        time.sleep(0.1)
        self._ser.read(8)

    def _read_registers(self, function: int) -> PzemMetrics:
        assert self._ser is not None
        request = build_read_frame(self.address, function, REG_MEASURE_BASE, REG_COUNT)
        response = self._transact(request)

        if response is None:
            raise PzemError(
                f"Không nhận được phản hồi từ PZEM (addr 0x{self.address:02X}, "
                f"func 0x{function:02X}, {self.port} @ {self.baudrate} baud). "
                "LƯU Ý: PZEM-004T V3.0 chỉ hoạt động khi được cấp nguồn lưới AC "
                "(nối chân L/N), cấp 5V qua USB-TTL là không đủ."
            )

        # Phản hồi lỗi: addr + (func | 0x80) + mã lỗi + CRC
        if len(response) >= 3 and response[1] == (function | 0x80):
            codes = {
                0x01: "Illegal function (mã hàm không hợp lệ)",
                0x02: "Illegal address (địa chỉ thanh ghi không hợp lệ)",
                0x03: "Illegal data (dữ liệu không hợp lệ)",
                0x04: "Slave error (lỗi thiết bị)",
            }
            code = response[2]
            raise PzemError(
                f"PZEM báo lỗi 0x{code:02X}: {codes.get(code, 'không rõ')}"
            )

        # Kiểm tra CRC
        body = response[:-2]
        rx_crc = response[-2] | (response[-1] << 8)
        if crc16_modbus(body) != rx_crc:
            raise PzemError("CRC phản hồi không hợp lệ (nhiễu hoặc sai địa chỉ)")

        return self._decode(response[3:23])

    @staticmethod
    def _decode(data: bytes) -> PzemMetrics:
        """Giải mã 20 byte dữ liệu thanh ghi theo bảng trong tài liệu.

        Bảng thanh ghi (mỗi thanh ghi 16 bit, truyền theo thứ tự tăng dần):
            0x0000  Điện áp            0.1 V
            0x0001  Dòng điện thấp     0.001 A   ┐ ghép thành 32 bit
            0x0002  Dòng điện cao                ┘ (cao đứng trước, thấp đứng sau)
            0x0003  Công suất thấp     0.1 W     ┐
            0x0004  Công suất cao                ┘
            0x0005  Điện năng thấp     1 Wh      ┐
            0x0006  Điện năng cao                ┘
            0x0007  Tần số             0.1 Hz
            0x0008  Hệ số công suất    0.01
            0x0009  Trạng thái cảnh báo
        """
        if len(data) < 20:
            raise PzemError(f"Dữ liệu thanh ghi quá ngắn: {len(data)} byte (cần 20)")

        def u16(i: int) -> int:
            """Đọc 1 thanh ghi 16 bit tại offset byte `i`."""
            return (data[i] << 8) | data[i + 1]

        def u32(i: int) -> int:
            """Đọc 1 giá trị 32 bit gồm 2 thanh ghi liên tiếp.

            Theo tài liệu, thanh ghi CAO đứng trước, thanh ghi THẤP đứng sau,
            nên giá trị = (cao << 16) | thấp.
            """
            low = u16(i)
            high = u16(i + 2)
            return (high << 16) | low

        voltage = u16(0) / 10.0
        current = u32(2) / 1000.0
        power = u32(6) / 10.0
        energy_wh = u32(10)
        frequency = u16(14) / 10.0
        power_factor = u16(16) / 100.0
        alarm = u16(18)

        # PZEM trả 0xFFFF cho giá trị đo không hợp lệ (chưa có tải / lỗi đo).
        # Hiển thị 0 thay vì giá trị rác (655.3 A, 4294967.2 W, ...).
        # LƯU Ý: thanh ghi cảnh báo dùng 0xFFFF theo nghĩa "đang báo động",
        # nên không áp dụng quy tắc này cho alarm.
        if u16(0) == INVALID:
            voltage = 0.0
        if u32(2) == INVALID32:
            current = 0.0
        if u32(6) == INVALID32:
            power = 0.0
        if u32(10) == INVALID32:
            energy_wh = 0
        if u16(14) == INVALID:
            frequency = 0.0
        if u16(16) == INVALID:
            power_factor = 0.0

        return PzemMetrics(
            voltage=voltage,
            current=current,
            power=power,
            energy=float(energy_wh),
            energy_kwh=energy_wh / 1000.0,
            frequency=frequency,
            power_factor=power_factor,
            alarm=alarm,
        )

    # ------------------------------------------------------------------ #
    # Nội bộ
    # ------------------------------------------------------------------ #
    def _transact(self, request: bytes) -> Optional[bytes]:
        """Gửi frame và chờ phản hồi hoàn chỉnh."""
        assert self._ser is not None
        self._ser.reset_input_buffer()
        self._ser.write(request)
        self._ser.flush()

        deadline = time.time() + self.timeout
        buf = b""
        while time.time() < deadline:
            chunk = self._ser.read(128)
            if not chunk:
                continue
            buf += chunk
            # Phản hồi thành công: addr + func + count + data + CRC
            if len(buf) >= 3 and buf[1] == request[1] and len(buf) >= 5 + buf[2]:
                return buf[: 5 + buf[2]]
            # Phản hồi lỗi: addr + (func|0x80) + code + CRC
            if len(buf) >= 5 and buf[1] == (request[1] | 0x80):
                return buf[:5]
        return buf if buf else None

    def scan_addresses(self, addresses=None, delay: float = 0.05) -> list:
        """Dò xem địa chỉ slave nào phản hồi.

        Mặc định thử trước các địa chỉ thường gặp (0xF8 chung, 0x01-0x10),
        rồi mới quét toàn bộ dải 0x01-0xF7 nếu chưa tìm thấy.

        Trả về danh sách địa chỉ hoạt động.
        """
        if not self.is_open:
            raise PzemError("Cổng serial chưa mở")

        if addresses is None:
            # Thử trước địa chỉ chung 0xF8 và các địa chỉ thường gặp 0x01-0x10,
            # rồi mới quét toàn bộ dải 0x01-0xF7. Loại trùng bằng dict.
            common = [PZEM_GENERAL_ADDRESS] + list(range(0x01, 0x11))
            full = [a for a in range(PZEM_MIN_ADDRESS, PZEM_MAX_ADDRESS + 1)
                    if a not in common]
            addresses = list(dict.fromkeys(common + full))

        found = []
        # Giảm timeout tạm thời khi quét để không chờ lâu cho mỗi địa chỉ
        original_timeout = self._ser.timeout
        self._ser.timeout = 0.06
        try:
            for address in addresses:
                request = build_read_frame(address, CMD_READ_INPUT, REG_MEASURE_BASE, REG_COUNT)
                self._ser.reset_input_buffer()
                self._ser.write(request)
                self._ser.flush()
                time.sleep(delay)
                resp = self._ser.read(64)
                if resp and len(resp) >= 3 and resp[1] == CMD_READ_INPUT:
                    found.append(address)
        finally:
            self._ser.timeout = original_timeout
        return found
