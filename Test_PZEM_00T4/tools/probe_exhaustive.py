"""Phep thu cuoi: baud x parity x dia chi x func, kem delay 3.5 char truoc khi gui."""
import os
import sys
import time

import serial

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pzem004t import CMD_READ_HOLDING, CMD_READ_INPUT, build_read_frame

BAUDS = (9600, 4800, 19200, 115200, 2400, 1200)
ADDRESSES = (0x01, 0x02, 0x03, 0x05, 0x10, 0xF7, 0xF8, 0xFE, 0xFF)
FUNCTIONS = (CMD_READ_INPUT, CMD_READ_HOLDING)
CONFIGS = (
    ("8N1", serial.EIGHTBITS, serial.PARITY_NONE, serial.STOPBITS_ONE),
    ("8N2", serial.EIGHTBITS, serial.PARITY_NONE, serial.STOPBITS_TWO),
    ("8E1", serial.EIGHTBITS, serial.PARITY_EVEN, serial.STOPBITS_ONE),
    ("8O1", serial.EIGHTBITS, serial.PARITY_ODD, serial.STOPBITS_ONE),
)


def hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def try_read(sp, address, function, char_time):
    """Gui frame doc, cho dung 3.5 char truoc, doc phan hoi."""
    sp.reset_input_buffer()
    time.sleep(char_time * 3.5)
    sp.write(build_read_frame(address, function, 0x0000, 0x000A))
    sp.flush()
    time.sleep(char_time * 20)
    return sp.read(64)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM10"

    for baud in BAUDS:
        char_time = 1.0 / baud
        for cfg_name, bitsize, parity, stopbits in CONFIGS:
            try:
                sp = serial.Serial(
                    port, baud, bytesize=bitsize, parity=parity, stopbits=stopbits,
                    timeout=0.2, write_timeout=0.5, dsrdtr=False, rtscts=False,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"open failed: {exc}")
                return
            with sp:
                for address in ADDRESSES:
                    for function in FUNCTIONS:
                        resp = try_read(sp, address, function, char_time)
                        if resp:
                            print(f"\n*** HIT baud={baud} cfg={cfg_name} "
                                  f"addr=0x{address:02X} func=0x{function:02X}")
                            print(f"    RX {hx(resp)}")
                            return
                print(f"  miss baud={baud} {cfg_name}")
    print("\nNO RESPONSE - van de o tang giao tiep vat / dau / nguon 5V")


if __name__ == "__main__":
    main()
