# -*- coding: utf-8 -*-
"""检查单文件版的**启动画面**到底出不出来（顺手截一张图存到 out/）。

    python CN_Refined\\installer\\tools\\check_splash.py [exe路径]

为什么专门写这个：单文件版双击后要先解压 ~40 MB（界面 10 秒左右才出来），
这期间就靠 PyInstaller 的 `--splash` 顶着。而 `Get-Process ... MainWindowTitle`
**探不到** Tk 的 splash 窗口（实测），所以这里用 EnumWindows 按 PID 枚举，
把窗口类名/标题/位置都打出来，并对检出到的窗口区域截一张图（只截它那块矩形）。
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
DEFAULT_EXE = PKG / "out" / "release" / "ObraDinnCN-Installer.exe"

user32 = ctypes.windll.user32
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def windows_of(pid: int) -> list[dict]:
    out: list[dict] = []

    def cb(hwnd, _lp):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value != pid:
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, title, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        out.append({"hwnd": hwnd, "cls": cls.value, "title": title.value,
                    "rect": (r.left, r.top, r.right - r.left, r.bottom - r.top),
                    "visible": bool(user32.IsWindowVisible(hwnd))})
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # type: ignore[union-attr]
    except Exception:                                          # noqa: BLE001
        pass
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXE
    if not exe.is_file():
        print("[!] 找不到 %s" % exe)
        return 2
    print("[*] 启动 %s" % exe)
    t0 = time.monotonic()
    proc = subprocess.Popen([str(exe)])
    seen: list[str] = []
    shot_done = False
    while time.monotonic() - t0 < 25:
        for w in windows_of(proc.pid):
            if not w["visible"]:
                continue
            key = "%s|%s|%s" % (w["cls"], w["title"], w["rect"])
            if key not in seen:
                seen.append(key)
                print("  t=%4.1fs  %-18s %-28s %s"
                      % (time.monotonic() - t0, w["cls"], w["title"] or "(无标题)", w["rect"]))
                # ★ 一发现就截（等循环结束再截就晚了：app 窗口已经开了、把画面压住了）
                if (not shot_done and w["cls"].startswith("Tk")
                        and w["rect"][2] > 200 and w["rect"][3] > 150):
                    x, y, cw, ch = w["rect"]
                    user32.SetForegroundWindow(w["hwnd"])
                    time.sleep(0.35)
                    try:
                        from PIL import ImageGrab
                        img = ImageGrab.grab(bbox=(x, y, x + cw, y + ch))
                        out = PKG / "out" / "splash_shot.png"
                        img.save(out)
                        shot_done = True
                        print("[+] 截到启动画面：%s  %dx%d" % (out, img.size[0], img.size[1]))
                    except Exception as e:                 # noqa: BLE001
                        print("[!] 截图失败：%s" % e)
        if proc.poll() is not None:
            break
        try:                                   # 服务起来 = 界面快出来了，收工
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:8790/api/options", timeout=1.5).read()
            print("  t=%4.1fs  服务可用（界面应该在开了）" % (time.monotonic() - t0))
            break
        except Exception:                      # noqa: BLE001
            pass
        time.sleep(0.25)

    if not shot_done:
        print("[!] 没看到（或没截到）启动画面 —— 可能没生效，或本机启动太快没赶上")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
