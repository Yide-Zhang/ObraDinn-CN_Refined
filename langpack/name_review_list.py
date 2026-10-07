#!/usr/bin/env python3
"""生成「人名待核清单」——把**我改动过官方译名**的人名连同我当时的依据列出来，
方便拿《世界人名翻译大辞典》逐条复核（用户 2026-10-07 要求）。

    python CN_Refined/langpack/name_review_list.py
    → CN_Refined/out/names_review.tsv（utf-8-sig，Excel/记事本直接看）
    → CN_Refined/out/names_review.md （同内容；最后一列填词典结果，**重生成时会自动保留**）

为什么要这份：我自己发现 `Butement` 那处是**没查词典就按拼读猜**的（词典里其实有
「布特门特」）。所以把同类项全摆出来：凡是 v4≠v1（即我动过官方译名）的，都必须能对着
词典站住；标记 ★ 的是我自己都记得"当时是靠拼读/方言/性别推断"的，优先查。

列：序号 / 键 / 生地 / 英文名 / 官方原译(v1) / 我们的精修(v4) / 我当时的依据 / 标记
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fill_v4 as F4                                    # noqa: E402  复用 V4 表与 PLACE

ROOT = HERE.parent.parent
TSV = HERE / "extracted" / "crew_name_variants.tsv"
CREW_JSON = ROOT / "jsonDump" / "Crew.json"
OUT = HERE.parent / "out" / "names_review.tsv"
MD = HERE.parent / "out" / "names_review.md"
TABLE = HERE.parent / "out" / "name_table.md"       # 全量姓名对照表（60 人）

# 「我没动过、但看着有疑点」的（官方译名）：键 -> 该查什么
CHECK_UNCHANGED = {
    "mate1": "Hoscut —— 罕见拼写（mate1 与 pass1 都用它），查 Hoscut / Hoskett",
    "mate3": "Perrott —— 查 佩罗特 / 佩罗",
    "seaf": "Shirley 作**姓**（此人为男）—— 查姓氏条目：谢利 / 雪莉",
    "sea3": "Lars（丹麦）—— 查 拉斯 / 拉尔斯；Linde 林德",
    "seae": "O'Hagan —— 查 奥黑根",
    "mid2": "Lanke —— 查 兰克",
    "stewship": "Zungi / Sathi（印度）—— 查 尊吉 / 萨提",
    "bosunmate": "Miner —— 查 迈纳 / 迈因纳",
    "pass5": "Spratt —— 查 斯普拉特",
    "seab": "Brennan —— 查 布伦南",
}
# 用户 2026-10-07 查《世界人名翻译大辞典》的结果（标「已改」的已落到 fill_v4.py 与源表）
DICT_RESULT = {
    "top6":    "布特门特 ← 已改（原按拼读作 比特门特）",
    "captain": "威特里尔 ← 已改（Witter + -el；原 威特瑞）",
    "pass1":   "威特里尔 ← 已改（随 captain）",
    "bosun":   "克勒斯蒂尔 ← 已改（原 克莱斯蒂尔）",
    "butcher": "奥法雷 ← 已改（原我作 奥法雷尔；与官方写法同）",
    "pass2":   "农西奥·帕斯夸 ← 已改（原 南齐奥·帕斯夸）",
    "seaa":    "哈马杜·迪翁 ← 已改（原 哈马杜·迪奥姆）",
    "gunner":     "克里斯蒂安·沃尔夫 ✓ 与我一致",
    "gunnermate": "奥卢斯·怀亚特 ✓",
    "mate2":      "爱德华·尼科尔斯 ✓",
    "mid1":       "彼得·米尔罗伊 ✓",
    "mid3":       "词典未收（保留 查尔斯·赫什蒂克）",
    "sea1":       "阿拉克斯·尼基申 ✓",
    "sea2":       "内森·彼得斯 ✓",
    "sea4":       "伦弗雷德·拉朱布 ✓",
    "sea5":       "阿列克谢·托波罗夫 ✓",
    "sea6":       "约翰·内普尔斯 ✓",
    "stewm4":     "戴维·詹姆斯 ✓",
    "top2":       "列昂尼德·沃尔科夫 ✓",
    "top5":       "奥米德·古尔 ✓",
    "top9":       "尼古拉斯·博特里尔 ✓",
    "topa":       "刘易斯·沃克 ✓",
    # pass6 / pass9（性别中立设计）不涉词典 —— 待确认罗马字
    # 第四档（官方译名待复核）的结果，2026-10-07：
    "bosunmate": "查尔斯·迈纳 ✓ 与官方一致",
    "mate1":     "词典未收（保留 威廉·霍斯卡特）",
    "mate3":     "马丁·佩罗特 ✓",
    "mid2":      "托马斯·兰克 ✓",
    "pass5":     "爱德华·斯普拉特 ✓",
    "sea3":      "拉斯·林德 ✓（词典也作 拉斯）",
    "seab":      "亨利·布伦南 ✓",
    "seae":      "帕特里克·奥黑根 ✓",
    "seaf":      "雪利 ← 已改（词典 Shirley → 雪利；原官方/我作 谢利）",
    "stewship":  "词典未收（保留 尊吉·萨提）",
}


def merge_handfilled(path: Path) -> dict:
    """★ 把已有 md 里**手填的最后一列**按 `键` 读出来

    为什么：这份清单是脚本重生成的，而人会在文件里直接填「词典译名」。
    早期版本直接覆盖文件，把用户填的内容干掉了（2026-10-07 踩过）——
    现在重生成前先备份，并把已填值合并回来，手填的永远不丢。
    """
    got: dict = {}
    if not path.is_file():
        return got
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) < 4:
            continue
        key = next((c.strip("`") for c in cells if c.startswith("`") and c.endswith("`")), "")
        last = cells[-1]
        if key and last and "待填" not in last and not set(last) <= set("-: "):
            got[key] = last
    return got


def flags(note: str, changed: bool) -> str:
    f = []
    if "按拼读" in note or "按.*读" in note:
        f.append("★按拼读")
    if "方言" in note or "闽南" in note or "性别" in note:
        f.append("★方言/性别推断")
    if changed and not note:
        f.append("★无依据")
    if "词典" not in note and "规范" not in note and "新华社" not in note and changed and note:
        f.append("未引词典")
    return " ".join(f) or ("改动过" if changed else "=官方")


def name_table(rows: list[dict], shorts: dict) -> str:
    """全量姓名对照表：官方 vs 精修，全名与短名并列（发版/校对时一眼看完 60 人）"""
    L = ["# 姓名对照表（共 %d 人）" % len(rows), "",
         "官方 v1/v2 = 游戏原译（我们绝不动）；精修 v4/v5 = 本补丁的译名。"
         "「短名」= 游戏里简称槽位（v2 用官方姓、v5 用精修姓）。", "",
         "| # | 键 | 英文名 | 生地 | 官方全名 | 精修全名 | 官方短名 | 精修短名 |",
         "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: x["no"]):
        s = shorts.get(r["id"], {})
        bold = lambda t: ("**%s**" % t) if t and t != r["official"] else t  # noqa: E731
        L.append("| %d | `%s` | %s | %s | %s | %s | %s | %s |"
                 % (r["no"], r["id"], r["en_name"] or r["en"], r["place"],
                    r["official"], bold(r["ours"]),
                    s.get("v2", ""), bold(s.get("v5", ""))))
    L.append("")
    return "\n".join(L)


def markdown(rows: list[dict], merged: dict) -> str:
    """同一份数据的 Markdown 版：最后一列是词典核校结果

    ★ 重生成不会丢掉手填值：`main()` 先 `merge_handfilled()` 把旧文件里那一列读回来，
    并先写一份 `.bak`（早期版本直接覆盖，把用户填的内容干掉了 —— 2026-10-07 踩过）。
    """
    changed = [r for r in rows if r["changed"]]
    same = [r for r in rows if not r["changed"]]
    hi = [r for r in changed if r["flag"].startswith("★")]
    rest = [r for r in changed if not r["flag"].startswith("★")]
    L = ["# 人名待核清单（对《世界人名翻译大辞典》逐条核）", "",
         "为什么有这份：`Butement` 那处是我**没查词典就按拼读猜**的（词典里其实有"
         "「布特门特」）。所以把同类项全摆出来 —— 凡是 v4≠v1（我动过官方译名）的，"
         "都得能对着词典站住。", "",
         "- 共 %d 人；**我动过官方译名的 %d 人**（下表），其余 %d 人未动。" % (len(rows), len(changed), len(same)),
         "- 最后一列留空，查到什么填什么（写「词典未收」也行）；回填给我，我一条流水线改完并重打包。",
         "- 生地只是线索，**不作为读音依据**；读音统一按英语（除俄语/波斯语等明显非英语音节）。", ""]

    def table(items):
        L.append("| # | 键 | 英文名 | 生地 | 官方原译 (v1) | 我们的精修 (v4) | 我当时的依据 | 词典译名 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in items:
            note = r["note"] or "（未记依据）"
            filled = DICT_RESULT.get(r["id"]) or merged.get(r["id"], "")
            L.append("| %d | `%s` | %s | %s | %s | **%s** | %s | %s |"
                     % (r["no"], r["id"], r["en_name"] or r["en"], r["place"],
                        r["official"] or "(空)", r["ours"], note, filled))
        L.append("")

    L.append("## 一、★ 优先查（我当时靠拼读 / 方言推断，`Butement` 就是这一类）")
    L.append("")
    table(hi)
    L.append("## 二、其余我改动过官方译名的（同一种风险：都只用了「按拼读」的规则）")
    L.append("")
    table(rest)
    L.append("## 三、我没动过的（= 官方译名，仅供参考）")
    L.append("")
    L.append("| # | 键 | 英文名 | 生地 | 译名 |")
    L.append("|---|---|---|---|---|")
    for r in same:
        L.append("| %d | `%s` | %s | %s | %s |" % (r["no"], r["id"], r["en_name"] or r["en"],
                                                   r["place"], r["official"]))
    L.append("")
    L.append("## 四、官方译名里想请你顺手核的（我没动过，但看着有疑点）")
    L.append("")
    L.append("| # | 键 | 英文名 | 生地 | 官方译名 | 疑点 | 词典译名 |")
    L.append("|---|---|---|---|---|---|---|")
    for r in same:
        if r["id"] not in CHECK_UNCHANGED:
            continue
        filled = DICT_RESULT.get(r["id"]) or merged.get(r["id"], "")
        L.append("| %d | `%s` | %s | %s | %s | %s | %s |"
                 % (r["no"], r["id"], r["en_name"] or r["en"], r["place"],
                    r["official"], CHECK_UNCHANGED[r["id"]], filled))
    L.append("")
    L.append("（其余未动过的名字我过了两遍，都是现行规范译法：Davies→戴维斯、Booth→布斯、"
             "Wallace→华莱士、McKay→麦凯、Gibbs→吉布斯、Andersen→安德森、"
             "Jackson→杰克逊、Dalton→道尔顿、Akbar→阿克巴、Syed→赛义德、Wasim→瓦西姆 …；"
             "另外 6 个是中文名（李煌/张捷/洪力/李伟/谢一明/陈石），不涉词典。）")
    L.append("")
    L.append("## 附：回填后我会跑的流水线")
    L.append("")
    L.append("```")
    L.append("fill_v4.py（含依据）→ crew_name_variants.tsv → check_table.py 验表")
    L.append("  → build_pack.py --all 重出 20 个 TSV → make_package.py 同步进 assets → 重打包 exe")
    L.append("```")
    L.append("")
    return "\n".join(L)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # type: ignore[union-attr]
    except Exception:                                        # noqa: BLE001
        pass
    crew = {r["id"]: r for r in json.loads(CREW_JSON.read_text(encoding="utf-8"))["rows"]}
    rows = []
    shorts: dict = {}
    for ln in TSV.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t")
        if len(f) < 7 or f[0].endswith("Dia]"):
            continue
        if f[0].endswith("Short]"):
            cid = F4.crew_key_to_id(f[0].replace("Short]", "]"))
            shorts[cid] = {"v2": f[3].strip(), "v5": f[6].strip()}
            continue
        cid = F4.crew_key_to_id(f[0])
        v1, v4 = f[2].strip(), f[5].strip()
        note = F4.V4.get(cid, ("", ""))[1]
        info = crew.get(cid, {})
        birth = str(info.get("birthplace", "")).replace("#crew_origin_", "")
        rows.append({
            "id": cid, "key": f[0].strip("[]"), "en": f[1],
            "place": F4.PLACE.get(birth, birth or "?"),
            "official": v1, "ours": v4, "note": note,
            "flag": flags(note, v4 != v1),
            "changed": v4 != v1,
            "en_name": str(info.get("name_unused", "")),
        })

    order = {"★按拼读": 0, "★方言/性别推断": 1, "★无依据": 2}
    def rank(r):
        for k, v in order.items():
            if r["flag"].startswith(k):
                return v
        return 3 if r["changed"] else 4
    rows.sort(key=lambda r: (rank(r), r["id"]))

    out = ["序号\t键\t生地\t英文名\t官方原译(v1)\t我们的精修(v4)\t我当时的依据\t标记"]
    for i, r in enumerate(rows, 1):
        r["no"] = i
        out.append("\t".join([str(i), r["id"], r["place"], r["en_name"] or r["en"].split("|")[0].strip(),
                              r["official"], r["ours"], r["note"] or "（未记依据）", r["flag"]]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8-sig")
    merged = merge_handfilled(MD)                       # ★ 先读回手填的，再覆盖
    if MD.is_file():
        shutil.copy2(MD, MD.with_name(MD.name + ".bak"))
    MD.write_text(markdown(rows, merged), encoding="utf-8")
    TABLE.write_text(name_table(rows, shorts), encoding="utf-8")
    print("[+] %s" % TABLE)
    print("[i] 手填列已保留 %d 项（重生成前备份 %s.bak）" % (len(merged), MD.name))

    changed = [r for r in rows if r["changed"]]
    star = [r for r in rows if r["flag"].startswith("★")]
    print("[+] %s（共 %d 人）" % (OUT, len(rows)))
    print("[+] %s" % MD)
    print("    动过官方译名的 %d 人；其中我标了★的 %d 人（优先查）" % (len(changed), len(star)))
    for r in star + [x for x in changed if x not in star]:
        print("    %-8s %-14s %-16s %-16s  %s" % (r["id"], r["place"], r["ours"],
                                                  r["official"] or "(空)", r["flag"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
