# -*- coding: utf-8 -*-
"""无损往返测试：不修改任何东西，UnityPy 读出来再存回去，看能否还原原文件。

这决定「用 UnityPy 改 .assets 再存盘」这条路可不可信 ——
若连原样往返都不一致，就不能拿它去改游戏文件。

用法: python CN_Refined\\assets\\roundtrip_test.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import UnityPy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIG = ROOT / "CN_Refined" / "originalassets"
OUT = HERE / "out" / "roundtrip"

lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def obj_snapshot(path: Path):
    """{pathId: (type, byte_size, raw_sha)}"""
    env = UnityPy.load(str(path))
    snap = {}
    for o in env.objects:
        try:
            raw = o.get_raw_data()
            h = sha(bytes(raw))
        except Exception as e:                            # noqa: BLE001
            h = "ERR:%s" % type(e).__name__
        snap[o.path_id] = (o.type.name, o.byte_size, h)
    return snap


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in ("sharedassets6.assets", "sharedassets0.assets", "sharedassets2.assets"):
        src = ORIG / fn
        if not src.exists():
            say("缺 %s" % src)
            continue
        raw0 = src.read_bytes()
        say("=" * 84)
        say("%s   原始 %s 字节  sha=%s" % (fn, format(len(raw0), ","), sha(raw0)))
        env = UnityPy.load(str(src))
        try:
            raw1 = env.file.save()
        except Exception as e:                             # noqa: BLE001
            say("  ✗ save() 抛错: %s: %s" % (type(e).__name__, e))
            continue
        same = raw1 == raw0
        say("  往返后 %s 字节  sha=%s   **逐字节相同=%s**"
            % (format(len(raw1), ","), sha(raw1), same))
        dst = OUT / fn
        dst.write_bytes(raw1)
        if not same:
            # 找出第一处不同
            n = min(len(raw0), len(raw1))
            i = next((k for k in range(n) if raw0[k] != raw1[k]), -1)
            say("  首处差异偏移: %s (0x%X)  长度差 %+d"
                % (i if i >= 0 else "无（仅长度不同）", i if i >= 0 else 0,
                   len(raw1) - len(raw0)))
            # 对象级比对
            s0 = obj_snapshot(src)
            try:
                s1 = obj_snapshot(dst)
            except Exception as e:                         # noqa: BLE001
                say("  ✗ 往返文件读不回来: %s: %s" % (type(e).__name__, e))
                say("")
                continue
            say("  对象数: %d → %d" % (len(s0), len(s1)))
            diff = [k for k in s0 if k in s1 and s0[k] != s1[k]]
            only0 = [k for k in s0 if k not in s1]
            only1 = [k for k in s1 if k not in s0]
            say("  内容不同的对象 %d 个，只在原始 %d，只在往返 %d"
                % (len(diff), len(only0), len(only1)))
            for k in diff[:8]:
                say("     pathId=%s  %s  %d→%d  %s→%s"
                    % (k, s0[k][0], s0[k][1], s1[k][1], s0[k][2], s1[k][2]))
            for k in only0[:5]:
                say("     仅原始有 pathId=%s %s" % (k, s0[k]))
            for k in only1[:5]:
                say("     仅往返有 pathId=%s %s" % (k, s1[k]))
        say("")

    text = "\n".join(lines)
    (HERE / "out" / "roundtrip.txt").write_text(text + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
