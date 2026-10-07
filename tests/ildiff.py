#!/usr/bin/env python3
"""比较两份 ilspycmd -il 全量转储，回答「这次改动到底动了哪些方法」。

用法: python ildiff.py <a.il> <b.il> <详细输出> <允许改动的类型前缀>

只把 `// Method begins at RVA` / `// Header size` 这类会随全局布局漂移的行去掉 ——
方法内的 IL_xxxx 偏移是方法局部的，不受别处改动影响，所以其余行可以直接比。
判定：**改动只能出现在允许的前缀里**（patchwrap 应当只动 TextWrap）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

END = re.compile(r"^\s*\} // end of method (.+?)\s*$")


def parse(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    cur: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        # ★ 必须先 strip：这些注释行前面有缩进，直接 startswith 会漏掉，
        #   于是「RVA 全局移位」会被当成方法改动了（实测 5107 个方法假报）。
        s = raw.strip()
        if s.startswith("// Method begins at") or s.startswith("// Header size"):
            continue
        cur.append(raw)
        m = END.match(raw)
        if m:
            key = m.group(1)
            out[key] = [x for x in cur if x.strip()]
            cur = []
    return out


def main() -> int:
    a_path, b_path, detail, allow = sys.argv[1:5]
    A = parse(Path(a_path))
    B = parse(Path(b_path))

    added = [k for k in B if k not in A]
    removed = [k for k in A if k not in B]
    changed = [k for k in A if k in B and A[k] != B[k]]

    outside = [k for k in (added + removed + changed) if not k.startswith(allow)]

    print("methods A=%d B=%d" % (len(A), len(B)))
    print("added=%d removed=%d changed=%d" % (len(added), len(removed), len(changed)))
    print("outside(%s)=%d   <- 必须为 0" % (allow, len(outside)))
    for k in (added + removed + changed):
        tag = "added" if k in added else ("removed" if k in removed else "changed")
        mark = "  !! 越界" if not k.startswith(allow) else ""
        print("  %-7s %s%s" % (tag, k, mark))

    lines = ["# %s  vs  %s" % (a_path, b_path), ""]
    lines.append("added=%d removed=%d changed=%d outside=%d"
                 % (len(added), len(removed), len(changed), len(outside)))
    lines.append("")
    for k in changed:
        lines.append("=== changed %s ===" % k)
        sa, sb = set(A[k]), set(B[k])
        for x in A[k]:
            if x not in sb:
                lines.append("  - " + x)
        for x in B[k]:
            if x not in sa:
                lines.append("  + " + x)
        lines.append("")
    for k in added + removed:
        lines.append("%s %s" % ("+" if k in added else "-", k))
    Path(detail).write_text("\n".join(lines), encoding="utf-8")
    print("detail -> %s" % detail)
    return 1 if outside else 0


if __name__ == "__main__":
    sys.exit(main())
