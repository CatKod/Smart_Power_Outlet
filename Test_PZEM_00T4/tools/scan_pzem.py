"""Scan PZEM-004T: thử mọi tổ hợp địa chỉ slave x function code x baud."""
import os
import sys
import time

import serial

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pzem004t import CMD_READ_HOLDING, CMD_READ_INPUT, build_read_frame

ADDRESSES = (0x01, 0x02, 0x03, 0x10, 0xF7, 0xF8, 0xFE, 0xFF)
FUNCTIONS = (CMD_READ_INPUT, CMD_READ_HOLDING)


def hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
    bauds = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [9600]

    for baud in bauds:
        try:
            sp = serial.Serial(port, baud, timeout=0.15, write_timeout=0.5)
        except Exception as exc:  # noqa: BLE001
            print(f"open {port}@{baud} failed: {exc}")
            return
        with sp:
            print(f"--- baud {baud} ---")
            for address in ADDRESSES:
                for function in FUNCTIONS:
                    req = build_read_frame(address, function, 0x0000, 0x000A)
                    sp.reset_input_buffer()
                    sp.write(req)
                    sp.flush()
                    time.sleep(0.22)
                    resp = sp.read(64)
                    if resp:
                        print(f"  HIT addr=0x{address:02X} func=0x{function:02X}")
                        print(f"     TX {hx(req)}")
                        print(f"     RX {hx(resp)}")
                        return
    print("NO RESPONSE")


if __name__ == "__main__":
    main()
