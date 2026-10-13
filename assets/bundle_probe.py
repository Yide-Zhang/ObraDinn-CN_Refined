# -*- coding: utf-8 -*-
"""语言包 bundle 的读写探针：头部信息 + UnityPy 往返可靠性。

要回答两件事：
  1. 游戏这份 lang-zh-s 是什么压缩/什么版本（决定写回去要用什么 packer）
  2. **UnityPy 能不能可靠地重写它** —— 读出来再存回去，再读一遍，
     比对字符串对象字节 与 4 张图的像素是否完全一致

用法: python CN_Refined\\assets\\bundle_probe.py [bundle路径]
产物: CN_Refined\\assets\\out\\bundle_probe.txt
"""
from __future__ import annotations

import hashlib
import inspect
import sys
from pathlib import Path

import UnityPy
from UnityPy.files import BundleFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GAME = Path(r"F:\AceAttorneySeries\gameFiles\steamapps\common\ObraDinn\ObraDinn_Data")
DEFAULT = GAME / "StreamingAssets" / "lang-zh-s"
lines: list[str] = []


def say(m: str = "") -> None:
    lines.append(m)


def digest(p: Path) -> dict:
    """对象名 -> 内容摘要（MonoBehaviour 用原始字节，图用像素）"""
    env = UnityPy.load(str(p))
    out = {}
    for o in env.objects:
        try:
            d = o.read()
        except Exception as e:                                 # noqa: BLE001
            out[o.path_id] = ("ERR", str(e))
            continue
        key = "%s:%s" % (o.type.name, getattr(d, "m_Name", "?"))
        if o.type.name in ("Texture2D", "Sprite"):
            try:
                img = d.image
                out[key] = ("img", img.size, hashlib.sha256(img.tobytes()).hexdigest()[:16])
            except Exception as e:                             # noqa: BLE001
                out[key] = ("img-ERR", str(e))
        else:
            raw = None
            try:
                raw = o.get_raw_data()
            except Exception:                                  # noqa: BLE001
                pass
            if raw is None:
                out[key] = ("nosize",)
            else:
                b = bytes(raw)
                out[key] = ("bytes", len(b), hashlib.sha256(b).hexdigest()[:16])
    return out


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    say("语言包 bundle 探针: %s" % p)
    if not p.exists():
        say("✗ 不存在")
        (HERE / "out" / "bundle_probe.txt").write_text("\n".join(lines), encoding="utf-8-sig")
        return 1
    # 头部
    head = p.read_bytes()[:64]
    say("  前 48 字节(hex): %s" % head[:48].hex())
    say("  签名: %r" % head[:head.index(0)].decode("latin1"))
    say("  文件大小: %d B" % p.stat().st_size)
    try:
        say("  BundleFile.save 签名: %s" % inspect.signature(BundleFile.save))
    except Exception as e:                                     # noqa: BLE001
        say("  (取 save 签名失败: %s)" % e)

    env = UnityPy.load(str(p))
    bf = env.file
    say("  bundle 类型: %s" % type(bf).__name__)
    for attr in ("signature", "version", "version_engine", "version_player", "flags",
                 "compression", "is_uncompressed", "is_lzma", "is_lz4"):
        if hasattr(bf, attr):
            try:
                say("    %-16s = %r" % (attr, getattr(bf, attr)))
            except Exception:                                  # noqa: BLE001
                pass
    if hasattr(bf, "files"):
        say("  files: %s" % [type(f).__name__ for f in getattr(bf, "files", [])])
    say("  对象数: %d" % len(list(env.objects)))
    say("")

    d0 = digest(p)
    say("  原始对象摘要:")
    for k in sorted(d0):
        say("    %-34s %s" % (k, d0[k]))
    say("")

    # 往返
    for packer in (None, "lz4", "lzma"):
        try:
            data = env.file.save(packer=packer) if packer else env.file.save()
        except TypeError:
            try:
                data = env.file.save(packer) if packer else env.file.save()
            except Exception as e:                             # noqa: BLE001
                say("  往返 packer=%-5s 调用失败: %s: %s" % (packer, type(e).__name__, e))
                continue
        except Exception as e:                                 # noqa: BLE001
            say("  往返 packer=%-5s 调用失败: %s: %s" % (packer, type(e).__name__, e))
            continue
        out = HERE / "out" / ("_rt-%s-%s" % (packer or "none", p.name))
        out.write_bytes(data)
        say("  往返 packer=%-5s 写出 %d B（原 %d，%+d）→ %s"
            % (packer, len(data), p.stat().st_size, len(data) - p.stat().st_size, out.name))
        try:
            d1 = digest(out)
        except Exception as e:                                 # noqa: BLE001
            say("      ✗ 重新读取失败: %s: %s" % (type(e).__name__, e))
            continue
        keys = set(d0) | set(d1)
        diff = [k for k in sorted(keys) if d0.get(k) != d1.get(k)]
        say("      对象数 %d → %d，摘要不一致 %d 个%s"
            % (len(d0), len(d1), len(diff),
               ("（前几个: %s）" % ", ".join(diff[:5])) if diff else "  ✓ 全部一致"))
        # 头部（压缩类型）
        h1 = out.read_bytes()[:64]
        say("      头部前 32 字节: %s" % h1[:32].hex())
    say("")
    (HERE / "out" / "bundle_probe.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(l for l in lines if l.isascii()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
