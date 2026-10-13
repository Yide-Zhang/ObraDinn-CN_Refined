# -*- coding: utf-8 -*-
"""SerializedFile 布局自检：data_offset + Σ(对齐后对象字节) 是否等于 file_size？

用来判断「UnityPy 写出来的文件结构」与「原始 / 你 dev 里能用的那份」有没有差别
（例如末尾多出来的 4 个零字节）。

用法: python CN_Refined\\assets\\_check_layout.py
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import UnityPy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FILES = [
    ("原始 shs0", ROOT / "CN_Refined" / "originalassets" / "sharedassets0.assets"),
    ("dev shs0", ROOT / "CN_Refined" / "olddevassets" / "sharedassets0.assets"),
    ("我 shs0", ROOT / "CN_Refined" / "out" / "assets" / "sharedassets0.assets"),
    ("原始 shs2", ROOT / "CN_Refined" / "originalassets" / "sharedassets2.assets"),
    ("dev shs2", ROOT / "CN_Refined" / "olddevassets" / "sharedassets2.assets"),
    ("我 shs2", ROOT / "CN_Refined" / "out" / "assets" / "sharedassets2.assets"),
]

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def main() -> int:
    say("SerializedFile 布局自检")
    say("=" * 96)
    say("  %-10s %12s %10s %12s %12s %8s  %s"
        % ("文件", "file_size", "data_off", "Σ对齐byteSize", "算得总长", "差额", "末尾4字节"))
    for tag, p in FILES:
        if not p.exists():
            say("  %-10s ✗ 缺" % tag)
            continue
        b = p.read_bytes()
        # 头部：前 4 个字段（大端）
        meta_sz = struct.unpack_from(">I", b, 0)[0]
        file_sz = struct.unpack_from(">I", b, 4)[0]
        ver = struct.unpack_from(">I", b, 8)[0]
        data_off = struct.unpack_from(">I", b, 12)[0]
        env = UnityPy.load(str(p))
        total = 0
        for o in env.objects:
            total += (o.byte_size + 3) & ~3          # 每个对象 4 字节对齐
        calc = data_off + total
        say("  %-10s %12d %10d %12d %12d %8d  %s   ver=%d meta=%d"
            % (tag, file_sz, data_off, total, calc, file_sz - calc,
               b[-4:].hex(" "), ver, meta_sz))
        if file_sz != len(b):
            say("             ⚠ 头部 file_size(%d) ≠ 实际长度(%d)" % (file_sz, len(b)))
    say("")
    say("  说明：差额 = 0 表示「对象数据紧密到文件尾」，原始文件应当如此；")
    say("       若我的产出差额 ≠ 0，就是 UnityPy 多加的对齐填充 —— 需要裁掉再修 file_size。")
    text = "\n".join(lines)
    (HERE / "out" / "layout.txt").write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
