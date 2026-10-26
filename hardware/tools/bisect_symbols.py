"""Find which embedded symbol makes kicad-cli refuse to load the schematic."""
import subprocess
import sys

sys.path.insert(0, r"d:\GitHub\Smart_Power_Outlet\hardware\tools")
from gen_schematic import (embed_symbol, load_symbol, COMPONENTS,
                           _u, _f, symbol_pins)

KICAD = r"D:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
OUT = r"C:\Users\kimvi\AppData\Local\Temp\sym_test.kicad_sch"
RPT = r"C:\Users\kimvi\AppData\Local\Temp\sym_test_erc.json"
ROOT_UUID = "6b6b6b6b-6b6b-6b6b-6b6b-6b6b6b6b6b6b"


def try_symbol(lib, sym, name, rot=0, x=100, y=100):
    block = embed_symbol(lib, sym, lib)
    pins = symbol_pins(lib, sym)
    pin_list = "\n".join(
        f'\t\t(pin "{n}" (uuid "{_u()}"))' for n in sorted(pins))
    text = (
        "(kicad_sch\n"
        '\t(version 20250114)\n'
        '\t(generator "eeschema")\n'
        '\t(generator_version "8.0")\n'
        f'\t(uuid "{ROOT_UUID}")\n'
        '\t(paper "A4")\n'
        '\t(lib_symbols\n\t\t' + block + '\n\t)\n'
        '\t(symbol\n'
        f'\t\t(lib_id "{lib}:{sym}")\n'
        f'\t\t(at {_f(x)} {_f(y)} {rot})\n'
        '\t\t(unit 1)\n'
        '\t\t(exclude_from_sim no)\n'
        '\t\t(in_bom yes)\n'
        '\t\t(on_board yes)\n'
        '\t\t(dnp no)\n'
        f'\t\t(uuid "{_u()}")\n'
        '\t\t(property "Reference" "X1" (at 100 90 0)\n'
        '\t\t\t(effects (font (size 1.27 1.27))))\n'
        '\t\t(property "Value" "V" (at 100 87 0)\n'
        '\t\t\t(effects (font (size 1.27 1.27))))\n'
        + pin_list + "\n"
        '\t\t(instances\n'
        '\t\t\t(project "t"\n'
        f'\t\t\t\t(path "/{ROOT_UUID}"\n'
        '\t\t\t\t\t(reference "X1") (unit 1)\n'
        '\t\t\t\t)\n'
        '\t\t\t)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(sheet_instances\n'
        '\t\t(path "/" (page "1"))\n'
        '\t)\n'
        ')\n'
    )
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    r = subprocess.run([KICAD, "sch", "erc", OUT, "--format", "json",
                        "--output", RPT], capture_output=True, errors="replace")
    ok = "Không thể tải" not in (r.stderr or "")
    print(f"{name:<42} {'OK ' if ok else 'FAIL'} rc={r.returncode}")
    return ok


tests = [
    ("Connector_Generic", "Conn_01x02", "J1"),
    ("Connector_Generic", "Conn_01x06", "J3"),
    ("Device", "Fuse", "F1"),
    ("Device", "Varistor", "RV1"),
    ("Converter_ACDC", "HLK-PM01", "U1"),
    ("Device", "C", "C1"),
    ("Regulator_Linear", "AMS1117-3.3", "U2"),
    ("Relay", "SANYOU_SRD_Form_A", "K1"),
    ("Device", "D", "D5"),
    ("Transistor_FET", "AO3400A", "Q1"),
    ("Device", "R", "R1"),
    ("Device", "LED", "D6"),
    ("Switch", "SW_Push", "SW1"),
    ("power", "GND", "GND"),
    ("power", "+5V", "+5V"),
    ("power", "+3V3", "+3V3"),
    ("power", "PWR_FLAG", "PWR_FLAG"),
]

failed = []
for lib, sym, name in tests:
    if not try_symbol(lib, sym, name):
        failed.append((lib, sym))

print("\nFAILED:", failed if failed else "none")