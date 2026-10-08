#!/usr/bin/env python3
"""证明「头部插入式」补丁没有动到原方法体。

用法: python ilhead.py <a.il> <b.il> <详细输出> [方法名 ...]

`ildiff.py` 只能告诉我们「哪些方法变了」；对于**在方法头插入几条指令**的补丁，
方法内所有 IL_xxxx 偏移都会平移，于是整个方法体都会显示成 changed —— 看不出
「原体到底动没动」。

这个工具补上那半个证明：把 IL_xxxx 标签和分支目标都归一化掉，然后要求
**A 的指令序列仍是 B 的连续尾部**（原封不动，只是在前面插了东西）。
补丁只允许在方法头部插入时，这个断言必须成立。

不给方法名时，检查两个文件里所有「两边都有但文本不同」的方法。
exit 0 = 每个方法都通过；同时打印注入的前缀（+）供肉眼核对。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ildiff import parse  # noqa: E402  （共用同一套「方法块」解析，避免两处口径不一致）

LABEL = re.compile(r"^IL_[0-9a-fA-F]{4}:\s*")
TARGET = re.compile(r"\bIL_[0-9a-fA-F]{4}\b")
HEAD = re.compile(r"head:\s*IL_[0-9a-fA-F]{4}")

LABEL = re.compile(r"^IL_[0-9a-fA-F]{4}:\s*")
TARGET = re.compile(r"\bIL_[0-9a-fA-F]{4}\b")
HEAD = re.compile(r"head:\s*IL_[0-9a-fA-F]{4}")
LOCALDECL = re.compile(r"^\[\d+\]|^\)")


def norm(lines: list[str]) -> list[str]:
    """把方法块归一化成「纯指令序列」。

    ★ 唯一可靠的判据：`ilspycmd -il` 只给**真指令**加 `IL_xxxx:` 标签。
      签名（可能跨行）、`.maxstack`、`.locals init ( … )` 的续行 `[0] …` / `)`、
      `// loop start (head: IL_00b8)` 注解 —— 全都不带标签，一条规则全部滤掉。
      （前两版分别用「行首排除」和「跳过 cil managed」，各踩了一次：跨行签名、
      以及 .locals 列表续行，都把没动过的原体误判成「改动不只发生在头部」。）

    偏移也去掉：IL_xxxx 是方法局部的，头部插一条就全体平移，不能参与比较；
    分支目标同理，换成 `*`。
    """
    out: list[str] = []
    for s in lines:
        s = s.strip()
        m = LABEL.match(s)
        if not m:
            continue
        out.append(TARGET.sub("*", s[m.end():]))
    return out


def directives(lines: list[str]) -> list[str]:
    """指令以外的关键声明行（只报不判）。

    含 `.field`：类型字段声明会跟着该类型**第一个方法**一起被切进来，所以新增字段
    会以「Player::.ctor 变了」的形式出现在 ildiff 里 —— 默认路径（不指定方法名）下
    由这里把真实原因（多了哪几个字段）报出来，免得以后自己吓自己。
    """
    out: list[str] = []
    for s in lines:
        s = s.strip()
        if s.startswith((".maxstack", ".locals", ".entrypoint", ".field")):
            out.append(re.sub(r"\s+", " ", s))
    return out


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    a_path, b_path, detail = sys.argv[1:4]
    A = parse(Path(a_path))
    B = parse(Path(b_path))

    want = sys.argv[4:]
    if not want:
        want = [k for k in A if k in B and A[k] != B[k]]

    added = [k for k in B if k not in A]
    bad: list[str] = []
    lines: list[str] = []

    print("A=%s" % a_path)
    print("B=%s" % b_path)
    print("检查 %d 个方法；新增方法 %d 个" % (len(want), len(added)))
    for k in want:
        if k not in B:
            print("  !! %s 只存在于 A（方法被删了？）" % k)
            bad.append(k)
            continue
        full_a, full_b = norm(A[k]), norm(B[k])
        dirs_a, dirs_b = directives(A[k]), directives(B[k])
        na, nb = full_a, full_b
        if len(nb) < len(na) or nb[len(nb) - len(na):] != na:
            print("  !! %s 原体不是新体的尾部 —— 改动不只发生在头部" % k)
            bad.append(k)
            lines.append("=== NOT-A-TAIL %s ===" % k)
            for x in na:
                lines.append("  A| " + x)
            for x in nb:
                lines.append("  B| " + x)
            lines.append("")
            continue
        inj = nb[:len(nb) - len(na)]
        print("  ok %-40s 原体 %d 条指令未变，头部插入 %d 条" % (k, len(na), len(inj)))
        lines.append("=== %s: 头部插入 %d 条（原体 %d 条逐条未变） ===" % (k, len(inj), len(na)))
        for x in inj:
            lines.append("  + " + x)
        if dirs_a != dirs_b:
            # .maxstack 变大是正常的（插入的指令要压栈）；不作失败，但记下来
            lines.append("  ~ 指令外行为有变：")
            for x in dirs_a:
                if x not in dirs_b:
                    lines.append("    A| " + x)
            for x in dirs_b:
                if x not in dirs_a:
                    lines.append("    B| " + x)
            print("     ~ %s 的指令外行（.maxstack/.locals 等）有变，详见 detail" % k)
        lines.append("")

    for k in added:
        lines.append("=== 新增方法 %s ===" % k)
        for x in norm(B[k]):
            lines.append("  + " + x)
        lines.append("")

    Path(detail).write_text("\n".join(lines), encoding="utf-8")
    print("detail -> %s" % detail)
    if bad:
        print("失败：%d 个方法没通过" % len(bad))
        return 1
    print("全部通过：改动只发生在方法头部")
    return 0


if __name__ == "__main__":
    sys.exit(main())
