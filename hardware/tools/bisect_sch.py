"""Bisect the minimal schematic: progressively strip parts to find what
kicad-cli refuses to load."""
import subprocess
import sys

KICAD = r"D:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
OUT = r"C:\Users\kimvi\AppData\Local\Temp\bisect_test.kicad_sch"


def try_load(name, text):
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    rpt = r"C:\Users\kimvi\AppData\Local\Temp\bisect_erc.json"
    r = subprocess.run([KICAD, "sch", "erc", OUT, "--format", "json",
                        "--output", rpt], capture_output=True,
                       errors="replace", text=True)
    ok = "Không thể tải" not in (r.stderr or "")
    print(f"{name:<40} rc={r.returncode} load={'OK' if ok else 'FAIL'}")
    return ok


BASE = """(kicad_sch
\t(version 20250114)
\t(generator "eeschema")
\t(generator_version "8.0")
\t(uuid "6b6b6b6b-6b6b-6b6b-6b6b-6b6b6b6b6b6b")
\t(paper "A4")
{body}
\t(sheet_instances
\t\t(path "/" (page "1"))
\t)
)
"""

# 1. empty schematic
try_load("empty", BASE.format(body=""))

# 2. empty lib_symbols
try_load("empty lib_symbols", BASE.format(body='\t(lib_symbols\n\t)'))

# 3. simple wire only
wire = '''\t(wire (pts (xy 50 50) (xy 60 50))
\t\t(stroke (width 0) (type default))
\t\t(uuid "11111111-1111-1111-1111-111111111111")
\t)'''
try_load("wire only", BASE.format(body=wire))

# 4. label only
label = '''\t(label "NET1"
\t\t(at 60 50 0)
\t\t(effects (font (size 1.27 1.27)) (justify left bottom))
\t\t(uuid "22222222-2222-2222-2222-222222222222")
\t)'''
try_load("wire+label", BASE.format(body=wire + "\n" + label))

# 5. minimal symbol instance referencing a lib symbol (no lib_symbols block)
sym = '''\t(symbol
\t\t(lib_id "Device:R")
\t\t(at 100 100 0)
\t\t(unit 1)
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(dnp no)
\t\t(uuid "33333333-3333-3333-3333-333333333333")
\t\t(property "Reference" "R1" (at 100 100 0)
\t\t\t(effects (font (size 1.27 1.27))))
\t\t(property "Value" "1k" (at 100 100 0)
\t\t\t(effects (font (size 1.27 1.27))))
\t\t(pin "1" (uuid "44444444-4444-4444-4444-444444444444"))
\t\t(pin "2" (uuid "55555555-5555-5555-5555-555555555555"))
\t\t(instances
\t\t\t(project "bisect"
\t\t\t\t(path "/6b6b6b6b-6b6b-6b6b-6b6b-6b6b6b6b6b6b"
\t\t\t\t\t(reference "R1") (unit 1)
\t\t\t\t)
\t\t\t)
\t\t)
\t)'''
try_load("symbol w/o lib_symbols", BASE.format(body=sym))

# 6. with embedded lib_symbols (sanitized Device:R)
import sys
sys.path.insert(0, r"d:\GitHub\Smart_Power_Outlet\hardware\tools")
from gen_schematic import embed_symbol
libs = '\t(lib_symbols\n\t\t' + embed_symbol("Device", "R", "Device") + '\n\t)'
try_load("symbol + lib_symbols", BASE.format(body=libs + "\n" + sym))

# 7. raw (unsanitized) lib_symbols to confirm the sanitizer was the issue
from gen_schematic import load_symbol
raw = '\t(lib_symbols\n\t\t' + load_symbol("Device", "R") + '\n\t)'
try_load("symbol + raw lib_symbols", BASE.format(body=raw + "\n" + sym))
