"""Export the KiCad netlist (s-expression) and diff it against the intended
NETS table to find wrong connectivity."""
import os
import re
import subprocess
import sys

sys.path.insert(0, r"d:\GitHub\Smart_Power_Outlet\hardware\tools")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gen_schematic import NETS

KICAD = r"D:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
SCH = r"D:\GitHub\Smart_Power_Outlet\hardware\smart_outlet\smart_outlet.kicad_sch"
NET = r"D:\GitHub\Smart_Power_Outlet\hardware\smart_outlet\smart_outlet-net.net"

r = subprocess.run([KICAD, "sch", "export", "netlist", "--format", "kicadsexpr",
                    SCH, "--output", NET], capture_output=True)
err = r.stderr.decode("utf-8", "replace").strip()
print(f"netlist export rc={r.returncode} {err}")

text = open(NET, encoding="utf-8").read()

kicad_nets = {}
for m in re.finditer(
        r'\(net\s*\(code "[^"]*"\)\s*\(name "([^"]+)"\)(.*?)(?=\(net\s|\Z)',
        text, re.S):
    name, body = m.group(1), m.group(2)
    nodes = []
    for nm in re.finditer(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', body):
        nodes.append((nm.group(1), nm.group(2)))
    kicad_nets[name] = nodes

print("\n=== KiCad nets vs intended nets ===")
all_ok = True
for name in sorted(kicad_nets):
    nodes = kicad_nets[name]
    nodeset = set(nodes)
    matched = None
    for net, conns in NETS.items():
        if nodeset == set(conns):
            matched = net
            break
    if matched:
        print(f"[OK  ] {name:<12} {len(nodes):>2} nodes == intended '{matched}'")
    else:
        all_ok = False
        best = max(NETS, key=lambda n: len(set(NETS[n]) & nodeset))
        missing = set(NETS[best]) - nodeset
        extra = nodeset - set(NETS[best])
        print(f"[DIFF] {name:<12} {len(nodes):>2} nodes")
        print(f"        closest='{best}' missing={sorted(missing)} extra={sorted(extra)}")

all_nodes = set()
for nodes in kicad_nets.values():
    all_nodes.update(nodes)
for net, conns in NETS.items():
    for rp in conns:
        if rp not in all_nodes:
            all_ok = False
            print(f"[MISS] {rp} intended on '{net}' not found in any net")

print("\nRESULT:", "ALL NETS MATCH" if all_ok else "MISMATCHES FOUND")
