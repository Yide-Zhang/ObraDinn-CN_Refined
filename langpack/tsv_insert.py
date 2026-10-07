#!/usr/bin/env python3
"""在 TSV 里安全插一行（保住 CRLF、先备份、可看出插在哪儿）。

为什么要脚本而不用编辑器改：这表是 CRLF，手改容易把整份文件的行尾改掉。

用法（字段用多个参数给，避免在命令行里写制表符）:
    python CN_Refined/langpack/tsv_insert.py 表.tsv --after "[CrewNameGunnerDia]" \
        --key "[CrewNamePass7Dia]" --fields "It-Beng Sia | I. Sia" 明 明 Beng 明 明 dialog_d3_m1_da

幂等: 若 --key 已存在则只报告，不改文件。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("--after", required=True, help="插在这一行的 key 之后")
    ap.add_argument("--key", required=True)
    ap.add_argument("--fields", nargs="+", required=True, help="除 key 之外的各列（按顺序）")
    ap.add_argument("--dry", action="store_true")
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

    for i, ln in enumerate(lines):
        if ln.split("\t")[0].strip() == args.key:
            print("已存在 %s（第 %d 行），不改" % (args.key, i + 1))
            return 0

    row = "\t".join([args.key] + args.fields)
    pos = None
    for i, ln in enumerate(lines):
        if ln.split("\t")[0].strip() == args.after:
            pos = i + 1
            break
    if pos is None:
        print("[X] 找不到锚点 %s" % args.after)
        return 1
    if len(row.split("\t")) != len(lines[pos - 1].split("\t")):
        print("[X] 列数不一致: 新行 %d 列, 锚点行 %d 列"
              % (len(row.split("\t")), len(lines[pos - 1].split("\t"))))
        return 1

    print("将插入到第 %d 行之前（%s 之后）:" % (pos + 1, args.after))
    print("  " + row.replace("\t", " | "))
    if args.dry:
        print("[dry-run] 没写文件")
        return 0

    lines.insert(pos, row)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.with_name(path.name + ".bak-" + stamp)
    shutil.copy2(path, bak)
    path.write_bytes((eol.join(lines) + (eol if tail else "")).encode("utf-8"))
    print("已写回 %s" % path.name)
    print("备份   %s" % bak.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
