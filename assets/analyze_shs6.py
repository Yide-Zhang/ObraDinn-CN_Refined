# -*- coding: utf-8 -*-
"""分析 sharedassets6.assets：找出鸣谢文本在哪、你当初是怎么注入的。

做法：
  1. 原始 vs 你注入过的 逐字节 diff -> 变化区段
  2. 变化区段前后解码 UTF-8，看清字符串格式（长度前缀？对齐？）
  3. 把文件里所有"长度前缀 + UTF-8"的候选串列出来

用法: python CN_Refined\\assets\\analyze_shs6.py
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIG = ROOT / "CN_Refined" / "originalassets" / "sharedassets6.assets"
USER = ROOT / "CN_Refined" / "olddevassets" / "sharedassets6.assets"
OUT = HERE / "out" / "shs6.txt"

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


def utf8_at(buf: bytes, pos: int, span: int = 64) -> str:
    """把 pos 前后的字节当 UTF-8 尽力解码（控制字符/NUL 换成 ·，免得报告被当成二进制）"""
    lo, hi = max(0, pos - span), min(len(buf), pos + span)
    s = buf[lo:hi].decode("utf-8", "replace")
    return "".join(c if (c.isprintable() or c in "\r\n\t") else "·" for c in s)


def walk_strings(buf: bytes, minlen: int = 2):
    """扫描「int32 长度 + N 字节」且内容是合法 UTF-8 的候选串 -> [(偏移, 长度, 文本)]"""
    out = []
    for i in range(len(buf) - 5):
        n = struct.unpack_from("<i", buf, i)[0]
        if not (minlen <= n <= 4096) or i + 4 + n > len(buf):
            continue
        raw = buf[i + 4:i + 4 + n]
        if b"\x00" in raw:
            continue
        try:
            s = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if all(0x20 <= ord(c) <= 0xFFFF and c.isprintable() for c in s):
            out.append((i, n, s))
    return out


def main() -> int:
    a, b = ORIG.read_bytes(), USER.read_bytes()
    say("sharedassets6.assets 分析")
    say("=" * 84)
    say("  原始 %d 字节   %s" % (len(a), ORIG))
    say("  你的 %d 字节   %s" % (len(b), USER))
    say("  长度差 %+d" % (len(b) - len(a)))

    hdr = struct.unpack_from("<IIII", a, 0)
    say("  头部(按 uint32×4 读): metadata_size=%d file_size=%d ver=%d data_off=%d" % hdr)
    say("")

    rs = regions(a, b)
    say("【1】逐字节差异区段: %d 个" % len(rs))
    for (i, j) in rs[:20]:
        say("  偏移 %d..%d (长 %d)  %s"
            % (i, j, j - i, "头部/metadata" if i < 200 else "data 区"))
        say("     原始: %s" % a[i:j].hex(" ")[:160])
        say("     你的: %s" % b[i:j].hex(" ")[:160])
        say("     ← 原始上下文: %s" % utf8_at(a, i))
        say("     ← 你的上下文: %s" % utf8_at(b, i))
    say("")

    say("【2】原始文件里的候选字符串（长度前缀 + UTF-8），只列含非 ASCII 的")
    cands = [t for t in walk_strings(a) if any(ord(c) > 127 for c in t[2])]
    say("  共 %d 个" % len(cands))
    for off, n, s in cands[:60]:
        say("    @%-6d len=%-4d %s" % (off, n, s.replace("\n", "\\n")[:100]))
    say("")

    say("【3】你的文件里同一批串（看改了什么）")
    cands2 = [t for t in walk_strings(b) if any(ord(c) > 127 for c in t[2])]
    say("  共 %d 个" % len(cands2))
    for off, n, s in cands2[:60]:
        say("    @%-6d len=%-4d %s" % (off, n, s.replace("\n", "\\n")[:100]))

    text = "\n".join(lines)
    OUT.write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    print("\n报告 -> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
