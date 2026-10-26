"""Kiem chung CRC + giai ma frame that tu PZEM-004T that tren COM10."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pzem004t import Pzem004T, crc16_modbus  # noqa: E402

RESPONSE = bytes([
    0x01, 0x04, 0x14,              # addr, func, byte count = 20
    0x09, 0x22,                    # 0x0000 dien ap
    0x00, 0x4B, 0x00, 0x00,        # 0x0001-0x0002 dong dien
    0x00, 0x61, 0x00, 0x00,        # 0x0003-0x0004 cong suat
    0x00, 0x02, 0x00, 0x00,        # 0x0005-0x0006 dien nang
    0x01, 0xF5,                    # 0x0007 tan so
    0x00, 0x37,                    # 0x0008 he so cong suat
    0x00, 0x00,                    # 0x0009 canh bao
    0x5B, 0xCB,                    # CRC
])

REQUEST = bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x0A, 0x70, 0x0D])


def main():
    # --- Kiem tra CRC cua frame nhan duoc ---
    body = RESPONSE[:-2]
    rx_crc = RESPONSE[-2] | (RESPONSE[-1] << 8)
    calc = crc16_modbus(body)
    print(f"CRC nhan duoc : 0x{rx_crc:04X}")
    print(f"CRC tinh toan : 0x{calc:04X}")
    assert calc == rx_crc, "CRC KHONG KHOP"
    print("OK  CRC phan hoi hop le")

    # --- Kiem tra CRC frame yeu cau ---
    req_crc = crc16_modbus(REQUEST[:-2])
    assert REQUEST == bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x0A,
                             req_crc & 0xFF, req_crc >> 8])
    print(f"OK  CRC frame yeu cau hop tai lieu: "
          f"{' '.join(f'{b:02X}' for b in REQUEST)}")

    # --- Giai ma ---
    m = Pzem004T._decode(RESPONSE[3:23])
    print()
    print("Gia tri do duoc:")
    print(f"  Dien ap       : {m.voltage} V")
    print(f"  Dong dien     : {m.current} A")
    print(f"  Cong suat     : {m.power} W")
    print(f"  Dien nang     : {m.energy} Wh ({m.energy_kwh} kWh)")
    print(f"  Tan so        : {m.frequency} Hz")
    print(f"  He so CS      : {m.power_factor}")
    print(f"  Canh bao      : 0x{m.alarm:04X} "
          f"({'BANG' if m.alarm == 0xFFFF else 'binh thuong'})")
    print()
    # Kiem tra nhan doi: P = V * I * PF
    expected = m.voltage * m.current * m.power_factor
    print(f"Kiem tra P = V x I x PF = {m.voltage} x {m.current} x "
          f"{m.power_factor} = {expected:.2f} W (do duoc {m.power} W)")


if __name__ == "__main__":
    main()
