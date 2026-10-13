# -*- coding: utf-8 -*-
"""探明 UnityPy 1.25 的「改字段 + 存回 .assets」API（一次性用）。"""
from pathlib import Path

import UnityPy

ROOT = Path(__file__).resolve().parents[2]
ORIG = ROOT / "CN_Refined" / "originalassets" / "sharedassets0.assets"

env = UnityPy.load(str(ORIG))
f = env.file
print("env.file type   :", type(f))
print("file.save?      :", hasattr(f, "save"))
print("env.save?       :", hasattr(env, "save"))
for n in ("save", "packer", "is_bundle"):
    print("  .%s = %r" % (n, getattr(f, n, None)))
try:
    import inspect
    print("save sig        :", inspect.signature(f.save))
except Exception as e:                                   # noqa: BLE001
    print("save sig err    :", e)

obj = next(o for o in env.objects if o.type.name == "Font")
print("obj type        :", type(obj))
print("obj.read/save?  :", hasattr(obj, "read"), hasattr(obj, "save"))
d = obj.read()
print("data type       :", type(d))
print("data.save?      :", hasattr(d, "save"))
print("m_FontData type :", type(d.m_FontData), len(d.m_FontData))
print("env.objects n   :", len(env.objects))
print("assetsfile?     :", hasattr(env, "assets_file"), getattr(env, "assets_file", None) is not None)
bf = getattr(env, "file", None)
print("dir(file) save-ish:", [x for x in dir(bf) if "save" in x.lower() or "write" in x.lower()])
print("dir(obj) save-ish :", [x for x in dir(obj) if "save" in x.lower() or "write" in x.lower()])
print("dir(data) save-ish:", [x for x in dir(d) if "save" in x.lower() or "write" in x.lower()])
