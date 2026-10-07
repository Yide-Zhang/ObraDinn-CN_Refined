# -*- coding: utf-8 -*-
"""验证演示模式（DEMO）真的不落盘 —— 直接拿**真游戏目录**跑，最硬的判据。

    python CN_Refined\\installer\\tools\\test_demo_mode.py

做三件事：
  1) 记录真游戏那 5 个文件的 sha + ObraDinnCN-installer 是否存在
  2) 开 DEMO 跑一遍 install / restore
  3) 再记一次，两者必须完全一致（且日志里能看到「演示」字样、报告文件照旧生成）
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[1]
OUT = PKG / "out"
sys.path.insert(0, str(PKG))

import engine as E                                     # noqa: E402

GAME = Path("F:/AceAttorneySeries/gameFiles/steamapps/common/ObraDinn")
REL = [E.DLL_REL,
       E.SHS_REL / "sharedassets0.assets",
       E.SHS_REL / "sharedassets2.assets",
       E.SHS_REL / "sharedassets6.assets",
       E.SA_REL / E.LANG]
STASH = GAME / E.STASH_DIR

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)
    print(m, flush=True)


def snap() -> dict:
    d = {"stash_exists": STASH.exists()}
    if d["stash_exists"]:
        d["stash_files"] = sorted(p.name for p in STASH.rglob("*") if p.is_file())
    d["files"] = {}
    for rel in REL:
        p = GAME / rel
        d["files"][rel.as_posix()] = E.sha(p)[:16] if p.is_file() else "（缺失）"
    return d


def main() -> int:
    if not E.looks_like_game(GAME):
        say("✗ 找不到真游戏目录 %s" % GAME)
        return 1
    say("真游戏目录: %s" % GAME)
    say("")
    say("① 演示前")
    before = snap()
    for k, v in before["files"].items():
        say("    %-44s %s" % (k, v))
    say("    ObraDinnCN-installer 存在? %s" % before["stash_exists"])

    # ---- 开演示模式 ----
    E.DEMO = True
    say("")
    say("② 演示 install（v5 / 未和谐 / 双语）")
    opt = E.Options(version="v5", harmonized=False, dialog="bi")
    ok1, log1 = E.install(GAME, opt, force=True)
    for ln in log1:
        say("    " + ln)
    say("    返回 ok=%s" % ok1)

    say("")
    say("③ 演示 restore")
    ok2, log2 = E.restore(GAME)
    for ln in log2:
        say("    " + ln)
    say("    返回 ok=%s" % ok2)
    E.DEMO = False

    # ---- 复查 ----
    say("")
    say("④ 演示后（必须与①完全一致）")
    after = snap()
    same_files = before["files"] == after["files"]
    for k, v in after["files"].items():
        mark = "=" if before["files"].get(k) == v else "✗ 变了!"
        say("    %-44s %s  %s" % (k, v, mark))
    say("    ObraDinnCN-installer 存在? %s（演示前 %s）"
        % (after["stash_exists"], before["stash_exists"]))
    say("")
    ok = same_files and after["stash_exists"] == before["stash_exists"]
    has_demo_word = any("演示" in ln for ln in log1 + log2)
    ok &= has_demo_word
    say("文件未变: %s ✓" % same_files if same_files else "✗ 文件被改了！")
    say("日志里有「演示」字样: %s" % ("有 ✓" if has_demo_word else "没有 ✗"))
    say("")
    say("结论：%s" % ("演示模式无副作用 ✓" if ok else "有问题 ✗"))

    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "demo-mode.txt"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("报告: %s" % p)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
