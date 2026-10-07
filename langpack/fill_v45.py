#!/usr/bin/env python3
"""把 v4 / v5 补成与 v1 / v2 同构（用户 2026-10-06 定）。

对照关系（每人两行：全名行 + Short 行）:

    行      v1                    v2                      v4                    v5
    全名    当前全名              = v1                    精修全名              = v4
    Short   当前 Short 槽位值     「当前版」做 Short      精修全名(= v4 全名行)  「精修版」做 Short
            (= 全名，未缩写)      (英文首字母+当前版姓)                          (英文首字母+精修版姓)

也就是: **v4/v5 之于 v1/v2，等于「精修版」之于「当前版」**。
本脚本只补两件之前没写的东西:
  * Short 行的 v4 = 对应全名行的 v4
  * 全名行的 v5 = 自己的 v4
Dia 段不动。

用法:
    python CN_Refined/langpack/fill_v45.py --dry
    python CN_Refined/langpack/fill_v45.py --report <UTF-8 文件>
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TSV = HERE / "extracted" / "crew_name_variants.tsv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", default=str(DEFAULT_TSV))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--report")
    args = ap.parse_args()
    path = Path(args.tsv)
    if not path.is_file():
        print("[X] 找不到 %s" % path)
        return 1

    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(eol)
    tail = False
    if lines and lines[-1] == "":
        lines.pop()
        tail = True

    def data_rows():
        for i, ln in enumerate(lines):
            if not ln.strip() or ln.startswith("#"):
                continue
            f = ln.split("\t")
            if len(f) < 7 or f[0].strip() == "[]键":
                continue
            yield i, f

    # 1) 收全名行的 v4 / v1
    full_v4, full_v1 = {}, {}
    for _i, f in data_rows():
        if f[0].endswith("Short]") or f[0].endswith("Dia]"):
            continue
        cid = f[0].replace("[CrewName", "").replace("]", "").lower()
        full_v4[cid] = f[5].strip()
        full_v1[cid] = f[2].strip()

    # 2) 补 Short 行的 v4、全名行的 v5；Dia 行若“称呼 = 全名”则跟着精修名走
    ops, missing = [], []
    for i, f in data_rows():
        key = f[0]
        if key.endswith("Dia]"):
            base = key.replace("[CrewName", "").replace("Dia]", "").lower()
            want = full_v4.get(base, "")
            if want and f[2].strip() and f[2].strip() == full_v1.get(base, "") \
                    and (f[5].strip() != want or f[6].strip() != want):
                ops.append((key, "v4/v5", f[5].strip(), want,
                            "Dia 称呼 = 该人全名 → 跟着精修名走"))
                f[5] = f[6] = want
                lines[i] = "\t".join(f)
            continue
        if key.endswith("Short]"):
            base = key.replace("[CrewName", "").replace("Short]", "").lower()
            if base not in full_v4 or not full_v4[base]:
                missing.append(key)
                continue
            want, col, why = full_v4[base], 5, "Short 行 v4 = 该人的精修全名"
        else:
            if not f[5].strip():
                missing.append(key)
                continue
            want, col, why = f[5].strip(), 6, "全名行 v5 = 自己的 v4"
        if f[col].strip() != want:
            ops.append((key, "v%d" % (col - 1), f[col].strip(), want, why))
            f[col] = want
            lines[i] = "\t".join(f)

    rep = []
    say = rep.append
    say("补全 %d 格（Short 行 v4 + 全名行 v5）" % len(ops))
    if missing:
        say("!! 缺基底: %s" % ", ".join(missing))
    say("")
    say("%-22s %-4s %-18s %-18s %s" % ("键", "列", "原值", "补成", "依据"))
    say("-" * 96)
    for key, col, old, new, why in ops:
        say("%-22s %-4s %-18s %-18s %s"
            % (key.replace("[CrewName", "").replace("]", ""), col,
               old if old else "(空)", new, why))

    text = "\n".join(rep) + "\n"
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8-sig")
        print("report -> %s" % args.report)
    else:
        sys.stdout.write(text)

    if args.dry:
        print("[dry-run] 没写文件")
        return 0

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.with_name(path.name + ".bak-" + stamp)
    shutil.copy2(path, bak)
    path.write_bytes((eol.join(lines) + (eol if tail else "")).encode("utf-8"))
    print("已写回 %s" % path.name)
    print("备份   %s" % bak.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
