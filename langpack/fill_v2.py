#!/usr/bin/env python3
"""批量填 v2（版本2 = 和当前版类似但做 Short）。

规则（从用户在 Captain / Pass1 / Pass4 三处的示例反推）:
  * 全名行  : v2 = v1        （全名占位符没有 Short 可言，与版本1 相同）
  * Short 行: v2 = 英文 Short 里的首字母部分 + 空格 + 中文姓
        例:  "R. Witterel"   + 威特瑞 -> "R. 威特瑞"
             "A.H. Witterel" + 威特瑞 -> "A.H. 威特瑞"
             "J. Bird"       + 伯德   -> "J. 伯德"
        英文 Short 没有空格（如 "Maba"）-> 没有首字母可加，保持原来的姓形态
  * Dia 行  : 不动（用户明确说「除了 dia 的部分」）

中文姓的取法（沿用已被确认的 v2 提案）: 有「·」取最后一段，否则取首字。

用法:
    python CN_Refined/langpack/fill_v2.py --dry     # 只看会改成什么
    python CN_Refined/langpack/fill_v2.py           # 真写（先备份 .bak-<时间戳>）
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TSV = HERE / "extracted" / "crew_name_variants.tsv"


def kind_of(key: str) -> str:
    if key.endswith("Short]"):
        return "Short"
    if key.endswith("Dia]"):
        return "Dia"
    return "全名"


def surname_of(zh: str) -> str:
    """中文姓: 有「·」取最后一段；否则取首字。"""
    zh = zh.strip()
    if not zh:
        return ""
    if "·" in zh:
        return zh.split("·")[-1]
    return zh[0]


def initials_of(en: str) -> str:
    """英文 Short 里的首字母部分: "R. Witterel"->"R."; "A.H. Witterel"->"A.H.";
    没有空格（"Maba"）-> 空串。"""
    tail = en.split("|")[-1].strip()
    if " " not in tail:
        return ""
    return tail.rsplit(" ", 1)[0].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", default=str(DEFAULT_TSV))
    ap.add_argument("--dry", action="store_true", help="只打印，不写文件")
    ap.add_argument("--report", help="报告写成这个 UTF-8 文件（控制台中文会乱码时用）")
    args = ap.parse_args()
    path = Path(args.tsv)
    if not path.is_file():
        print("[X] 找不到 %s" % path)
        return 1

    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(eol)
    if lines and lines[-1] == "":
        lines.pop()
        tail = True
    else:
        tail = False

    changed, skipped_dia, no_initials = [], 0, []
    unchanged = []
    for i, ln in enumerate(lines):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t")
        if len(f) < 7 or f[0].strip() == "[]键":
            continue
        key, en, v1, cur_v2 = f[0], f[1], f[2], f[3]
        kind = kind_of(key)
        if kind == "Dia":
            skipped_dia += 1
            continue
        if kind == "全名":
            new = v1.strip()
        else:
            head = initials_of(en)
            if not head:
                no_initials.append(key)
                new = cur_v2.strip()          # 没首字母可加 -> 保持原样
            else:
                # 若这一格已经是「首字母 + 姓」的形状，别再套一层
                if cur_v2.strip().startswith(head + " "):
                    surname = cur_v2.strip()[len(head) + 1:].strip()
                else:
                    surname = surname_of(v1)
                new = (head + " " + surname).strip()
        if new != cur_v2.strip():
            f[3] = new
            changed.append((kind, key, v1, cur_v2, new, f[0]))
            lines[i] = "\t".join(f)
        else:
            unchanged.append(kind + ":" + key.replace("[CrewName", "").replace("]", ""))

    rep = []

    def say(s=""):
        rep.append(s)

    say("共 %d 行要改（Dia 跳过 %d 行）" % (len(changed), skipped_dia))
    say("未改动 %d 行: %s" % (len(unchanged), ", ".join(unchanged)))
    if no_initials:
        say("无首字母可加、保持原值: %s" % ", ".join(no_initials))
    say("")
    say("%-6s %-22s %-24s %-14s %s" % ("类型", "键", "v1（当前版）", "旧 v2", "新 v2"))
    say("-" * 100)
    for kind, key, v1, old, new, _ in changed:
        say("%-6s %-22s %-24s %-14s %s"
            % (kind, key.replace("[CrewName", "").replace("]", ""),
               v1, old if old else "(空)", new))

    text = "\n".join(rep) + "\n"
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8-sig")   # 带 BOM，方便别的工具认编码
        print("report -> %s" % args.report)
    else:
        sys.stdout.write(text)

    if args.dry:
        print("[dry-run] 没写文件")
        return 0

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.with_name(path.name + ".bak-" + stamp)
    shutil.copy2(path, bak)
    out = eol.join(lines) + (eol if tail else "")
    path.write_bytes(out.encode("utf-8"))
    print("已写回 %s" % path.name)
    print("备份   %s" % bak.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
