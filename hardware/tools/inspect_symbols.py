"""Dump full pin details (number, position, angle, etype, name) for every
symbol used by gen_schematic.py so pin functions can be verified."""
import re
import sys

sys.path.insert(0, r"d:\GitHub\Smart_Power_Outlet\hardware\tools")
from gen_schematic import load_symbol, symbol_pins, find_block

CHECKS = [
    ("Device", "D"),
    ("Device", "LED"),
    ("Transistor_FET", "AO3400A"),
    ("Regulator_Linear", "AMS1117-3.3"),
    ("Converter_ACDC", "HLK-PM01"),
    ("Relay", "SANYOU_SRD_Form_A"),
    ("Switch", "SW_Push"),
    ("Connector_Generic", "Conn_01x02"),
    ("Connector_Generic", "Conn_01x06"),
    ("Device", "R"),
    ("Device", "C"),
]

for lib, sym in CHECKS:
    block = load_symbol(lib, sym)
    ext = re.search(r'\(extends "([^"]+)"\)', block)
    if ext:
        block = load_symbol(lib, ext.group(1))
    print(f"=== {lib}:{sym}" + (f" (extends {ext.group(1)})" if ext else ""))
    for m in re.finditer(r'\(pin (\w+) (\w+)\s*\(at (-?[\d.]+) (-?[\d.]+) (-?\d+)\)', block):
        etype, shape, x, y, ang = m.groups()
        s, e = find_block(block, m.start())
        pin_text = block[s:e]
        num = re.search(r'\(number "([^"]*)"', pin_text)
        name = re.search(r'\(name "([^"]*)"', pin_text)
        print(f"  pin {num.group(1) if num else '?':>3} "
              f"name={name.group(1) if name else '?':<8} "
              f"at ({x},{y}) ang={ang} type={etype}")
