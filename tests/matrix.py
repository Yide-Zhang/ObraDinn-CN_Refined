#!/usr/bin/env python3
"""三个补丁的兼容性矩阵：patchwrap / patchdll / revealhook 各种叠加顺序。

每个顺序跑完，对最终 DLL 做全套检查：
  * patchwrap --check          应为 current（断行就是这版）
  * revealhook --check         应为 0（钩子在）
  * core.can_patch             patchdll 的**裸字节锚点**还认不认（关键：Cecil 重写会不会打断它）
  * core._const_value          档位常量读得出来吗
  * core.verify_patched_dll    四处是不是都到位
  * core._looks_vanilla        应为 False
  * 类型/方法/字段计数

stdout 只留 ASCII；详细日志写 UTF-8 文件（控制台会把中文搞乱）。

从 CN_Refined/tests/ 运行。素材（原版 DLL / css 基准）与共享的 langtool 都还在工作区根，
不搬进来 —— 见下面的 ROOT/LT 注释。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# ★ 本脚本住在 <工作区根>/CN_Refined/tests/ 下：
#   * 「素材」（originalDLLWin 那份原版 DLL、css 那份基准源码）仍在**工作区根**，不搬过来
#   * langtool 是三个产品共享的上游：源码在 <根>/hardcore/langtool
#     （CN_Refined 不复制它，发布时带一份构建好的二进制），这里只用它的构建产物
TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent.parent
OUT = TESTS / "out"
LT = ROOT / "hardcore" / "langtool" / "bin" / "Release" / "net8.0" / "langtool.dll"
# 游戏 Managed 目录：patchwrap 要它才能让 Cecil 重建元数据（解析 UnityEngine.*）
DEPS = os.environ.get(
    "OBRADINN_MANAGED",
    r"F:\AceAttorneySeries\gameFiles\steamapps\common\ObraDinn\ObraDinn_Data\Managed")
LEVEL = 58

sys.path.insert(0, str(ROOT))
import patcher.core as core  # noqa: E402


def run(*args: str) -> tuple[int, str]:
    p = subprocess.run(["dotnet", str(LT), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def wrap_state(dll: Path) -> tuple[str, int]:
    rc, out = run("patchwrap", str(dll), "--check", "--deps=" + DEPS)
    state = "?"
    for line in out.splitlines():
        if line.startswith("WrapPatch: "):
            state = line.split()[1]
            break
    return state, rc


def apply_chain(label: str, chain: list[str], log: list[str]) -> Path | None:
    cur = ROOT / "originalDLLWin" / "Assembly-CSharp.dll"
    for i, step in enumerate(chain):
        nxt = OUT / ("%s_%d_%s.dll" % (label, i, step))
        if step == "wrap":
            rc, out = run("patchwrap", str(cur), str(nxt), "--deps=" + DEPS)
        elif step == "diff":
            rc, out = run("patchdll", str(cur), str(nxt), str(LEVEL), "--deps=" + DEPS)
        else:
            rc, out = run("revealhook", str(cur), str(nxt), "--deps=" + DEPS)
        log.append("### %s step %d (%s) rc=%d\n%s" % (label, i, step, rc, out))
        if rc != 0:
            log.append("!!! step failed\n")
            return None
        cur = nxt
    return cur


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    orders = [
        ("WDR", ["wrap", "diff", "hook"]),
        ("DRW", ["diff", "hook", "wrap"]),
        ("RWD", ["hook", "wrap", "diff"]),
        ("WRD", ["wrap", "hook", "diff"]),
        ("DWR", ["diff", "wrap", "hook"]),
        ("RW", ["hook", "wrap"]),
        ("WR", ["wrap", "hook"]),
        ("DW", ["diff", "wrap"]),
        ("WD", ["wrap", "diff"]),
    ]
    log: list[str] = []
    rows: list[tuple[str, bool]] = []

    for label, chain in orders:
        final = apply_chain(label, chain, log)
        if final is None:
            print("%-5s  STEP-FAILED" % label)
            continue
        buf = final.read_bytes()
        st, wrc = wrap_state(final)
        hrc, _ = run("revealhook", str(final), "--check", "--deps=" + DEPS)
        ok_can, why_can = core.can_patch(buf)
        val, cands, why_note = core._const_value(buf)
        vok, vwhy = core.verify_patched_dll(final, LEVEL)
        van = core._looks_vanilla(final)
        want_hook = "hook" in chain
        want_diff = "diff" in chain
        # ★ 没跑 patchdll 的链路：难度常量就该是 3、_looks_vanilla 就该是 True
        #   （_looks_vanilla 只看难度那四个站点，与断行无关）—— 那是正确的，不是失败。
        ok = (st == "current" and wrc == 0 and ok_can
              and (val == LEVEL if want_diff else val == core.VANILLA)
              and (vok if want_diff else not vok)
              and (not van if want_diff else van)
              and (hrc == 0 if want_hook else hrc != 0))
        print("%-5s %s wrap=%-9s(wrc=%d) hook_exit=%-2d can_patch=%-5s const=%-4s "
              "verify=%-5s vanilla=%s"
              % (label, "OK " if ok else "BAD", st, wrc, hrc, ok_can, val, vok, van))
        if not ok_can:
            print("      can_patch failed: %s" % why_can)
        if want_diff and not vok:
            print("      verify failed: %s" % vwhy)
        log.append("=== %s final=%s\nwrap=%s rc=%d\nhook_exit=%d\ncan_patch=%s (%s)\n"
                   "const=%s %s\nverify=%s (%s)\nlooks_vanilla=%s\nok=%s\n"
                   % (label, final, st, wrc, hrc, ok_can, why_can, val, cands,
                      vok, vwhy, van, ok))
        rows.append((label, ok))

    bad = [lbl for lbl, ok in rows if not ok]
    log.append("bad: %s\n" % bad)
    (OUT / "matrix.log.txt").write_text("\n".join(log), encoding="utf-8")
    print("orders=%d  all_good=%d  bad=%s" % (len(rows), len(rows) - len(bad),
                                              bad or "none"))
    print("log -> %s" % (OUT / "matrix.log.txt"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
