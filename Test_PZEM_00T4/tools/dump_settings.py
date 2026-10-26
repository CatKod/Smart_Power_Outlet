"""Doc raw thanh ghi holding (func 0x03) cua PZEM de xac dinh vi tri that su."""

import os
import sys
import time

import serial

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pzem004t import (  # noqa: E402
    CMD_READ_HOLDING, PZEM_DEFAULT_ADDRESS, build_read_frame, crc16_modbus,
)


def hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def read_regs(sp, address, start, count):
    req = build_read_frame(address, CMD_READ_HOLDING, start, count)
    sp.reset_input_buffer()
    sp.write(req)
    sp.flush()
    time.sleep(0.3)
    resp = sp.read(64)
    ok = False
    if resp and len(resp) >= 5:
        body = resp[:-2]
        rx = resp[-2] | (resp[-1] << 8)
        ok = crc16_modbus(body) == rx
    print(f"  reg 0x{start:04X} x{count}: RX {hx(resp)}  crc_ok={ok}")
    if ok and len(resp) >= 5 + resp[2]:
        data = resp[3:3 + resp[2]]
        regs = []
        for i in range(0, len(data) - 1, 2):
            regs.append((data[i] << 8) | data[i + 1])
        print(f"      raw regs: " + ", ".join(f"0x{r:04X} ({r})" for r in regs))
    return resp


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
    address = int(sys.argv[2], 0) if len(sys.argv) > 2 else PZEM_DEFAULT_ADDRESS

    with serial.Serial(port, 9600, timeout=0.5, write_timeout=1.0) as sp:
        print(f"Port {port}, slave 0x{address:02X}")
        print("--- Doc 4 thanh ghi holding tu 0x0000 ---")
        read_regs(sp, address, 0x0000, 0x0004)
        print("--- Doc 1 thanh ghi tai 0x0001 (nguong canh bao) ---")
        read_regs(sp, address, 0x0001, 0x0001)
        print("--- Doc 1 thanh ghi tai 0x0002 (dia chi slave) ---")
        read_regs(sp, address, 0x0002, 0x0001)
        print("--- Doc 2 thanh ghi tu 0x0001 ---")
        read_regs(sp, address, 0x0001, 0x0002)


if __name__ == "__main__":
    main()
