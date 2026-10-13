# -*- coding: utf-8 -*-
"""打印各字体 name 表的 family/subfamily/full/PS 名 + CFF 名，用于和 Unity 的 m_FontNames 对照。

Unity 的 Font 对象里有 m_FontNames（例如 SourceHanSerif-SemiBold 的 m_FontNames=['Source Han Serif']）。
动态字体加载时 Unity 会拿**字体内部的 family 名**去对 m_FontNames，对不上就判定字体不可用 →
回落系统字体（中文 Windows = Microsoft YaHei）。所以要挨个看名字。

用法: python CN_Refined\\assets\\_dump_names2.py
产物: CN_Refined\\assets\\out\\fontnames.txt
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import UnityPy
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OA = ROOT / "CN_Refined" / "originalassets"
DEV = ROOT / "CN_Refined" / "olddevassets"
MINE = ROOT / "CN_Refined" / "out" / "assets"

# (标签, ("file", 路径) 或 ("assets", assets路径, 字体对象名))
SRC = [
    ("游戏原始 Serif(能用)", ("assets", OA / "sharedassets0.assets", "SourceHanSerif-SemiBold")),
    ("dev   Serif(能用)", ("assets", DEV / "sharedassets0.assets", "SourceHanSerif-SemiBold")),
    ("我     Serif(回落)", ("assets", MINE / "sharedassets0.assets", "SourceHanSerif-SemiBold")),
    ("font_src SC 源", ("file", ROOT / "font_src" / "SOURCEHANSERIFSC-SEMIBOLD.OTF")),
    ("游戏原始 851(能用)", ("assets", OA / "sharedassets2.assets", "851tegaki_zatsu_normal_0883")),
    ("dev    851(能用)", ("assets", DEV / "sharedassets2.assets", "851tegaki_zatsu_normal_0883")),
    ("我      851", ("assets", MINE / "sharedassets2.assets", "851tegaki_zatsu_normal_0883")),
]
NAMES = {0: "copyright", 1: "family", 2: "subfamily", 3: "uid", 4: "full",
         6: "postscript", 16: "typoFamily", 17: "typoSub", 18: "macFamily",
         20: "macPS", 21: "wwsFamily", 22: "wwsSub"}
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def get_bytes(kind) -> bytes:
    if kind[0] == "file":
        p: Path = kind[1]
        return p.read_bytes() if p.exists() else b""
    _, assets, fname = kind
    if not assets.exists():
        return b""
    env = UnityPy.load(str(assets))
    for o in env.objects:
        if o.type.name == "Font":
            d = o.read()
            if d.m_Name == fname or fname in d.m_FontNames:
                return bytes(d.m_FontData)
    return b""


def dump(tag: str, kind) -> None:
    data = get_bytes(kind)
    say("=" * 78)
    if not data:
        say("%-20s ✗ 取不到字体数据（路径或对象名不对）" % tag)
        return
    try:
        f = TTFont(io.BytesIO(data), lazy=True)
    except Exception as e:                                # noqa: BLE001
        say("%-20s ✗ 不是可解析字体: %s" % (tag, e))
        return
    say("%-20s  %.2f MB  sfnt=%s  表 %d 个"
        % (tag, len(data) / 1048576, f.sfntVersion.strip(), len(f.keys())))
    for key in ("CFF ", "CFF2"):
        if key in f:
            cff = f[key].cff
            fn = list(cff.fontNames)
            top = cff[fn[0]]
            say("    CFF  fontNames   = %s" % fn)
            say("    CFF  FamilyName  = %r   FullName = %r"
                % (getattr(top, "FamilyName", None), getattr(top, "FullName", None)))
            ros = getattr(top, "ROS", None)
            if ros:
                say("    CFF  ROS         = %s（CID-keyed）" % (ros,))
            subrs = getattr(top, "Subrs", None)
            say("    子程序个数      = %d%s" % (len(subrs or []), "" if subrs else "（已展平）"))
    if "name" in f:
        got: dict[str, list[str]] = {}
        for rec in f["name"].names:
            if rec.nameID not in NAMES:
                continue
            try:
                s = rec.toUnicode()
            except Exception:                             # noqa: BLE001
                s = repr(rec.string)
            key = "name %-2d %-11s%s" % (rec.nameID, NAMES[rec.nameID],
                                         "" if rec.platformID == 3 else "/mac")
            got.setdefault(key, []).append(s)
        for k in sorted(got, key=lambda x: (int(x.split()[1]), x)):
            say("    %-26s %s" % (k, " | ".join(sorted(set(got[k])))))
    f.close()


def main() -> int:
    say("各字体身份名对照（重点看 family / full / postscript 和 Unity 的 m_FontNames 对不对得上）")
    for tag, kind in SRC:
        dump(tag, kind)
    text = "\n".join(lines)
    (HERE / "out" / "fontnames.txt").write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
