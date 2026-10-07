# -*- coding: utf-8 -*-
"""
交叉校验：姓名列碎片（两块对比）改动的行，是否与 TSV 一致。

名单排版是等距的：
    纹理坐标  第 n 行中心 y = ROW1_Y + (n-1) * PITCH
    （ROW1_Y=52, PITCH=26；由 base vs namerefined 的行带拟合得出 o≈8/9 i0=1，
      并被用户 f2/f3 的裁剪范围独立佐证：f2 覆盖第 23-26 行、f3 覆盖第 38-41 行）
片段内的坐标 = 纹理坐标 - 该碎片在 fragments.json 里的 y。

用法:
    # 精修名版：改动的行应等于 TSV 里 v1≠v4 的那 22 行
    python CN_Refined\\langpack\\check_name_rows.py

    # 英文名版：60 行应全部不同（查漏翻）
    python CN_Refined\\langpack\\check_name_rows.py --a ManifestCrew_f1.png ^
        --b ManifestCrew_f1_enname.png --expect all
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
FRAGDIR = ROOT / "CN_Refined" / "Textures" / "fragments"
META = FRAGDIR / "fragments.json"
TSV = ROOT / "CN_Refined" / "langpack" / "extracted" / "crew_name_variants.tsv"
OUT = ROOT / "CN_Refined" / "out" / "textures"
CHK = OUT / "_check"

PITCH = 26          # 行距
ROW1_Y = 52         # 第 1 行中心在纹理里的 y
BAND = 11           # 每行取中心 ±BAND 像素判定

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def read_tsv():
    rows = []
    with TSV.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            if not r or r[0].startswith("#") or len(r) < 7:
                continue
            rows.append(r)
    full, short, dia = [], [], []
    for r in rows:
        k = r[0].strip().strip("[]")
        (short if k.endswith("Short") else dia if k.endswith("Dia") else full).append(r)
    return full, short, dia


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="ManifestCrew_f1.png")
    ap.add_argument("--b", default="ManifestCrew_f1_namerefined.png")
    ap.add_argument("--expect", choices=["tsv", "all"], default="tsv")
    ap.add_argument("--min", type=int, default=20,
                    help="一行至少要有多少差异像素才算真改动（默认 20，低于此视为抗锯齿噪声）")
    args = ap.parse_args()

    CHK.mkdir(parents=True, exist_ok=True)
    meta = json.loads(META.read_text(encoding="utf-8"))
    frags = meta["ManifestCrew.png"]["fragments"]
    f1 = next(f for f in frags if f["id"] == 1)
    top = f1["y"]                      # 该碎片在纹理里的裁剪原点
    ih = Image.open(FRAGDIR / args.a).convert("L")
    h = ih.height

    say("【A】行格")
    say("-" * 66)
    say(f"  纹理坐标 第 n 行中心 y = {ROW1_Y} + (n-1) × {PITCH}")
    say(f"  姓名列碎片裁剪原点 y={top} → 片段内第 n 行中心 y = {ROW1_Y - top} + (n-1) × {PITCH}")
    say(f"  碎片高 {h} → 可容纳 {max(0, (h - (ROW1_Y - top)) // PITCH + 1)} 行")

    ia = Image.open(FRAGDIR / args.a).convert("L")
    ib = Image.open(FRAGDIR / args.b).convert("L")
    if ia.size != ib.size:
        print(f"尺寸不同：{ia.size} vs {ib.size}", file=sys.stderr)
        return 2
    d = ImageChops.difference(ia, ib)
    d.point(lambda v: 255 if v else 0).save(CHK / f"mask-{args.b}")
    px = d.load()
    w = d.width
    rowdiff = [sum(1 for x in range(w) if px[x, y]) for y in range(h)]

    say("")
    say("【B】TSV 期望")
    say("-" * 66)
    full, short, dia = read_tsv()
    v1v4 = [i + 1 for i, r in enumerate(full) if r[2] != r[5]]
    say(f"  全名 {len(full)} / Short {len(short)} / Dia {len(dia)} 行")
    if args.expect == "tsv":
        expected = set(v1v4)
        say(f"  期望改动 v1≠v4 的 {len(expected)} 行：{sorted(expected)}")
    else:
        expected = set(range(1, len(full) + 1))
        say(f"  期望全部 {len(expected)} 行都不同（查漏翻）")

    say("")
    say(f"【C】逐行判定（第 n 行中心 ±{BAND}px 内的差异像素数，阈值 {args.min}）")
    say("-" * 66)
    present: dict[int, int] = {}
    noise: dict[int, int] = {}
    for n in range(1, len(full) + 1):
        c = (ROW1_Y - top) + (n - 1) * PITCH
        n0, n1 = max(0, c - BAND), min(h - 1, c + BAND)
        if n0 > n1:
            break
        cnt = sum(rowdiff[n0:n1 + 1])
        if cnt >= args.min:
            present[n] = cnt
        elif cnt:
            noise[n] = cnt
    hit = sorted(expected & set(present))
    miss = sorted(expected - set(present))
    extra = sorted(set(present) - expected)
    say(f"  检出行数 {len(present)} / 片段可容 {len(full)} 行")
    for n in sorted(present):
        r = full[n - 1]
        flag = "" if n in expected else "   <- 预期外"
        say(f"    #{n:<3} 差异 {present[n]:<6} {r[0].strip('[]'):<24}{flag}")
    if noise:
        say("")
        say(f"  噪声行（差异 {args.min} 像素以下，视为抗锯齿）："
            + "、".join(f"#{n}({c}px)" for n, c in sorted(noise.items())))
    if miss:
        say("")
        say(f"  未检测到改动（漏改？）的 {len(miss)} 行：")
        for n in miss:
            r = full[n - 1]
            say(f"    #{n:<3} {r[0].strip('[]'):<26} {r[2]}")

    say("")
    say("【D】结论")
    say("-" * 66)
    say(f"  命中 {len(hit)}/{len(expected)}   漏 {len(miss)}   预期外 {len(extra)}")
    if extra:
        for n in extra:
            r = full[n - 1]
            say(f"    意外改动 #{n} {r[0].strip('[]')}  {r[2]} → {r[5]}")
    ok = not miss and not extra
    tgt = f"TSV 的 v1≠v4 的 {len(expected)} 行" if args.expect == "tsv" else f"全部 {len(expected)} 行"
    say("")
    say(f"  {args.a} → {args.b} 的改动行 与 {tgt} 完全一致 ✓" if ok
        else f"  ⚠ 与 {tgt} 有出入，见上")

    text = "\n".join(lines)
    print(text)
    (OUT / "check_name_rows_report.txt").write_text(text + "\n", encoding="utf-8-sig")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
