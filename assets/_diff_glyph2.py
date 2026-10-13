# -*- coding: utf-8 -*-
"""对比某个字的**字形**：游戏内嵌 851tegaki vs 我们这版 vs 项目里其它 851 vs 宋体。

三层证据：
  1. cmap / 字形名 / 字形索引 / unitsPerEm
  2. fontTools 录轮廓（RecordingPen，会展开复合字形）→ 哈希；同一哈希 = 同一条轮廓
  3. FreeType 渲染 → ① 竖排大图 ② 与游戏内嵌原始的**叠色图**（黑=重合 / 蓝=原始 / 红=对方）

用法:
  python CN_Refined\\assets\\_diff_glyph2.py            # 默认比「船」
  python CN_Refined\\assets\\_diff_glyph2.py 船 舟
产物: out\\glyphdiff.txt + out\\verify\\glyph-<字>.png + out\\verify\\overlay-<字>.png
"""
from __future__ import annotations

import hashlib
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

# 顺序有意义：第 1 个是基准（游戏内嵌原始 851）
SRC = [
    ("G851", "游戏内嵌 851tegaki（原始）",
     ("assets", OA / "sharedassets2.assets", "851tegaki_zatsu_normal_0883")),
    ("O851", "我们这版 851tegaki（已装进游戏）",
     ("assets", MINE / "sharedassets2.assets", "851tegaki_zatsu_normal_0883")),
    ("D851", "你 dev 装的 851tegaki",
     ("assets", DEV / "sharedassets2.assets", "851tegaki_zatsu_normal_0883")),
    ("P851", "项目根 851tegakizatsu.otf",
     ("file", ROOT / "851tegakizatsu.otf")),
    ("I851", "instructor/fonts 851tegakizatsu-subset.otf",
     ("file", ROOT / "instructor" / "fonts" / "851tegakizatsu-subset.otf")),
    ("SCserif", "font_src 思源宋体 SC（正文本体）",
     ("file", ROOT / "font_src" / "SOURCEHANSERIFSC-SEMIBOLD.OTF")),
    ("Gserif", "游戏内嵌 思源宋体（日式形态）",
     ("assets", OA / "sharedassets0.assets", "SourceHanSerif-SemiBold")),
]
PX = 150
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def load(kind) -> bytes:
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
            if getattr(d, "m_Name", "") == fname:
                return bytes(d.m_FontData)
    return b""


def outline_sig(font: TTFont, ch: str):
    gname = font.getBestCmap().get(ord(ch))
    if not gname:
        return None, None, 0, 0
    pen = RecordingPen()
    font.getGlyphSet()[gname].draw(pen)
    sig = hashlib.sha256(repr(pen.value).encode()).hexdigest()[:12]
    moves = sum(1 for op, _ in pen.value if op == "moveTo")
    pts = sum(len(a[0]) for op, a in pen.value if op.endswith("To") and a)
    return sig, gname, moves, pts


def render(path: Path, ch: str) -> Image.Image | None:
    im = Image.new("L", (PX, PX), 255)
    try:
        f = ImageFont.truetype(str(path), int(PX * 0.72))
    except Exception:                                     # noqa: BLE001
        return None
    ImageDraw.Draw(im).text((PX * 0.18, PX * 0.12), ch, font=f, fill=0)
    return im


def main() -> int:
    chars = sys.argv[1:] or ["船"]
    VER.mkdir(parents=True, exist_ok=True)
    say("字形对比：游戏内嵌 851tegaki  vs  我们这版  vs  项目里其它 851  vs  宋体")
    say("=" * 104)

    fonts: dict[str, tuple[Path, bytes]] = {}
    for tag, desc, kind in SRC:
        data = load(kind)
        if not data:
            say("  %-8s ✗ 取不到字体数据 —— %s" % (tag, desc))
            continue
        p = OUTF / ("_diff-%s.%s" % (tag, "otf" if data[:4] == b"OTTO" else "ttf"))
        p.write_bytes(data)
        fonts[tag] = (p, data)
        say("  %-8s %s" % (tag, desc))
    say("")
    base_tag = "G851"

    for ch in chars:
        say("-" * 104)
        say("字: %s  U+%04X" % (ch, ord(ch)))
        rows = []
        for tag, (p, _data) in fonts.items():
            f = TTFont(str(p), lazy=True)
            sig, gname, moves, pts = outline_sig(f, ch)
            upem = f["head"].unitsPerEm
            gid = f.getGlyphOrder().index(gname) if gname else -1
            f.close()
            rows.append((tag, sig, gname, gid, moves, pts, upem))
            say("  %-8s cmap=%-5s 字形名=%-11s gid=%-6d 轮廓哈希=%-13s 子路径=%-3d 点=%-4d upem=%d"
                % (tag, "有" if sig else "**无**", gname or "-", gid, sig or "-", moves, pts, upem))
        base = next((r for r in rows if r[0] == base_tag), None)
        for r in rows:
            if r[0] == base_tag or base is None:
                continue
            if base[1] and r[1] == base[1]:
                say("  → %-8s 与游戏内嵌 **同一轮廓** ✓" % r[0])
            elif base[1] or r[1]:
                say("  → %-8s 与游戏内嵌 **轮廓不同** ✗" % r[0])
            else:
                say("  → %-8s 两边都没有这个字" % r[0])

        # 竖排大图
        sheet = Image.new("L", (PX + 200, (PX + 4) * len(fonts)), 255)
        sd = ImageDraw.Draw(sheet)
        for i, (tag, _) in enumerate(fonts.items()):
            im = render(fonts[tag][0], ch)
            if im is None:
                continue
            sheet.paste(im, (0, i * (PX + 4)))
            sig = next(r[1] for r in rows if r[0] == tag)
            note = "同游戏原始 ✓" if (base and sig == base[1]) else "轮廓不同 ✗"
            sd.text((PX + 10, i * (PX + 4) + PX // 2),
                    "%s %s  %s" % (tag, ("(无字形)" if not sig else ""), note), fill=0)
        sheet.save(VER / ("glyph-%s.png" % ch))
        say("  竖排图: %s" % (VER / ("glyph-%s.png" % ch)))

        # 叠色图：基准=蓝，对方=红，重合=黑
        if base_tag in fonts:
            bim = render(fonts[base_tag][0], ch)
            others = [t for t in fonts if t != base_tag]
            cols = 3
            rowsn = (len(others) + cols - 1) // cols
            ov = Image.new("RGB", (PX * cols + 8, (PX + 20) * rowsn), (255, 255, 255))
            od = ImageDraw.Draw(ov)
            for j, tag in enumerate(others):
                im = render(fonts[tag][0], ch)
                if im is None or bim is None:
                    continue
                x, y = (j % cols) * PX + 4, (j // cols) * (PX + 20)
                cell = Image.new("RGB", (PX, PX), (255, 255, 255))
                bp, ip, cp = bim.load(), im.load(), cell.load()
                for yy in range(PX):
                    for xx in range(PX):
                        a, b = bp[xx, yy] < 128, ip[xx, yy] < 128
                        cp[xx, yy] = ((0, 0, 0) if (a and b) else
                                      (0, 0, 255) if a else (255, 0, 0) if b else (255, 255, 255))
                ov.paste(cell, (x, y))
                od.text((x + 4, y + PX + 3), "%s vs 原始 (黑=重合 蓝=原始 红=这支)" % tag, fill=(0, 0, 0))
            ov.save(VER / ("overlay-%s.png" % ch))
            say("  叠色图: %s" % (VER / ("overlay-%s.png" % ch)))
        say("")

    (HERE / "out" / "glyphdiff.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
