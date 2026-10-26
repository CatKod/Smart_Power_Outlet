"""Kiem chung viec giai ma thanh ghi PZEM-004T bang frame vi du trong tai lieu.

Frame vi du (muc 2.3 tai lieu):
  Master -> Slave : 01 04 00 00 00 0A 70 0D
  Slave -> Master : 01 04 14 08 98 03 E8 00 00 08 98 00 00 00 00 00 00
                     00 01 F4 00 64 00 00 [CRC_H] [CRC_L]

Gia tri mong doi:
  Voltage  = 0x0898 = 2200 -> 220.0 V
  Current  = 0x000003E8 = 1000 -> 1.000 A
  Power    = 0x00000898 = 2200 -> 220.0 W
  Energy   = 0x00000000 = 0 -> 0 Wh
  Freq     = 0x01F4 = 500 -> 50.0 Hz
  PF       = 0x0064 = 100 -> 1.00
  Alarm    = 0x0000 -> binh thuong
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pzem004t import Pzem004T, crc16_modbus  # noqa: E402

EXAMPLE_DATA = bytes([
    0x08, 0x98, 0x03, 0xE8, 0x00, 0x00, 0x08, 0x98, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x01, 0xF4, 0x00, 0x64, 0x00, 0x00,
])

EXPECTED = {
    "voltage": 220.0,
    "current": 1.0,
    "power": 220.0,
    "energy": 0.0,
    "frequency": 50.0,
    "power_factor": 1.0,
    "alarm": 0,
}


def test_crc_matches_doc():
    """CRC cua frame mau trong tai lieu phai la 0x0D70 (byte thap gui truoc)."""
    body = bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x0A])
    crc = crc16_modbus(body)
    assert crc == 0x0D70, f"CRC khong khop: 0x{crc:04X} != 0x0D70"
    frame = body + bytes([crc & 0xFF, crc >> 8])
    assert frame == bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x0A, 0x70, 0x0D]), frame.hex()
    print("OK  CRC frame mau khop tai lieu: " + " ".join(f"{b:02X}" for b in frame))


def test_decode_example():
    """Giai ma 20 byte du lieu cua frame vi du va doi chieu gia tri mong doi."""
    m = Pzem004T._decode(EXAMPLE_DATA)
    for key, expected in EXPECTED.items():
        actual = getattr(m, key)
        assert abs(actual - expected) < 1e-6, f"{key}: {actual} != {expected}"
        print(f"OK  {key:14s} = {actual}")
    assert m.energy_kwh == 0.0, m.energy_kwh
    print(f"OK  {'energy_kwh':14s} = {m.energy_kwh}")


def test_decode_realistic():
    """Kiem tra voi gia tri thuc te: 220.5 V, 1.234 A, 271.4 W, 1500 Wh."""
    # current 32 bit = 1234 -> 0x000004D2
    data = bytearray(20)
    data[0:2] = (2205).to_bytes(2, "big")          # 220.5 V
    data[2:4] = (1234 & 0xFFFF).to_bytes(2, "big")  # current low
    data[4:6] = (1234 >> 16).to_bytes(2, "big")     # current high
    data[6:8] = (2714 & 0xFFFF).to_bytes(2, "big")  # power low
    data[8:10] = (2714 >> 16).to_bytes(2, "big")    # power high
    data[10:12] = (1500 & 0xFFFF).to_bytes(2, "big")  # energy low
    data[12:14] = (1500 >> 16).to_bytes(2, "big")   # energy high
    data[14:16] = (500).to_bytes(2, "big")          # 50.0 Hz
    data[16:18] = (95).to_bytes(2, "big")           # PF 0.95
    data[18:20] = (0xFFFF).to_bytes(2, "big")       # alarm active

    m = Pzem004T._decode(bytes(data))
    assert abs(m.voltage - 220.5) < 1e-6, m.voltage
    assert abs(m.current - 1.234) < 1e-6, m.current
    assert abs(m.power - 271.4) < 1e-6, m.power
    assert m.energy == 1500, m.energy
    assert abs(m.energy_kwh - 1.5) < 1e-6, m.energy_kwh
    assert abs(m.frequency - 50.0) < 1e-6, m.frequency
    assert abs(m.power_factor - 0.95) < 1e-6, m.power_factor
    assert m.alarm == 0xFFFF, m.alarm
    print(f"OK  gia tri thuc te: {m.voltage} V, {m.current} A, {m.power} W, "
          f"{m.energy} Wh, {m.frequency} Hz, PF {m.power_factor}, alarm 0x{m.alarm:04X}")


def test_decode_no_load():
    """Khi chua co tai, PZEM tra gia tri sentinel 0xFFFF -> phai hien thi 0."""
    data = bytearray(20)
    for i in range(0, 20, 2):
        data[i:i + 2] = b"\xFF\xFF"
    m = Pzem004T._decode(bytes(data))
    assert m.voltage == 0.0, m.voltage
    assert m.current == 0.0, m.current
    assert m.power == 0.0, m.power
    assert m.energy == 0, m.energy
    assert m.frequency == 0.0, m.frequency
    assert m.power_factor == 0.0, m.power_factor
    assert m.alarm == 0xFFFF, f"alarm 0xFFFF = dang bao dong, khong phai gia tri invalid: {m.alarm}"
    print(f"OK  chua co tai (sentinel 0xFFFF): {m.voltage} V, {m.current} A, "
          f"{m.power} W, {m.energy} Wh, {m.frequency} Hz, PF {m.power_factor}")
    print(f"OK  alarm 0xFFFF giu nguyen nghia 'dang bao dong'")


if __name__ == "__main__":
    test_crc_matches_doc()
    test_decode_example()
    test_decode_realistic()
    test_decode_no_load()
    print("\nTAT CA KIEM THU PASS")
