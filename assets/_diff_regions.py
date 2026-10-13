# -*- coding: utf-8 -*-
"""两文件差异区段分析（用来看往返测试那 +4 字节到底动在哪）。"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIG = ROOT / "CN_Refined" / "originalassets"
RT = HERE / "out" / "roundtrip"

FILES = ["sharedassets0.assets", "sharedassets6.assets"]

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def regions(a: bytes, b: bytes):
    n = min(len(a), len(b))
    out, i = [], 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def main() -> int:
    for fn in FILES:
        p0, p1 = ORIG / fn, RT / fn
        if not (p0.exists() and p1.exists()):
            say("缺文件: %s / %s" % (p0, p1))
            continue
        a, b = p0.read_bytes(), p1.read_bytes()
        say("=" * 84)
        say(fn)
        hdr = struct.unpack("<IqII", a[:20])
        say("  原始头部: metadata_size=%d file_size=%d version=%d data_offset=%d"
            % hdr)
        hdr2 = struct.unpack("<IqII", b[:20])
        say("  往返头部: metadata_size=%d file_size=%d version=%d data_offset=%d"
            % hdr2)
        say("  长度: %d → %d  (%+d)" % (len(a), len(b), len(b) - len(a)))
        rs = regions(a, b)
        say("  差异区段 %d 个（前 12）:" % len(rs))
        for (i, j) in rs[:12]:
            inmeta = i < hdr[0] + 20
            say("    偏移 %-12d..%-12d 长 %-6d  %s"
                % (i, j, j - i, "metadata/头部" if inmeta else "data 区"))
            say("        原始: %s" % a[i:min(j, i + 24)].hex(" "))
            say("        往返: %s" % b[i:min(j, i + 24)].hex(" "))
        # 尾部
        if len(a) != len(b):
            tail = max(len(a), len(b))
            say("  尾部 16 字节:")
            say("        原始: %s" % a[max(0, len(a) - 16):].hex(" "))
            say("        往返: %s" % b[max(0, len(b) - 16):].hex(" "))
            say("        (%d)" % tail)
        say("")

    text = "\n".join(lines)
    (HERE / "out" / "diff_regions.txt").write_text(text + "\n", encoding="utf-8-sig")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
