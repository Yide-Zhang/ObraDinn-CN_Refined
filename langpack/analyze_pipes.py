# -*- coding: utf-8 -*-
"""
摸清模板里 `|` 的**全部**用法 —— 决定「去原文」能怎么删。

背景：对话行是「原文 | 译文」两段，但 `|` 在别的行还兼着别的用途
（`fate_parts_*` / `fate_ent_*` 是分段数据、`glossary_*` 是「词条 | 释义」），
所以不能全文盲删。判定方法：拿**原始英文包**对照 ——
若模板值形如 `<英文原文><空白>|<余下>`，那它确实是「原文 | 译文」。

用法: python CN_Refined\\langpack\\analyze_pipes.py
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EX = HERE / "extracted"
TPL = EX / "template-zh-s.tsv"
EN = EX / "original-en.tsv"
ZH0 = EX / "original-zh-s.tsv"
REPORT = EX / "pipe_usage.txt"
SAMPLE = 6                      # 每类列几行样例

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def load(path: Path) -> dict[str, str]:
    raw = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    out: dict[str, str] = {}
    for ln in raw.split("\n"):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t", 1)
        if len(f) == 2:
            out[f[0]] = f[1]
    return out


def prefix(key: str) -> str:
    return key.split("_", 1)[0]


def vis(v: str) -> str:
    """把容易看错的空白显形：半角空格、全角空格(U+3000)、制表符"""
    return (v.replace("\u3000", "␣全角␣").replace(" ", "␣").replace("\\t", "␣制表␣"))


def main() -> int:
    tpl, en, zh0 = load(TPL), load(EN), load(ZH0)
    say(f"模板 {TPL.name}: {len(tpl)} 键    英文包: {len(en)} 键    原中文包: {len(zh0)} 键")
    say("")

    piped = {k: v for k, v in tpl.items() if "|" in v}
    say(f"【总览】模板里含 `|` 的键 {len(piped)} / {len(tpl)}")
    say("")

    # ---- 判定「原文 | 译文」----
    # 英文包里：英文台词是纯文本（无竖线）；外语台词才写成「原文 | 英文」。
    # 所以模板若是双语行，其第一条竖线前的内容 = 英文包的「原文」部分。
    # 再加「模板恰好一条竖线」把 fate_parts_*/fate_ent_*（多段数据）挡掉。
    def head(v: str) -> str:
        return v.split("|", 1)[0].strip(" \t")

    def norm(v: str) -> str:
        """压掉所有空白（含全角 U+3000）—— 两包偶有半角/全角之分，比较时不算差异"""
        return re.sub(r"\s+", "", v)

    def en_orig(key: str):
        """英文包在这一键上的「原文」部分"""
        e = en.get(key)
        if e is None:
            return None
        return e if "|" not in e else head(e)

    def as_bilingual(key: str, detail: bool = False):
        v = tpl.get(key, "")
        if v.count("|") != 1:
            return (False, f"模板有 {v.count('|')} 条竖线") if detail else False
        eo = en_orig(key)
        if eo is None or eo == "":
            return (False, "英文包无此键或为空") if detail else False
        if norm(head(v)) != norm(eo):
            return (False, "竖线前内容 != 英文包原文") if detail else False
        if head(v) != eo:
            return (True, "仅空白不同") if detail else True
        return (True, "") if detail else True

    def strip_orig(v: str) -> str:
        """删掉第一条 `|` 及其前面的全部内容"""
        return v.split("|", 1)[1].lstrip(" \t")

    bi, other = [], []
    for k, v in piped.items():
        (bi if as_bilingual(k) else other).append(k)

    say("【A】`<原文> | <译文>` 型（可安全去原文）")
    say("-" * 70)
    c = Counter(prefix(k) for k in bi)
    say(f"  共 {len(bi)} 键，按前缀：{dict(c)}")
    n_foreign = sum(1 for k in bi
                    if as_bilingual(k, True)[0] and head(tpl[k]) and not head(tpl[k]).isascii())
    say(f"  其中竖线前是**非 ASCII 原文**（外语台词）的 {n_foreign} 键")
    ws_only = [k for k in bi if as_bilingual(k, True)[1] == "仅空白不同"]
    if ws_only:
        say(f"  （其中 {len(ws_only)} 键与英文包的原文**只差空白**（半角/全角），"
            f"模板与官方中文包一致，不用改）")
        for k in ws_only:
            say(f"      {k}: 模板 {vis(head(tpl[k]))}   /   英文包 {vis(en_orig(k))}")
    say("")

    say("【B】`|` 的其它用途（**不能**去原文）")
    say("-" * 70)
    say(f"  共 {len(other)} 键")
    groups: dict[str, list[str]] = defaultdict(list)
    for k in other:
        groups[prefix(k)].append(k)
    for p, ks in sorted(groups.items()):
        say(f"  --- {p}  ({len(ks)} 键)")
        for k in ks[:SAMPLE]:
            say(f"      模板  {k}  =  {tpl[k][:110]}")
            say(f"      英文  {k}  =  {(en.get(k) or '<无>')[:110]}")
        if len(ks) > SAMPLE:
            say(f"      …另 {len(ks) - SAMPLE} 键")
        say("")

    say("【C】按前缀统计「含 | 的键」里两类各占多少")
    say("-" * 70)
    allpre = Counter(prefix(k) for k in piped)
    for p in sorted(allpre):
        nb = sum(1 for k in bi if prefix(k) == p)
        no = allpre[p] - nb
        say(f"  {p:<14} 含| {allpre[p]:>3}   可删 {nb:>3}   不可删 {no:>3}"
            + ("   <- 混合！" if nb and no else ""))

    say("")
    say("【D】结论")
    say("-" * 70)
    safe_all = not any(prefix(k) != "dialog" for k in bi)
    if safe_all:
        say("  可去原文的键**全部**是 `dialog_` 前缀 → 规则「只处理 dialog_*」安全 ✓")
    else:
        bad = sorted({prefix(k) for k in bi if prefix(k) != "dialog"})
        say(f"  ⚠ 除 dialog 外还有：{bad} —— 不能只按前缀判断")
    dial = [k for k in piped if prefix(k) == "dialog"]
    dial_other = [k for k in dial if not as_bilingual(k)]
    if dial_other:
        say(f"  ⚠ 有 {len(dial_other)} 个 dialog 键含 `|` 但不是「原文|译文」：")
        for k in dial_other:
            say(f"      {k}  原因：{as_bilingual(k, True)[1]}")
            say(f"        模板    : {vis(tpl[k])[:110]}")
            say(f"        英文包  : {vis(en.get(k) or '<无>')[:110]}")
            say(f"        原中文包: {vis(zh0.get(k) or '<无>')[:110]}")
    else:
        say(f"  `dialog_` 里含 `|` 的 {len(dial)} 键，**全部**符合「原文 | 译文」✓")
    say("")
    say("  去原文后的抽样（各类各一）：")
    seen = set()
    for k in bi:
        p = prefix(k)
        if p in seen:
            continue
        seen.add(p)
        say(f"    {k}")
        say(f"      前: {tpl[k][:96]}")
        say(f"      后: {strip_orig(tpl[k])[:96]}")
    for k in bi:
        if not head(tpl[k]).isascii():
            say(f"    （外语原文用例）{k}")
            say(f"      前: {tpl[k][:96]}")
            say(f"      后: {strip_orig(tpl[k])[:96]}")
            break

    text = "\n".join(lines)
    print(text)
    REPORT.write_text(text + "\n", encoding="utf-8-sig")
    print(f"\n报告已写入 {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
