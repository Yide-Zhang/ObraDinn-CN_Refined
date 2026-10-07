#!/usr/bin/env python3
"""生成「改动前后人名对照图」（PNG）—— 极简版。

只列 **有改动的全名**（v4 精修名 != v1 当前名），按船员名册顺序，两列、每列 10 个：

    原名 -> 现名
        (英文名)

配色只用两种（用户指定）: 底色 #333319 / 前景 #E5FFFF
字体用一直在用的那套: 中文 = 思源宋体 SemiBold，英文 = 游戏本体 IM FELL (IMFeENrm28P)

用法: python CN_Refined/langpack/make_name_diff_chart.py [表文件] [--out 输出.png]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_TSV = HERE / "extracted" / "crew_name_variants.tsv"
DEFAULT_OUT = HERE.parent / "out" / "name_diff_chart.png"

BG = (0x33, 0x33, 0x19)
FG = (0xE5, 0xFF, 0xFF)

FONT_ZH = [ROOT / "font_src" / "SOURCEHANSERIFSC-SEMIBOLD.OTF",
           ROOT / "gui" / "fonts" / "SourceHanSerifSC-SemiBold-subset.otf"]
FONT_EN = [ROOT / "font_src" / "IMFeENrm28P.ttf",
           ROOT / "gui" / "fonts" / "IMFeENrm28P.ttf"]


def pick(paths):
    for p in paths:
        if p.is_file():
            return str(p)
    return None


def font(paths, size):
    p = pick(paths)
    if p:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def runs(s: str):
    """按「中日韩字 / 其他」切段，好让中英各用各自的字体。"""
    out, cur, cur_zh = [], "", None
    for ch in s:
        is_zh = ord(ch) > 0x2E80
        if cur_zh is None or is_zh == cur_zh:
            cur, cur_zh = cur + ch, is_zh
        else:
            out.append((cur, cur_zh))
            cur, cur_zh = ch, is_zh
    if cur:
        out.append((cur, cur_zh))
    return out


def draw_mixed(d, x, y, s, f_zh, f_en, fill):
    """中英混排：中文用思源宋体，拉丁用 IM FELL。"""
    for run, is_zh in runs(s):
        f = f_zh if is_zh else f_en
        d.text((x, y), run, font=f, fill=fill)
        x += d.textlength(run, font=f)
    return x


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", default=str(DEFAULT_TSV))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    raw = Path(args.tsv).read_bytes().decode("utf-8")
    pairs = []
    for ln in raw.replace("\r\n", "\n").split("\n"):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t")
        if len(f) < 7 or f[0].strip() == "[]键":
            continue
        key, en, v1, v4 = f[0], f[1], f[2].strip(), f[5].strip()
        if key.endswith("Short]") or key.endswith("Dia]"):
            continue
        if not v1 or not v4 or v4 == v1:
            continue
        pairs.append((v1, v4, en.split("|")[0].strip()))

    if not pairs:
        print("没有改动的全名")
        return 1

    zh_name = pick(FONT_ZH)
    en_name = pick(FONT_EN)
    if not zh_name or not en_name:
        print("[X] 找不到字体: zh=%s en=%s" % (zh_name, en_name))
        return 1
    print("字体: %s | %s" % (Path(zh_name).name, Path(en_name).name))

    f_title = ImageFont.truetype(zh_name, 30)
    f_big = ImageFont.truetype(zh_name, 27)      # 原名 / 现名
    f_en = ImageFont.truetype(en_name, 22)       # (英文名)

    COLS = 2
    PER_COL = -(-len(pairs) // COLS)             # 向上取整：21 条 -> 11+10
    MARGIN, GAP = 48, 44
    ROW_H = 76
    IND = 26                                     # 英文名缩进
    AGAP = 18                                    # 老名与箭头之间的最小间隙

    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    OLD_W = max(int(probe.textlength(v1, font=f_big)) for v1, _, _ in pairs)
    NEW_W = max(int(probe.textlength(v4, font=f_big)) for _, v4, _ in pairs)
    ARR_W = int(probe.textlength("→", font=f_big))
    COL_W = OLD_W + AGAP + ARR_W + AGAP + NEW_W

    HEAD = 124
    W = MARGIN * 2 + COL_W * COLS + GAP * (COLS - 1)
    H = HEAD + ROW_H * PER_COL + 44

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 标题
    d.text((MARGIN, 34), "人名改动对照", font=f_title, fill=FG)
    d.rectangle((MARGIN, 88, W - MARGIN, 90), fill=FG)

    # 两列 × 每列 PER_COL 个（先左列自上而下，再右列）；箭头对齐到固定列
    for idx, (v1, v4, en) in enumerate(pairs):
        c, r = divmod(idx, PER_COL)
        if c >= COLS:
            break
        x = MARGIN + c * (COL_W + GAP)
        y = HEAD + r * ROW_H
        d.text((x, y), v1, font=f_big, fill=FG)
        ax = x + OLD_W + AGAP
        d.text((ax, y), "→", font=f_big, fill=FG)
        d.text((ax + ARR_W + AGAP, y), v4, font=f_big, fill=FG)
        d.text((x + IND, y + 36), "(" + en + ")", font=f_en, fill=FG)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print("已生成 %s  (%dx%d, %d 条)" % (out, W, H, len(pairs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
