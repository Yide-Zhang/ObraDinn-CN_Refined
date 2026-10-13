# -*- coding: utf-8 -*-
"""把两份 851tegaki 形状不同的字出成对照图：上=游戏内嵌（原版），下=项目根那份。

用法: python CN_Refined\\assets\\_sheet_851_21.py
产物: CN_Refined\\assets\\out\\verify\\cmp851-21chars.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EMB = HERE / "out" / "fonts" / "orig-851tegaki_zatsu_normal_0883.ttf"
PROJ = ROOT / "851tegakizatsu.otf"
VER = HERE / "out" / "verify"
CHARS = "海船博将所迪詹达直毒敷屠航溺画舵窦角底睹包"
COLS, CELL = 7, 190
PAD = 150


def main() -> int:
    n = len(CHARS)
    rows = (n + COLS - 1) // COLS
    img = Image.new("RGB", (COLS * CELL + 8, rows * CELL * 2 + 56), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    fa = ImageFont.truetype(str(EMB), PAD)
    fb = ImageFont.truetype(str(PROJ), PAD)
    for i, ch in enumerate(CHARS):
        x = (i % COLS) * CELL + 8
        y = (i // COLS) * CELL * 2 + 30
        dr.text((x + 20, y), ch, font=fa, fill=(0, 0, 0))
        dr.text((x + 20, y + CELL), ch, font=fb, fill=(0, 0, 0))
    dr.text((8, 6), "UP = game embedded 851tegaki (vanilla)   DOWN = project 851tegakizatsu.otf", fill=(0, 0, 0))
    VER.mkdir(parents=True, exist_ok=True)
    img.save(VER / "cmp851-21chars.png")
    print("saved", VER / "cmp851-21chars.png", "ascii-only:", all(c.isascii() for c in CHARS) is False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
