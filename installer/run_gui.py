# -*- coding: utf-8 -*-
"""启动安装向导。

开发时：
    python CN_Refined\\installer\\run_gui.py                 # 自动开浏览器
    python3 CN_Refined/installer/run_gui.py --port 8791 --no-browser

打包后：
    Windows：双击 ObraDinnCN-Installer.exe
    macOS：  双击 ObraDinnCN-Installer.app
（同一个入口，PyInstaller 打的就是这个文件。）

浏览器只是界面，真正的文件操作都在 engine.py 里；关掉向导 = 界面上的「退出」按钮。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# ★ 打包成 --windowed 后**没有控制台**：sys.stdout/stderr 是 None，
#   而 engine 到处 print 日志 → 一 print 就 AttributeError。这里先兜住。
# ★ 但「不是 None」不等于「能写」：stdout 被重定向/管道时 Python 会按系统 locale
#   建流（Windows 上是 GBK），日志里的 ✓/✗ 一写就 UnicodeEncodeError。
#   所以已有的流也统一改成 utf-8 + replace，打不出字总比把流程搞崩强。
for _name in ("stdout", "stderr"):
    _s = getattr(sys, _name, None)
    if _s is None or not hasattr(_s, "write"):
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))
    else:
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
        except Exception:                             # noqa: BLE001
            pass
if sys.stderr is None or not hasattr(sys.stderr, "write"):
    sys.stderr = sys.stdout


def _fatal(msg: str) -> None:
    """窗口模式下没有控制台，出错必须弹个框，否则用户什么都看不到

    ★ macOS 上用 osascript 而不是 tkinter：osascript 是系统自带的，不依赖 Tcl/Tk；
      在 .app 里弹一个原生对话框也是最自然的样子。
    """
    try:                                              # 启动画面别憨在那
        import pyi_splash                             # type: ignore[import-not-found]
        pyi_splash.close()
    except Exception:                                 # noqa: BLE001
        pass
    if sys.platform == "darwin":
        try:
            safe = msg.replace('"', "'").replace("\\", "/")[:600]
            subprocess.run(["osascript", "-e",
                            'display dialog "%s" with title "奥伯拉丁中文精修补丁" '
                            'buttons {"好"} default button 1 with icon stop' % safe],
                           capture_output=True, text=True)
            return
        except OSError:
            pass
    try:
        import tkinter                                # noqa: PLC0415
        from tkinter import messagebox                # noqa: PLC0415
        r = tkinter.Tk()
        r.withdraw()
        messagebox.showerror("奥伯拉丁中文精修补丁 · 安装向导", msg)
        r.destroy()
    except Exception:                                 # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        from gui import server
    except Exception as ex:                           # noqa: BLE001
        _fatal("向导启动失败：%s: %s" % (type(ex).__name__, ex))
        raise SystemExit(1)
    try:
        raise SystemExit(server.main())
    except SystemExit:
        raise
    except Exception as ex:                           # noqa: BLE001
        _fatal("向导出错退出了：%s: %s" % (type(ex).__name__, ex))
        raise SystemExit(1)
