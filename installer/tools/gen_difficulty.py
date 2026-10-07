# -*- coding: utf-8 -*-
"""生成 data/difficulty.json —— 难度档位表（内容参考 hardcore）。

    python CN_Refined\\installer\\tools\\gen_difficulty.py

背景（见 hardcore/PATCH-SPEC.md）：
  游戏按「批」验证下落，原版批大小写死 3（`FateEditor.UpdateFateGuesses` 里 `int num = 3;`）。
  批越大越难：批内错一个就全批不通过，且没有中间检查点。hardcore 把它改成可配档位，
  同时改掉两处配套代码（2 元素数组分支、音效索引取模）和盖章步进间隔（让总时长恒定）。

  档位集合 = {4, 6, 9, 14, 29, 58}（hardcore 现行；早先的 7 已拆成 6 和 9，不再有 7）。
  「3」= 原版行为，安装时**不动 DLL**。

  语言包侧：4 个键的中文数字要跟着档位变（hardcore 是直接改写这 4 条，
  `_lang/out/lv*/edits-zh-s.txt`）。我们保留自己的译文，只换数字 —— 见 engine.apply_difficulty()。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
DATA = PKG / "data"

# 批大小 -> (中文数字, 档位名, 一句话说明)
LEVELS = [
    (3, "三", "原版（不改）", "按原版节奏：每次验证 3 人"),
    (4, "四", "容易", "每批验证 4 个下落"),
    (6, "六", "中等", "每批验证 6 个下落"),
    (9, "九", "较难", "每批验证 9 个下落"),
    (14, "十四", "困难", "每批验证 14 个下落"),
    (29, "二十九", "极难", "每批验证 29 个下落"),
    (58, "五十八", "硬核", "一次结清全部 58 人的下落（没有中间检查点）"),
]

# 随档位变化的中文数字所在的键（与 hardcore 的 edits-zh-s.txt 完全一致）
KEYS = ["welldone_3_first", "welldone_3_more",
        "help_faceclear_fates0", "help_faceclear_fates1"]

# 中文数字字符集（用于在译文里把旧数字换成新数字，保留我们自己的措辞）
NUM_CHARS = "〇一二三四五六七八九十百两"


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    obj = {
        "note": "难度档位表。patch=true 的档位要跑 langtool patchdll；3 是原版行为，不动 DLL。",
        "keys": KEYS,
        "num_chars": NUM_CHARS,
        "batch_keys_note": "这 4 个键里的中文数字随档位变（TSV 里写死的是原版「三」）",
        "levels": [
            {"level": n, "zh": zh, "label": label, "desc": desc, "patch": n != 3}
            for n, zh, label, desc in LEVELS
        ],
    }
    p = DATA / "difficulty.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")

    # 自检：每个档位的 zh 必须是合法中文数字且非空
    bad = [l for l in obj["levels"] if not l["zh"] or any(c not in NUM_CHARS for c in l["zh"])]
    for l in obj["levels"]:
        print("  %-3s 批 %-4s %s" % (l["level"], l["zh"], l["desc"]))
    print("")
    print("  ✓ %s" % p)
    print("  档位 %d 个，自检%s" % (len(obj["levels"]), "通过 ✓" if not bad else "失败 ✗ %s" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
