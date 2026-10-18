#!/usr/bin/env python3
"""Decode collector dumps in data/raw/realauction/ into <fips>-<kind>.json.

Accepts *.b64 (one gzip+base64 string) and *.chunks (one "index<TAB>crc32hex<TAB>piece" line per piece, as returned by
window.__chunk(i) in tools/realauction_console.js). Pieces whose CRC does not match are reported so they can be copied
again; nothing is decoded until every piece is present and verified.
"""
import base64, glob, gzip, json, os, sys, zlib
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "raw", "realauction")


def report(out, d):
    aucs = d["auctions"]
    ps = [x for a in aucs for x in a["parcels"]]
    print(f"{os.path.basename(out)}: {d['fips']} {d['kind']} {len(aucs)} days, {len(ps)} items, {dict(Counter(x.get('status') for x in ps))}, parcel no: {sum(1 for x in ps if x.get('parcel'))}, value: {sum(1 for x in ps if x.get('value'))}")


def save(src, b64):
    d = json.loads(gzip.decompress(base64.b64decode(b64)))
    out = os.path.splitext(src)[0] + ".json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    os.remove(src)
    report(out, d)


ok = True
for p in sorted(glob.glob(os.path.join(RAW, "*.b64"))):
    try:
        save(p, open(p).read().strip())
    except Exception as e:
        ok = False
        print(f"{os.path.basename(p)}: FAILED {e}")
for p in sorted(glob.glob(os.path.join(RAW, "*.chunks"))):
    pieces, bad, n = {}, [], None
    for line in open(p, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        i, crc, data = line.split("\t", 2)
        i = int(i)
        if format(zlib.crc32(data.encode("latin-1")) & 0xFFFFFFFF, "x") != crc.lower():
            bad.append(i)
        else:
            pieces[i] = data
    n = max(list(pieces) + bad) + 1 if (pieces or bad) else 0
    bad = sorted(set(i for i in bad if i not in pieces))  # a later good copy of a piece supersedes a bad one
    missing = [i for i in range(n) if i not in pieces]
    if bad or missing:
        ok = False
        print(f"{os.path.basename(p)}: bad CRC pieces {bad}, missing {missing} (have {len(pieces)})")
        continue
    try:
        save(p, "".join(pieces[i] for i in range(n)))
    except Exception as e:
        ok = False
        print(f"{os.path.basename(p)}: FAILED {e} (a piece may be short; last piece index {n-1})")
sys.exit(0 if ok else 1)
