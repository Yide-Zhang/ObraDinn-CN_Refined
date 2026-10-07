# -*- coding: utf-8 -*-
"""验证「本补丁不改难度，只读难度 + 写对应文案」这条流水线。

    python CN_Refined\\installer\\tools\\test_difficulty_flow.py

两个场景（都在沙盒里跑，不碰真游戏）：
  A) 玩家是原版游戏（DLL 里批大小 3）→ 文案应为「三个」，DLL 难度不变（只加换行修补）
  B) 玩家自己用过 hardcore 那套难度补丁（批大小 58）→ 文案应为「五十八」，
     且我们的安装**不能**动那个难度（DLL 装完仍是 58）
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[1]
CR = ROOT / "CN_Refined"
SB = CR / "out" / "testgame"
OUT = PKG / "out"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PKG))

import engine as E                                     # noqa: E402
import make_testgame as MT                             # noqa: E402

KEYS = ["welldone_3_first", "welldone_3_more",
        "help_faceclear_fates0", "help_faceclear_fates1"]
LANGTOOL = PKG / "assets" / "langtool" / "langtool.exe"

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)
    print(m, flush=True)


def keys_of(sandbox: Path) -> dict[str, str]:
    """导出沙盒里的 lang-zh-s，取出那 4 个键"""
    tsv = OUT / "_flow-export.tsv"
    lt = LANGTOOL if LANGTOOL.is_file() else E.langtool()
    cmd = ([str(lt)] if lt.suffix.lower() == ".exe" else ["dotnet", str(lt)])
    r = subprocess.run(cmd + ["export", str(sandbox / "ObraDinn_Data" / "StreamingAssets" / "lang-zh-s"),
                              str(tsv)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return {"__error__": (r.stderr or r.stdout or "")[-300:]}
    out = {}
    for ln in tsv.read_text(encoding="utf-8").splitlines():
        k, _, v = ln.partition("\t")
        if k in KEYS:
            out[k] = v
    return out


def install() -> tuple[bool, list[str]]:
    opt = E.Options(version="v5", harmonized=False, dialog="bi")   # level=None → 自动读
    return E.install(SB, opt, force=True)


def dll_state() -> tuple[str, int | None, bool]:
    dll = SB / "ObraDinn_Data" / "Managed" / "Assembly-CSharp.dll"
    lv, b2 = E.dll_difficulty_level(dll)
    return E.sha(dll)[:16], lv, b2


def step(tag: str) -> None:
    say("")
    say("=" * 84)
    say(tag)
    say("=" * 84)


def main() -> int:
    ok_all = True

    # ---------------------------------------------------------------- 场景 A
    step("场景 A：原版游戏")
    MT.main()                                          # 重建沙盒（真原版）
    sha0, lv0, _ = dll_state()
    say("安装前 DLL: sha=%s  难度=%s" % (sha0, lv0))
    ok, _log = install()
    sha1, lv1, b21 = dll_state()
    k = keys_of(SB)
    say("安装完成=%s" % ok)
    say("安装后 DLL: sha=%s  难度=%s  B2=%s" % (sha1, lv1, b21))
    say("4 条文案:")
    for kk in KEYS:
        say("    %-22s %s" % (kk, k.get(kk, "（缺失）")))
    a_ok = (ok and lv0 == lv1 == 3 and "三个" in k.get("help_faceclear_fates0", "")
            and "三个" in k.get("welldone_3_first", ""))
    say("→ %s（难度必须没被我们改：%s → %s）" % ("通过 ✓" if a_ok else "不通过 ✗", lv0, lv1))
    ok_all &= a_ok

    # ---------------------------------------------------------------- 场景 B
    step("场景 B：玩家自己打过 hardcore 难度补丁（58）")
    dll = SB / "ObraDinn_Data" / "Managed" / "Assembly-CSharp.dll"
    tmp = OUT / "_flow-lv58.dll"
    managed = str((CR / "originalassets" / "_gamebackup-20261006-220426").parent)
    real_managed = str(Path("F:/AceAttorneySeries/gameFiles/steamapps/common/ObraDinn/"
                            "ObraDinn_Data/Managed"))
    cmd = ([str(LANGTOOL)] if LANGTOOL.suffix.lower() == ".exe" else ["dotnet", str(LANGTOOL)])
    r = subprocess.run(cmd + ["patchdll", str(dll), str(tmp), "58", "--deps=" + real_managed],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    say("（模拟玩家侧：patchdll -> 58  返回码 %d）" % r.returncode)
    if r.returncode != 0 or not tmp.is_file():
        say("✗ 模拟失败，跳过场景 B")
        return 1
    shutil.copy2(tmp, dll)
    sha2, lv2, b22 = dll_state()
    say("玩家打过之后 DLL: sha=%s  难度=%s  B2=%s" % (sha2, lv2, b22))

    ok, _log = install()
    sha3, lv3, b23 = dll_state()
    k = keys_of(SB)
    say("我们的安装完成=%s" % ok)
    say("安装后 DLL: sha=%s  难度=%s  B2=%s" % (sha3, lv3, b23))
    say("4 条文案:")
    for kk in KEYS:
        say("    %-22s %s" % (kk, k.get(kk, "（缺失）")))
    b_ok = (ok and lv2 == lv3 == 58 and b23
            and "五十八" in k.get("help_faceclear_fates0", "")
            and "五十八" in k.get("welldone_3_first", ""))
    say("→ %s（我们的安装既没把 58 退回 3，也没重复打补丁）" % ("通过 ✓" if b_ok else "不通过 ✗"))
    ok_all &= b_ok

    # 顺便：再加一次 wrap 是否仍然幂等
    step("补充：换行修补（wrap）幂等性")
    lt = E.langtool()
    rc = subprocess.run(([str(lt)] if lt.suffix.lower() == ".exe" else ["dotnet", str(lt)])
                        + ["patchwrap", str(dll), "--check"], capture_output=True).returncode
    say("patchwrap --check 返回码 = %d（0 = 已打）" % rc)
    ok_all &= (rc == 0)

    say("")
    say("总体：%s" % ("全部通过 ✓" if ok_all else "有不通过项 ✗"))
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "difficulty-flow.txt"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("报告: %s" % p)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
