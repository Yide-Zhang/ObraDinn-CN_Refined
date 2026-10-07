#!/usr/bin/env python3
"""批量填 v4（精修中文名）。

依据:
  * `jsonDump/Crew.json` 里每个人的 `birthplace`（#crew_origin_xxx）定「名从主人」的语种
  * 按现行译名规范（新华社《世界人名翻译大辞典》体例）逐人核校

只动 **全名行** 的 v4；Short 行与 Dia 段的 v4 留空。

用法:
    python CN_Refined/langpack/fill_v4.py --dry                 # 只看会改成什么
    python CN_Refined/langpack/fill_v4.py --report <UTF-8 文件>  # 报告落盘
    python CN_Refined/langpack/fill_v4.py                       # 真写（先备份）
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent                    # ObraDinnSave/
DEFAULT_TSV = HERE / "extracted" / "crew_name_variants.tsv"
CREW_JSON = ROOT / "jsonDump" / "Crew.json"

# 生地 -> 地名中译（只为了报告好读，**不作为读音依据**；读音统一按英语）
PLACE = {
    "england": "英格兰", "scotland": "苏格兰", "ireland": "爱尔兰",
    "america": "美国", "wales": "威尔士", "austria": "奥地利",
    "france": "法国", "italy": "意大利", "poland": "波兰",
    "russia": "俄罗斯", "denmark": "丹麦", "sweden": "瑞典",
    "persia": "波斯", "india": "印度", "sierra": "塞拉利昂",
    "newguinea": "新几内亚", "china": "中国", "formosa": "formosa",
}

# crew id -> (精修中文名 v4, 说明)。说明为空 = 与当前版一致（已合规范）。
V4 = {
    # ---- 英语 ----
    "captain":      ("罗伯特·威特里尔", "Witter- + -el → 威特里尔（用户查《世界人名翻译大辞典》：Witter 威特 + -el 里尔）；早先误作「威特瑞」"),
    "mate1":        ("威廉·霍斯卡特", ""),
    "mate2":        ("爱德华·尼科尔斯", "Nichols：-ols → 科尔斯（原「尼柯斯」漏尔）"),
    "mate3":        ("马丁·佩罗特", ""),
    "mate4":        ("约翰·戴维斯", ""),
    "surgeon":      ("亨利·埃文斯", ""),
    "surgeonmate":  ("詹姆斯·华莱士", ""),
    "carp":         ("温斯顿·史密斯", ""),
    "carpmate":     ("马库斯·吉布斯", ""),
    "cook":         ("托马斯·塞夫顿", ""),
    "purser":       ("邓肯·麦凯", ""),
    "sea9":         ("芬利·道尔顿", ""),
    "pass5":        ("爱德华·斯普拉特", ""),
    "pass3":        ("艾米莉·杰克逊", ""),
    "pass4":        ("简·伯德小姐", "Miss Jane Bird；Crew.json 作 Ms.（以语言包 Miss 为准）"),
    "stewm1":       ("保罗·莫斯", ""),
    "stewm3":       ("罗德里克·安德森", ""),
    "stewm4":       ("戴维·詹姆斯", "Davey → 戴维（原「大卫」是 David 的译法）"),
    "mid1":         ("彼得·米尔罗伊", "Milroy：Mil-roy → 米尔罗伊（原「米罗」丢了 roy）"),
    "mid2":         ("托马斯·兰克", ""),
    "mid3":         ("查尔斯·赫什蒂克", "Hershtik：-ik → 克（原「赫什蒂」漏克）"),
    "sea2":         ("内森·彼得斯", "Nathan → 内森（原「南森」不规范）"),
    "seab":         ("亨利·布伦南", ""),
    "sead":         ("亚历山大·布斯", ""),
    "seag":         ("塞缪尔·彼得斯", ""),
    # ---- 苏格兰 / 爱尔兰 ----
    "pass1":        ("阿比盖尔·霍斯卡特·威特里尔", "随 captain 保持一致（同为 Witterel → 威特里尔）"),
    "top6":         ("蒂莫西·布特门特", "词典 [英]：Butement → 布特门特（原按拼读误作「比特门特」）"),
    "butcher":      ("埃米尔·奥法雷", "词典：O'Farrell → 奥法雷（原我多补了一个「尔」，退回官方写法）"),
    "stewm2":       ("塞缪尔·加利根", ""),
    "seae":         ("帕特里克·奥黑根", ""),
    # ---- 奥地利（德语）----
    "bosun":        ("阿尔弗雷德·克勒斯蒂尔", "词典：Klestil → 克勒斯蒂尔（原我作「克莱斯蒂尔」，Alfred 德语 → 阿尔弗雷德）"),
    "gunner":       ("克里斯蒂安·沃尔夫", "Christian 作人名行译→克里斯蒂安（如 Christian Bale）；原「克里斯汀」是 Christine"),
    # ---- 法国（**仍按英语读法**：生地只是游戏线索，不是读音依据）----
    "bosunmate":    ("查尔斯·迈纳", "英语读法 Charles → 查尔斯；Miner → 迈纳（与当前版一致）"),
    # ---- 意大利 ----
    "pass2":        ("农西奥·帕斯夸", "词典：意大利语 Nunzio → 农西奥（原我按英语作「南齐奥」）"),
    # ---- 波兰（仍按英语读法）----
    "gunnermate":   ("奥卢斯·怀亚特", "英语读法 Wia-ter → 怀亚特（原「维尔特」把 a 丢了；按波兰语原名则为 维亚特尔）"),
    # ---- 俄语 ----
    "top2":         ("列昂尼德·沃尔科夫", "俄语 Leonid → 列昂尼德；Volkov → 沃尔科夫"),
    "sea1":         ("阿拉克斯·尼基申", "Alarcus → 阿拉克斯；俄语 -shin → 申（原「尼基新」用「新」）"),
    "sea5":         ("阿列克谢·托波罗夫", "俄语 Aleksei → 阿列克谢；Toporov → 托波罗夫"),
    # ---- 北欧 ----
    "sea3":         ("拉斯·林德", ""),
    "stewcap":      ("菲利普·达尔", ""),
    # ---- 波斯 ----
    "top5":         ("奥米德·古尔", "波斯语 Omid → 奥米德（原「奥米」漏德）"),
    # ---- 印度 / 西非 ----
    "stewship":     ("尊吉·萨提", ""),
    "sea7":         ("亚伯拉罕·阿克巴", ""),
    "sea8":         ("威廉·瓦西姆", ""),
    "seac":         ("所罗门·赛义德", ""),
    "sea4":         ("伦弗雷德·拉朱布", "Renfred → 伦弗雷德（原「雷弗莱」音节颠倒）；Rajub → 拉朱布"),
    "seaa":         ("哈马杜·迪翁", "词典：Diom → 迪翁（原我作「迪奥姆」）；Hamadou → 哈马杜"),
    # ---- 威尔士 ----
    "sea6":         ("约翰·内普尔斯", "Naples 作姓 → 内普尔斯（原「拿坡」用了地名俗译）"),
    # ---- 英格兰（续）----
    "top9":         ("尼古拉斯·博特里尔", "Nicholas → 尼古拉斯；Botterill：-ill → 尔"),
    "seaf":         ("乔治·雪利", "词典：Shirley → 雪利（原官方作「谢利」；我错按「男性不用雪莉」推断，词典不区分）"),
    "topa":         ("刘易斯·沃克", "Lewis → 刘易斯（原「路易斯」是法/西语译法）"),
    # ---- 汉语 ----
    "top1":         ("李煌", ""),
    "top4":         ("张捷", ""),
    "top7":         ("洪力", ""),
    "top8":         ("李伟", ""),
    "pass6":        ("林文澜", "Lan 按闽南语 lân → 谰；「兰」是现代女名常用字，会泄露原文没有的性别信息"),
    "pass7":        ("谢一明", ""),
    "pass8":        ("陈石", ""),
    "pass9":        ("刘鹤星", "性别中性化：福→鹤(ho̍k)、生→星(seng)，音节全对；否则四个人（福摩萨贵族素描同框）里只有它偏男，反衬出林文澜"),
    # ---- 新几内亚 ----
    "top3":         ("马巴", ""),
}


def crew_key_to_id(key: str) -> str:
    """`[CrewNameMate1]` -> `mate1`; `[CrewNameSeaC]` -> `seac`"""
    return key.replace("[CrewName", "").replace("]", "").lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", default=str(DEFAULT_TSV))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--report")
    args = ap.parse_args()
    path = Path(args.tsv)
    for p in (path, CREW_JSON):
        if not p.is_file():
            print("[X] 找不到 %s" % p)
            return 1

    crew = {}
    for row in json.loads(CREW_JSON.read_text(encoding="utf-8"))["rows"]:
        crew[row["id"]] = row

    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(eol)
    tail = False
    if lines and lines[-1] == "":
        lines.pop()
        tail = True

    rep = []
    say = rep.append
    changed, same, missing, writes = [], [], [], 0
    for i, ln in enumerate(lines):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t")
        if len(f) < 7 or f[0].strip() == "[]键":
            continue
        key = f[0]
        if key.endswith("Short]") or key.endswith("Dia]"):
            continue                       # v4 只对全名行有意义
        cid = crew_key_to_id(key)
        if cid not in V4:
            missing.append(cid)
            continue
        new, note = V4[cid]
        entry = (cid, key, f[1], f[2], new, note)
        if new == f[2].strip():
            same.append(entry)
        else:
            changed.append(entry)
        if f[5].strip() != new:            # v4 = 第 6 列
            lines[i] = "\t".join(f[:5] + [new] + f[6:])
            writes += 1

    say("全名行 60：与当前版一致（保留）%d 行；重新翻译 %d 行；实际写入 %d 格"
        % (len(same), len(changed), writes))
    say("读音依据：**统一按英语读法**（生地在游戏里是线索机制，不作为读音依据；仅当列表备查）")
    if missing:
        say("未在精修表里配到: %s" % ", ".join(missing))
    say("")
    say("【重新翻译 %d 行】" % len(changed))
    say("%-11s %-10s %-24s %-15s %-16s %s"
        % ("键", "生地", "英文名", "当前 v1", "精修 v4", "依据"))
    say("-" * 124)
    for cid, key, en, v1, new, note in changed:
        row = crew.get(cid, {})
        birth = str(row.get("birthplace", "")).replace("#crew_origin_", "")
        say("%-11s %-10s %-24s %-15s %-16s %s"
            % (key.replace("[CrewName", "").replace("]", ""),
               PLACE.get(birth, birth or "?"), row.get("name_unused", ""),
               v1 if v1 else "(空)", new, note))
    say("")
    say("【保留 %d 行】（已是现行规范译法）" % len(same))
    say("%-11s %-10s %-24s %-16s %s" % ("键", "生地", "英文名", "精修 v4（= 当前版）", "备注"))
    say("-" * 100)
    for cid, key, en, v1, new, note in same:
        row = crew.get(cid, {})
        birth = str(row.get("birthplace", "")).replace("#crew_origin_", "")
        say("%-11s %-10s %-24s %-16s %s"
            % (key.replace("[CrewName", "").replace("]", ""),
               PLACE.get(birth, birth or "?"), row.get("name_unused", ""), new, note))

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
