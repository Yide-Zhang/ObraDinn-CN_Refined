# -*- coding: utf-8 -*-
"""**看得见吗**：项目根 `851tegakizatsu.otf` 与游戏内嵌 851tegaki，逐字做真实渲染比对。

为什么不能只比轮廓哈希：项目那份是 FontForge 转的 CFF，二次曲线→三次曲线后
**每个字**的轮廓记录都会变（所以哈希 100% 不同），但形状可能完全一样。

做法：两支字体都 FreeType 渲染成 256px 灰度图 →
  ① 取**墨迹包围盒**（bbox）尺寸差 —— 形状变了/变大变小就会露出来
  ② 按 bbox 对齐后逐像素比 —— 笔画位置/粗细变了就会露出来
判定「看得见」：bbox 宽或高差 > 2px，或对齐后墨迹差异 > 2%

用法: python CN_Refined\\assets\\_cmp_851_visual.py [--limit N] [--thresh 0.02]
产物: CN_Refined\\assets\\out\\cmp851visual.txt + out\\verify\\cmp851-diff.png（差异最大的几张）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EMB = HERE / "out" / "fonts" / "orig-851tegaki_zatsu_normal_0883.ttf"
PROJ = ROOT / "851tegakizatsu.otf"
VER = HERE / "out" / "verify"
SZ = 256

sys.path.insert(0, str(HERE))
import make_subset_fonts as MS  # noqa: E402

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def render(p: Path, ch: str) -> Image.Image:
    """渲染成灰度图，白底黑字"""
    im = Image.new("L", (SZ * 2, SZ * 2), 255)
    f = ImageFont.truetype(str(p), SZ)
    ImageDraw.Draw(im).text((SZ // 2, SZ // 2), ch, font=f, fill=0)
    return im


def ink_crop(im: Image.Image):
    bbox = ImageChops.difference(im, Image.new("L", im.size, 255)).getbbox()
    if bbox is None:
        return None, (0, 0)
    return im.crop(bbox), (bbox[2] - bbox[0], bbox[3] - bbox[1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只测前 N 个字（默认全部）")
    ap.add_argument("--thresh", type=float, default=0.02, help="墨迹差异阈值（默认 2%%）")
    args = ap.parse_args()
    if not (EMB.exists() and PROJ.exists()):
        say("✗ 缺字体文件: %s / %s" % (EMB, PROJ))
        (HERE / "out" / "cmp851visual.txt").write_text("\n".join(lines), encoding="utf-8-sig")
        return 1

    charset, _ = MS.collect_chars()
    chars = sorted(c for c in charset if MS.CJK_CHAR(c) and not c.isspace())
    if args.limit:
        chars = chars[:args.limit]
    say("项目根 851tegakizatsu.otf  vs  游戏内嵌 851tegaki —— 渲染级比对（%d 字，%dpx）"
        % (len(chars), SZ))
    say("=" * 96)
    say("判定「看得见」= bbox 宽或高差 > 2px，或按 bbox 对齐后墨迹差异 > %.0f%%" % (args.thresh * 100))
    say("")

    visible: list[tuple[float, int, str, int, int, int, int]] = []   # (ratio, dsize, ch, w1,h1,w2,h2)
    same = 0
    for i, ch in enumerate(chars):
        a, (w1, h1) = ink_crop(render(EMB, ch))
        b, (w2, h2) = ink_crop(render(PROJ, ch))
        if a is None or b is None:
            continue
        W, H = max(a.width, b.width), max(a.height, b.height)
        ca = Image.new("L", (W, H), 255)
        cb = Image.new("L", (W, H), 255)
        ca.paste(a, (0, 0))
        cb.paste(b, (0, 0))
        d = ImageChops.difference(ca, cb)
        big = sum(1 for v in d.getdata() if v > 64)
        ink = max(1, sum(1 for v in ca.getdata() if v < 128))
        ratio = big / ink
        dsize = max(abs(w1 - w2), abs(h1 - h2))
        if dsize > 2 or ratio > args.thresh:
            visible.append((ratio, dsize, ch, w1, h1, w2, h2))
        else:
            same += 1
        if (i + 1) % 500 == 0:
            print("  ...%d/%d" % (i + 1, len(chars)), flush=True)

    visible.sort(key=lambda t: (-t[0], -t[1]))
    say("一致（看不出）: %d 字" % same)
    say("**看得出不同**: %d 字  （占 %.1f%%）"
        % (len(visible), 100.0 * len(visible) / max(len(chars), 1)))
    if visible:
        say("")
        say("  %-4s %-6s %-6s %-14s %s" % ("字", "墨差", "尺寸差", "游戏内嵌 w×h", "项目根 w×h"))
        for ratio, dsize, ch, w1, h1, w2, h2 in visible[:50]:
            say("  %-4s %5.1f%% %5dpx  %5d×%-5d  %5d×%-5d" % (ch, ratio * 100, dsize, w1, h1, w2, h2))
        say("")
        say("  全部有差异的字: %s" % "".join(t[2] for t in visible))
        # 差异最大的 8 个出图
        n = min(8, len(visible))
        cell = 200
        sheet = Image.new("RGB", (cell * n + 8, cell * 2 + 40), (255, 255, 255))
        sd = ImageDraw.Draw(sheet)
        for i, (_r, _d, ch, *_rest) in enumerate(visible[:n]):
            for row, p in ((0, EMB), (1, PROJ)):
                im = render(p, ch).resize((SZ // 2, SZ // 2))
                sheet.paste(im.convert("RGB"), (i * cell + 4, row * cell))
            sd.text((i * cell + 6, cell * 2 + 6), "%s  上=游戏内嵌 下=项目根" % ch, fill=(0, 0, 0))
        VER.mkdir(parents=True, exist_ok=True)
        sheet.save(VER / "cmp851-diff.png")
        say("  差异最大 8 字对比图: %s" % (VER / "cmp851-diff.png"))
    (HERE / "out" / "cmp851visual.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
