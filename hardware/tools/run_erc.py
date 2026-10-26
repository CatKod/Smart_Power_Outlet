"""ERC check on the current generated schematic."""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KICAD = r"D:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
SCH = r"D:\GitHub\Smart_Power_Outlet\hardware\smart_outlet\smart_outlet.kicad_sch"
RPT = r"D:\GitHub\Smart_Power_Outlet\hardware\smart_outlet\erc.json"

if os.path.exists(RPT):
    os.remove(RPT)

r = subprocess.run([KICAD, "sch", "erc", SCH, "--format", "json",
                    "--output", RPT], capture_output=True)
err = r.stderr.decode("utf-8", "replace").strip()
print(f"rc={r.returncode}")
print(f"stderr={err!r}")
if os.path.exists(RPT):
    import json
    with open(RPT, encoding="utf-8") as fh:
        data = json.load(fh)
    print(f"sheets: {data.get('sheets')}")
    print(f"total violations: {data.get('total_violations')}")
    print(f"unconnected: {data.get('unconnected_items')}")
    print(f"excluded: {data.get('excluded')}")
    for v in data.get("violations", []):
        print(f"  [{v.get('severity')}] {v.get('description')}")
else:
    print("no ERC report produced")
