# -*- coding: utf-8 -*-
"""
校验碎片与坐标：
1) 基准碎片 vs 原纹理在同坐标处的像素 —— 全等说明坐标/裁切精确，贴回去无缝
2) 从贴好的成品里把每处碎片区域 1:1 抠出来，存到 out/textures/_check/
用法: python CN_Refined\\langpack\\check_paste.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
TEXDIR = ROOT / "CN_Refined" / "Textures"
FRAGDIR = TEXDIR / "fragments"
META = FRAGDIR / "fragments.json"
OUTDIR = ROOT / "CN_Refined" / "out" / "textures"
CHKDIR = OUTDIR / "_check"

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def main() -> int:
    meta = json.loads(META.read_text(encoding="utf-8"))
    CHKDIR.mkdir(parents=True, exist_ok=True)
    bad = 0

    say("【1】基准碎片 与 原纹理同坐标区域 的像素比对")
    say("-" * 68)
    for tex_name, info in meta.items():
        stem = Path(tex_name).stem
        tex = Image.open(TEXDIR / tex_name).convert("RGBA")
        for f in sorted(info["fragments"], key=lambda f: f["id"]):
            p = FRAGDIR / f"{stem}_f{f['id']}.png"
            if not p.exists():
                say(f"  {tex_name} # {f['id']}  缺基准碎片")
                continue
            frag = Image.open(p).convert("RGBA")
            box = (f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"])
            region = tex.crop(box)
            if region.size != frag.size:
                say(f"  {tex_name} # {f['id']}  尺寸不符 {region.size} vs {frag.size}")
                bad += 1
                continue
            diff = ImageChops.difference(region, frag).convert("L")
            hist = diff.histogram()
            total = sum(hist)
            nonzero = total - hist[0]
            worst = max(i for i, c in enumerate(hist) if c)
            pct = 100.0 * nonzero / total
            tag = "全等 ✓" if nonzero == 0 else f"差异 {pct:.2f}%（最大 {worst}）"
            if nonzero:
                bad += 1
                # 存一张差异可视化
                diff.point(lambda v: min(255, v * 4)).save(CHKDIR / f"diff-{stem}-f{f['id']}.png")
            say(f"  {tex_name} # {f['id']}  {frag.width}×{frag.height} @({f['x']},{f['y']})  {tag}")

    say("")
    say("【2】成品里各碎片区域的 1:1 抠图")
    say("-" * 68)
    for out in sorted(OUTDIR.glob("*.png")):
        stem = out.stem
        tex_name = None
        for k in meta:
            if stem.startswith(Path(k).stem):
                tex_name = k
        if not tex_name:
            continue
        img = Image.open(out).convert("RGBA")
        for f in sorted(meta[tex_name]["fragments"], key=lambda f: f["id"]):
            pad = 12
            x0 = max(0, f["x"] - pad)
            y0 = max(0, f["y"] - pad)
            x1 = min(img.width, f["x"] + f["w"] + pad)
            y1 = min(img.height, f["y"] + f["h"] + pad)
            c = img.crop((x0, y0, x1, y1))
            name = f"crop-{stem}-f{f['id']}.png"
            c.save(CHKDIR / name)
            say(f"  {out.name} # {f['id']}  -> _check/{name}  {c.width}×{c.height}")

    say("")
    say("=" * 68)
    say("基准碎片与原纹理像素全等 → 坐标精确、贴回无缝" if bad == 0
        else f"有 {bad} 处不吻合（详见上方），差异图见 _check/")
    text = "\n".join(lines)
    print(text)
    (OUTDIR / "check_paste_report.txt").write_text(text + "\n", encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
