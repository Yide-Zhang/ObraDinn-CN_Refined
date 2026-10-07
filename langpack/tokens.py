#!/usr/bin/env python3
"""把模板里的 [] 占位符展开成实际文本 —— 构建期的那一步。

三类占位符（用户 2026-10-06 定的语义）:

  1. 人名（138 个，来自 crew_name_variants.tsv，需选一个版本）
       [CrewNameXxx]       全名行
       [CrewNameXxxShort]  Short 行
       [CrewNameXxxDia]    Dia 行（对话/信件里的称呼）
     版本 v1..v5:
       v1 = 当前版          v2 = 当前版做 Short
       v4 = 精修版          v5 = 精修版做 Short
       v3 = 英文名（不用于中文版）

  2. 地域（按"是否和谐"二选一）
       未和谐: [China] = 中国        [Formosa] = 福尔摩莎
       和谐  : [China] = 中国大陆     [Formosa] = 中国台湾

  3. 难度: [DifficultyZH] → 该 key 难度对应的**中文小写数字**
       依据: 英文包把这些数字**写成英文单词**（"sets of three" / "Three fates correct"），
             中文包写汉字（"以三个为一组" / "有三个下落正确"），难度由 key 名区分（_3_ / _2_ / _easy）。
       → 模板里的 [DifficultyZH] 等于该 key 的那一个固定汉字（现模板 4 处，都是「三」）。
       → 数字转换覆盖 一…九十九（含用户点名的 三/四/六…五十八）。

用法:
    python CN_Refined/langpack/tokens.py --test
    python CN_Refined/langpack/tokens.py --version v4 --harmonized --demo
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TPL = HERE / "extracted" / "template-zh-s.tsv"
TBL = HERE / "extracted" / "crew_name_variants.tsv"

DIGITS = "零一二三四五六七八九"
REGION = {
    True:  {"[China]": "中国大陆", "[Formosa]": "中国台湾"},       # 和谐
    False: {"[China]": "中国",     "[Formosa]": "福尔摩莎"},        # 未和谐
}
NAME_RE = re.compile(r"\[CrewName[A-Za-z0-9_]+\]|\[China\]|\[Formosa\]|\[DifficultyZH\]")


def to_zh(n: int) -> str:
    """1..99 -> 中文小写数字（一 十 十一 二十 二十一 … 五十八 … 九十九）。"""
    if not 1 <= n <= 99:
        raise ValueError("只支持 1..99，收到 %r" % n)
    if n < 10:
        return DIGITS[n]
    tens, ones = divmod(n, 10)
    s = "" if tens == 1 else DIGITS[tens]
    s += "十"
    if ones:
        s += DIGITS[ones]
    return s


def difficulty_of(key: str) -> int:
    """该 key 的难度对应的批次数（英文/中文包都是写死的固定值）。"""
    m = re.search(r"_(\d+)(?:_|$)", key)
    if m:
        return int(m.group(1))
    if key.endswith("_easy"):
        return 2
    return 3                       # help_faceclear_fates0 / fates1 等基础 key = 三个


# 调色板: 取哪一列去展开。
# ★ Short 行刻意存的是「全名」（用户 2026-10-06 确认是特意设计），
#   所以 current / refined 两个正式调色板是【整列】选的，不分槽位；
#   v2/v5（真正的短形式）只是「将来若决定真缩写」的备选，单独放 short 调色板。
PALETTE = {
    "current": {"full": "v1", "short": "v1", "dia": "v1"},   # 当前版（应与现有包逐字一致）
    "refined": {"full": "v4", "short": "v4", "dia": "v4"},   # 精修版
    "short":   {"full": "v4", "short": "v5", "dia": "v4"},   # 若决定真的缩写
}


def slot_of(tok: str) -> str:
    if tok.endswith("Short]"):
        return "short"
    if tok.endswith("Dia]"):
        return "dia"
    return "full"


def load_names(path: Path) -> dict:
    """读人名表 -> {版本: {占位符: 值}}。"""
    cols = {"v1": 2, "v2": 3, "v3": 4, "v4": 5, "v5": 6}
    out = {v: {} for v in cols}
    raw = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    for ln in raw.split("\n"):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t")
        if len(f) < 7 or f[0].strip() == "[]键":
            continue
        for v, c in cols.items():
            out[v][f[0].strip()] = f[c].strip()
    return out


def expand(text: str, names: dict, harmonized: bool, difficulty: int,
           palette: str = "refined", forced_version: str = None, missing=None) -> str:
    region = REGION[bool(harmonized)]
    pal = PALETTE[palette]

    def sub(m):
        tok = m.group(0)
        if tok in region:
            return region[tok]
        if tok == "[DifficultyZH]":
            return to_zh(difficulty)
        ver = forced_version or pal[slot_of(tok)]
        v = names.get(ver, {}).get(tok, "")
        if v == "":
            if missing is not None:
                missing.add(tok)
            return tok
        return v
    return NAME_RE.sub(sub, text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=None, help="强行指定所有名字取哪一版 v1..v5（默认按槽位自动）")
    ap.add_argument("--palette", default="refined", choices=["refined", "current", "short"],
                    help="refined=整列 v4；current=整列 v1；short=全名 v4 / Short v5")
    ap.add_argument("--harmonized", action="store_true", help="用和谐版词（中国大陆/中国台湾）")
    ap.add_argument("--unharmonized", action="store_true", help="用未和谐版词（中国/福尔摩莎）")
    ap.add_argument("--test", action="store_true", help="自检 + 举例")
    ap.add_argument("--report", help="报告写成 UTF-8 文件（控制台中文会乱码时用）")
    args = ap.parse_args()

    rep = []

    def say(s=""):
        rep.append(s)

    if args.test:
        expect = {1: "一", 3: "三", 4: "四", 6: "六", 9: "九", 10: "十", 11: "十一",
                  20: "二十", 21: "二十一", 30: "三十", 58: "五十八", 99: "九十九"}
        bad = [(n, to_zh(n), s) for n, s in expect.items() if to_zh(n) != s]
        say("to_zh 自检 %d 例: %s" % (len(expect), "全部通过 ✓" if not bad else "!! %r" % bad))
        say("三、四、六…五十八 抽查: %s" % " ".join(to_zh(n) for n in (3, 4, 6, 20, 58)))
        say("")

    harmonized = args.harmonized or not args.unharmonized
    names = load_names(TBL)
    say("人名表 %d 行，调色板=%s，地域词=%s" % (len(names["v4"]), args.palette,
                                          "和谐" if harmonized else "未和谐"))
    if args.version:
        say("（已强行指定所有名字取 %s）" % args.version)

    # 用模板真实行做样例
    demo_keys = ["welldone_3_first", "welldone_3_more", "help_faceclear_fates0",
                 "help_faceclear_fates1", "help_faceclear_fates0_easy",
                 "crew_origin_china", "crew_origin_formosa", "sketch_formosans",
                 "crew_name_bosun", "dialog_d2_m1_ka", "dialog_d3_m1_da",
                 "tally_parting_book", "intro_built"]
    tpl = {}
    for ln in TPL.read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n"):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.split("\t")
        if len(f) >= 2:
            tpl[f[0]] = f[1]
    pack = {}
    dev = HERE / "extracted" / "dev-zh-s.tsv"
    if dev.is_file():
        for ln in dev.read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n"):
            if not ln.strip() or ln.startswith("#"):
                continue
            f = ln.split("\t")
            if len(f) >= 2:
                pack[f[0]] = f[1]

    say("")
    missing = set()
    same = 0
    for k in demo_keys:
        if k not in tpl:
            continue
        got = expand(tpl[k], names, harmonized, difficulty_of(k),
                     palette=args.palette, forced_version=args.version, missing=missing)
        cur = pack.get(k, "")
        flag = ""
        if cur:
            flag = "  ← 与当前包一致 ✓" if got == cur else "  ← 与当前包不同"
            if got == cur:
                same += 1
        say("%-24s %s%s" % (k, got.replace("\\n", "⏎"), flag))
    say("")
    say("（其中 %d 行与当前包逐字相同）" % same)
    if missing:
        say("!! 未展开的占位符: %s" % ", ".join(sorted(missing)))

    text = "\n".join(rep) + "\n"
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8-sig")
        print("report -> %s" % args.report)
    else:
        sys.stdout.write(text)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
