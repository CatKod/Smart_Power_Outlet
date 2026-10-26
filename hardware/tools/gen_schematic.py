#!/usr/bin/env python3
"""Generate a KiCad 10 schematic for the Smart Power Outlet carrier board.

Usage:  python gen_schematic.py [output_dir]

Reads symbol definitions directly from the KiCad 10 standard library so pin
positions always match, then emits a self-contained .kicad_sch plus a minimal
.kicad_pro. Connectivity is done with per-pin wire stubs + local labels, which
ERC resolves into nets without long routed wires.

Coordinate conventions (verified against KiCad 10):
  - symbol libraries use Y-UP, schematic files use Y-DOWN
  - (at x y rot) rotation is counter-clockwise as displayed
"""

import math
import os
import re
import sys
import uuid

KICAD_SHARE = r"D:\Program Files\KiCad\10.0\share\kicad"
SYM_DIR = os.path.join(KICAD_SHARE, "symbols")
PROJECT_NAME = "smart_outlet"

STUB = 2.54          # wire stub length from each pin (mm)
FONT = (1.27, 1.27)


def _u():
    return str(uuid.uuid4())


def _f(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


# ----------------------------------------------------------------------------
# Minimal s-expression parsing of the KiCad symbol libraries
# ----------------------------------------------------------------------------

def find_block(text, start):
    """Return (start, end) indices of the balanced paren block beginning at
    text[start] == '(', ignoring parens inside double-quoted strings."""
    depth = 0
    i = start
    in_str = False
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
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
                return start, i + 1
        i += 1
    raise ValueError("unbalanced block")


def load_symbol(libfile, symname):
    """Return raw s-expr text of symbol <symname> from <libfile>."""
    path = os.path.join(SYM_DIR, libfile + ".kicad_sym")
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    marker = f'(symbol "{symname}"'
    idx = 0
    while True:
        idx = text.find(marker, idx)
        if idx < 0:
            raise KeyError(f"{libfile}:{symname} not found")
        # ensure it is a top-level-ish definition, i.e. preceded by whitespace
        prev = text[idx - 1]
        if prev not in " \t\r\n(":
            idx += 1
            continue
        s, e = find_block(text, idx)
        return text[s:e]


def extends_base(libfile, symname):
    """If the library symbol derives from another via (extends ...), return
    the base symbol's name, else None."""
    block = load_symbol(libfile, symname)
    m = re.search(r'\(extends "([^"]+)"\)', block)
    return m.group(1) if m else None


# Token pairs that exist only in KiCad 10 .kicad_sym library files and are
# rejected by the schematic (20250114) parser - must be stripped when embedding.
LIB_ONLY_KEYWORDS = [
    "show_name",
    "do_not_autoplace",
    "in_pos_files",
    "duplicate_pin_numbers_are_jumpers",
]


def sanitize_lib_symbol(block):
    """Rewrite a KiCad 10 library symbol into schematic-compatible form.

    - drop library-only keywords
    - move property-level (hide yes) inside the following (effects ...) block
      (schematic format only accepts hide inside effects for properties)
    """
    for kw in LIB_ONLY_KEYWORDS:
        block = re.sub(r'\(\s*' + kw + r'\s+(?:yes|no)\s*\)', '', block)

    out = []
    i = 0
    tok = "(hide yes)"
    while True:
        idx = block.find(tok, i)
        if idx < 0:
            out.append(block[i:])
            break
        rest_start = idx + len(tok)
        m = re.match(r'\s*\(effects', block[rest_start:])
        if not m:
            # pin-level or nested hide - valid as-is
            out.append(block[i:rest_start])
            i = rest_start
            continue
        out.append(block[i:idx])
        eff_start = rest_start + m.end() - len("(effects")
        s, e = find_block(block, eff_start)
        eff_text = block[s:e]
        closing = eff_text.rfind(")")
        out.append(eff_text[:closing].rstrip() + " (hide yes))")
        i = e
    return "".join(out)


def embed_symbol(libfile, symname, libname):
    """Return a flattened, self-contained definition for <libname>:<symname>.

    Symbols that (extends ...) a base carry no pins of their own, so the base
    definition is loaded and renamed - this matches what KiCad itself writes
    into a schematic's lib_symbols cache. Sub-symbols keep their plain name
    (no lib prefix), e.g. "R_0_1", as KiCad does in real schematic files."""
    srcname = extends_base(libfile, symname) or symname
    block = load_symbol(libfile, srcname)
    # top-level symbol gets the lib prefix
    block = re.sub(
        r'\(symbol "' + re.escape(srcname) + '"',
        '(symbol "' + f"{libname}:{symname}" + '"',
        block,
        count=1,
    )
    # sub-symbols (<name>_<unit>_<variant>) keep plain names, renamed to
    # the derived symbol so unit lookup matches the lib_id used by instances
    block = re.sub(
        r'\(symbol "' + re.escape(srcname) + r'(_\d+_\d+)"',
        lambda m: '(symbol "' + symname + m.group(1) + '"',
        block,
    )
    return sanitize_lib_symbol(block)


def symbol_pins(libfile, symname):
    """Return {pin_number: (x, y, angle, electrical_type)} in symbol coords
    (Y-UP library frame), resolving (extends ...) to the base symbol."""
    base = extends_base(libfile, symname)
    block = load_symbol(libfile, base) if base else load_symbol(libfile, symname)
    pins = {}
    for m in re.finditer(
            r'\(pin (\w+) (\w+)\s*\(at (-?[\d.]+) (-?[\d.]+) (-?\d+)\)', block):
        etype, _shape, x, y, ang = m.groups()
        x, y, ang = float(x), float(y), int(ang)
        # find the pin number within this pin block
        s, e = find_block(block, m.start())
        pin_text = block[s:e]
        nm = re.search(r'\(number "([^"]*)"', pin_text)
        if nm:
            pins[nm.group(1)] = (x, y, ang, etype)
    return pins


def rotate(px, py, rot):
    """Map a symbol-relative pin offset (Y-UP library frame) into schematic
    world coordinates (Y-DOWN) for a symbol rotated rot degrees CCW."""
    if rot == 0:
        return px, -py
    if rot == 90:
        return -py, -px
    if rot == 180:
        return -px, py
    if rot == 270:
        return py, px
    raise ValueError(rot)


def stub_dir(pangle, rot):
    """Outward direction of a pin (unit vector) in world coordinates."""
    a = math.radians((pangle + rot) % 360)
    return -math.cos(a), math.sin(a)


# ----------------------------------------------------------------------------
# Netlist: component -> pin -> net
# ----------------------------------------------------------------------------

# Components: (ref, value, footprint, libfile, symname, rotation, x, y)
# All positions are multiples of 1.27 mm (KiCad symbol grid) and spaced so
# that pin stubs (2.54 mm) from neighbouring symbols never touch.
COMPONENTS = [
    # --- AC input / protection ---
    ("J1",  "AC_IN L,N",      "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal", "Connector_Generic", "Conn_01x02", 0,   40.64, 55.88),
    ("F1",  "2A/T",           "Fuse:Fuse_Bourns_MF-RG300",                     "Device",            "Fuse",       90,  60.96, 55.88),
    ("RV1", "V275EU2",        "Varistor:RV_Disc_D7mm_W3.4mm_P5mm",             "Device",            "Varistor",   90,  60.96, 83.82),
    ("U1",  "HLK-PM01",       "Converter_ACDC:Converter_ACDC_Hi-Link_HLK-PMxx", "Converter_ACDC",    "HLK-PM01",   0,   91.44, 60.96),
    # --- 5V rail decoupling ---
    ("C1",  "10uF/16V",       "Capacitor_SMD:C_0805_2012Metric",               "Device",            "C",          90, 114.30, 49.53),
    ("C2",  "100nF/50V",      "Capacitor_SMD:C_0603_1608Metric",               "Device",            "C",          90, 137.16, 49.53),
    # --- 3.3V LDO ---
    ("U2",  "AMS1117-3.3",    "Package_TO_SOT_SMD:SOT-223-3_TabPin2",          "Regulator_Linear",  "AMS1117-3.3", 0, 114.30, 76.20),
    ("C3",  "10uF/10V",       "Capacitor_SMD:C_0805_2012Metric",               "Device",            "C",          90, 160.02, 49.53),
    ("C4",  "100nF/50V",      "Capacitor_SMD:C_0603_1608Metric",               "Device",            "C",          90, 182.88, 49.53),
    # --- Relay + driver ---
    ("K1",  "SRD-05VDC-SL-C", "Relay_THT:Relay_SPST_SANYOU_SRD_Series_Form_A", "Relay",             "SANYOU_SRD_Form_A", 0, 91.44, 104.14),
    ("D5",  "1N4007",         "Diode_SMD:D_SMA",                               "Device",            "D",          90,  73.66, 104.14),
    ("Q1",  "AO3400A",        "Package_TO_SOT_SMD:SOT-23",                     "Transistor_FET",    "AO3400A",    0,   73.66, 132.08),
    ("R1",  "1k",             "Resistor_SMD:R_0603_1608Metric",                "Device",            "R",          90,  58.42, 132.08),
    ("R2",  "100k",           "Resistor_SMD:R_0603_1608Metric",                "Device",            "R",          90,  58.42, 146.05),
    ("R3",  "1k",             "Resistor_SMD:R_0603_1608Metric",                "Device",            "R",          90,  91.44, 132.08),
    ("D6",  "LED_GREEN",      "LED_SMD:LED_0603_1608Metric",                   "Device",            "LED",        90,  91.44, 152.40),
    # --- AC output to outlet ---
    ("J2",  "AC_OUT L,N",     "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal", "Connector_Generic", "Conn_01x02", 0,  127.00, 104.14),
    # --- Core board header ---
    ("J3",  "ESP32-P4-CORE",  "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", "Connector_Generic", "Conn_01x06", 90, 167.64, 59.69),
    # --- BOOT button (GPIO35, active-low) ---
    ("SW1", "RESET_WIFI",     "Button_Switch_THT:SW_PUSH_6mm",                 "Switch",            "SW_Push",    0,  167.64, 119.38),
    ("C5",  "100nF",          "Capacitor_SMD:C_0603_1608Metric",               "Device",            "C",          90, 190.50, 119.38),
    ("R4",  "10k",            "Resistor_SMD:R_0603_1608Metric",                "Device",            "R",          90, 213.36, 119.38),
]

# Pin functions verified against the KiCad 10 libraries:
#   HLK-PM01: 1=AC/L 2=AC/N 3=-Vout 4=+Vout
#   Device:D / Device:LED: 1=K(cathode) 2=A(anode)
#   AO3400A (Q_NMOS_GSD): 1=G 2=S 3=D
#   SANYOU_SRD_Form_A: 1,2=coil 3=COM 5=NO
#   AMS1117-3.3: 1=GND 2=VO 3=VI
NETS = {
    "AC_L":   [("J1", "1"), ("F1", "1")],
    "AC_L_F": [("F1", "2"), ("RV1", "1"), ("U1", "1"), ("K1", "3")],
    "AC_N":   [("J1", "2"), ("RV1", "2"), ("U1", "2"), ("J2", "2")],
    "AC_SW":  [("K1", "5"), ("J2", "1")],
    "+5V":    [("U1", "4"), ("C1", "1"), ("C2", "1"), ("U2", "3"), ("K1", "1"),
               ("D5", "1"), ("R3", "1")],
    "GND":    [("U1", "3"), ("C1", "2"), ("C2", "2"), ("U2", "1"), ("C3", "2"), ("C4", "2"),
               ("Q1", "2"), ("R2", "1"), ("SW1", "2"), ("C5", "2"), ("J3", "2")],
    "+3V3":   [("U2", "2"), ("C3", "1"), ("C4", "1"), ("R4", "1"), ("J3", "1")],
    "RELAY":  [("J3", "4"), ("R1", "2")],
    "GATE":   [("R1", "1"), ("R2", "2"), ("Q1", "1")],
    "SW_NODE":[("Q1", "3"), ("K1", "2"), ("D5", "2"), ("D6", "1")],
    "LED_A":  [("R3", "2"), ("D6", "2")],
    "BOOT":   [("J3", "5"), ("SW1", "1"), ("C5", "1"), ("R4", "2")],
    "UART_TX":[("J3", "6")],
    "UART_RX":[("J3", "3")],
}

# DC rails get a power symbol for readability (they are driven by real
# power_out pins); the AC mains nets have no power symbol, so each needs a
# PWR_FLAG to satisfy ERC's "power input not driven" check.
POWER_SYMS = {"+5V": ("+5V", True), "+3V3": ("+3V3", True), "GND": ("GND", False)}
FLAG_NETS = ["AC_L_F", "AC_N"]


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "smart_outlet")
    os.makedirs(out_dir, exist_ok=True)

    root_uuid = _u()
    sheet_uuid = root_uuid  # single-sheet project

    # ---- collect pins actually used, verify all nets reference existing pins
    pin_cache = {}
    used_libs = {}
    for ref, value, fp, lib, sym, rot, x, y in COMPONENTS:
        pins = symbol_pins(lib, sym)
        pin_cache[ref] = pins
        used_libs[f"{lib}:{sym}"] = (lib, sym)
    seen = set()
    for net, conns in NETS.items():
        for ref, pin in conns:
            comp = next(c for c in COMPONENTS if c[0] == ref)
            if pin not in pin_cache[ref]:
                raise SystemExit(
                    f"ERROR: {ref} ({comp[3]}:{comp[4]}) has no pin {pin}; "
                    f"available: {sorted(pin_cache[ref])}")
            if (ref, pin) in seen:
                raise SystemExit(f"ERROR: {ref} pin {pin} appears in multiple nets")
            seen.add((ref, pin))

    # ---- lib_symbols section
    lib_syms = []
    for full, (lib, sym) in sorted(used_libs.items()):
        lib_syms.append(embed_symbol(lib, sym, lib))

    # ---- place components, compute stubs
    out = []
    wires = []
    labels = []
    pwr_index = 0

    for ref, value, fp, lib, sym, rot, x, y in COMPONENTS:
        full = f"{lib}:{sym}"
        pins = pin_cache[ref]
        su = _u()
        props = [
            ("Reference", ref, x - 6.35, y - 6.35),
            ("Value", value, x - 6.35, y - 8.89),
            ("Footprint", fp, x - 6.35, y - 11.43),
            ("Datasheet", "~", x - 6.35, y - 13.97),
            ("Description", "", x - 6.35, y - 16.51),
        ]
        prop_txt = []
        for pname, pval, px, py in props:
            hidden = "" if pname in ("Reference", "Value") else " (hide yes)"
            prop_txt.append(
                f'\t\t(property "{pname}" "{pval}"\n'
                f'\t\t\t(at {_f(px)} {_f(py)} 0)\n'
                f'\t\t\t(effects (font (size {_f(FONT[0])} {_f(FONT[1])})){hidden})\n'
                f'\t\t)'
            )
        pin_list = "\n".join(
            f'\t\t(pin "{n}" (uuid "{_u()}"))' for n in sorted(pins))
        out.append(
            f'\t(symbol\n'
            f'\t\t(lib_id "{full}")\n'
            f'\t\t(at {_f(x)} {_f(y)} {rot})\n'
            f'\t\t(unit 1)\n'
            f'\t\t(exclude_from_sim no)\n'
            f'\t\t(in_bom yes)\n'
            f'\t\t(on_board yes)\n'
            f'\t\t(dnp no)\n'
            f'\t\t(uuid "{su}")\n'
            + "\n".join(prop_txt) + "\n" +
            pin_list + "\n" +
            f'\t\t(instances\n'
            f'\t\t\t(project "{PROJECT_NAME}"\n'
            f'\t\t\t\t(path "/{sheet_uuid}"\n'
            f'\t\t\t\t\t(reference "{ref}") (unit 1)\n'
            f'\t\t\t\t)\n'
            f'\t\t\t)\n'
            f'\t\t)\n'
            f'\t)'
        )

        # map pins to nets
        pin_net = {}
        for net, conns in NETS.items():
            for r, p in conns:
                if r == ref:
                    pin_net[p] = net

        for pnum, (px, py, pangle, _et) in pins.items():
            dx, dy = stub_dir(pangle, rot)
            ax = x + rotate(px, py, rot)[0]
            ay = y + rotate(px, py, rot)[1]
            bx = ax + dx * STUB
            by = ay + dy * STUB
            if pnum in pin_net:
                wires.append((ax, ay, bx, by))
                net = pin_net[pnum]
                # label angle: keep text upright-ish; 0 reads left-to-right
                lang = 0 if dx >= 0 else 180
                labels.append((net, bx, by, lang))

    # ---- power symbols + PWR_FLAGs
    def emit_power_sym(lib, name, ref, px, py, value):
        used_libs.setdefault(f"{lib}:{name}", (lib, name))
        return (
            f'\t(symbol\n'
            f'\t\t(lib_id "{lib}:{name}")\n'
            f'\t\t(at {_f(px)} {_f(py)} 0)\n'
            f'\t\t(unit 1)\n'
            f'\t\t(exclude_from_sim no)\n'
            f'\t\t(in_bom yes)\n'
            f'\t\t(on_board yes)\n'
            f'\t\t(dnp no)\n'
            f'\t\t(uuid "{_u()}")\n'
            f'\t\t(property "Reference" "{ref}" (at {_f(px)} {_f(py)} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27))))\n'
            f'\t\t(property "Value" "{value}" (at {_f(px)} {_f(py + 2.54)} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27))))\n'
            f'\t\t(property "Footprint" "" (at {_f(px)} {_f(py)} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'\t\t(property "Datasheet" "" (at {_f(px)} {_f(py)} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'\t\t(property "Description" "" (at {_f(px)} {_f(py)} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'\t\t(pin "1" (uuid "{_u()}"))\n'
            f'\t\t(instances\n'
            f'\t\t\t(project "{PROJECT_NAME}"\n'
            f'\t\t\t\t(path "/{sheet_uuid}"\n'
            f'\t\t\t\t\t(reference "{ref}") (unit 1)\n'
            f'\t\t\t\t)\n'
            f'\t\t\t)\n'
            f'\t\t)\n'
            f'\t)'
        )

    def first_stub(net):
        for n, x, y, _a in labels:
            if n == net:
                return x, y
        return None

    # power symbols sit above the stub end for +rails, below for GND
    for net, (pname, above) in POWER_SYMS.items():
        pos = first_stub(net)
        if not pos:
            continue
        lx, ly = pos
        wy = ly - 5.08 if above else ly + 5.08
        wires.append((lx, ly, lx, wy))
        pwr_index += 1
        out.append(emit_power_sym("power", pname, f"#PWR0{pwr_index}", lx, wy, pname))

    for net in FLAG_NETS:
        pos = first_stub(net)
        if not pos:
            continue
        lx, ly = pos
        # PWR_FLAG sits directly ON the stub end (same spot as a label) -
        # no extra wire, so it can never short across a neighbouring pin.
        pwr_index += 1
        out.append(emit_power_sym("power", "PWR_FLAG", f"#PWR0{pwr_index}", lx, ly, "PWR_FLAG"))

    # ---- re-embed lib_symbols including any power symbols added late
    final_libs = []
    for full, (lib, sym) in sorted(used_libs.items()):
        final_libs.append(embed_symbol(lib, sym, full.split(":", 1)[0]))

    # ---- wires / labels text
    wire_txt = "\n".join(
        f'\t(wire (pts (xy {_f(a)} {_f(b)}) (xy {_f(c)} {_f(d)}))\n'
        f'\t\t(stroke (width 0) (type default))\n'
        f'\t\t(uuid "{_u()}")\n'
        f'\t)'
        for a, b, c, d in wires
    )
    label_txt = "\n".join(
        f'\t(label "{name}"\n'
        f'\t\t(at {_f(x)} {_f(y)} {ang})\n'
        f'\t\t(effects (font (size 1.27 1.27)) (justify left bottom))\n'
        f'\t\t(uuid "{_u()}")\n'
        f'\t)'
        for name, x, y, ang in labels
    )

    title = (
        f'\t(title_block\n'
        f'\t\t(title "Smart Power Outlet - Carrier Board")\n'
        f'\t\t(date "2026-09-07")\n'
        f'\t\t(rev "A")\n'
        f'\t\t(company "Smart Power Outlet Project")\n'
        f'\t)'
    )

    sch = (
        f'(kicad_sch\n'
        f'\t(version 20250114)\n'
        f'\t(generator "eeschema")\n'
        f'\t(generator_version "8.0")\n'
        f'\t(uuid "{root_uuid}")\n'
        f'\t(paper "A4")\n'
        f'{title}\n'
        f'\t(lib_symbols\n' + "\n".join("\t\t" + s for s in final_libs) + '\n\t)\n'
        + "\n".join(out) + "\n"
        + wire_txt + "\n"
        + label_txt + "\n"
        f'\t(sheet_instances\n'
        f'\t\t(path "/" (page "1"))\n'
        f'\t)\n'
        f')\n'
    )

    sch_path = os.path.join(out_dir, f"{PROJECT_NAME}.kicad_sch")
    with open(sch_path, "w", encoding="utf-8") as fh:
        fh.write(sch)

    pro = f'''{{
  "board": {{}},
  "boards": [],
  "cvpcb": {{"equivalence_files": []}},
  "libraries": {{"pinned_footprint_libs": [], "pinned_symbol_libs": []}},
  "meta": {{"filename": "{PROJECT_NAME}.kicad_pro", "version": 3}},
  "net_settings": {{"classes": [{{"bus_width": 12.0, "clearance": 0.2, "diff_pair_gap": 0.25,
      "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2, "line_style": 0, "microvia_diameter": 0.3,
      "microvia_drill": 0.1, "name": "Default", "pcb_color": "rgba(0, 0, 0, 0.000)",
      "schematic_color": "rgba(0, 0, 0, 0.000)", "track_width": 0.2, "via_diameter": 0.6,
      "via_drill": 0.3, "wire_width": 6.0}}], "meta": {{"version": 3}}}},
  "pcbnew": {{"page_layout_descr_file": ""}},
  "schematic": {{"legacy_lib_dir": "", "legacy_lib_list": []}},
  "sheets": [["{root_uuid}", "Root"]],
  "text_variables": []
}}
'''
    pro_path = os.path.join(out_dir, f"{PROJECT_NAME}.kicad_pro")
    with open(pro_path, "w", encoding="utf-8") as fh:
        fh.write(pro)

    print(f"Wrote {sch_path}")
    print(f"Wrote {pro_path}")
    print(f"Components: {len(COMPONENTS)}, nets: {len(NETS)}, wires: {len(wires)}, labels: {len(labels)}")


if __name__ == "__main__":
    main()
