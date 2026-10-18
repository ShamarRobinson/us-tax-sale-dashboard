#!/usr/bin/env python3
"""Turn pasted collector status output into data/raw/realauction/<fips>-<kind>.chunks files.

Used when a RealAuction portal has to be collected through a browser tab whose output can only be copied as text (the
piece-by-piece transcription protocol in docs/HANDOFF.md). Reads stdin and accepts the raw text as a tool returns it:
either the JSON-escaped string (with \\" and \\n escapes) or plain text. Each record starts with
{"fips":"NNNNN", ... "done":{...}} ... n=K and is followed by lines "<index> <crc32hex> <base64 piece>".

    python3 tools/ingest_chunks.py foreclosure < pasted.txt
    python3 tools/decode_dumps.py          # verifies every piece's CRC and writes <fips>-<kind>.json

A synthetic header line such as {"fips":"12105","done":{"days":58}} n=19 works when only the pieces were copied.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "raw", "realauction")
KIND = sys.argv[1] if len(sys.argv) > 1 else "sheriff"

txt = sys.stdin.read()
txt = txt.replace('\\"', '"').replace("\\n", "\n")
recs = re.split(r'(?=\{"fips":")', txt)
n_written = 0
os.makedirs(RAW, exist_ok=True)
for rec in recs:
    m = re.match(r'\{"fips":"(\d+)"', rec)
    if not m:
        continue
    fips = m.group(1)
    if '"done":null' in rec.split("\n", 1)[0]:
        print(f"{fips}: not done yet")
        continue
    lines = []
    for line in rec.split("\n")[1:]:
        line = line.strip().strip('"')
        mm = re.match(r"^(\d+) ([0-9a-f]{1,8}) ([A-Za-z0-9+/=]+)$", line)
        if mm:
            lines.append("\t".join(mm.groups()))
    if not lines:
        print(f"{fips}: no pieces found")
        continue
    path = os.path.join(RAW, f"{fips}-{KIND}.chunks")
    mode = "a" if os.path.exists(path) else "w"
    with open(path, mode, encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{fips}: {len(lines)} piece(s) {'appended to' if mode == 'a' else 'written to'} {os.path.basename(path)}")
    n_written += 1
print(f"{n_written} file(s)")
