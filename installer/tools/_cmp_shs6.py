# -*- coding: utf-8 -*-
"""把三份 sharedassets6.assets 放一起比：mac 机上的 / Windows 原版 / 我们的产物。

要回答的问题：mac 上那份到底是原版，还是已经被某种工具改过（改的是不是同一批文本）。
"""
from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # CN_Refined/
FILES = {
    "mac": ROOT / "out" / "_mac_shs6.assets",
    "win原版": ROOT / "originalassets" / "sharedassets6.assets",
    "我们的": ROOT / "installer" / "assets" / "sharedassets6.assets",
}
OUT = ROOT / "out" / "_mac_shs6_report.txt"


def read_str(buf: bytes, off: int):
    n = struct.unpack_from("<i", buf, off)[0]
    if not (0 <= n <= 65535) or off + 4 + n > len(buf):
        return None
    raw = buf[off + 4:off + 4 + n]
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return s, off + 4 + n + ((-n) % 4)


def credits(buf: bytes):
    """-> [(id, 文本, 文本在文件里的偏移)]"""
    out = []
    off = 0
    while True:
        p = buf.find(b"#credits_", off)
        if p < 0:
            break
        off = p + 1
        rid = read_str(buf, p - 4)
        if not rid or not rid[0].startswith("#credits_"):
            continue
        txt = read_str(buf, rid[1])
        if not txt:
            continue
        out.append((rid[0], txt[0], rid[1]))
    return out


def regions(a: bytes, b: bytes, gap: int = 8):
    """两段字节的差异区间（把邻近的差异合并成一段）"""
    n = min(len(a), len(b))
    diffs = [i for i in range(n) if a[i] != b[i]]
    out = []
    for i in diffs:
        if out and i - out[-1][1] <= gap:
            out[-1][1] = i + 1
        else:
            out.append([i, i + 1])
    if len(a) != len(b):
        out.append([n, max(len(a), len(b))])
    return [(lo, hi, hi - lo) for lo, hi in out]


L: list[str] = []
say = L.append

data = {}
for k, p in FILES.items():
    if not p.is_file():
        say("缺文件：%s (%s)" % (k, p))
        continue
    data[k] = p.read_bytes()
    b = data[k]
    hdr = struct.unpack_from(">IIII", b, 0)
    say("== %-6s %d B" % (k, len(b)))
    say("   SerializedFile 头：metadata=%d file_size=%d version=%d data_offset=%d"
        % hdr)
    uv = b[20:60].split(b"\x00")[0]
    say("   unity 版本串：%s   字节序标记：%s"
        % (uv.decode("latin-1"), b[16:20].hex()))
    ents = credits(b)
    say("   #credits_* 有文本的条目：%d 个" % len(ents))
    for kk, v, off in ents:
        if v:
            say("      %-26s @%-6d %r" % (kk, off, v[:70]))
    say("")

# 两两比
for a, b in (("win原版", "我们的"), ("mac", "我们的"), ("mac", "win原版")):
    if a not in data or b not in data:
        continue
    rs = regions(data[a], data[b])
    tot = sum(r[2] for r in rs)
    say("== %s vs %s：差异 %d 处，共 %d 字节" % (a, b, len(rs), tot))
    for lo, hi, n in rs[:25]:
        say("   %6d..%-6d (%d B)  %s" % (lo, hi, n, data[b][lo:min(hi, lo + 48)].hex(" ")[:150]))
    if len(rs) > 25:
        say("   …还有 %d 处" % (len(rs) - 25))
    say("")

OUT.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L)[:6000])
print("\n（全文写到 %s）" % OUT)
