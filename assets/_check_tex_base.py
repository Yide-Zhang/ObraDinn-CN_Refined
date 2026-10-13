# -*- coding: utf-8 -*-
"""核对成品图的基准：是不是**以用户做的四张全图**为底。

三方对照（像素级）：
  A = 用户全图      CN_Refined\\Textures\\<tex>.png
  B = 官方 zh-s 包   originalassets\\langpacks\\lang-zh-s 里的 Texture2D（原版）
  C = 我们的成品     CN_Refined\\out\\textures\\<tex>-<name>-<region>.png

要看的两个数：
  ① C vs A 的差异是否**只落在碎片矩形内**（是 → 基准就是 A ✓）
  ② A vs B 在碎片矩形**之外**差多少（= 用户全图相对官方重绘了多少）

用法: python CN_Refined\\assets\\_check_tex_base.py
产物: CN_Refined\\assets\\out\\texbase.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import UnityPy
from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TEX = ROOT / "CN_Refined" / "Textures"
OURS = ROOT / "CN_Refined" / "out" / "textures"
OFFICIAL = ROOT / "CN_Refined" / "originalassets" / "langpacks" / "lang-zh-s"
META = TEX / "fragments" / "fragments.json"
NAMES = ["ManifestCrew", "FolioSketch", "FolioDeck", "FolioChart"]
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def official_images() -> dict:
    env = UnityPy.load(str(OFFICIAL))
    out = {}
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        d = o.read()
        nm = getattr(d, "m_Name", "")
        if nm in NAMES:
            out[nm] = d.image.convert("RGBA")
    return out


def rects() -> dict:
    """从 fragments.json 取各纹理的碎片矩形"""
    meta = json.loads(META.read_text(encoding="utf-8"))
    out: dict[str, list] = {}
    for key, info in meta.items():
        nm = Path(key).stem
        for frag in (info if isinstance(info, list) else info.get("fragments", [])):
            r = frag.get("rect") or frag
            out.setdefault(nm, []).append((int(r["x"]), int(r["y"]),
                                           int(r["w"]), int(r["h"])))
    return out


def inside(x: int, y: int, rs: list) -> bool:
    return any(rx <= x < rx + rw and ry <= y < ry + rh for rx, ry, rw, rh in rs)


def compare(a: Image.Image, b: Image.Image, rs: list, tag: str) -> None:
    """逐像素比，分别统计「碎片内」与「碎片外」的差异数"""
    if a.size != b.size:
        say("  %-34s ✗ 尺寸不同 %s vs %s" % (tag, a.size, b.size))
        return
    pa, pb = a.load(), b.load()
    W, H = a.size
    din = dout = 0
    for y in range(H):
        for x in range(W):
            if pa[x, y] != pb[x, y]:
                if inside(x, y, rs):
                    din += 1
                else:
                    dout += 1
    say("  %-34s 差异: 碎片内 %-8d 碎片外 %-8d %s"
        % (tag, din, dout, "✓ 只差在碎片内" if dout == 0 else "← 碎片外也有差异"))


def main() -> int:
    off = official_images()
    rs = rects()
    say("成品图基准核对（A=用户全图 / B=官方 zh-s / C=我们的成品）")
    say("=" * 96)
    say("fragments.json 里的碎片矩形: %s"
        % {k: v for k, v in sorted(rs.items())})
    say("")
    ok = True
    for nm in NAMES:
        a_p = TEX / ("%s.png" % nm)
        if not a_p.exists() or nm not in off:
            say("%s: ⚠ 缺图（用户全图 %s / 官方包里 %s）"
                % (nm, a_p.exists(), nm in off))
            continue
        a = Image.open(a_p).convert("RGBA")
        b = off[nm]
        say("%s   用户全图 %s   官方包 %s" % (nm, a.size, b.size))
        compare(a, b, rs.get(nm, []), "A 用户全图 vs B 官方包")
        # 我方成品（ManifestCrew 三种姓名轴取 refined；FolioSketch 取 unharm）
        for c_p in sorted(OURS.glob("%s-*.png" % nm)):
            c = Image.open(c_p).convert("RGBA")
            compare(c, a, rs.get(nm, []), "C %s vs A 用户全图" % c_p.stem)
            compare(c, b, rs.get(nm, []), "C %s vs B 官方包" % c_p.stem)
        say("")
    if OURS.exists():
        say("我方成品目录里有 %d 张：%s"
            % (len(list(OURS.glob('*.png'))), ", ".join(sorted(p.name for p in OURS.glob("*.png")))))
    (HERE / "out" / "texbase.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii() or True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
