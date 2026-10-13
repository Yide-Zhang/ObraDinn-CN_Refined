# -*- coding: utf-8 -*-
"""对比两支「思源宋体」：游戏自带的那支 vs 项目 font_src 里的 SC 版。

关键怀疑：游戏自带的 `SourceHanSerif-SemiBold` 是多语言（默认日文形态）版，
而我做子集时**用的是它**，所以字形没变 —— 看起来「还是旧字体」。
你 dev 里换的是 `SOURCEHANSERIFSC-SEMIBOLD.OTF`（简体中文形态）。

做法：对一批「日文/简体字形明显不同」的汉字，把两边的轮廓点画出来比一比。

用法: python CN_Refined\\assets\\compare_fonts.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GAME = HERE / "out" / "fonts" / "orig-SourceHanSerif-SemiBold.otf"
SC = ROOT / "font_src" / "SOURCEHANSERIFSC-SEMIBOLD.OTF"
DEV = HERE / "out" / "fonts" / "old-SourceHanSerif-SemiBold.otf"
GUI = ROOT / "gui" / "fonts" / "SourceHanSerifSC-SemiBold-subset.otf"

# 这些字在「日文形态 / 简体形态」下差别明显
PROBE = "直骨次令包化强収每海温真者具角過寫誘練雑說直"

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def outline_sig(font: TTFont, ch: str) -> str | None:
    cmap = font.getBestCmap()
    gname = cmap.get(ord(ch))
    if not gname:
        return None
    gs = font.getGlyphSet()
    pen = RecordingPen()
    gs[gname].draw(pen)
    return hashlib.sha256(repr(pen.value).encode()).hexdigest()[:12]


def info(p: Path, tag: str):
    if not p.exists():
        say("  %-8s ✗ 缺 %s" % (tag, p))
        return None
    f = TTFont(str(p), lazy=True)
    cm = f.getBestCmap()
    n = f["maxp"].numGlyphs
    say("  %-8s %-46s %8.2f MB  %6d 字形  %6d cmap"
        % (tag, p.name, p.stat().st_size / 1048576, n, len(cm)))
    return f


def main() -> int:
    say("思源宋体 字形对比")
    say("=" * 92)
    fg = info(GAME, "游戏自带")
    fs = info(SC, "项目SC")
    fd = info(DEV, "你的dev")
    fu = info(GUI, "gui子集")
    if not (fg and fs):
        return 1
    say("")
    say("按字逐个比轮廓（同一哈希 = 同一字形）:")
    say("  %-4s %-14s %-14s %-14s %-14s %s"
        % ("字", "游戏自带", "项目SC", "你的dev", "gui子集", "游戏 vs SC"))
    diff = 0
    same = 0
    for ch in PROBE:
        sigs = []
        for f in (fg, fs, fd, fu):
            sigs.append(outline_sig(f, ch) if f else None)
        a, b = sigs[0], sigs[1]
        verdict = "同" if (a and b and a == b) else ("**不同**" if (a and b) else "?")
        if a and b:
            if a == b:
                same += 1
            else:
                diff += 1
        say("  %-4s %-14s %-14s %-14s %-14s %s"
            % (ch, a or "-", b or "-", sigs[2] or "-", sigs[3] or "-", verdict))
    say("")
    say("  合计：相同 %d 字，不同 %d 字" % (same, diff))
    say("")
    say("=" * 92)
    if diff == 0:
        say("结论：游戏自带那支与项目 SC 版**字形完全相同** → 换字体不会有视觉变化")
    else:
        say("结论：**两支字体字形不同**（%d/%d 个探针字不同）→" % (diff, same))
        say("      游戏自带那支 ≠ 项目 SC 版；子集必须从 **font_src 的 SC 版** 做，")
        say("      否则简体中文会显示成另一套字形（你看到的「还是旧字体」）")
    text = "\n".join(lines)
    (HERE / "out" / "compare_fonts.txt").write_text(text + "\n", encoding="utf-8-sig")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
