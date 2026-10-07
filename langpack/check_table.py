#!/usr/bin/env python3
"""核对人名表是否满足「v4/v5 镜像 v1/v2」的全部约束。只读，不改文件。

约定（用户 2026-10-06 定）:
  * 全名行: v1 = 当前全名, v2 = v1        |  v4 = 精修全名, v5 = v4
  * Short行: v1 = 当前 Short 槽位值(=全名) |  v4 = 该人的精修全名
             v2 = 英文Short首字母+当前版姓 |  v5 = 英文Short首字母+精修版姓
  * Dia 行: v4 = 「把精修结果代进当前称呼」, v5 = v4（Dia 不缩写）
     → 所以 v5 == v4 是硬要求；而 v4 == v1 **仅当此人名字没被精修过**

检查项: 列数/字段数、v4/v5 是否填齐、上面每一条是否成立。
用法: python CN_Refined/langpack/check_table.py [表文件] [--report <UTF-8 文件>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TSV = HERE / "extracted" / "crew_name_variants.tsv"
HONORIFIC = ("小姐", "女士", "先生", "夫人", "公子", "船长", "大副")


def surname_of(zh: str) -> str:
    zh = zh.strip()
    if not zh:
        return ""
    tail = zh.split("·")[-1] if "·" in zh else zh[0]
    for h in HONORIFIC:
        if tail.endswith(h) and len(tail) > len(h):
            return tail[: -len(h)]
    return tail


def initials_of(en: str) -> str:
    tail = en.split("|")[-1].strip()
    if " " not in tail:
        return ""
    return tail.rsplit(" ", 1)[0].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", default=str(DEFAULT_TSV))
    ap.add_argument("--report")
    args = ap.parse_args()
    path = Path(args.tsv)
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = [x for x in raw.split(eol) if x.strip()]
    raw_lines = raw.split(eol)

    rep = []
    say = rep.append
    say("文件: %s（%s，%d 行）" % (path.name, "CRLF" if eol == "\r\n" else "LF",
                                  len([x for x in raw_lines if x != ""])))

    data = []
    for i, ln in enumerate(raw_lines):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t")
        if len(f) < 7 or f[0].strip() == "[]键":
            continue
        data.append((i + 1, f))

    bad = []
    full_v4 = {}
    for ln_no, f in data:
        if not (f[0].endswith("Short]") or f[0].endswith("Dia]")):
            full_v4[f[0].replace("[CrewName", "").replace("]", "").lower()] = f[5].strip()

    n_full = n_short = n_dia = 0
    stale_dia = []
    for ln_no, f in data:
        key, en = f[0], f[1]
        v1, v2, v4, v5 = f[2], f[3], f[5], f[6]
        if key.endswith("Dia]"):
            n_dia += 1
            if not v4.strip() or not v5.strip():
                bad.append((ln_no, key, "Dia 行 v4/v5 未填"))
            elif v5.strip() != v4.strip():
                bad.append((ln_no, key, "Dia 行 v5(%s) 应等于 v4(%s)" % (v5, v4)))
            base = key.replace("[CrewName", "").replace("Dia]", "").lower()
            full = full_v4.get(base, "")
            if v4.strip() == v1.strip() and full and full != v1.strip():
                stale_dia.append((ln_no, key, v1, full, v4))
        elif key.endswith("Short]"):
            n_short += 1
            base = key.replace("[CrewName", "").replace("Short]", "").lower()
            want_v4 = full_v4.get(base, "")
            if not v4.strip() or not v5.strip():
                bad.append((ln_no, key, "Short 行 v4/v5 未填"))
            if v4.strip() != want_v4:
                bad.append((ln_no, key, "Short 行 v4(%s) 应等于该人精修全名(%s)"
                            % (v4 or "(空)", want_v4 or "(缺)")))
            head = initials_of(en)
            want_v5 = (head + " " + surname_of(v4)).strip() if head else v4.strip()
            if v5.strip() != want_v5:
                bad.append((ln_no, key, "Short 行 v5(%s) 应为 首字母+精修姓(%s)"
                            % (v5 or "(空)", want_v5)))
        else:
            n_full += 1
            if not v4.strip() or not v5.strip():
                bad.append((ln_no, key, "全名行 v4/v5 未填"))
            if v5.strip() != v4.strip():
                bad.append((ln_no, key, "全名行 v5(%s) 应等于 v4(%s)" % (v5, v4)))

    say("行数: 全名 %d / Short %d / Dia %d" % (n_full, n_short, n_dia))
    say("")
    if bad:
        say("发现 %d 处不符:" % len(bad))
        for ln_no, key, msg in bad:
            say("  第%-4d %-24s %s" % (ln_no, key, msg))
    else:
        say("全部 %d 行都符合约定 ✓" % len(data))
        say("  · 每行 v4/v5 都已填")
        say("  · 全名行 v5 = v4；Short 行 v4 = 精修全名、v5 = 首字母+精修姓")
        say("  · Dia 行 v5 = v4（v4 为「精修后的称呼」）")
    if stale_dia:
        say("")
        say("请复核 %d 行 Dia（此人名字有过精修，但这一格仍等于 v1 —— 若是有意保留的昵称/称呼就没问题）:"
            % len(stale_dia))
        for ln_no, key, v1, full, v4 in stale_dia:
            say("  第%-4d %-24s 当前=%-12s 精修全名=%-16s 本格=%s"
                % (ln_no, key, v1, full, v4))

    text = "\n".join(rep) + "\n"
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8-sig")
        print("report -> %s" % args.report)
    else:
        sys.stdout.write(text)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
