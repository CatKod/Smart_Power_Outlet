"""So sanh cac bien the CRC de tim dung quy uoc cua PZEM-004T.

Frame mau trong tai lieu:  01 04 00 00 00 0A 70 0D
=> CRC value = 0x0D70 (Low byte 0x70 gui truoc, High byte 0x0D gui sau)
"""

FRAME_BODY = bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x0A])
TARGET = 0x0D70


def crc_modbus(data: bytes, init: int = 0xFFFF) -> int:
    """CRC-16 Modbus: poly 0xA001 reflected, init 0xFFFF."""
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def crc_generic(data: bytes, poly: int, init: int, refin: bool, refout: bool, xorout: int) -> int:
    """CRC generic voi tham so hoa bien."""

    def reflect(value: bytes, width: int) -> int:
        out = 0
        for i in range(width):
            if value[i // 8] & (1 << (i % 8)):
                out |= 1 << (width - 1 - i)
        return out

    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    if refout:
        crc = reflect(crc.to_bytes(2, "big"), 16)
    return (crc ^ xorout) & 0xFFFF


CANDIDATES = {
    "Modbus (init=0xFFFF)": lambda d: crc_modbus(d, 0xFFFF),
    "ARC/IBM (init=0x0000)": lambda d: crc_modbus(d, 0x0000),
    "XMODEM (init=0x0000,poly=0x1021)": lambda d: crc_generic(d, 0x1021, 0x0000, False, False, 0x0000),
    "CCITT-FALSE (init=0xFFFF,poly=0x1021)": lambda d: crc_generic(d, 0x1021, 0xFFFF, False, False, 0x0000),
    "KERMIT (poly=0x1021,refin/refout)": lambda d: crc_generic(d, 0x1021, 0x0000, True, True, 0x0000),
    "MODBUS init=0xFFFF xorout=0xFFFF": lambda d: crc_modbus(d, 0xFFFF) ^ 0xFFFF,
}


def main():
    print(f"Target CRC tu tai lieu: 0x{TARGET:04X}")
    print(f"Frame body: {' '.join(f'{b:02X}' for b in FRAME_BODY)}\n")

    for name, fn in CANDIDATES.items():
        value = fn(FRAME_BODY)
        lo, hi = value & 0xFF, value >> 8
        match = "   <== KHOP VOI TAI LIEU" if value == TARGET else ""
        frame = FRAME_BODY + bytes([lo, hi])
        alt = FRAME_BODY + bytes([hi, lo])
        print(f"{name:40s} = 0x{value:04X}")
        print(f"{'':40s}  lo/hi: {' '.join(f'{b:02X}' for b in frame)}{match}")
        print(f"{'':40s}  hi/lo: {' '.join(f'{b:02X}' for b in alt)}")

    print("\nFrame tai lieu   : 01 04 00 00 00 0A 70 0D")


if __name__ == "__main__":
    main()
