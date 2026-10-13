# -*- coding: utf-8 -*-
"""批量量化：项目根那份 `851tegakizatsu.otf` 与**游戏内嵌**那份 851tegaki 差多少字。

用「字符集覆盖到的 CJK」逐字比轮廓哈希（RecordingPen -> sha256）：
  · 两边同一轮廓   = 一致
  · 哈希不同       = 字形不同（用叠色图看是位置变了还是笔画变了）
  · 只有一边有     = 覆盖差异

用法: python CN_Refined\\assets\\_cmp_851_pair.py
产物: CN_Refined\\assets\\out\\cmp851.txt
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ROOT_851 = ROOT / "851tegakizatsu.otf"
EMB = HERE / "out" / "fonts" / "orig-851tegaki_zatsu_normal_0883.ttf"
OURS = HERE / "out" / "verify" / "851tegaki_zatsu_normal_0883.otf"

sys.path.insert(0, str(HERE))
import make_subset_fonts as MS  # noqa: E402

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def sig_of(font: TTFont, cmap: dict, ch: str):
    gname = cmap.get(ord(ch))
    if not gname:
        return None
    pen = RecordingPen()
    font.getGlyphSet()[gname].draw(pen)
    return hashlib.sha256(repr(pen.value).encode()).hexdigest()[:12]


def main() -> int:
    charset, _ = MS.collect_chars()
    chars = sorted(c for c in charset if MS.CJK_CHAR(c) and not c.isspace())
    say("851tegaki 三份对照（字符集里的 CJK，共 %d 字）" % len(chars))
    say("=" * 88)
    fonts = {}
    for tag, p in (("游戏内嵌", EMB), ("我们这版", OURS), ("项目根 851tegakizatsu.otf", ROOT_851)):
        if not p.exists():
            say("  ✗ 缺 %s" % p)
            continue
        f = TTFont(str(p), lazy=True)
        fonts[tag] = (f, f.getBestCmap())
        say("  %-26s %8.2f MB  %6d 字形  %6d cmap"
            % (tag, p.stat().st_size / 1048576, f["maxp"].numGlyphs, len(fonts[tag][1])))
    say("")

    a, b = fonts.get("游戏内嵌"), fonts.get("我们这版")
    if a and b:
        same = diff = 0
        for ch in chars:
            sa, sb = sig_of(a[0], a[1], ch), sig_of(b[0], b[1], ch)
            if sa and sa == sb:
                same += 1
            elif sa or sb:
                diff += 1
        say("我们这版 vs 游戏内嵌:  同一轮廓 %d / 不同 %d / 共 %d  → %s"
            % (same, diff, len(chars), "**完全一致 ✓**" if diff == 0 else "✗"))

    a, b = fonts.get("游戏内嵌"), fonts.get("项目根 851tegakizatsu.otf")
    if a and b:
        same = diff = only_a = only_b = 0
        diffs: list[str] = []
        for ch in chars:
            sa, sb = sig_of(a[0], a[1], ch), sig_of(b[0], b[1], ch)
            if sa and sb:
                if sa == sb:
                    same += 1
                else:
                    diff += 1
                    if len(diffs) < 70:
                        diffs.append(ch)
            elif sa:
                only_a += 1
            else:
                only_b += 1
        tot = same + diff + only_a + only_b
        say("项目根 vs 游戏内嵌:  同一 %d / **不同 %d** / 仅游戏有 %d / 仅项目有 %d  （共 %d，不同占 %.1f%%）"
            % (same, diff, only_a, only_b, tot, 100.0 * diff / max(tot, 1)))
        say("  字形不同的字（前 70）: %s" % "".join(diffs))
        say("")
        say("  含义：若改用项目根那份当源，这 %d 个字的形状会与**未改动版游戏**看起来不一样。" % diff)
    for f, _ in fonts.values():
        f.close()
    (HERE / "out" / "cmp851.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
