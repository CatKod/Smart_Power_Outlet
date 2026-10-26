"""Progressive single-symbol test: add one element type at a time."""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KICAD = r"D:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
PATH = r"C:\Users\kimvi\AppData\Local\Temp\prog.kicad_sch"
ROOT = "11111111-1111-1111-1111-111111111111"

HEADER = (
    "(kicad_sch\n"
    "\t(version 20250114)\n"
    '\t(generator "eeschema")\n'
    '\t(generator_version "8.0")\n'
    f'\t(uuid "{ROOT}")\n'
    '\t(paper "A4")\n'
)
FOOTER = (
    "\t(sheet_instances\n"
    '\t\t(path "/" (page "1"))\n'
    "\t)\n"
    ")\n"
)

SYMBOL = (
    "\t(symbol\n"
    '\t\t(lib_id "Device:R")\n'
    "\t\t(at 100 100 0)\n"
    "\t\t(unit 1)\n"
    "\t\t(exclude_from_sim no)\n"
    "\t\t(in_bom yes)\n"
    "\t\t(on_board yes)\n"
    "\t\t(dnp no)\n"
    '\t\t(uuid "22222222-2222-2222-2222-222222222222")\n'
    '\t\t(property "Reference" "R1" (at 100 100 0)\n'
    "\t\t\t(effects (font (size 1.27 1.27))))\n"
    '\t\t(property "Value" "1k" (at 100 97.46 0)\n'
    "\t\t\t(effects (font (size 1.27 1.27))))\n"
    '\t\t(pin "1" (uuid "33333333-3333-3333-3333-333333333333"))\n'
    '\t\t(pin "2" (uuid "44444444-4444-4444-4444-444444444444"))\n'
    "\t\t(instances\n"
    '\t\t\t(project "t"\n'
    f'\t\t\t\t(path "/{ROOT}"\n'
    '\t\t\t\t\t(reference "R1") (unit 1)\n'
    "\t\t\t\t)\n"
    "\t\t\t)\n"
    "\t\t)\n"
    "\t)\n"
)


def run(name, body):
    with open(PATH, "w", encoding="utf-8") as fh:
        fh.write(HEADER + body + FOOTER)
    out = PATH + ".json"
    try:
        os.remove(out)
    except OSError:
        pass
    r = subprocess.run([KICAD, "sch", "erc", PATH, "--format", "json",
                        "--output", out], capture_output=True)
    err = r.stderr.decode("utf-8", "replace").strip()
    loaded = "không thể tải" not in err.lower()
    print(f"{name:32} rc={r.returncode} load={'OK ' if loaded else 'FAIL'}")


run("symbol only (no lib_symbols)", SYMBOL)
run("symbol twice", SYMBOL + SYMBOL)
