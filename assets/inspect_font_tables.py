# -*- coding: utf-8 -*-
"""逐表体检：两支「思源宋体」源字体 + 我的两个子集 + 你 dev 里那支能用的。

第一次（游戏自带字体做子集）字体能加载；
第二次（font_src 的 SC 版做子集）变成系统字体 = 加载失败。
→ 逐个字段比，找出 SC 那支（或其子集）有什么让 Unity/FreeType 不接受的东西。

用法: python CN_Refined\\assets\\inspect_font_tables.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
A = HERE / "out"
CAND = [
    ("游戏自带源", A / "fonts" / "orig-SourceHanSerif-SemiBold.otf"),
    ("项目SC源", ROOT / "font_src" / "SOURCEHANSERIFSC-SEMIBOLD.OTF"),
    ("dev能用支", A / "fonts" / "old-SourceHanSerif-SemiBold.otf"),
    ("我上一版子集", A / "subset" / "B_orig-SourceHanSerif-SemiBold.otf"),
    ("我这一版子集", A / "verify" / "SourceHanSerif-SemiBold.otf"),
]

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def probe(p: Path, tag: str):
    if not p.exists():
        say("  %-14s ✗ 缺 %s" % (tag, p))
        return
    f = TTFont(str(p), lazy=True)
    t = set(f.keys())
    say("─" * 90)
    say("%s   %s   %.2f MB" % (tag, p.name, p.stat().st_size / 1048576))
    say("  表(%d): %s" % (len(t), ", ".join(sorted(t))))
    try:
        say("  maxp: version=0x%X numGlyphs=%d" % (f["maxp"].tableVersion, f["maxp"].numGlyphs))
    except Exception as e:                                  # noqa: BLE001
        say("  maxp: ✗ %s" % e)
    h = f["head"]
    say("  head: unitsPerEm=%d flags=0x%X indexToLocFormat=%d macStyle=0x%X"
        % (h.unitsPerEm, h.flags, h.indexToLocFormat, h.macStyle))
    say("  hhea: ascent=%d descent=%d numberOfHMetrics=%d"
        % (f["hhea"].ascent, f["hhea"].descent, f["hhea"].numberOfHMetrics))
    try:
        o = f["OS/2"]
        say("  OS/2: version=%d fsType=0x%X usWeightClass=%d 编码页=0x%04X%04X/0x%04X%04X"
            % (o.version, o.fsType, o.usWeightClass,
               o.ulCodePageRange1, o.ulCodePageRange2,
               o.ulUnicodeRange3, o.ulUnicodeRange4))
    except Exception as e:                                  # noqa: BLE001
        say("  OS/2: ✗ %s" % e)
    try:
        say("  post: format=%s" % f["post"].formatType)
    except Exception as e:                                  # noqa: BLE001
        say("  post: ✗ %s" % e)
    if "CFF " in t:
        c = f["CFF "].cff
        top = c[c.fontNames[0]]
        say("  CFF: 字体数=%d isCID=%s ROS=%s CharStrings=%d"
            % (len(c.fontNames), getattr(top, "ROS", None) is not None,
               getattr(top, "ROS", None), len(top.CharStrings.charStrings)
               if hasattr(top, "CharStrings") else -1))
        say("       FDArray=%s FDSelect=%s 子程序(全局/局部)=%s"
            % (hasattr(top, "FDArray"), hasattr(top, "FDSelect"),
               (len(c.GlobalSubrs) if hasattr(c, "GlobalSubrs") else "?")))
    try:
        subt = [(hex(tb.platformID), hex(tb.platEncID), tb.format)
                for tb in f["cmap"].tables]
        say("  cmap: %s" % subt)
    except Exception as e:                                  # noqa: BLE001
        say("  cmap: ✗ %s" % e)
    try:
        nid = sorted({r.nameID for r in f["name"].names})
        say("  name: ID=%s" % nid)
    except Exception as e:                                  # noqa: BLE001
        say("  name: ✗ %s" % e)
    f.close()


def main() -> int:
    say("字体逐表体检")
    say("=" * 90)
    for tag, p in CAND:
        probe(p, tag)
    text = "\n".join(lines)
    (A / "font_tables.txt").write_text(text + "\n", encoding="utf-8-sig")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
