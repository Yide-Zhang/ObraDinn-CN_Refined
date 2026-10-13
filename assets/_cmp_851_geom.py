# -*- coding: utf-8 -*-
"""项目根 `851tegakizatsu.otf` 与游戏内嵌 851tegaki：**几何级**逐字比对。

既不能只比轮廓哈希（FontForge 把二次曲线转成三次，每个字的记录都会变），
也不能只比渲染图（TTF 与 CFF 的 hinting 不同，会造出一大片假的"2px 差"）。

办法：用 BasePen 把轮廓**按曲线采样展平**成多边形（二次/三次都统一），然后比几何量：
  ① 包围盒（四条边各容忍 2 单位，upem=1024 ≈ 0.2%）
  ② 轮廓条数
  ③ 各轮廓 |面积| 之和、周长（相对差 < 0.5%）
三项都在容忍内 = 同一形状（只是曲线表述不同）；否则 = 真的不一样。

用法: python CN_Refined\\assets\\_cmp_851_geom.py [--limit N]
产物: out\\cmp851geom.txt + out\\verify\\cmp851-top.png（差异最大的几个）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fontTools.pens.basePen import BasePen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EMB = HERE / "out" / "fonts" / "orig-851tegaki_zatsu_normal_0883.ttf"
PROJ = ROOT / "851tegakizatsu.otf"

sys.path.insert(0, str(HERE))
import make_subset_fonts as MS  # noqa: E402

STEPS = 24
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


class FlatPen(BasePen):
    """BasePen 会把 qCurveTo/curveTo 拆成 _qCurveToOne/_curveToOne（复合字形也会展开）"""

    def __init__(self, glyphSet):
        super().__init__(glyphSet)
        self.contours: list[list[tuple[float, float]]] = []

    def _moveTo(self, p):
        self.contours.append([(float(p[0]), float(p[1]))])

    def _lineTo(self, p):
        self.contours[-1].append((float(p[0]), float(p[1])))

    def _curveToOne(self, c1, c2, p3):
        p0 = self.contours[-1][-1]
        for i in range(1, STEPS + 1):
            t = i / STEPS
            u = 1 - t
            x = (u ** 3) * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0]
            y = (u ** 3) * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1]
            self.contours[-1].append((x, y))

    def _qCurveToOne(self, c1, p2):
        p0 = self.contours[-1][-1]
        for i in range(1, STEPS + 1):
            t = i / STEPS
            u = 1 - t
            x = u * u * p0[0] + 2 * u * t * c1[0] + t * t * p2[0]
            y = u * u * p0[1] + 2 * u * t * c1[1] + t * t * p2[1]
            self.contours[-1].append((x, y))

    def _closePath(self):
        pass

    def _endPath(self):
        pass


def geom(font, ch: str):
    cmap = font.getBestCmap()
    gname = cmap.get(ord(ch))
    if not gname:
        return None
    gs = font.getGlyphSet()
    pen = FlatPen(gs)
    gs[gname].draw(pen)
    pts = [p for c in pen.contours for p in c]
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    area = per = 0.0
    for c in pen.contours:
        a = 0.0
        n = len(c)
        for i in range(n):
            x1, y1 = c[i]
            x2, y2 = c[(i + 1) % n]
            a += x1 * y2 - x2 * y1
            per += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        area += abs(a / 2.0)
    return {
        "bbox": (min(xs), min(ys), max(xs), max(ys)),
        "nc": len(pen.contours),
        "area": area,
        "per": per,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    from fontTools.ttLib import TTFont

    if not (EMB.exists() and PROJ.exists()):
        say("✗ 缺字体文件")
        (HERE / "out" / "cmp851geom.txt").write_text("\n".join(lines), encoding="utf-8-sig")
        return 1
    fa, fb = TTFont(str(EMB), lazy=True), TTFont(str(PROJ), lazy=True)
    say("几何级比对：项目根 851tegakizatsu.otf  vs  游戏内嵌 851tegaki")
    say("=" * 96)
    say("  %-22s %6d 字形  upem=%d" % ("游戏内嵌", fa["maxp"].numGlyphs, fa["head"].unitsPerEm))
    say("  %-22s %6d 字形  upem=%d" % ("项目根", fb["maxp"].numGlyphs, fb["head"].unitsPerEm))
    say("  容忍：包围盒每条边 ±2 单位；轮廓数必须相同；面积/周长相对差 < 0.5%")
    say("")

    charset, _ = MS.collect_chars()
    chars = sorted(c for c in charset if MS.CJK_CHAR(c) and not c.isspace())
    if args.limit:
        chars = chars[:args.limit]
    same, diff, miss = 0, [], 0
    for ch in chars:
        ga, gb = geom(fa, ch), geom(fb, ch)
        if ga is None or gb is None:
            miss += 1
            continue
        box_ok = all(abs(x - y) <= 2 for x, y in zip(ga["bbox"], gb["bbox"]))
        nc_ok = ga["nc"] == gb["nc"]
        ar = abs(ga["area"] - gb["area"]) / max(ga["area"], 1.0)
        pr = abs(ga["per"] - gb["per"]) / max(ga["per"], 1.0)
        if box_ok and nc_ok and ar < 0.005 and pr < 0.005:
            same += 1
        else:
            score = max(ar, pr, 0.0) * 100
            if not box_ok:
                score += 100
            if not nc_ok:
                score += 100
            diff.append((score, ch, ga, gb, ar, pr, box_ok, nc_ok))
    diff.sort(key=lambda t: -t[0])
    say("一致（形状相同，仅曲线表述不同）: %d 字" % same)
    say("**形状真的不同**: %d 字   缺字: %d" % (len(diff), miss))
    if diff:
        say("")
        say("  %-4s %-7s %-6s %-6s %-22s %-22s" % ("字", "面积差", "周长差", "轮廓", "游戏内嵌 bbox", "项目根 bbox"))
        for _s, ch, ga, gb, ar, pr, box_ok, nc_ok in diff[:40]:
            say("  %-4s %6.2f%% %6.2f%% %2d→%-4d (%4d,%4d,%5d,%5d) → (%4d,%4d,%5d,%5d)%s%s"
                % (ch, ar * 100, pr * 100, ga["nc"], gb["nc"],
                   *ga["bbox"], *gb["bbox"],
                   "" if box_ok else " 包围盒✗", "" if nc_ok else " 轮廓数✗"))
        say("")
        say("  全部形状不同的字: %s" % "".join(t[1] for t in diff))
    fa.close()
    fb.close()
    (HERE / "out" / "cmp851geom.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
