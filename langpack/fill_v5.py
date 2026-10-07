#!/usr/bin/env python3
"""批量填 v5（精修中文名 + Short）。

规则（用户 2026-10-06 定）:
  * v5 以 **v4（精修全名）** 为底，规则与 v2 相同:
        v5 = 英文 Short 里的首字母部分 + 空格 + 精修名的「姓」
  * 「姓」取法: 有「·」取最后一段，再剥掉 小姐/女士/先生/夫人/公子 之类
        （Pass4「简·伯德小姐」→ 伯德，与 v1 的 Short 槽位「简·伯德」处理一致）
    没有「·」的（中文名）取首字
  * 英文 Short 没有空格（如 Maba）→ 没有首字母可加，v5 = 精修全名
  * 只写 **Short 行**；Dia 段不动

用法:
    python CN_Refined/langpack/fill_v5.py --dry
    python CN_Refined/langpack/fill_v5.py --report <UTF-8 文件>
    python CN_Refined/langpack/fill_v5.py            # 真写（先备份）
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TSV = HERE / "extracted" / "crew_name_variants.tsv"

HONORIFIC = ("小姐", "女士", "先生", "夫人", "公子", "船长", "大副")


def surname_of(zh: str) -> str:
    """精修名的姓: 有「·」取最后一段并剥掉敬称；否则取首字。"""
    zh = zh.strip()
    if not zh:
        return ""
    tail = zh.split("·")[-1] if "·" in zh else zh[0]
    for h in HONORIFIC:
        if tail.endswith(h) and len(tail) > len(h):
            return tail[: -len(h)]
    return tail


def initials_of(en: str) -> str:
    """英文 Short 的首字母部分: "R. Witterel"->"R."; "Maba"->""。"""
    tail = en.split("|")[-1].strip()
    if " " not in tail:
        return ""
    return tail.rsplit(" ", 1)[0].strip()


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

    def rows():
        for i, ln in enumerate(lines):
            if not ln.strip() or ln.startswith("#"):
                continue
            f = ln.split("\t")
            if len(f) < 7 or f[0].strip() == "[]键":
                continue
            yield i, f

    # 1) 先收全名行的 v4
    full_v4, full_v1 = {}, {}
    for _i, f in rows():
        key = f[0]
        if key.endswith("Short]") or key.endswith("Dia]"):
            continue
        cid = key.replace("[CrewName", "").replace("]", "").lower()
        full_v4[cid] = f[5].strip()          # v4
        full_v1[cid] = f[2].strip()          # v1

    # 2) 给 Short 行算 v5
    changed, same, missing = [], [], []
    for i, f in rows():
        key = f[0]
        if not key.endswith("Short]"):
            continue
        cid = key.replace("[CrewName", "").replace("]", "").lower()
        base = cid[: -len("short")] if cid.endswith("short") else cid
        if base not in full_v4 or not full_v4[base]:
            missing.append(key)
            continue
        v4 = full_v4[base]
        head = initials_of(f[1])
        sn = surname_of(v4)
        new = (head + " " + sn).strip() if head else v4
        cur = f[6].strip()                   # v5 = 第 7 列
        rec = (key, f[1], v4, sn, new, f[3].strip())
        if new != cur:
            f[6] = new
            lines[i] = "\t".join(f)
            changed.append(rec)
        else:
            same.append(rec)

    rep = []
    say = rep.append
    say("v5 写入 %d 行 / 已是该值 %d 行 / 缺基底 %d 行" % (len(changed), len(same), len(missing)))
    if missing:
        say("缺基底（全名行没有 v4）: %s" % ", ".join(missing))
    say("")
    say("%-22s %-24s %-16s %-6s %-14s %-14s %s"
        % ("键", "英文 Short", "v4 精修全名", "姓", "v5 新值", "v2（当前版）", "与 v2 同?"))
    say("-" * 128)
    for key, en, v4, sn, new, v2 in changed + same:
        say("%-22s %-24s %-16s %-6s %-14s %-14s %s"
            % (key.replace("[CrewName", "").replace("]", ""),
               en.split("|")[-1].strip(), v4, sn, new, v2 or "(空)",
               "同" if new == v2 else "**异**"))

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
