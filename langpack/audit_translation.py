# -*- coding: utf-8 -*-
"""翻译质量审计：英文原版  vs  我们的 template-zh-s。

每一项检查都**同时跑官方中文包**，用来分清「我们引入的问题」和「继承官方的问题」。

检查项：
  A 未翻译（中文与英文完全相同）
  B `$` 占位符集合不一致（硬错误，会导致游戏里变量丢失）
  C 富文本标签（<size=…> 等）不一致
  D `\\n` / `\\t` 数量不一致（差得多 = 可能漏了一整段）
  E 中文段落里混入半角标点
  F 引号问题（半角 " / 不配对）
  G 中文里残留英文单词
  H 长度比异常（疑似漏译/超译）
  I 职务术语一致性（crew_job_* / deck_* / fate_ent_* 三处应一致）
  J 我们改动过的键里，是否**机械回归**（丢了 `$var`/标签 或 `\\n` 数变了）

用法: python CN_Refined\\langpack\\audit_translation.py
产物: CN_Refined\\out\\audit\\template_quality.txt
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EX = HERE / "extracted"
OUTDIR = HERE.parent / "out" / "audit"
REPORT = OUTDIR / "template_quality.txt"

TPL = EX / "template-zh-s.tsv"
EN = EX / "original-en.tsv"
OFF = EX / "original-zh-s.tsv"

# ⚠ Python 的 \w 会匹配汉字（`$0个下落` 会被当成变量名）—— 必须显式限定字符集
VAR = re.compile(r"\$[A-Za-z0-9_]+")
TAG = re.compile(r"<[^>]+>")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def eff(key: str, v: str) -> str:
    """取「译文部分」：双语 dialog 行（`原文 | 译文`）只看竖线之后。

    否则会把原文当成中文里的「残留英文」/ 换成别的什么。
    非双语行的 `|` 是数据分隔（fate_* / crew_name_* / glossary_*），不能切。
    已查证：`dialog_*` 且恰好一条竖线的 347 行**全部**是「原文 | 译文」。
    """
    if key.startswith("dialog_") and v.count("|") == 1:
        return v.split("|", 1)[1].lstrip(" \t\u3000")
    return v


def cjk(s: str) -> bool:
    return bool(CJK.search(s))


lines: list[str] = []
_section: list[str] = []


def say(m: str = "") -> None:
    _section.append(m)


def flush(title: str) -> None:
    lines.append(title)
    lines.extend(_section)
    lines.append("")
    _section.clear()


def load(p: Path) -> dict[str, str]:
    out = {}
    for ln in p.read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n"):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t", 1)
        if len(f) == 2:
            out[f[0]] = f[1]
    return out


def n_esc(v: str, ch: str) -> int:
    return v.count("\\" + ch)


# --------------------------------------------------------------- 检查项
def chk_untranslated(e: str, z: str):
    if e.strip() and z.strip() == e.strip():
        return "与英文完全相同"
    return None


def chk_var(e: str, z: str):
    a, b = sorted(VAR.findall(e)), sorted(VAR.findall(z))
    if a != b:
        return "英文 %s / 中文 %s" % (a or "无", b or "无")
    return None


def chk_tag(e: str, z: str):
    a, b = TAG.findall(e), TAG.findall(z)
    if a != b:
        return "英文 %s / 中文 %s" % (a or "无", b or "无")
    return None


def chk_break(e: str, z: str):
    ne, nz = n_esc(e, "n"), n_esc(z, "n")
    if ne and nz != ne:
        return "\\n 英文 %d / 中文 %d" % (ne, nz)
    return None


def chk_halfpunct(e: str, z: str):
    if not cjk(z):
        return None
    bad = []
    for i, ch in enumerate(z):
        if ch not in ",.?!;:":
            continue
        prev = z[i - 1] if i else ""
        nxt = z[i + 1] if i + 1 < len(z) else ""
        # 只报「被中文夹着」或「跟在中文后面且不在行尾数字/英文里」的
        if (cjk(prev) or prev == "") and (cjk(nxt) or nxt == ""):
            bad.append(ch)
    if bad:
        return "混入 %s" % "".join(sorted(set(bad)))
    return None


def chk_quote(e: str, z: str):
    if not cjk(z):
        return None
    msgs = []
    if '"' in z:
        msgs.append('半角双引号 %d 个' % z.count('"'))
    o, c = z.count("\u201c"), z.count("\u201d")
    if o != c:
        msgs.append("“%d/”%d 不配对" % (o, c))
    return "、".join(msgs) if msgs else None


NAMEY = {"Obra", "Dinn", "Memento", "Mortem", "Lucas", "Pope", "LLC", "Voices.com",
         "H.E.", "Amazon", "Windows", "Mac", "Linux", "OS", "Steam"}
WORD = re.compile(r"[A-Za-z][A-Za-z'’.\-]{2,}")


def chk_latin(e: str, z: str):
    if not cjk(z):
        return None
    # 占位符 `[...]`（CrewName/DifficultyZH/China/Formosa）不是「残留英文」
    z = re.sub(r"\[[^\]]*\]", "", z)
    left = [w for w in WORD.findall(z) if w not in NAMEY]
    return "残留英文 %s" % ", ".join(sorted(set(left))) if left else None


def chk_len(e: str, z: str):
    if len(e) < 20 or VAR.search(e) or TAG.search(e):
        return None
    r = len(z) / max(1, len(e))
    if r < 0.22:
        return "中文只有英文的 %.0f%% 长" % (r * 100)
    if r > 2.2:
        return "中文是英文的 %.0f%% 长" % (r * 100)
    return None


LISTY = re.compile(r"^[a-z0-9-]+(?:, [a-z0-9-]+)+$")


def chk_honorific(e: str, z: str):
    """敬语混用：同一段里既用「您」又用「你」"""
    if z.count("您") and z.count("你"):
        return "同时用了您(%d) 和 你(%d)" % (z.count("您"), z.count("你"))
    return None


def chk_listy(e: str, z: str):
    """逗号分隔的 id 列表（如 fate_sort）：元素集/顺序是否被改过"""
    if not (LISTY.match(e.strip()) and LISTY.match(z.strip())):
        return None
    a, b = e.strip().split(", "), z.strip().split(", ")
    if set(a) != set(b):
        return "列表元素变了：多 %s / 少 %s" % (sorted(set(b) - set(a)), sorted(set(a) - set(b)))
    if a != b:
        return "元素相同但**顺序被改了**"
    return None


PERKEY = [("A 未翻译", chk_untranslated), ("B $占位符不一致", chk_var),
          ("C 富文本标签不一致", chk_tag), ("D \\n 数量不一致", chk_break),
          ("E 混入半角标点", chk_halfpunct), ("F 引号问题", chk_quote),
          ("G 残留英文单词", chk_latin), ("H 长度比异常", chk_len),
          ("I 您/你混用", chk_honorific), ("J 列表字段被动过", chk_listy)]

# ★ 用户已确认「有意如此」的项 —— 不再当作待修（2026-10-06 确认）
ACCEPTED = {
    "C 富文本标签不一致":
        "8 个 fate_parts_* 删掉 <M>/<F>/<m>/<f>/<b> 变体标签是**故意的**——"
        "中文不随性别变格。源码 Manifest.ApplyGender 证明：标签只做条件删段、"
        "没有标签就原样显示，所以完全安全。",
    "F 引号问题":
        "bookmarked_* 的半角 \" 是官方自带的，游戏里渲染正常，不改。",
    "I 您/你混用":
        "官方包自身也混用（2 键）；我们已把 office_letter_mid 修好（现 0 键）。",
}


def run(rows: dict[str, str], en: dict[str, str]):
    """返回 {检查名: [(key, 说明), ...]}；双语 dialog 行只比译文部分"""
    res = defaultdict(list)
    for k, z in rows.items():
        e = en.get(k)
        if e is None:
            continue
        zz, ee = eff(k, z), eff(k, e)
        for name, fn in PERKEY:
            r = fn(ee, zz)
            if r:
                res[name].append((k, r))
    return res


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    en, tpl, off = load(EN), load(TPL), load(OFF)
    changed = {k for k in tpl if k in off and tpl[k] != off[k]}

    rt, ro = run(tpl, en), run(off, en)

    lines.append("翻译质量审计：英文原版  vs  我们的 template-zh-s")
    lines.append("=" * 78)
    lines.append("英文包 %d 键；我们的模板 %d 键；官方中文包 %d 键" % (len(en), len(tpl), len(off)))
    lines.append("我们相对官方中文包改动了 %d 键（这部分是本审计的重点）" % len(changed))
    lines.append("")
    lines.append("每项都给「我们 / 官方」两个计数：")
    lines.append("  · 两边都有 → 继承官方的问题")
    lines.append("  · 只有我们有 → **我们引入的**（要修）")
    lines.append("")
    lines.append("【总表】")
    lines.append("-" * 78)
    lines.append("  %-22s %8s %8s %8s" % ("检查项", "我们", "官方", "我们独有"))
    for name, _ in PERKEY:
        a, b = rt[name], ro[name]
        ka, kb = {k for k, _ in a}, {k for k, _ in b}
        mine = len(ka - kb)
        mark = ""
        if name in ACCEPTED:
            mark = "   ← 已确认故意" if mine else "   ← 已确认故意"
        lines.append("  %-22s %8d %8d %8d%s" % (name, len(a), len(b), mine, mark))
    lines.append("")
    lines.append("  带「已确认故意」的行不计为待修；其余项的「我们独有」才是真问题。")
    lines.append("")

    for name, _ in PERKEY:
        a, b = rt[name], ro[name]
        if not a:
            continue
        bs = {k: m for k, m in b}
        mine = [(k, m) for k, m in a if k not in bs]
        both = [(k, m) for k, m in a if k in bs]
        say("【%s】我们 %d 个（官方 %d 个）" % (name, len(a), len(b)))
        acc = name in ACCEPTED
        if acc:
            say("  ✔ 此项**已确认有意如此**，不算问题：%s" % ACCEPTED[name])
        if mine:
            say("  ── %s：%d 个" % ("已确认（官方没有）" if acc else "我们独有（官方没有）← 需要修",
                                  len(mine)))
            for k, m in mine:
                say("      %s" % k)
                say("          %s" % m)
                say("          EN: %s" % en[k][:110])
                say("          中: %s" % tpl[k][:110])
        if both:
            say("  ── 官方也有（继承）：%d 个" % len(both))
            show = both if len(both) <= 20 else both[:6]
            for k, m in show:
                say("      %s   %s" % (k, m))
                if name in ("I 您/你混用", "J 列表字段被动过"):
                    say("          官方: %s" % off.get(k, "")[:150])
                    say("          我们: %s" % tpl.get(k, "")[:150])
            if len(show) < len(both):
                say("      …另 %d 个" % (len(both) - len(show)))
        flush("")

    # ---- I職务术语一致性 ----
    say("【K】职务术语一致性：crew_job_* / deck_* / fate_ent_* 三处应一致")
    jobs = sorted(k[len("crew_job_"):] for k in tpl if k.startswith("crew_job_"))
    bad = 0
    for j in jobs:
        got = {}
        if "crew_job_" + j in tpl:
            got["crew_job_" + j] = tpl["crew_job_" + j]
        if "deck_" + j in tpl:
            got["deck_" + j] = tpl["deck_" + j]
        fe = "fate_ent_" + j
        if fe in tpl:
            m = re.search(r"（(.+?)）", tpl[fe])
            if m:
                got[fe] = m.group(1)
        vals = set(got.values())
        if len(vals) > 1:
            bad += 1
            say("  ✗ %s" % j)
            for k, v in got.items():
                say("        %-22s %s" % (k, v))
    if not bad:
        say("  三处用到职务的地方完全一致 ✓（共 %d 个职务）" % len(jobs))
    say("")

    # ---- J 改动键的机械回归 ----
    say("【L】我们改动过的 %d 键：机械回归检查" % len(changed))
    say("  只比「机器可判定」的东西：$占位符、富文本标签、\\n 数 —— 不看措辞")
    reg = []
    for k in sorted(changed):
        e, a, b = en.get(k, ""), off[k], tpl[k]
        msgs = []
        ea, eb = sorted(VAR.findall(a)), sorted(VAR.findall(b))
        if ea != eb:
            msgs.append("$占位符 %s → %s" % (ea or "无", eb or "无"))
        ta, tb = TAG.findall(a), TAG.findall(b)
        if ta != tb:
            msgs.append("标签 %s → %s" % (ta or "无", tb or "无"))
        na, nb = n_esc(a, "n"), n_esc(b, "n")
        if na != nb:
            msgs.append("\\n %d → %d" % (na, nb))
        if msgs:
            reg.append((k, msgs, e, a, b))
    if reg:
        say("  ⚠ 有 %d 个键在我们改写时动了机器可判定的东西：" % len(reg))
        for k, msgs, e, a, b in reg:
            say("      %s   %s" % (k, "；".join(msgs)))
            say("          EN : %s" % e[:110])
            say("          官方: %s" % a[:110])
            say("          我们: %s" % b[:110])
    else:
        say("  改动过的键里，$占位符 / 标签 / \\n 数**一处都没动** ✓")
    say("")

    # ---- 术语漂移：同一英文，多种中文 ----
    say("【M】术语漂移：同一个英文短句被译成了不同中文（≥3 种才算）")
    m = defaultdict(set)
    for k, e in en.items():
        z = tpl.get(k)
        if not z:
            continue
        e, z = eff(k, e), eff(k, z)
        if "|" in e or VAR.search(e) or TAG.search(e) or len(e) > 26:
            continue
        if re.match(r"^[\w' .\-]+$", e):
            m[e.strip().lower()].add(z.strip())
    drift = {k: v for k, v in m.items() if len(v) >= 3}
    if not drift:
        say("  无（同一英文短句的译法都收敛）")
    for k, v in sorted(drift.items(), key=lambda x: -len(x[1]))[:20]:
        say("  %-28s %s" % (k, " / ".join(sorted(v))))
    say("")

    # ---- L 长句抽样（供人逐句读）----
    say("【N】长句抽样对照：英文 vs 我们（按长度降序，前 45 条）")
    say("  这类句子最能看出翻译功底（信息量最大、最容易漏或添油加醋）")
    long_rows = []
    for k, z in tpl.items():
        e = en.get(k)
        if not e:
            continue
        ee, zz = eff(k, e), eff(k, z)
        if VAR.search(ee) or TAG.search(ee):
            continue
        if len(ee) >= 70:
            long_rows.append((len(ee), k, ee, zz))
    long_rows.sort(reverse=True)
    for n, k, ee, zz in long_rows[:45]:
        say("  ── %s（英文 %d 字符）" % (k, n))
        say("     EN: %s" % ee)
        say("     中 : %s" % zz)
    say("  （共 %d 条长度 ≥70 的句子）" % len(long_rows))
    say("")

    # ---- 改动对照表（给人工审的表格）----
    chg = ["键\t英文\t官方中文\t我们的中文"]
    for k in sorted(changed):
        chg.append("\t".join([k, en.get(k, "").replace("\t", " "),
                              off[k].replace("\t", " "),
                              tpl[k].replace("\t", " ")]))
    (OUTDIR / "our_changes.tsv").write_text("\n".join(chg) + "\n", encoding="utf-8-sig")

    flush("")          # ← I/J/K/L 也在缓冲里，必须收尾一次才写得出去
    text = "\n".join(lines)
    print(text)
    REPORT.write_text(text + "\n", encoding="utf-8-sig")
    print("报告已写入 %s" % REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
