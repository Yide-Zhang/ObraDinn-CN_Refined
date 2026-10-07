# -*- coding: utf-8 -*-
"""生成「单语模板」并出可审阅的对照清单。

产物：
  1. `langpack/extracted/template-zh-s-mono.tsv`  —— 去掉原文的单语模板（可直接打开/对比）
  2. `out/packs/REVIEW-mono.tsv`  —— 表格：键 / 双语 / 单语 / 标记（347 行 + 未改动的 dialog 行）
  3. `out/packs/REVIEW-mono.txt`  —— 人读版：概览 + 可疑项 + 按章节逐条对照

去原文用的是 `build_pack.py` 里**同一个** strip_original，保证审查对象 = 实际构建逻辑。

用法: python CN_Refined\\langpack\\make_mono_review.py
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_pack as B  # noqa: E402  —— 复用它的 strip_original

EX = HERE / "extracted"
PACKS = HERE.parent / "out" / "packs"
TPL = EX / "template-zh-s.tsv"
MONO = EX / "template-zh-s-mono.tsv"
EN = EX / "original-en.tsv"
# ★ 官方 zh-s：判定「官方自己带竖线 → 单语也保留原文」
OFF = EX / "original-zh-s.tsv"
FORCE = "--force" in sys.argv      # --force = 按新规则重写，丢弃单语模板里的手改
CJK = lambda s: any("\u4e00" <= c <= "\u9fff" for c in s)   # noqa: E731

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def load(path: Path):
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    rows, order = [], []
    for ln in raw.split(eol):
        if not ln.strip() or ln.startswith("#"):
            rows.append((None, ln))
            continue
        f = ln.split("\t", 1)
        if len(f) == 2:
            rows.append((f[0], f[1]))
            order.append(f[0])
        else:
            rows.append((None, ln))
    # 末尾空行已作为一行保留在 rows 里，join 回去就自带结尾换行 —— 不要再补
    return raw, eol, rows, order


def group_of(key: str) -> str:
    s = key[len("dialog_"):] if key.startswith("dialog_") else key
    return s.rsplit("_", 1)[0] if "_" in s else s


def main() -> int:
    raw, eol, rows, order = load(TPL)
    enr = {}
    for ln in EN.read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n"):
        f = ln.split("\t", 1)
        if len(f) == 2:
            enr[f[0]] = f[1]

    offr = {}
    if OFF.exists():
        for ln in OFF.read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n"):
            f = ln.split("\t", 1)
            if len(f) == 2:
                offr[f[0]] = f[1]
    prev = {}
    if MONO.exists():
        for ln in MONO.read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n"):
            f = ln.split("\t", 1)
            if len(f) == 2:
                prev[f[0]] = f[1]

    out_rows, changed, untouched = [], [], []
    kept_official, manual, stale = [], [], []
    for kind, val in rows:
        if kind is None:
            out_rows.append(val)
            continue
        if not kind.startswith("dialog_"):
            new = val
        else:
            # ★ 规则：官方 zh-s 那一行带竖线 → 单语保留原文（原文是线索）
            new = B.mono_value(kind, val, offr.get(kind, ""))
            if new == val and "|" in val:
                kept_official.append(kind)
        # ★ 与磁盘上那份合并（除非 --force），三分支：
        #   · 与规则值相同        → 照规则值（等于没动）
        #   · 等于「严格删」的产物 → 那是**旧规则的残留**，跟进新规则（不算手改）
        #   · 其它                → 视为手改，保留磁盘上的那份
        old = prev.get(kind)
        if old is not None and old != new and kind.startswith("dialog_") and not FORCE:
            strict = B.strip_original(kind, val)
            if old == strict and new != strict:
                stale.append(kind)
            else:
                manual.append((kind, new, old))
                new = old
        if kind.startswith("dialog_"):
            (changed if new != val else untouched).append((kind, val, new))
        out_rows.append(kind + "\t" + new)

    MONO.write_bytes(eol.join(out_rows).encode("utf-8"))

    # --------------------------- 可疑项 ---------------------------
    flags = defaultdict(list)
    for k, bi, mo in changed:
        head = bi.split("|", 1)[0]
        if mo == "":
            flags["单语是空的"].append(k)
        elif not CJK(mo):
            has_tok = "[CrewName" in mo
            flags["只含人名占位符+标点（展开后是中文名，正常）" if has_tok
                  else "单语里没有汉字"].append(k)
        if "|" in mo:
            flags["单语里还留着竖线"].append(k)
        if mo != mo.rstrip():
            flags["单语末尾有空格"].append(k)
        if mo == head.strip():
            flags["原文与译文相同"].append(k)
        if mo[:1] in "、，。！？；：）】」』":
            flags["单语以标点开头"].append(k)

    # --------------------------- 人读报告 ---------------------------
    say("单语模板 审查清单")
    say("=" * 74)
    say(f"来源模板 : {TPL.name}（{len(order)} 键）")
    say(f"单语模板 : {MONO.name}")
    say(f"  官方带竖线（单语保留原文）的行 {len(kept_official)} 个"
        f"{('：' + ', '.join(kept_official[:8]) + ('…' if len(kept_official) > 8 else '')) if kept_official else ''}")
    if stale:
        say(f"  ★ 旧规则残留、已跟进新规则的行 {len(stale)} 个"
            f"（旧=删原文，新=保留原文）：{', '.join(stale[:6])}"
            + ("…" if len(stale) > 6 else ""))
    if manual:
        say(f"  ★ 保留模板里的手改 {len(manual)} 行（与规则值不同，未覆盖）：")
        for k, gen, old in manual:
            say(f"      {k}  规则值={gen[:36]!r} → 保留={old[:36]!r}")
    if FORCE and prev:
        say("  （--force：已按规则重写，手改未保留）")
    say(f"dialog_* 键 {len(changed) + len(untouched)} 个："
        f"含竖线**已去原文** {len(changed)} 个，不含竖线**原样保留** {len(untouched)} 个")
    say(f"其余 {len(order) - len(changed) - len(untouched)} 键一个字符都没动")
    say("")

    say("【1】可疑项（请重点看）")
    say("-" * 74)
    if not flags:
        say("  无 ✓")
    for name, ks in flags.items():
        say(f"  {name}：{len(ks)} 个")
        for k in ks[:12]:
            bi = dict((a, b) for a, b, _ in changed)[k]
            mo = dict((a, c) for a, _, c in changed)[k]
            say(f"      {k}")
            say(f"          双语: {bi[:92]}")
            say(f"          单语: {mo[:92]}")
        if len(ks) > 12:
            say(f"      …另 {len(ks) - 12} 个")
    say("")

    say("【2】已去原文的 %d 行（按场景分组对照）" % len(changed))
    say("-" * 74)
    groups = defaultdict(list)
    for k, bi, mo in changed:
        groups[group_of(k)].append((k, bi, mo))
    for g in sorted(groups):
        say(f"  ── {g}  ({len(groups[g])} 行)")
        for k, bi, mo in groups[g]:
            say(f"     {k}")
            say(f"        双语: {bi}")
            say(f"        单语: {mo}")
        say("")

    say("【3】含竖线但**未**改动的 dialog 行 = 无（应为 0）"
        if not untouched else f"【3】**未改动**的 dialog 行 {len(untouched)} 个（本就没有原文）")
    say("-" * 74)
    for k, bi, mo in untouched:
        e = enr.get(k, "<无>")
        same = "  ← 与英文包相同" if bi == e else ""
        say(f"  {k}")
        say(f"      模板  : {bi}")
        say(f"      英文包: {e}{same}")
    say("")

    say("【4】对照表")
    say("-" * 74)
    say(f"  {PACKS / 'REVIEW-mono.tsv'}（键 / 双语 / 单语 / 标记）")

    text = "\n".join(lines)
    print(text)
    (PACKS / "REVIEW-mono.txt").write_text(text + "\n", encoding="utf-8-sig")

    lines_out = ["键\t双语\t单语\t标记"]
    for kind, val in rows:
        if kind is None or not kind.startswith("dialog_"):
            continue
        mo = B.strip_original(kind, val)
        marks = []
        if mo == val:
            marks.append("未改动")
        if mo == "":
            marks.append("空")
        elif not CJK(mo):
            marks.append("无汉字")
        if "|" in mo:
            marks.append("残留竖线")
        if mo == val.split("|", 1)[0].strip():
            marks.append("原文=译文")
        lines_out.append("\t".join([kind, val, mo, " ".join(marks)]))
    (PACKS / "REVIEW-mono.tsv").write_text("\n".join(lines_out) + "\n", encoding="utf-8-sig")

    print(f"\n单语模板 -> {MONO}")
    print(f"人读清单 -> {PACKS / 'REVIEW-mono.txt'}")
    print(f"对照表   -> {PACKS / 'REVIEW-mono.tsv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
