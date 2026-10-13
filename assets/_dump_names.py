# -*- coding: utf-8 -*-
"""打印各字体 name 表的 family/subfamily/full/PS 名 + CFF 名，用于和 Unity 的 m_FontNames 对照。

用法: python CN_Refined\\assets\\_dump_names.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FONTS = [
    ("游戏原始 Serif(能用)", ROOT / "CN_Refined" / "assets" / "out" / "fonts" / "orig-SourceHanSerif-SemiBold.otf"),
    ("我 SC 子集(回落)", ROOT / "CN_Refined" / "assets" / "out" / "subsets" / "SourceHanSerif-SemiBold.otf"),
    ("font_src SC 源", ROOT / "font_src" / "SOURCEHANSERIFSC-SEMIBOLD.OTF"),
    ("游戏原始 851(能用)", ROOT / "CN_Refined" / "assets" / "out" / "fonts" / "orig-851tegaki_zatsu_normal_0883.ttf"),
    ("我 851 子集", ROOT / "CN_Refined" / "assets" / "out" / "subsets" / "851tegaki_zatsu_normal_0883.otf"),
    ("dev Serif(能用)", ROOT / "CN_Refined" / "olddevassets" / "_fonts" / "SourceHanSerif-SemiBold.otf"),
    ("dev 851(能用)", ROOT / "CN_Refined" / "olddevassets" / "_fonts" / "851tegaki_zatsu_normal_0883.otf"),
]
# 有些路径可能不存在 → 兜底：去 olddevassets 里现取
NAMES = {1: "family", 2: "subfamily", 3: "uid", 4: "full", 6: "postscript", 16: "typoFamily", 17: "typoSub"}
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def dump(tag: str, p: Path) -> None:
    if not p.exists():
        say("%-22s ✗ 不存在 %s" % (tag, p))
        return
    try:
        f = TTFont(str(p), lazy=True)
    except Exception as e:                              # noqa: BLE001
        say("%-22s ✗ 打不开 %s" % (tag, e))
        return
    say("=" * 76)
    say("%s\n  %s  (%.2f MB)" % (tag, p.name, p.stat().st_size / 1048576))
    if "CFF " in f:
        cff = f["CFF "].cff
        say("  CFF 顶层 fontNames=%s" % list(cff.fontNames))
        td = cff[cff.fontNames[0]]
        say("  CFF ROS=%s / FamilyName=%r FullName=%r"
            % (getattr(td, "ROS", None), getattr(td, "FamilyName", None), getattr(td, "FullName", None)))
    if "name" in f:
        got: dict[str, list[str]] = {}
        for rec in f["name"].names:
            if rec.nameID in NAMES:
                try:
                    s = rec.toUnicode()
                except Exception:                       # noqa: BLE001
                    s = repr(rec.string)
                got.setdefault("%d(%s)%s" % (rec.nameID, NAMES[rec.nameID],
                                             "" if rec.platformID == 3 else "/mac"), []).append(s)
        for k in sorted(got, key=lambda x: (int(x.split("(")[0]), x)):
            say("  name %-22s %s" % (k, " | ".join(sorted(set(got[k])))))
    else:
        say("  ✗ 没有 name 表")


def main() -> int:
    for tag, p in FONTS:
        dump(tag, p)
    text = "\n".join(lines)
    (HERE / "out" / "fontnames.txt").write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
