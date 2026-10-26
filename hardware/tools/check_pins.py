import sys
sys.path.insert(0, r"d:\GitHub\Smart_Power_Outlet\hardware\tools")
from gen_schematic import symbol_pins

checks = [
    ("Device", "D"), ("Device", "LED"), ("Device", "Q_NMOS_GSD"),
    ("Device", "R"), ("Device", "C"), ("Device", "Fuse"), ("Device", "Varistor"),
    ("Regulator_Linear", "AMS1117-3.3"), ("Converter_ACDC", "HLK-PM01"),
    ("Switch", "SW_Push"), ("Transistor_FET", "AO3400A"),
    ("Connector_Generic", "Conn_01x02"), ("Connector_Generic", "Conn_01x06"),
    ("Relay", "SANYOU_SRD_Form_A"),
]
for lib, sym in checks:
    try:
        pins = symbol_pins(lib, sym)
        print(f"{lib}:{sym}")
        for num, (x, y, a, et) in sorted(pins.items()):
            print(f"   pin {num}: at ({x},{y}) ang={a} type={et}")
    except Exception as e:
        print(f"{lib}:{sym} -> ERROR {e}")
