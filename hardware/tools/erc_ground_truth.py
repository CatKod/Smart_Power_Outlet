"""Ground-truth ERC loader test with byte-level stderr capture."""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KICAD = r"D:\Program Files\KiCad\10.0\bin\kicad-cli.exe"


def erc(label, path):
    for suffix in (".json", ".rpt"):
        try:
            os.remove(path + suffix)
        except OSError:
            pass
    r = subprocess.run(
        [KICAD, "sch", "erc", path, "--format", "json",
         "--output", path + ".json"],
        capture_output=True)
    err = r.stderr.decode("utf-8", "replace").strip()
    has_report = os.path.exists(path + ".json")
    loaded = "không thể tải" not in err.lower()
    print(f"{label:22} rc={r.returncode} load={'OK ' if loaded else 'FAIL'} "
          f"report={has_report} err={err!r}")


erc("demo", r"C:\Users\kimvi\AppData\Local\Temp\demo_copy.kicad_sch")
erc("t1(original)", r"C:\Users\kimvi\AppData\Local\Temp\ktest\t1.kicad_sch")
erc("bisect(empty)", r"C:\Users\kimvi\AppData\Local\Temp\bisect_test.kicad_sch")
erc("min_test", r"C:\Users\kimvi\AppData\Local\Temp\min_test.kicad_sch")
