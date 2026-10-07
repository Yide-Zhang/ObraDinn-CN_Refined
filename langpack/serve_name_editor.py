#!/usr/bin/env python3
"""人名对照表编辑器 —— 本地服务（只为让网页能**原地保存**）。

    python CN_Refined/langpack/serve_name_editor.py [表文件] [--port 8791] [--no-open]

    GET  /            编辑器页面（name_editor.html）
    GET  /api/load    读表，原样返回 UTF-8 文本
    POST /api/save    写回：先复制一份 .prev，再写临时文件 + os.replace（原子）

只绑 127.0.0.1，不对外。直接双击 name_editor.html 也能用（那种方式只能靠
文件选择 + 下载，不能原地保存）。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TSV = HERE / "extracted" / "crew_name_variants.tsv"
HTML_PATH = HERE / "name_editor.html"
MAX_BODY = 8 * 1024 * 1024


def make_handler(tsv: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "NameEditor/1.0"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):      # 精简日志
            sys.stderr.write("  %s\n" % (fmt % args))

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):                                        # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                if not HTML_PATH.is_file():
                    self._send(500, b"name_editor.html not found",
                               "text/plain; charset=utf-8")
                    return
                self._send(200, HTML_PATH.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/load":
                if not tsv.is_file():
                    self._send(404, str(tsv).encode("utf-8"),
                               "text/plain; charset=utf-8")
                    return
                self._send(200, tsv.read_bytes(), "text/plain; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self):                                       # noqa: N802
            path = self.path.split("?", 1)[0]
            if path != "/api/save":
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n <= 0 or n > MAX_BODY:
                self._send(400, b"bad content-length", "text/plain; charset=utf-8")
                return
            data = self.rfile.read(n)
            tmp = tsv.with_name(tsv.name + ".tmp")
            try:
                if tsv.is_file():                                # 留一份上一次的
                    shutil.copy2(tsv, tsv.with_name(tsv.name + ".prev"))
                tmp.write_bytes(data)
                os.replace(tmp, tsv)                             # 原子替换
            except OSError as e:
                self._send(500, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                return
            self._send(200, b'{"ok":true}', "application/json; charset=utf-8")
    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description="人名对照表编辑器（本地服务）")
    ap.add_argument("tsv", nargs="?", default=str(DEFAULT_TSV), help="要编辑的表")
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--no-open", action="store_true", help="不自动开浏览器")
    a = ap.parse_args()

    tsv = Path(a.tsv).resolve()
    print("表文件 : %s" % tsv)
    print("         %s" % ("存在 ✓" if tsv.is_file() else "**不存在** —— 请先跑 make_name_table.py"))
    if not HTML_PATH.is_file():
        print("[X] 找不到 %s" % HTML_PATH)
        return 1

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(tsv))
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("编辑器 : %s   （Ctrl+C 退出）" % url)
    if not a.no_open:
        try:
            webbrowser.open(url)
        except Exception:                                        # noqa: BLE001
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n退出")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
