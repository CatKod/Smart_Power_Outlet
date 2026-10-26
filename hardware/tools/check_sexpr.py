"""Sanity checks on the generated .kicad_sch: paren balance and s-expr parse."""
import sys

path = r"d:\GitHub\Smart_Power_Outlet\hardware\smart_outlet\smart_outlet.kicad_sch"
with open(path, "r", encoding="utf-8") as fh:
    text = fh.read()

# tokenizer that respects quoted strings
tokens = []
i, n = 0, len(text)
in_str = False
buf = ""
line = 1
while i < n:
    c = text[i]
    if c == "\n":
        line += 1
    if in_str:
        if c == "\\":
            buf += text[i:i+2]
            i += 2
            continue
        if c == '"':
            in_str = False
        buf += c
    else:
        if c == '"':
            in_str = True
            buf = c
        elif c in "()":
            tokens.append((c, line))
        elif c.isspace():
            if buf:
                tokens.append((buf, line))
                buf = ""
        else:
            buf += c
    i += 1
if buf:
    tokens.append((buf, line))

depth = 0
min_depth_line = None
stack = []
for tok, ln in tokens:
    if tok == "(":
        stack.append(ln)
    elif tok == ")":
        if not stack:
            print(f"UNMATCHED ) at line {ln}")
            sys.exit(1)
        stack.pop()

if stack:
    print(f"UNCLOSED ( opened at lines: {stack[-20:]}")
else:
    print("Parens balanced OK")

# report depth at a few known landmarks
depth = 0
marks = {}
i, n = 0, len(text)
in_str = False
ln = 1
for tok, ln in tokens:
    if tok == "(":
        depth += 1
    elif tok == ")":
        depth -= 1
    if ln not in marks:
        marks[ln] = depth

print(f"final depth: {depth}")
