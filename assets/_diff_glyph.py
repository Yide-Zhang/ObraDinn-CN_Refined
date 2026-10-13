# -*- coding: utf-8 -*-
"""对比某几个字的**字形**：游戏里原始的 851tegaki vs 我们这个版（以及 dev / SC 宋体作参照）。

回答的问题：同一个「船」字，游戏原始内嵌的手写体画出来的，和我们现在装进去的那支画出来的，
到底一不一样。

三层证据：
  1. cmap 有没有这个码位、字形名、字形索引
  2. fontTools 把轮廓**录一遍**（RecordingPen）→ 哈希；同一哈希 = 同一条轮廓
     （会展开复合字形，所以「复合/独立」这种写法差异不算差异）
  3. FreeType 真实渲染成图 → 逐像素比

用法:
  python CN_Refined\\assets\\_diff_glyph.py             # 默认比「船」
  python CN_Refined\\assets\\_diff_glyph.py 船 舟 艘
产物: CN_Refined\\assets\\out\\glyphdiff.txt  +  out\\verify\\glyph-<字>.png
"""
from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

import UnityPy
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OA = ROOT / "CN_Refined" / "originalassets"
DEV = ROOT / "CN_Refined" / "olddevassets"
MINE = ROOT / "CN_Refined" / "out" / "assets"
OUTF = HERE / "out" / "fonts"
VER = HERE / "out" / "verify"

# (短标签, 来源)  来源 = ("assets", 路径, Font对象名) 或 ("file", 路径) 或 ("data", bytes)
SRC = [
    ("G851", ("assets", OA / "sharedassets2.assets", "851tegaki_zatsu_normal_0883")),
    ("O851", ("assets", MINE / "sharedassets2.assets", "851tegaki_zatsu_normal_0883")),
    ("D851", ("assets", DEV / "sharedassets2.assets", "851tegaki_zatsu_normal_0883")),
    ("SCserif", ("file", ROOT / "font_src" / "SOURCEHANSERIFSC-SEMIBOLD.OTF")),
    ("Gserif", ("assets", OA / "sharedassets0.assets", "SourceHanSerif-SemiBold")),
]
LEGEND = {
    "G851": "游戏原始 851tegaki（未改动）",
    "O851": "我们这版 851tegaki（已装进游戏）",
    "D851": "你 dev 的 851tegaki",
    "SCserif": "font_src 思源宋体 SC（正文用）",
    "Gserif": "游戏原始 思源宋体（日式形态）",
}
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def load(kind) -> tuple[str, bytes]:
    if kind[0] == "file":
        p: Path = kind[1]
        return (p.stem, p.read_bytes()) if p.exists() else ("", b"")
    _, assets, fname = kind
    if not assets.exists():
        return "", b""
    env = UnityPy.load(str(assets))
    for o in env.objects:
        if o.type.name == "Font":
            d = o.read()
            if getattr(d, "m_Name", "") == fname:
                return fname, bytes(d.m_FontData)
    return "", b""


def outline_sig(font: TTFont, ch: str):
    gname = font.getBestCmap().get(ord(ch))
    if not gname:
        return None, None, 0, 0
    pen = RecordingPen()
    font.getGlyphSet()[gname].draw(pen)
    sig = hashlib.sha256(repr(pen.value).encode()).hexdigest()[:12]
    moves = sum(1 for op, _ in pen.value if op == "moveTo")
    pts = sum(len(args[0]) for op, args in pen.value if op.endswith("To") and args)
    return sig, gname, moves, pts


def main() -> int:
    chars = sys.argv[1:] or ["船"]
    VER.mkdir(parents=True, exist_ok=True)
    say("字形对比（同一哈希 / 同一像素 = 同一字形）")
    say("=" * 96)
    for tag, kind in SRC:
        say("  %-8s %s" % (tag, LEGEND[tag]))
    say("")

    fonts: dict[str, tuple[Path, bytes]] = {}
    for tag, kind in SRC:
        name, data = load(kind)
        if not data:
            say("✗ %s 取不到字体数据" % tag)
            continue
        p = OUTF / ("_diff-%s.%s" % (tag, "otf" if data[:4] == b"OTTO" else "ttf"))
        p.write_bytes(data)
        fonts[tag] = (p, data)

    for ch in chars:
        say("-" * 96)
        say("字: %s  U+%04X" % (ch, ord(ch)))
        rows = []
        for tag, (p, data) in fonts.items():
            f = TTFont(str(p), lazy=True)
            sig, gname, moves, pts = outline_sig(f, ch)
            gid = "-"
            if gname:
                order = f.getGlyphOrder()
                gid = order.index(gname)
            f.close()
            rows.append((tag, sig, gname, gid, moves, pts, len(data)))
            say("  %-8s cmap=%-6s 字形名=%-12s gid=%-6s 轮廓哈希=%-13s 子路径=%-3d 点=%-4d"
                % (tag, "有" if sig else "**无**", gname or "-", gid, sig or "-", moves, pts))
        # 结论
        base = next((r for r in rows if r[0] == "G851"), None)
        ours = next((r for r in rows if r[0] == "O851"), None)
        if base and ours:
            if not base[1] and not ours[1]:
                say("  → 两边都没有这个字（都不会画）")
            elif base[1] == ours[1]:
                say("  → 游戏原始 与 我们这版 **完全同一轮廓** ✓ 没有区别")
            else:
                say("  → **轮廓不同** ✗ 需查（轮廓哈希 %s vs %s）" % (base[1], ours[1]))

        # 渲染图
        W, H = 120, 150
        img = Image.new("L", (W * len(fonts) + 8, H + 26), 255)
        dr = ImageDraw.Draw(img)
        for i, (tag, (p, _)) in enumerate(fonts.items()):
            try:
                fnt = ImageFont.truetype(str(p), 96)
            except Exception as e:                        # noqa: BLE001
                say("  ✗ %s FreeType 打不开: %s" % (tag, e))
                continue
            dr.text((8 + i * W + 20, 10), ch, font=fnt, fill=0)
            dr.text((8 + i * W + 6, H + 4), tag, fill=0)
        out = VER / ("glyph-%s.png" % ch)
        img.save(out)
        say("  渲染图: %s   （左→右: %s）" % (out, " / ".join(fonts)))

        # 逐像素比：游戏原始 vs 我们这版
        if "G851" in fonts and "O851" in fonts:
            try:
                buf = []
                for tag in ("G851", "O851"):
                    im = Image.new("L", (W, H), 255)
                    d2 = ImageDraw.Draw(im)
                    d2.text((20, 10), ch, font=ImageFont.truetype(str(fonts[tag][0]), 96), fill=0)
                    buf.append(im)
                px = [(a, b) for a, b in zip(buf[0].getdata(), buf[1].getdata()) if a != b]
                ink0 = sum(1 for v in buf[0].getdata() if v < 128)
                ink1 = sum(1 for v in buf[1].getdata() if v < 128)
                say("  逐像素: 不同像素 %d 个（墨迹 %d vs %d）%s"
                    % (len(px), ink0, ink1, "✓ 渲染完全一致" if not px else "⚠ 有差异"))
            except Exception as e:                        # noqa: BLE001
                say("  逐像素比对失败: %s" % e)
        say("")

    text = "\n".join(lines)
    (HERE / "out" / "glyphdiff.txt").write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
