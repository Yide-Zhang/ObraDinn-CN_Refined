# -*- coding: utf-8 -*-
"""
把碎片贴回整张纹理，生成最终图片（可按「姓名态 × 和谐态」自由组合）。

坐标来自 CN_Refined\\Textures\\fragments\\fragments.json（碎片选取器保存的）。
碎片文件命名： <纹理名>_f<编号>.png            基准
               <纹理名>_f<编号>_<标签>.png     变体

每个碎片属于一条「轴」（见 AXIS），同一轴上的标签即该轴的可选值：
  * name   轴（姓名列，随版本变）：zh / refined(精修) / en(英文) —— 由实际文件自动发现
  * region 轴（籍贯、标题，随和谐开关变）：unharm / harm —— 非空标签即"和谐"

用法：
    python CN_Refined\\langpack\\paste_fragments.py                  # 生成所有组合
    python CN_Refined\\langpack\\paste_fragments.py --combo en-unharm
    python CN_Refined\\langpack\\paste_fragments.py --tex ManifestCrew
    python CN_Refined\\langpack\\paste_fragments.py --report         # 附 UTF-8 报告文件
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]          # ObraDinnSave
TEXDIR = ROOT / "CN_Refined" / "Textures"
FRAGDIR = TEXDIR / "fragments"
META = FRAGDIR / "fragments.json"
OUTDIR = ROOT / "CN_Refined" / "out" / "textures"

# (纹理, 碎片编号) -> 轴；未列出的默认 region
AXIS = {
    ("ManifestCrew", 1): "name",
    ("ManifestCrew", 2): "region",
    ("ManifestCrew", 3): "region",
    ("FolioSketch", 1): "region",
}
DEFAULT_AXIS = "region"
# name 轴的标签 -> 输出名里用的短名
NAME_LABEL = {"": "zh", "namerefined": "refined", "enname": "en"}
AXIS_ORDER = ["name", "region"]
FRAG_RE = re.compile(r"^(?P<tex>.+)_f(?P<n>\d+)(?:_(?P<tag>.+))?\.png$", re.I)

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def axis_of(tex: str, fid: int) -> str:
    return AXIS.get((tex, fid), DEFAULT_AXIS)


def scan() -> dict[tuple[str, int], dict[str, Path]]:
    found: dict[tuple[str, int], dict[str, Path]] = {}
    for p in sorted(FRAGDIR.glob("*.png")):
        m = FRAG_RE.match(p.name)
        if not m:
            say(f"  ! 文件名不符合约定，已跳过：{p.name}")
            continue
        found.setdefault((m.group("tex"), int(m.group("n"))), {})[m.group("tag") or ""] = p
    return found


def axis_values(tags: dict[str, Path], axis: str) -> tuple[dict[str, str], str | None]:
    """返回 ({值: 标签}, 错误)"""
    if axis == "name":
        return {NAME_LABEL.get(t, t or "zh"): t for t in sorted(tags)}, None
    nonempty = sorted(t for t in tags if t)
    out = {"unharm": ""} if "" in tags else {}
    if len(nonempty) > 1:
        return out, "同一碎片有多个非空变体：" + ", ".join(nonempty)
    if nonempty:
        out["harm"] = nonempty[0]
    return out, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--combo", help="只生成某个组合，如 en-unharm")
    ap.add_argument("--tex", help="只处理某张纹理，如 ManifestCrew")
    ap.add_argument("--report", action="store_true", help="输出 UTF-8 报告文件")
    args = ap.parse_args()

    if not META.exists():
        print(f"找不到坐标文件：{META}", file=sys.stderr)
        return 2
    meta = json.loads(META.read_text(encoding="utf-8"))
    if args.tex:
        meta = {k: v for k, v in meta.items() if Path(k).stem == args.tex}
        if not meta:
            print(f"坐标文件里没有 {args.tex}", file=sys.stderr)
            return 2
    frags = scan()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    problems: list[str] = []
    written: dict[Path, list[str]] = {}

    for tex_name, info in meta.items():
        stem = Path(tex_name).stem
        base_path = TEXDIR / tex_name
        if not base_path.exists():
            problems.append(f"{tex_name}：基准纹理不存在")
            continue
        rects = sorted(info["fragments"], key=lambda f: f["id"])

        # 每块碎片各自一份「标签 -> 文件后缀」映射（同一标签在不同碎片上后缀不同）
        lab2tag: dict[tuple[str, int], dict[str, str]] = {}
        labels: dict[str, set[str]] = {}
        for f in rects:
            a = axis_of(stem, f["id"])
            vals, err = axis_values(frags.get((stem, f["id"]), {}), a)
            if err:
                problems.append(f"{tex_name} # {f['id']}：{err}")
            lab2tag[(stem, f["id"])] = vals
            labels[a] = set(vals) if a not in labels else labels[a] & set(vals)
        used_axes = [a for a in AXIS_ORDER if a in labels]
        if not used_axes or any(not labels[a] for a in used_axes):
            problems.append(f"{tex_name}：可选值交集为空，无法组合")
            continue

        with Image.open(base_path) as im0:
            say(f"### {tex_name}  {im0.width}×{im0.height}")
        say(f"    轴：{', '.join(f'{a}={sorted(labels[a])}' for a in used_axes)}")

        combos = list(itertools.product(*(sorted(labels[a]) for a in used_axes)))
        for combo in combos:
            want = dict(zip(used_axes, combo))
            key = "-".join(combo)
            if args.combo and key != args.combo:
                continue
            img = Image.open(base_path).convert("RGBA")
            picks: list[str] = []
            for f in rects:
                a = axis_of(stem, f["id"])
                val = want.get(a)
                tags = frags.get((stem, f["id"]), {})
                tag = lab2tag[(stem, f["id"])].get(val)    # 标签(如 zh/harm) -> 本块的后缀
                if val is None or tag not in tags:
                    problems.append(f"{tex_name} # {f['id']}：没有 {a}={val} 的碎片")
                    picks.append("!! 缺")
                    continue
                path = tags[tag]
                frag = Image.open(path).convert("RGBA")
                w, h, x, y = f["w"], f["h"], f["x"], f["y"]
                if (frag.width, frag.height) != (w, h):
                    problems.append(
                        f"{tex_name} # {f['id']}：碎片 {frag.width}×{frag.height} "
                        f"≠ 坐标 {w}×{h}，已裁切后贴入")
                    crop = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    crop.alpha_composite(
                        frag.crop((0, 0, min(w, frag.width), min(h, frag.height))))
                    frag = crop
                img.alpha_composite(frag, (x, y))
                picks.append(f"#{f['id']} <- {path.name}")
            out = OUTDIR / f"{stem}-{key}.png"
            img.save(out)
            written[out] = picks

    say("")
    say("=" * 68)
    for out, picks in written.items():
        say(f"{out.name}   {out.stat().st_size:,} 字节")
        for p in picks:
            say(f"    {p}")
    say("")
    if problems:
        say(f"有 {len(problems)} 个问题：")
        for t in problems:
            say(f"  - {t}")
    else:
        say(f"共写出 {len(written)} 张，全部碎片都贴入无误 ✓")

    text = "\n".join(lines)
    print(text)
    if args.report:
        (OUTDIR / "paste_report.txt").write_text(text + "\n", encoding="utf-8-sig")
        print(f"\n报告已写入 {OUTDIR / 'paste_report.txt'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
