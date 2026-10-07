#!/usr/bin/env python3
"""逐格比对两个 TSV，证明「到底改了哪一列、哪些行没被碰」。

用法:
    python CN_Refined/langpack/diff_tsv.py 旧.tsv 新.tsv [--report 报告.txt]

报告内容: 行数/行尾符、按列的改动计数、Dia 段改动数、逐条明细。
（控制台中文会乱码，所以支持 --report 让脚本自己写 UTF-8 文件。）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

COLS = ["[]键", "en", "v1", "v2", "v3", "v4", "v5", "出现处"]


def load(path: Path):
    raw = path.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("utf-8").split(eol)
    if lines and lines[-1] == "":
        lines.pop()
        tail = True
    else:
        tail = False
    return lines, eol, raw, tail


def is_data(ln: str) -> bool:
    return bool(ln.strip()) and not ln.startswith("#") and len(ln.split("\t")) >= 7 \
        and ln.split("\t")[0].strip() != "[]键"


def kind_of(ln: str) -> str:
    key = ln.split("\t")[0]
    if key.endswith("Short]"):
        return "Short"
    if key.endswith("Dia]"):
        return "Dia"
    return "全名"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--report")
    args = ap.parse_args()

    old, eol_o, raw_o, tail_o = load(Path(args.old))
    new, eol_n, raw_n, tail_n = load(Path(args.new))
    rep = []
    say = rep.append

    say("行数     : %d -> %d   %s" % (len(old), len(new),
                                     "OK" if len(old) == len(new) else "!! 变了"))
    say("行尾符   : %s -> %s   %s" % ({0x0d: "LF"}.get(0, "CRLF" if eol_o == "\r\n" else "LF"),
                                     "CRLF" if eol_n == "\r\n" else "LF",
                                     "OK" if (eol_o == eol_n and tail_o == tail_n) else "!! 变了"))
    say("字节数   : %d -> %d" % (len(raw_o), len(raw_n)))
    say("")

    if len(old) != len(new):
        say("!! 行数不一致，后面的逐行比对没有意义")
        Path(args.report).write_text("\n".join(rep) + "\n", encoding="utf-8-sig") \
            if args.report else sys.stdout.write("\n".join(rep) + "\n")
        return 1

    by_col = {c: 0 for c in COLS}
    by_kind = {}
    dia_touched = []
    details = []
    for i, (a, b) in enumerate(zip(old, new)):
        if a == b:
            continue
        fa, fb = a.split("\t"), b.split("\t")
        if len(fa) != len(fb):
            say("!! 第 %d 行列数变了: %d -> %d" % (i + 1, len(fa), len(fb)))
            continue
        for j, (x, y) in enumerate(zip(fa, fb)):
            if x != y:
                by_col[COLS[j] if j < len(COLS) else ("列%d" % j)] += 1
                details.append((i + 1, kind_of(a), fa[0], COLS[j] if j < len(COLS) else j,
                                x if x else "(空)", y if y else "(空)"))
        k = kind_of(a)
        by_kind[k] = by_kind.get(k, 0) + 1
        if k == "Dia":
            dia_touched.append(i + 1)

    say("改动行数 : %d" % sum(by_kind.values()))
    for k in ("全名", "Short", "Dia"):
        say("    %-5s : %d" % (k, by_kind.get(k, 0)))
    say("按列改动 :")
    for c in COLS:
        say("    %-6s : %d" % (c, by_col.get(c, 0)))
    say("Dia 段被碰的行: %s" % (", ".join(map(str, dia_touched)) if dia_touched else "无 ✓"))
    say("")
    say("明细（行号 / 类型 / 键 / 列 / 旧 -> 新）:")
    for row in details:
        say("  %-5d %-5s %-24s %-5s %s -> %s"
            % (row[0], row[1], row[2].replace("[CrewName", "").replace("]", ""),
               row[3], row[4], row[5]))

    text = "\n".join(rep) + "\n"
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8-sig")
        print("report -> %s" % args.report)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
