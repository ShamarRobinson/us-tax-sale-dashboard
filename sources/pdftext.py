"""Minimal text extraction for simple PDFs (FlateDecode page streams, Tm/Td/TD/T*/Tj/TJ/' operators, WinAnsi text),
enough to read the fixed-column result sheets that iltaxsale.com publishes. Returns lines ordered top to bottom with
text placed by x coordinate, like `pdftotext -layout`."""
import re
import shutil
import subprocess
import tempfile
import zlib

STREAM_START = re.compile(rb"stream\r?\n")
TOKEN = re.compile(rb"\[(?:[^\]\\]|\\.)*\]|\((?:[^()\\]|\\.)*\)|/[^\s/\[\]()<>]+|-?\d*\.?\d+|[A-Za-z'\"*]+")
ESC = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f", b"(": b"(", b")": b")", b"\\": b"\\"}


def _unescape(s):
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i:i + 1]
        if c == b"\\" and i + 1 < len(s):
            n = s[i + 1:i + 2]
            if n in ESC:
                out += ESC[n]
                i += 2
                continue
            m = re.match(rb"[0-7]{1,3}", s[i + 1:i + 4])
            if m:
                out.append(int(m.group(0), 8))
                i += 1 + len(m.group(0))
                continue
            i += 1
            continue
        out += c
        i += 1
    return bytes(out)


def _strings(tok):
    """Text of a (...) or [...] token."""
    if tok.startswith(b"("):
        return _unescape(tok[1:-1])
    parts = []
    for m in re.finditer(rb"\((?:[^()\\]|\\.)*\)|-?\d*\.?\d+", tok[1:-1]):
        t = m.group(0)
        if t.startswith(b"("):
            parts.append(_unescape(t[1:-1]))
        elif float(t) < -200:  # a big negative kern is a space the font left out
            parts.append(b" ")
    return b"".join(parts)


def page_streams(data):
    """Each stream's decoded bytes, found by scanning for the stream keyword (no backtracking over binary data)."""
    pos = 0
    while True:
        m = STREAM_START.search(data, pos)
        if not m:
            return
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            return
        hdr = data[max(0, m.start() - 400):m.start()]
        hdr = hdr[hdr.rfind(b"<<"):] if b"<<" in hdr else hdr
        body = data[start:end].rstrip(b"\r\n")
        pos = end + 9
        if b"FlateDecode" in hdr:
            try:
                yield zlib.decompress(body)
            except zlib.error:
                continue
        elif b"/Filter" not in hdr:
            yield body


def extract(data, scale=0.185):
    """Lines of text for every page, in reading order. scale converts PDF points to character columns.

    PDFs whose fonts use identity (glyph id) encodings come out as noise from the pure-Python reader; when the result
    looks like that and pdftotext (poppler) happens to be installed, its layout output is used instead."""
    pages = _extract(data, scale)
    sample = " ".join(" ".join(p) for p in pages)[:4000]
    odd = sum(1 for ch in sample if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\n"))
    if (not pages or odd > 0.15 * max(len(sample), 1)) and shutil.which("pdftotext"):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(data)
        try:
            text = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=120).stdout
            if text.strip():
                return [page.splitlines() for page in text.split("\f") if page.strip()]
        except (OSError, subprocess.SubprocessError):
            pass
    return pages


def _extract(data, scale):
    pages = []
    for stream in page_streams(data):
        if b"BT" not in stream:
            continue
        rows = {}
        x = y = 0.0
        lx = ly = 0.0
        leading = 0.0
        size = 10.0
        toks = TOKEN.findall(stream)
        stack = []
        for t in toks:
            if t[:1] in b"([":
                stack.append(t)
                continue
            if re.match(rb"-?\d*\.?\d+$", t) or t.startswith(b"/"):
                stack.append(t)
                continue
            op = t
            try:
                if op == b"Tm" and len(stack) >= 6:
                    x, y = float(stack[-2]), float(stack[-1])
                    lx, ly = x, y
                elif op in (b"Td", b"TD") and len(stack) >= 2:
                    lx += float(stack[-2])
                    ly += float(stack[-1])
                    x, y = lx, ly
                    if op == b"TD":
                        leading = -float(stack[-1])
                elif op == b"TL" and stack:
                    leading = float(stack[-1])
                elif op == b"T*":
                    ly -= leading
                    x, y = lx, ly
                elif op == b"Tf" and len(stack) >= 2:
                    size = float(stack[-1]) or size
                elif op in (b"Tj", b"'", b"\"", b"TJ") and stack:
                    if op in (b"'", b"\""):
                        ly -= leading
                        x, y = lx, ly
                    s = _strings(stack[-1]).decode("cp1252", "replace")
                    key = round(y / 3)  # rows within a few points are merged below
                    rows.setdefault(key, []).append((x, s))
                    x += len(s) * size * 0.5
            except (ValueError, IndexError):
                pass
            stack.clear()
        # merge rows whose baselines sit within 4 points of each other (superscripts, slightly offset cells)
        merged, last = [], None
        for key in sorted(rows, reverse=True):
            if last is not None and last - key <= 1:
                merged[-1][1].extend(rows[key])
            else:
                merged.append([key, list(rows[key])])
            last = key
        lines = []
        for key, parts in merged:
            parts.sort()
            line = ""
            for px, s in parts:
                col = int(px * scale)
                if col > len(line):
                    line += " " * (col - len(line))
                line += s
            lines.append(line.rstrip())
        pages.append(lines)
    return pages


if __name__ == "__main__":
    import sys
    for i, page in enumerate(extract(open(sys.argv[1], "rb").read())):
        print(f"--- page {i + 1}")
        print("\n".join(page))
