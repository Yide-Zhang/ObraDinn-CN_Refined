# -*- coding: utf-8 -*-
"""检查「新名字系统」是否完全落在字体子集范围内。

来源：
  1. crew_name_variants.tsv 的**全部**列（en / v1..v5）—— 每个版本的每个名字
  2. 20 个成品语言包里所有涉及人名的键（含展开后的实际串）
方法：从**成品 assets** 里抠出两支子集字体，用 FreeType 逐字渲染，确认都有墨迹。

用法: python CN_Refined\\assets\\check_name_coverage.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import UnityPy
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROD = ROOT / "CN_Refined" / "out" / "assets"
TBL = ROOT / "CN_Refined" / "langpack" / "extracted" / "crew_name_variants.tsv"
PACKS = ROOT / "CN_Refined" / "out" / "packs"
OUT = HERE / "out" / "name_coverage.txt"

TARGETS = {"sharedassets0.assets": "SourceHanSerif-SemiBold",
           "sharedassets2.assets": "851tegaki_zatsu_normal_0883"}

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def has_ink(font, c: str) -> bool:
    im = Image.new("L", (48, 48), 0)
    ImageDraw.Draw(im).text((6, 6), c, font=font, fill=255)
    return im.getbbox() is not None


def main() -> int:
    # ---- 收集所有需要能显示的文字 ----
    say("新名字系统 字体覆盖检查")
    say("=" * 84)
    names: dict[str, list[str]] = {}
    raw = TBL.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    cols = {"en": 1, "v1": 2, "v2": 3, "v3": 4, "v4": 5, "v5": 6}
    rows = [r for r in csv.reader(raw.splitlines(), delimiter="\t")
            if r and not r[0].startswith("#") and len(r) >= 7 and r[0].strip() != "[]键"]
    for v, ci in cols.items():
        names[v] = [r[ci].strip() for r in rows if r[ci].strip()]
    say("  人名表 %d 行；各列取值数: %s"
        % (len(rows), {k: len(v) for k, v in names.items()}))
    # Dia 行第 8 列（出现处）不用管；但 Dia 的 v3/v4 里可能有称呼
    for v in ("v3", "v4", "v5"):
        extra = [r[ci].strip() for r in rows
                 if len(r) > 7 and r[7].strip() and False]
        names[v] += extra

    # 成品语言包里所有含人名占位符展开结果的键
    pack_vals: set[str] = set()
    for p in sorted(PACKS.glob("*.tsv")):
        for ln in p.read_bytes().decode("utf-8-sig").splitlines():
            if "\t" in ln:
                pack_vals.add(ln.split("\t", 1)[1])
    name_keys = [v for v in pack_vals
                 if any(k in v for k in ("先生", "小姐", "夫人", "医生", "·"))]
    say("  成品语言包 %d 个取值，其中像人名的 %d 条" % (len(pack_vals), len(name_keys)))
    say("")

    # ---- 逐字体实测 ----
    all_chars: set[str] = set()
    for v, lst in names.items():
        all_chars |= set("".join(lst))
    for v in name_keys:
        all_chars |= set(v)
    all_chars = {c for c in all_chars if not c.isspace()}
    say("  待检字符合计 %d 个（含全部版本人名 + 成品里的人名串）" % len(all_chars))
    say("")

    ok = True
    for fn, fname in TARGETS.items():
        p = PROD / fn
        if not p.exists():
            say("  ✗ 缺成品 %s" % p)
            ok = False
            continue
        env = UnityPy.load(str(p))
        data = None
        for o in env.objects:
            if o.type.name == "Font":
                d = o.read()
                if getattr(d, "m_Name", "") == fname:
                    data = bytes(d.m_FontData)
        if data is None:
            say("  ✗ %s 里找不到字体 %s" % (fn, fname))
            ok = False
            continue
        tmp = HERE / "out" / "verify" / (fname + ".probe")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        font = ImageFont.truetype(str(tmp), 24)
        missing = [c for c in sorted(all_chars) if not has_ink(font, c)]
        say("  %-34s 待检 %d 字 →  缺 %d 个%s"
            % (fname, len(all_chars), len(missing),
               ("   缺: " + "".join(missing[:40])) if missing else "  ✓"))
        if missing:
            ok = False
            # 指出是哪些名字受影响
            for v, lst in names.items():
                bad = [n for n in lst if any(c in missing for c in n)]
                if bad:
                    say("      [%s] 受影响的人名 %d 个: %s" % (v, len(bad), "、".join(bad[:10])))
        say("")

    say("=" * 84)
    say("全部落在子集范围内 ✓" if ok else "⚠ 有字落在范围外，见上（要重跑 inject_fonts.py 扩字符集）")
    text = "\n".join(lines)
    OUT.write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
