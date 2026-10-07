#!/usr/bin/env python3
"""装一遍、验一遍 —— Windows / macOS 通用的整链自测。

为什么要有它：
  仓库里原来的 `tools/test_demo_mode.py` / `tools/test_difficulty_flow.py` 都**写死了
  Windows 的游戏路径**（F:\\…），mac 上跑不了；而 mac 版恰恰是最需要验证的 ——
  它在布局（.app 包里的 Data/）、langtool 二进制（Mach-O）、路径语义上都跟 Windows 不同。

它做的事（每步都打印证据，不靠“应该没问题”）：
  1. 定位游戏并打印**实际布局**（数据目录名、DLL / shs / StreamingAssets / stash 落点）
  2. langtool 能不能跑（`patchwrap --check` 返回 0 或 1 都算能跑；报别的就是坏）
  3. 装前 state（逐文件判定 原版/我们的/其它/未知）
  4. 记录 5 个目标文件的 sha
  5. 真装（`--demo` 则只走演示模式，不写盘）
  6. 装后 state（应当全是 ours）
  7. **再装一次** —— 5 个文件的 sha 必须一模一样（幂等：install 永远从确定基线重做）
  8. 结论 + 提醒去游戏里肉眼验（三个难度档 × 四张表）

用法：
    python3 CN_Refined/installer/tools/selftest.py                    # 自动探测游戏
    python3 CN_Refined/installer/tools/selftest.py --game "<游戏目录或 .app>"
    python3 CN_Refined/installer/tools/selftest.py --demo             # 只演示，不写盘
    python3 CN_Refined/installer/tools/selftest.py --restore          # 测完把游戏还原

★ 默认**不还原**：stash 里是用户自己机器的原始文件，安装结果是用户想要的补丁，
  不该被一个自测脚本擅自撤掉。
"""
from __future__ import annotations

import argparse
import hashlib
import platform
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent                        # CN_Refined/installer
sys.path.insert(0, str(PKG))

import engine as E                       # noqa: E402


def sha(p: Path) -> str:
    if not p.is_file():
        return "-"
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def targets(game: Path) -> list[Path]:
    """安装会碰的文件（OUR_FILES 由 engine 按当前布局生成）"""
    return [game / rel for rel in E.OUR_FILES]


def dump_state(game: Path, title: str) -> list:
    print("\n== %s ==" % title)
    st = E.inspect_state(game)
    for s in st:
        print("  %-44s %-8s %s" % (s.rel, s.verdict, s.detail))
    return st


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # type: ignore[union-attr]
    except Exception:                                     # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="安装器整链自测（Windows / macOS 通用）")
    ap.add_argument("--game", help="游戏目录（mac 可以是 .app 或 …/Contents/Resources/Data）")
    ap.add_argument("--demo", action="store_true", help="只跑演示模式（不写盘）")
    ap.add_argument("--restore", action="store_true", help="测完把游戏还原到安装前")
    ap.add_argument("--no-idem", action="store_true", help="跳过幂等复验（省时间）")
    ap.add_argument("--level", type=int, choices=range(6),
                    help="强制难度档位（默认读游戏当前难度）")
    a = ap.parse_args()

    print("[i] 平台 %s %s / Python %s" % (platform.system(), platform.machine(),
                                           sys.version.split()[0]))
    # ---- 1. 定位游戏 + 打印布局 ----
    if a.game:
        g = E.game_root(Path(a.game).expanduser())
        how = "命令行指定"
    else:
        g, how = E.detect_game()
    if g is None:
        print("[!] 没找到游戏：用 --game 指一个目录（mac 上给 .app 或 …/Resources/Data 都行）")
        return 2
    print("[i] 游戏：%s（%s）" % (g, how))
    print("    布局：数据目录 %s" % (E.DLL_REL.parts[0] if E.DLL_REL.parts else "?"))
    for rel in E.OUR_FILES:
        print("      %-46s %s" % (rel.as_posix(), "有" if (g / rel).is_file() else "缺"))
    print("    stash：%s" % (g / E.STASH_DIR))
    if not E.looks_like_game(g):
        print("[!] 这个目录不像 ObraDinn（mac 上要指到…/Contents/Resources 那一层）")
        return 2

    # ---- 2. langtool 能不能跑 ----
    lt = E.langtool()
    print("\n== langtool ==")
    if lt is None:
        print("  [!] 找不到 langtool（包里应有 assets/langtool/langtool.exe 或无扩展名的 langtool）")
        return 2
    print("  %s  %.2f MB" % (lt, lt.stat().st_size / 1048576))
    dll = g / E.DLL_REL
    rc = E.run(E.lt_cmd(lt, "patchwrap", str(dll), "--check"), quiet=True).returncode
    if rc not in (0, 1):
        print("  [!] patchwrap --check 返回 %d（期望 0=已打 / 1=没打）—— 这个二进制不对" % rc)
        return 2
    print("  ✓ 能跑（patchwrap --check 返回 %d：%s）" % (rc, "已打 wrap" if rc == 0 else "还没打"))

    # ---- 3~5. 装前 state → 记录 sha → 安装 ----
    dump_state(g, "安装前")
    before = {rel: sha(g / rel) for rel in E.OUR_FILES}
    opt = E.Options(version="v5", harmonized=False, dialog="bi", level=a.level)
    print("\n== 安装 ==")
    t0 = time.time()
    ok, log = E.install(g, opt, force=True)
    print("  用时 %.1f 秒，结果 %s" % (time.time() - t0, "成功" if ok else "失败"))
    for ln in log:
        if ln.strip():
            print("  " + ln)
    if not ok and not a.demo:
        print("[!] 安装没成功 —— 上面哪一步 ✗ 就是原因")
        return 1

    # ---- 6. 装后 state ----
    st = dump_state(g, "安装后")
    if not a.demo:
        bad = [s for s in st if s.verdict not in ("ours",)]
        if bad:
            print("[!] 这些文件装完还不是「我们的」：%s"
                  % ", ".join("%s[%s]" % (s.rel, s.verdict) for s in bad))
            return 1
        print("  ✓ 5 个目标文件全部判定为 ours")

    # ---- 7. 幂等复验 ----
    if not a.demo and not a.no_idem:
        after1 = {rel: sha(g / rel) for rel in E.OUR_FILES}
        print("\n== 再装一次（幂等复验）==")
        ok2, _log2 = E.install(g, opt, force=True)
        after2 = {rel: sha(g / rel) for rel in E.OUR_FILES}
        same = {rel: after1[rel] == after2[rel] for rel in E.OUR_FILES}
        for rel, eq in same.items():
            print("  %s %-46s %s" % ("✓" if eq else "✗", rel.as_posix(),
                                     after2[rel][:16] + "…"))
        if not ok2 or not all(same.values()):
            print("[!] 不幂等（第二次装出来的字节跟第一次不同）—— 这会让「重复点安装」变得危险")
            return 1
        print("  ✓ 幂等：两次安装的字节完全一致")
        changed = [rel.as_posix() for rel in E.OUR_FILES if before[rel] != after2[rel]]
        print("  [i] 相对安装前真正变了 %d/5 个：%s"
              % (len(changed), ", ".join(Path(c).name for c in changed)))

    if a.demo:
        print("\n[=] 演示模式走通（未写盘）")
    else:
        print("\n[=] PASS —— 装得上、状态对、可重复")
        print("    去游戏里肉眼验：三个难度档的「糟糕/好」文案、四张表（人名单/草图/甲板/海图）、")
        print("    『帮助 → 清除命运』的提示语，还有换行是否正常。")

    if a.restore:
        print("\n== 还原 ==")
        okr, logr = E.restore(g)
        for ln in logr:
            print("  " + ln)
        print("  还原结果 %s" % ("成功" if okr else "失败"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
