"""Dò cổng serial và nhận diện PZEM-004T — lõi của PC Agent.

Vấn đề cần giải: Windows **không** giữ nguyên số COM sau mỗi lần rút/cắm
USB-TTL. Với adapter không có serial number duy nhất (CH340 giá rẻ chẳng hạn),
Windows gán lại số COM khi cắm vào cổng USB khác. Vì vậy ta **không** chỉ nhớ
số COM — ta nhớ **cả đường dẫn USB vật lý** (`location`, ví dụ `1-4:x.3`),
vốn ổn định hơn nhiều.

Chính sách (xem `discover()`):

    1. Fast path  — thử cổng đã nhớ (nếu còn trong SERIALCOMM) + địa chỉ đã nhớ.
    2. Topology  — quét cổng hiện có, ưu tiên cổng có `location` khớp đã nhớ.
    3. Fallback  — quét các cổng USB-TTL ở địa chỉ ưu tiên (đã nhớ, 0x01, 0xF8).
    4. Slow scan — quét toàn bộ dải địa chỉ 0x01..0xF7 (chỉ khi được yêu cầu).

Quy tắc bất di bất dịch: **chỉ ghi đè cấu hình khi đã xác minh được** một
PZEM thật (frame đúng + CRC đúng + giá trị điện lưới hợp lý). Cổng hỏng,
cổng bị chiếm, hay thiết bị không cấp nguồn AC đều **không** được xoá
cấu hình đã nhớ — nếu không, service sẽ "ghi nhớ" rác rồi không bao giờ
quay lại đúng cổng cũ.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import serial
import serial.tools.list_ports

from .config import AgentConfig, ConfigStore
from .drivers.pzem004t import (
    CMD_READ_INPUT,
    REG_COUNT,
    REG_MEASURE_BASE,
    PzemError,
    Pzem004T,
    build_read_frame,
    crc16_modbus,
)

LOG = logging.getLogger("pc_agent.discovery")

# --- Thời gian chờ (giây) cho mỗi lần dò ---
PROBE_TIMEOUT_S = 0.20
PROBE_SETTLE_S = 0.05

# --- Ngưỡng "giá trị điện lưới hợp lý" để loại trừ thiết bị Modbus khác ---
PLAUSIBLE_VOLTAGE_V = (80.0, 260.0)
PLAUSIBLE_FREQUENCY_HZ = (45.0, 65.0)

# --- Chip bridge USB-TTL phổ biến (dùng để xếp hạng ưu tiên) ---
KNOWN_USB_BRIDGES = {
    (0x1A86, 0x7523): "WCH CH340",
    (0x1A86, 0x5523): "WCH CH341",
    (0x1A86, 0x55D4): "WCH CH9102",
    (0x10C4, 0xEA60): "Silicon Labs CP210x",
    (0x10C4, 0xEA70): "Silicon Labs CP2105",
    (0x0403, 0x6001): "FTDI FT232R",
    (0x0403, 0x6015): "FTDI FT230X",
    (0x067B, 0x2303): "Prolific PL2303",
}

# Địa chỉ đặc biệt của Modbus
ADDR_BROADCAST = 0x00
ADDR_GENERAL = 0xF8
ADDR_MIN = 0x01
ADDR_MAX = 0xF7


# --------------------------------------------------------------------------- #
# Kết quả dò
# --------------------------------------------------------------------------- #
@dataclass
class ProbeResult:
    """Kết quả dò một (cổng, địa chỉ)."""

    ok: bool
    status: str                 # "OK" | "SILENT" | "PORT_MISSING" | "PORT_BUSY" | "IO_ERROR" | ...
    port: str = ""
    address: Optional[int] = None
    location: Optional[str] = None
    voltage_v: Optional[float] = None
    frequency_hz: Optional[float] = None
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.status} port={self.port} addr={self.address}"


@dataclass
class CandidatePort:
    """Một cổng serial ứng viên, đã xếp hạng."""

    port: str
    tier: int                   # 1 = bridge USB-TTL đã biết, 2 = USB serial khác, 3 = cổng legacy
    description: str = ""
    location: Optional[str] = None
    vid: Optional[int] = None
    pid: Optional[int] = None


# --------------------------------------------------------------------------- #
# Liệt kê cổng
# --------------------------------------------------------------------------- #
def list_candidate_ports() -> List[CandidatePort]:
    """Liệt kê cổng serial hiện có, xếp hạng theo khả năng là USB-TTL."""
    candidates: List[CandidatePort] = []
    try:
        ports = list(serial.tools.list_ports.comports())
    except Exception as exc:  # noqa: BLE001
        LOG.error("Không liệt kê được cổng serial: %s", exc)
        return candidates

    for p in ports:
        vid, pid = p.vid, p.pid
        if vid is not None and pid is not None and (vid, pid) in KNOWN_USB_BRIDGES:
            tier = 1
        elif (p.hwid or "").upper().startswith("USB"):
            tier = 2
        else:
            tier = 3
        candidates.append(
            CandidatePort(
                port=p.device,
                tier=tier,
                description=p.description or "",
                location=p.location,
                vid=vid,
                pid=pid,
            )
        )

    candidates.sort(key=lambda c: (c.tier, c.port))
    return candidates


# --------------------------------------------------------------------------- #
# Dò một cổng / một địa chỉ
# --------------------------------------------------------------------------- #
def probe_address(
    port: str,
    address: int,
    baudrate: int = 9600,
    timeout: float = PROBE_TIMEOUT_S,
) -> ProbeResult:
    """Mở cổng, gửi Modbus 0x04, kiểm tra frame + CRC + giá trị hợp lý.

    Không ném exception — luôn trả về `ProbeResult` để caller quyết định.
    """
    ser: Optional[serial.Serial] = None
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            write_timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        status, detail = classify_open_error(exc)
        return ProbeResult(ok=False, status=status, port=port, address=address, detail=detail)

    try:
        request = build_read_frame(address, CMD_READ_INPUT, REG_MEASURE_BASE, REG_COUNT)
        ser.reset_input_buffer()
        ser.write(request)
        ser.flush()
        time.sleep(PROBE_SETTLE_S)

        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline and len(buf) < 25:
            chunk = ser.read(64)
            if chunk:
                buf += chunk

        if not buf:
            return ProbeResult(
                ok=False, status="SILENT", port=port, address=address,
                detail="Cổng mở được nhưng thiết bị không phản hồi",
            )

        # Kiểm tra hình dạng khung: addr + func + count + data + CRC
        if len(buf) < 3 or buf[1] != CMD_READ_INPUT:
            return ProbeResult(
                ok=False, status="NOT_PZEM", port=port, address=address,
                detail=f"Phản hồi không phải function 0x04: {buf[:8].hex(' ')}",
            )
        if buf[1] & 0x80:
            code = buf[2] if len(buf) > 2 else -1
            return ProbeResult(
                ok=False, status="SLAVE_ERROR", port=port, address=address,
                detail=f"Slave báo lỗi 0x{code:02X}",
            )
        if len(buf) < 5 + buf[2]:
            return ProbeResult(
                ok=False, status="SHORT_FRAME", port=port, address=address,
                detail=f"Khung ngắn: {len(buf)} byte",
            )

        body, rx_crc = buf[:-2], buf[-2] | (buf[-1] << 8)
        if crc16_modbus(body) != rx_crc:
            return ProbeResult(
                ok=False, status="CRC_ERROR", port=port, address=address,
                detail="CRC-16 không hợp lệ",
            )

        # Giải mã để kiểm tra giá trị điện lưới hợp lý
        try:
            metrics = Pzem004T._decode(buf[3:23])
        except PzemError as exc:
            return ProbeResult(
                ok=False, status="DECODE_ERROR", port=port, address=address, detail=str(exc),
            )

        v, f = metrics.voltage or 0.0, metrics.frequency or 0.0
        v_lo, v_hi = PLAUSIBLE_VOLTAGE_V
        f_lo, f_hi = PLAUSIBLE_FREQUENCY_HZ
        if not (v_lo <= v <= v_hi) or not (f_lo <= f <= f_hi):
            return ProbeResult(
                ok=False, status="IMPLAUSIBLE", port=port, address=address,
                detail=f"Giá trị không hợp lý: U={v:.1f}V, f={f:.1f}Hz",
            )

        return ProbeResult(
            ok=True, status="OK", port=port, address=address,
            voltage_v=v, frequency_hz=f,
        )
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            ok=False, status="IO_ERROR", port=port, address=address, detail=str(exc),
        )
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:  # noqa: BLE001
                pass


def classify_open_error(exc: Exception) -> Tuple[str, str]:
    """Phân loại lỗi mở cổng thành mã trạng thái + thông điệp tiếng Việt.

    Phân biệt 3 tình huống rất khác nhau, đã được kiểm chứng trên thực tế:
      - `PORT_BUSY`   → tiến trình khác đang giữ cổng (Access is denied)
      - `PORT_MISSING`→ thiết bị đã bị rút (không tìm thấy file)
      - `IO_ERROR`    → lỗi khác (driver, quyền, phần cứng)
    """
    text = str(exc)
    err = getattr(exc, "errno", None)
    win = getattr(exc, "winerror", None)

    if err == 13 or win == 5 or "Access is denied" in text or "PermissionError" in text:
        return (
            "PORT_BUSY",
            f"Cổng {text.split(':')[0].strip() if ':' in text else ''} đang bị tiến trình "
            "khác chiếm (Access is denied). Đóng serial monitor / PuTTY / PlatformIO "
            "đang dùng cổng này. KHÔNG phải lỗi dây hay nguồn.",
        )
    if err == 2 or win == 2 or "FileNotFoundError" in text or "No such file" in text:
        return (
            "PORT_MISSING",
            "Cổng serial không tồn tại — thiết bị USB-TTL có đang cắm không?",
        )
    return "IO_ERROR", f"Lỗi mở cổng: {text}"


# --------------------------------------------------------------------------- #
# Bộ dò
# --------------------------------------------------------------------------- #
class PortDiscovery:
    """Dò và xác minh PZEM-004T, theo đúng thứ tự ưu tiên đã định nghĩa."""

    def __init__(self, config: AgentConfig, store: Optional[ConfigStore] = None) -> None:
        self.config = config
        self.store = store or ConfigStore()

    # -- ưu tiên địa chỉ -------------------------------------------------- #
    def _priority_addresses(self, exhaustive: bool = False) -> List[int]:
        """Địa chỉ cần thử, theo thứ tự ưu tiên."""
        addrs: List[int] = []
        for a in (self.config.slave_address, 0x01, ADDR_GENERAL):
            if a and ADDR_MIN <= a <= ADDR_MAX and a not in addrs:
                addrs.append(a)
        if exhaustive:
            for a in range(ADDR_MIN, ADDR_MAX + 1):
                if a not in addrs:
                    addrs.append(a)
        return addrs

    # -- bước 1: fast path ------------------------------------------------ #
    def _try_remembered_port(self) -> Optional[ProbeResult]:
        port = self.config.port
        if not port:
            return None

        candidates = {c.port: c for c in list_candidate_ports()}
        if port not in candidates:
            LOG.info("Cổng đã nhớ %s không còn hiện diện", port)
            return None

        LOG.info("Thử fast-path trên cổng đã nhớ %s (địa chỉ 0x%02X)", port, self.config.slave_address)
        result = probe_address(port, self.config.slave_address, self.config.baudrate)
        if result.ok:
            result.location = candidates[port].location
            return result
        LOG.warning("Fast-path trên %s thất bại: %s (%s)", port, result.status, result.detail)
        return result

    # -- bước 2 + 3: quét ứng viên --------------------------------------- #
    def _scan_candidates(self, exhaustive: bool = False) -> Optional[ProbeResult]:
        candidates = list_candidate_ports()
        if not candidates:
            LOG.warning("Không có cổng serial nào trên hệ thống")
            return None

        # Ưu tiên cổng có cùng đường dẫn USB vật lý đã nhớ
        if self.config.usb_location:
            for c in candidates:
                if c.location and c.location == self.config.usb_location:
                    LOG.info(
                        "Ưu tiên cổng %s — khớp đường dẫn USB đã nhớ (%s)",
                        c.port, self.config.usb_location,
                    )
                    candidates.remove(c)
                    candidates.insert(0, c)
                    break

        addrs = self._priority_addresses(exhaustive)
        saw_silent = False
        saw_busy = False

        for cand in candidates:
            LOG.info("Dò cổng %s (hạng %d, %s)", cand.port, cand.tier, cand.description)
            for addr in addrs:
                result = probe_address(cand.port, addr, self.config.baudrate)
                if result.ok:
                    result.location = cand.location
                    return result
                if result.status == "SILENT":
                    saw_silent = True
                elif result.status == "PORT_BUSY":
                    saw_busy = True

        if saw_silent:
            LOG.error(
                "Một cổng mở được nhưng thiết bị im lặng. Nếu cổng đó là USB-TTL "
                "(CH340/CP210x), nguyên nhân gần như chắc chắn là PZEM-004T chưa "
                "được cấp nguồn lưới AC 220V ở chân L/N — module sẽ không trả lời "
                "trên UART cho tới khi có điện lưới."
            )
        if saw_busy:
            LOG.warning("Một cổng đang bị tiến trình khác chiếm — sẽ thử lại sau.")
        return None

    # -- API chính -------------------------------------------------------- #
    def discover(self, exhaustive: bool = False) -> Optional[ProbeResult]:
        """Chạy toàn bộ thang dò. Trả `ProbeResult` nếu tìm thấy PZEM.

        **Không** ghi cấu hình — việc lưu do `remember()` đảm nhiệm, để
        caller kiểm soát được chính sách chống flapping.
        """
        result = self._try_remembered_port()
        if result is not None and result.ok:
            return result

        result = self._scan_candidates(exhaustive=exhaustive)
        if result is not None and result.ok:
            return result

        return result if result is not None else None

    def remember(self, result: ProbeResult) -> None:
        """Ghi lại kết quả dò đã xác minh vào cấu hình và file.

        Chỉ được gọi khi `result.ok` — đây là điểm kiểm soát duy nhất cho
        chính sách chống flapping.
        """
        if not result.ok:
            return
        changed = False
        if self.config.port != result.port:
            self.config.port = result.port
            changed = True
        if result.address is not None and self.config.slave_address != result.address:
            self.config.slave_address = result.address
            changed = True
        if result.location and self.config.usb_location != result.location:
            self.config.usb_location = result.location
            changed = True
        self.config.last_verified_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if changed:
            LOG.info(
                "Ghi nhớ thiết bị: cổng=%s, địa chỉ=0x%02X, USB path=%s",
                self.config.port, self.config.slave_address, self.config.usb_location,
            )
        self.store.save(self.config)


def discover_device(
    config: AgentConfig,
    store: Optional[ConfigStore] = None,
    exhaustive: bool = False,
) -> Tuple[Optional[ProbeResult], AgentConfig]:
    """Tiện ích cấp cao: dò + (nếu thành công) ghi nhớ, trả về cả hai."""
    discovery = PortDiscovery(config, store)
    result = discovery.discover(exhaustive=exhaustive)
    if result is not None and result.ok:
        discovery.remember(result)
        config = discovery.config
    return result, config
