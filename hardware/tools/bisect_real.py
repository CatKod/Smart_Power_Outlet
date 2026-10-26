"""Bisect the REAL generated schematic: remove sections one at a time to
find what kicad-cli refuses to parse."""
import re
import subprocess

KICAD = r"D:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
SRC = r"D:\GitHub\Smart_Power_Outlet\hardware\smart_outlet\smart_outlet.kicad_sch"
OUT = r"C:\Users\kimvi\AppData\Local\Temp\real_bisect.kicad_sch"
RPT = r"C:\Users\kimvi\AppData\Local\Temp\real_bisect_erc.json"

with open(SRC, "r", encoding="utf-8") as fh:
    full = fh.read()


def try_load(name, text):
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    r = subprocess.run([KICAD, "sch", "erc", OUT, "--format", "json",
                        "--output", RPT], capture_output=True, errors="replace")
    err = r.stderr or ""
    loaded = "Không thể tải" not in err
    print(f"{name:<42} rc={r.returncode} load={'OK ' if loaded else 'FAIL'}")
    return loaded


def strip_symbols(text, keep_pred):
    """Remove (symbol ...) instance blocks whose lib_id matches."""
    out = []
    i = 0
    while True:
        m = re.search(r'\t\(symbol\n\t\t\(lib_id "([^"]+)"', text[i:])
        if not m:
            out.append(text[i:])
            break
        # find end of this symbol block (balanced parens from the (symbol)
        start = i + m.start()
        depth = 0
        j = start
        in_str = False
        n = len(text)
        while j < n:
            c = text[j]
            if in_str:
                if c == "\\":
                    j += 2
                    continue
                if c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append(text[i:start])
        if keep_pred(m.group(1)):
            out.append(text[start:j+1])
        i = j + 1
    return "".join(out)


def strip_wires(text):
    text = re.sub(r'\t\(wire .*?\)\n', '', text, flags=re.S)
    return text


def strip_labels(text):
    text = re.sub(r'\t\(label ".*?\)\n', '', text, flags=re.S)
    return text


def strip_title(text):
    return re.sub(r'\t\(title_block.*?\)\n', '', text, flags=re.S)


# baseline
try_load("FULL", full)
# remove all labels
try_load("no labels", strip_labels(full))
# remove all wires
try_load("no wires", strip_wires(full))
# remove title block
try_load("no title", strip_title(full))
# keep only non-power symbols
try_load("no power symbols", strip_symbols(full, lambda l: not l.startswith("power:")))
# keep only power symbols
try_load("only power symbols", strip_symbols(full, lambda l: l.startswith("power:")))