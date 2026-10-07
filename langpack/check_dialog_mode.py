# -*- coding: utf-8 -*-
"""校验「对话单语」包：与同版本的「双语」包逐键比对，确认只动了该动的行。

断言：
  1. 两包键集合/顺序完全一致，键数一致
  2. **非** dialog_ 行逐字节相同（`|` 的其它用途一处都没被碰）
  3. dialog_ 行：含 `|` 的 = 双语包第一条 `|` 之后（去首部空白）；
     不含 `|` 的 = 原样
  4. 改动行数 == 模板里 dialog_ 含 `|` 的行数（应 347）
  5. 单语包里 dialog_ 行不再残留原文（不含 `|`，且不以英文包原文开头）

用法: python CN_Refined\\langpack\\check_dialog_mode.py
"""
from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
EX = HERE / "extracted"
PACKS = HERE.parent / "out" / "packs"
TPL = EX / "template-zh-s.tsv"
EN = EX / "original-en.tsv"
OFF = EX / "original-zh-s.tsv"
REPORT = PACKS / "check_dialog_mode.txt"

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def load(path: Path):
    raw = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    rows = []
    for ln in raw.split("\n"):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t", 1)
        if len(f) == 2:
            rows.append((f[0], f[1]))
    return rows


def strip_orig(val: str) -> str:
    return val.split("|", 1)[1].lstrip(" \t\u3000")


# ★ 单语模式下必须**保留原文**的行，两个来源：
#   ①（主要，现算）**官方 zh-s 自己那一行带 `|`** —— 原文是外语/闽南语线索，不能删；
#   ②（额外申报）官方没带竖线但也不能删的，例如 `dialog_d2_m0_fa` 的 `Signor`
#      （意大利语，是确定该人籍贯的线索；官方写成「尼柯斯先生（Signor）」，也不删）。
KEEP_EXTRA = {
    "dialog_d2_m0_fa": "Signor（意大利语）是籍贯线索，不能删",
}


def main() -> int:
    tpl = dict(load(TPL))
    en = dict(load(EN))
    official = dict(load(OFF)) if OFF.exists() else {}
    # ① 官方 zh-s 自己带竖线的行（现算，会随官方包/模板变化自动跟上）
    off_pipe = {k for k, v in tpl.items() if k.startswith("dialog_") and "|" in v
                and "|" in (official.get(k) or "")}
    # ② + 额外申报的行
    keep_hit = off_pipe | {k for k in KEEP_EXTRA if k in tpl and "|" in tpl[k]}
    n_all = sum(1 for k, v in tpl.items() if k.startswith("dialog_") and "|" in v)
    n_expect = n_all - len(keep_hit)

    say("对话单语/双语 包校验")
    say("=" * 72)
    say(f"模板里 dialog_ 含竖线的行 = {n_all}；其中单语须保留原文 {len(keep_hit)} 行"
        f"（官方带竖线 {len(off_pipe)} + 额外申报 {len(keep_hit) - len(off_pipe)}）"
        f" → 预期改动数 = {n_expect}")
    say("")

    vers = [f"zh-s-{v}-{h}" for v in ("v1", "v2", "v3", "v4", "v5")
            for h in ("harm", "unharm")]
    allok = True
    for stem in vers:
        bi_p, mo_p = PACKS / f"{stem}-bi.tsv", PACKS / f"{stem}-mono.tsv"
        if not (bi_p.exists() and mo_p.exists()):
            say(f"[{stem}] 缺文件")
            allok = False
            continue
        bi, mo = load(bi_p), load(mo_p)
        keys_bi, keys_mo = [k for k, _ in bi], [k for k, _ in mo]
        probs = []
        if keys_bi != keys_mo:
            probs.append("键顺序/集合不同")
        changed, nondlg_bad, dlg_bad, kept = [], [], [], 0
        keepok, keepbad = [], []
        bd, md = dict(bi), dict(mo)
        for k in keys_bi:
            a, b = bd[k], md[k]
            if k in keep_hit:
                # 有意保留原文：应与双语值逐字相同，且原文首段（去空白后）必须还在
                # ⚠ 必须忽略空白：英文包用 U+3000、模板用半角空格（`dialog_d4_m0_ea/fa` 如此）
                o = en.get(k) or ""
                head = (o.split("|", 1)[0] if o else "").strip()
                first = re.sub(r"\s+", "", head.split(",", 1)[0][:24])
                if a != b:
                    keepbad.append(f"{k} 单语值与双语值不同（应保留原文）")
                elif first and first not in re.sub(r"\s+", "", b):
                    keepbad.append(f"{k} 单语值里找不到原文首段 {first!r}（线索可能被删了）")
                else:
                    keepok.append(k)
                continue
            if k.startswith("dialog_") and "|" in a:
                if b != strip_orig(a):
                    dlg_bad.append(k)
                else:
                    changed.append(k)
            else:
                if a != b:
                    nondlg_bad.append(k)
                if k.startswith("dialog_"):
                    kept += 1
        # 残留原文检查
        #   注意：「原文==译文」的行（如 `救命啊！ | 救命啊！`）删完必然还等于原文，
        #   那是正常的，不能算残留 —— 只对「原文≠译文」的行做这项检查。
        left, same = [], []
        for k in changed:
            a, b, o = bd[k], md[k], en.get(k)
            head = (o if "|" not in o else o.split("|", 1)[0].strip()) if o else None
            if "|" in b:
                left.append(f"{k} 单语值仍含竖线")
                continue
            if head is None or not b.startswith(head):
                continue
            if strip_orig(a) == head:
                same.append(k)          # 原文与译文相同，正常
            else:
                left.append(f"{k} 单语值仍以原文开头（原文≠译文，疑似没删掉）")
        ok = (not probs and not nondlg_bad and not dlg_bad
              and len(changed) == n_expect and not left and not keepbad
              and len(keepok) == len(keep_hit))
        allok &= ok
        say(f"[{stem}]  {len(keys_bi)} 键  "
            f"改动 {len(changed)}/{n_expect}  非dialog行被误改 {len(nondlg_bad)}  "
            f"改动不符 {len(dlg_bad)}  残留 {len(left)}  "
            f"有意保留原文 {len(keepok)}/{len(keep_hit)}"
            f"{'':>2}原文=译文 {len(same)}   {'✓' if ok else '✗'}")
        if keepbad:
            say("    ✗ 有意保留原文的行有问题：")
            for m in keepbad:
                say(f"      {m}")
        if same:
            say(f"    （原文与译文相同的行，删后自然等于原文，正常：{', '.join(same)}）")
        if probs:
            say(f"    {probs}")
        if nondlg_bad:
            say(f"    ✗ 非 dialog 行被改了 {len(nondlg_bad)} 个：")
            for k in nondlg_bad[:8]:
                say(f"        {k}")
                say(f"          双语: {bd[k][:88]}")
                say(f"          单语: {md[k][:88]}")
        if dlg_bad:
            for k in dlg_bad[:5]:
                say(f"    ✗ {k}")
                say(f"          双语: {bd[k][:88]}")
                say(f"          单语: {md[k][:88]}")
                say(f"          应为: {strip_orig(bd[k])[:88]}")
        for t in left[:5]:
            say(f"    ✗ {t}")

    say("")
    say("=" * 72)
    say("全部 20 个包通过 ✓" if allok else "⚠ 有包未通过，见上")
    # 抽样展示
    k0 = "dialog_intro_ba"
    if k0 in tpl:
        say("")
        say(f"抽样 {k0}:")
        say(f"  双语: {dict(load(PACKS / 'zh-s-v4-harm-bi.tsv')).get(k0, '')}")
        say(f"  单语: {dict(load(PACKS / 'zh-s-v4-harm-mono.tsv')).get(k0, '')}")
    k1 = "dialog_d1_m0_aa"
    if k1 in tpl:
        say(f"抽样 {k1}（外语原文行，原文是印地语）:")
        say(f"  双语: {dict(load(PACKS / 'zh-s-v4-harm-bi.tsv')).get(k1, '')}")
        say(f"  单语: {dict(load(PACKS / 'zh-s-v4-harm-mono.tsv')).get(k1, '')}")

    text = "\n".join(lines)
    print(text)
    REPORT.write_text(text + "\n", encoding="utf-8-sig")
    print(f"\n报告已写入 {REPORT}")
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
