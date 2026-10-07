#!/usr/bin/env python3
"""验一验**打出来的那个包**（不是开发树）—— Windows / macOS 通用。

    python  CN_Refined/installer/tools/check_release.py                 # 自动找 out/release 里的产物
    python3 CN_Refined/installer/tools/check_release.py <exe 或 .app 路径>
    python3 CN_Refined/installer/tools/check_release.py --real          # 跑真装（默认只跑演示，不写盘）
    python3 CN_Refined/installer/tools/check_release.py --keep-open     # 验完不关掉，留着看界面

为什么必须单独验一遍包：
  开发树里能跑 ≠ 包里能跑。少一个原生 dll（fmod_toolkit）、少一个数据文件（archspec 的 json）、
  langtool 没带上或没可执行位 —— 这些**只有在冻结环境里才会炸**，而且炸点恰好都在
  UnityPy 重建语言包那一步（演示模式也会走到那里）。这个脚本就是把包启动起来，
  用它的 HTTP 接口把关键路径全摸一遍，然后把进程收掉。

它查的东西：
  1. 能启动、界面服务能起来（单文件版要等 ~10 秒解压；.app 是瞬间）
  2. /api/options：标题、5 个版本 × TSV 是否齐、字体、预览文案、langtool 路径**在包里存在且可执行**
  3. /icon.png：窗口/任务栏图标路由能取到图（打包时最容易漏的东西之一）
  4. /api/state：能认到游戏、逐文件判定（这一步会把 engine.detect_game + inspect_state 跑一遍）
  5. /api/install（`--real` 才跑真装，否则用 --demo 启动、流程照跑但不写盘）+ 轮询 /api/progress
  6. /api/quit：能正常退出（打包成窗口模式后没控制台，这是唯一的退出入口）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent                        # installer/
RELEASE = PKG / "out" / "release"
APP = "ObraDinnCN-Installer"
PORT = 8788


def find_artifact() -> Path | None:
    for n in (APP + ".app", APP + ".exe", APP):
        p = RELEASE / n
        if p.exists():
            return p
    return None


def runnable(art: Path) -> Path:
    """从产物拿到**该直接执行的二进制**

    .app 里直接跑 Contents/MacOS/<name>：`open -a` 会把进程甩给 launchd，
    我们既拿不到 pid、也看不到它的 stdout，验证就无从谈起。
    """
    if art.suffix == ".app":
        return art / "Contents" / "MacOS" / APP
    if art.is_dir():
        return art / (APP + ".exe")
    return art


def get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def post(url: str, obj: dict, timeout: float = 10.0):
    body = json.dumps(obj).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def wait_up(port: int, deadline: float) -> bool:
    """等服务起来（.exe 单文件版要解压 ~10 秒，所以给足时间）"""
    while time.monotonic() < deadline:
        try:
            st, body = get("http://127.0.0.1:%d/api/options" % port)
            if st == 200 and b'"title"' in body:
                return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # type: ignore[union-attr]
    except Exception:                                     # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="验收打出来的包")
    ap.add_argument("artifact", nargs="?", help="exe / .app / 目录版文件夹")
    ap.add_argument("--real", action="store_true", help="跑真装（默认用 --demo，不写盘）")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--timeout", type=float, default=90.0, help="等界面服务起来的上限（秒）")
    ap.add_argument("--keep-open", action="store_true", help="验完不退出、也不关进程")
    a = ap.parse_args()

    art = Path(a.artifact).resolve() if a.artifact else find_artifact()
    if art is None or not art.exists():
        print("[!] 没找到产物（先跑 tools/build_release.py，或用参数指定路径）")
        return 2
    exe = runnable(art)
    if not exe.is_file():
        print("[!] 产物里找不到可执行文件：%s" % exe)
        return 2
    print("[i] 产物 %s" % art)
    print("[i] 启动 %s%s" % (exe, "" if a.real else "（--demo：流程照跑、不写盘）"))

    cmd = [str(exe), "--port", str(a.port), "--no-browser"]
    if not a.real:
        cmd.append("--demo")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    t0 = time.monotonic()
    base = "http://127.0.0.1:%d" % a.port
    ok = True
    try:
        if not wait_up(a.port, t0 + a.timeout):
            print("[!] 等了 %.0f 秒界面服务还是没起来 —— 包有问题（单文件版最多 ~15 秒）"
                  % a.timeout)
            return 1
        print("[+] 界面服务已起来（%.1f 秒）%s" % (time.monotonic() - t0, base))

        # ---- 2. /api/options ----
        _st, body = get(base + "/api/options")
        o = json.loads(body.decode("utf-8"))
        print("    标题：%s" % o.get("title"))
        vers = o.get("versions", [])
        lacking = [v["id"] for v in vers if not v.get("tsv")]
        print("    版本 %d 个：%s%s" % (len(vers), ", ".join(v["id"] for v in vers),
                                      "（缺 TSV：%s）" % lacking if lacking else "（TSV 都齐）"))
        if not vers or lacking:
            print("[!] 随包 TSV 不齐 —— 打包前的 assets/packs 不对")
            ok = False
        lt = Path(o.get("langtool") or "")
        lt_ok = lt.is_file() and (sys.platform == "win32" or lt.stat().st_mode & 0o111)
        print("    langtool：%s  %s" % (lt.name or "(空)", "存在且可执行 ✓" if lt_ok
                                      else "✗ 缺失或没有可执行位"))
        ok &= bool(lt_ok)
        fdirs = o.get("fonts", {}).get("dirs", [])
        print("    字体目录：%s" % (", ".join(fdirs) or "(无)"))
        missing_font = [f for f in (o.get("fonts", {}).get("serif"),
                                    o.get("fonts", {}).get("hand")) if not f or f == ""]
        if missing_font:
            print("[!] 界面字体没解析到（打包时 stage_fonts 那步）")
            ok = False

        # ---- 3. /icon.png ----
        st, body = get(base + "/icon.png")
        print("    /icon.png：HTTP %d，%d 字节 %s"
              % (st, len(body), "（PNG）" if body[:4] == b"\x89PNG" else "（不是 PNG！）"))
        ok &= (st == 200 and body[:4] == b"\x89PNG")

        # ---- 4. /api/state ----
        _st, body = get(base + "/api/state")
        s = json.loads(body.decode("utf-8"))
        if s.get("ok") and s.get("game"):
            print("    /api/state：游戏=%s（%s）难度档 %s %s"
                  % (s["game"], s.get("how", ""), s.get("level"), s.get("level_label", "")))
            for f in s.get("rows", []):
                print("        %-46s %-8s %s" % (f.get("rel"), f.get("verdict"),
                                                  f.get("detail", "")))
            if s.get("risky"):
                print("        [i] 既不是原版也不是我们的：%s" % ", ".join(s["risky"]))
        else:
            print("    /api/state：没认到游戏（%s）—— 这台机器上自动探测没找到目录，"
                  "界面上可以手动选（不影响包本身的验收）" % s.get("error", "?"))

        # ---- 5. 跑一遍装（演示/真装）----
        st, body = post(base + "/api/install",
                        {"version": "v5", "harmonized": False, "dialog": "bi",
                         "level": 3, "force": True})
        print("    /api/install：HTTP %d %s" % (st, body.decode("utf-8")[:120]))
        last = ""
        for _ in range(int(a.timeout * 2)):
            _st, body = get(base + "/api/progress")
            p = json.loads(body.decode("utf-8"))
            if p.get("log"):
                for ln in p["log"][-4:]:
                    if ln != last:
                        print("        " + ln)
                        last = ln
            if not p.get("busy"):
                break
            time.sleep(0.5)
        print("    流程结束：%s" % ("成功" if p.get("ok") else "✗ 失败"))
        ok &= bool(p.get("ok"))
        if not p.get("ok"):
            for ln in (p.get("log") or [])[-12:]:
                print("      | " + ln)

        # ---- 6. 退出 ----
        if a.keep_open:
            print("[i] --keep-open：进程留着（pid %d），界面在 %s" % (proc.pid, base))
            return 0 if ok else 1
        st, _ = post(base + "/api/quit", {})
        for _ in range(20):
            if proc.poll() is not None:
                break
            time.sleep(0.25)
        gone = proc.poll() is not None
        print("    /api/quit：HTTP %d，进程%s" % (st, "已退出 ✓" if gone else "还在（✗ 没收掉）"))
        ok &= gone
    finally:
        if proc.poll() is None and not a.keep_open:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if proc.stdout is not None:
            rest = proc.stdout.read() or ""
            if rest.strip():
                print("[i] 进程输出（窗口模式下通常为空）：")
                for ln in rest.strip().splitlines()[-15:]:
                    print("    " + ln)

    print("\n%s" % ("[=] PASS —— 这个包能跑、关键路径都通"
                    if ok else "[!] FAIL —— 见上面的 ✗"))
    if a.real:
        print("    （跑的是真装：游戏已经被装上了，要还原用 engine.py --restore 或界面上的还原）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
