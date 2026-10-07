#!/usr/bin/env python3
"""生成 CrewName 对照表（精修工作表）。

列：
    key | en（英文原值，**不改动**，逐字照抄） | v1（当前中文全名） | v2（当前中文 Short）
        | v3（英文名字版） | v4（精修中文名，待填） | v5（精修中文名+Short，待填）

数据来源：
    v1 / v2  ← dev 包的两格
    v3       ← en 包的两格（把英文的 ` | ` 写成模板用的 `|`）
    v4 / v5  ← 留空，精修阶段填

★ 中文版的 Short 槽位目前与全名相同（没有像英文那样缩写成「R. Witterel」），
  所以 v1 与 v2 通常一模一样 —— 这正是这张表要看出来的问题。

按模板里的出场顺序排列，只含 crew_name_*（不含 [China] / [Formosa] / [DifficultyZH]）。

用法: python make_name_table.py <TSV 目录> <输出.tsv>
注意: 重跑会覆盖输出（含你填过的 v4/v5）—— 要保留请先另存。
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

HEADER = (
    "# CN_Refined 人名占位符对照表（精修工作表）\n"
    "# 行 = 待赋值的 [] 键（与模板里的占位符一一对应；全名行与 Short 行成对相邻）\n"
    "# 列 = 候选值:\n"
    "#   en : 英文原值（**不改动**，逐字照抄，仅作对照）\n"
    "#   v1 : 版本1 = 和当前版类似\n"
    "#        （全名行 = 当前中文全名；Short 行 = 当前 Short 槽位的值，通常与全名相同）\n"
    "#   v2 : 版本2 = 和当前版类似但做 Short\n"
    "#        （只对 Short 行有意义；全名行此列留空）\n"
    "#        当前提案规则: 取「姓」—— 西式名取最后一个「·」之后，中文名取首字，\n"
    "#        英文本身就没缩写的（如 Maba|Maba）整名照搬。规则不对就整列重出。\n"
    "#   v3 : 版本3 = 英文名字版（全名行 = 英文全名；Short 行 = 英文 Short）\n"
    "#   v4 : 版本4 = 精修中文名（待填；只对全名行有意义）\n"
    "#   v5 : 版本5 = 精修中文名+Short（待填；只对 Short 行有意义）\n"
    "# 说明: 中文版的 Short 槽位目前与全名相同（未像英文那样缩写成「R. Witterel」）。\n"
    "# 已排除: [China] [Formosa] [DifficultyZH]\n"
    "#\n"
    "# []键\ten\tv1\tv2\tv3\tv4\tv5\n"
)


def en_form(en_line: str, en_full: str, en_short: str) -> str:
    """看英文台词里到底是怎么称呼这个人的（Dia 行的 v3）。

    Dia 值是「台词里的称呼」，英文那边就是原文里出现的那几个词 —— 拿人名表硬套
    （直接填 `C. Hershtik`）会驴唇不对马嘴：台词里叫的是 `Charlie`。
    所以按「最具体 → 最泛」把候选逐个在台词里找，找到哪个算哪个。
    """
    toks = (en_full or "").split()
    cands: list[str] = []
    for c in ((en_full or "").strip(), en_short, toks[-1] if toks else "",
              toks[0] if toks else ""):
        if c and c not in cands:
            cands.append(c)
    for c in cands:
        if c in en_line:
            return c
    return "(台词里没直呼其名，或用了昵称)"


def short_of(name: str, en_full: str, en_short: str) -> str:
    """「当前中文名做 Short」的提案：取姓。

    * 英文本身就没缩写（en_short == en_full，如 Maba|Maba）→ 整名照搬
    * 西式名（含「·」）→ 最后一个「·」之后那一段
    * 中文名（无「·」）→ 首字（姓在前的习惯：林文兰 → 林）
    """
    if not name:
        return ""
    if en_short and en_full and en_short == en_full:
        return name
    if "·" in name:
        return name.rsplit("·", 1)[1] or name
    return name[0] if len(name) >= 2 else name



def guess(tpl_val: str, other: str, tok: str) -> str:
    """把 other（同 key 的 **dev** 值）里对应 tok 位置的那段文字反推出来。

    ★ 不要用「公共前后缀」那种写法：模板行是被改写过文字的，局部一改前后缀就崩（三封信
      那种长段落会整段抓错）。改用字符级 diff 对齐：把 tok 在 tpl 里覆盖到的那几个
      opcode 的参照侧区间合起来，就是它被换成的值。
    ★ 也不能拿英文行来推 —— 中英字符不重合，对齐无意义；英文对照请取 crew_name_* 的 en 值。
    """
    p = tpl_val.find(tok)
    if p < 0 or not other:
        return "?"
    q = p + len(tok)
    sm = difflib.SequenceMatcher(None, tpl_val, other, autojunk=False)
    j1 = j2 = None
    for tag, i1, i2, k1, k2 in sm.get_opcodes():
        if i2 <= p or i1 >= q:
            continue
        if tag == "equal":
            off = p - i1
            j1, j2 = k1 + off, k1 + off + len(tok)
        else:
            j1 = k1 if j1 is None else min(j1, k1)
            j2 = k2 if j2 is None else max(j2, k2)
    if j1 is None or j2 is None or j2 <= j1:
        return "?"
    got = other[j1:j2]
    # 反推值过长 → 对齐失败了（局部改写太大），宁可标成 ? 让人看
    if len(got) > 12:
        return got[:12] + "…?"
    return got


def load(path: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        k, _, v = line.partition("\t")
        d[k] = v
    return d


def slots(v: str | None) -> tuple[str, str]:
    if v is None:
        return ("", "")
    a, sep, b = v.partition("|")
    if not sep:
        return (a.strip(), "")
    return (a.strip(), b.strip())


def main() -> int:
    root = Path(sys.argv[1])
    out = Path(sys.argv[2])

    dev = load(root / "dev-zh-s.tsv")
    en = load(root / "original-en.tsv")
    tpl = load(root / "template-zh-s.tsv")

    keys = [k for k in tpl if k.startswith("crew_name_")]
    rows: list[str] = [HEADER.rstrip("\n")]
    same = 0
    n_pair = 0
    for k in keys:
        d1, d2 = slots(dev.get(k))
        e1, e2 = slots(en.get(k))
        env = en.get(k, "")
        # 行头用模板里真实的占位符（不靠命名规则推）
        toks = re.findall(r"\[[A-Za-z0-9_]+\]", tpl.get(k, ""))
        if d1 == d2:
            same += 1
        rows.append("\t".join([toks[0] if toks else "[?]", env, d1, "", e1, "", ""]))
        if len(toks) > 1:
            n_pair += 1
            rows.append("\t".join([toks[1], env, d2, short_of(d2, e1, e2),
                                   e2 if e2 else e1, "", ""]))

    # ---- [CrewName<X>Dia]：对话/信件里的称呼 ----
    # ★ 按**占位符**去重：同一个 []键 在多个 key 里出现，赋值的还是同一个值，只该占一行。
    #   出现处合并成一列；若同一占位符在不同行反推出的值不一致，那是模板自身矛盾，标出来。
    dia: dict[str, list[tuple[str, str]]] = {}
    for k, v in tpl.items():
        for t in re.findall(r"\[CrewName[A-Za-z0-9_]*Dia\]", v):
            occ = dia.setdefault(t, [])
            if any(k == x[0] for x in occ):
                continue
            occ.append((k, guess(v, dev.get(k, ""), t)))

    rows.append("")
    rows.append("# ---- 以下是对话/信件里的称呼占位符（**已按占位符去重**，一个键只赋一次值）----")
    rows.append("# 列与上面一致；末尾额外多一列「出现处」（列在最后的辅助列，不属于那五个版本）")
    rows.append("#   v1 = 当前 Dia 值（从「模板行 ↔ dev 行」按字符对齐反推）")
    rows.append("#   v2 = 当前版做 Short（= 该人名的姓，规则同上）")
    rows.append("#   v3 = 英文台词里实际怎么称呼他 —— 从英文原文里逐候选找出来的")
    rows.append("# []键\ten\tv1\tv2\tv3\tv4\tv5\t出现处")
    for t, occ in dia.items():
        # [CrewNameSeaCDia] -> crew_name_seac（去前后缀、转小写）
        stem = t[len("[CrewName"):-len("Dia]")].lower()
        ck = "crew_name_" + stem
        ce1, ce2 = slots(en.get(ck))
        # ★ v2 从 **Short 槽位**取姓，不是全名槽位：pass4 的全名是「简·伯德小姐」，
        #   从全名取会得到「伯德小姐」（把敬称带进来了）；Short 槽位是「简·伯德」→ 「伯德」。
        _, cd2 = slots(dev.get(ck))

        vals = sorted({x[1] for x in occ})
        cur = " / ".join(vals)
        if len(vals) > 1:
            cur += "   ⚠ 同一占位符在不同行反推出的值不一致，需人工确认"

        forms: list[str] = []
        for k, _ in occ:
            f = en_form(en.get(k, ""), ce1, ce2)
            if f not in forms:
                forms.append(f)

        rows.append("\t".join([t, en.get(ck, ""), cur, short_of(cd2, ce1, ce2),
                               " / ".join(forms), "", "",
                               ", ".join(x[0] for x in occ)]))

    out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("crew_name_* = %d ; 全名行 + Short 行 = %d" % (len(keys), len(keys) + n_pair))
    print("当前 Short 槽位 == 全名 的 = %d" % same)
    print("Dia 占位符 = %d" % len(dia))
    print("%d 行 -> %s" % (len(rows), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
