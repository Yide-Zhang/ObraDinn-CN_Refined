# -*- coding: utf-8 -*-
"""CN_Refined 安装引擎（底层；GUI 只调用这里，不自己碰文件）。

设计要点（都是踩出来的）：
  · **幂等**：安装永远从「确定的基线」重做，不做增量叠加 —— 重复跑、换选项跑都走同一条路径。
      - sharedassets0/2：基线 = **游戏机上那份**（只改 Font 对象的 m_FontData，其它对象零改动，
        所以别人对这文件的改动会保留）；字体用包里带的**子集化 A**。
      - sharedassets6  ：**以机器那份为基底，只就地替换鸣谢文本块**
        （预生成件只当「文本从哪里来」的模板；整文件替换在 mac 上是错的 ——
         Windows 构建的 SerializedFile 平台字段不同，见 step_shs6 的说明）。
        直接拿 UnityPy 写这个文件会丢类型树，所以只能做字节手术。
      - lang-zh-s      ：Windows = 包内官方包重建；macOS = **机器自己那份当壳**
        （AssetBundle 平台相关），文本永远全量来自我们的 TSV。
      - Assembly-CSharp.dll：**不还原**，只在现有状态上叠加 wrap（与其它补丁任意顺序兼容）。
  · **备份在用户机上**：首次动手前把要改的文件原样进 stash（语义 = "我们发现它时的样子"），
    还原 = 把 stash 写回 → 回到"我动手之前"，别的工具打过的补丁原样保留。
  · **状态可见**：inspect_state() 对每个文件判定 原版/我们的/其它/未知，未知必须显式确认。

用法（CLI，也算自测入口）:
    python CN_Refined\\installer\\engine.py --game <目录> --state
    python CN_Refined\\installer\\engine.py --game <目录> --install --version v5 --harm unharm --dialog bi
    python CN_Refined\\installer\\engine.py --game <目录> --restore
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # ObraDinnSave/
PKG = Path(__file__).resolve().parent               # CN_Refined/installer/
ASSETS = PKG / "assets"                             # 随包资源（字体 A/B、官方包、图、langtool…）
DATA = PKG / "data"                                 # 生成的数据（难度表、已知哈希）
TMP = Path(tempfile.gettempdir()) / "ObraDinnCN-installer"   # 给 UnityPy 的临时副本放这里

# ---- 游戏相关文件名 ----
# ★ 布局差异（两种都要支持）：
#   Windows：<游戏根>\ObraDinn_Data\Managed\Assembly-CSharp.dll …
#   macOS  ：<X>.app/Contents/Resources/Data/Managed/Assembly-CSharp.dll …
#   所以下面这些 rel 路径是**按当前布局动态生成**的 —— 由 game_root() → _apply_layout() 设好，
#   而 game 永远是「装着数据目录的那个容器」（Windows=游戏根，mac=…/Contents/Resources）。
DATA_NAME_WIN = "ObraDinn_Data"        # Windows / Linux 常规数据目录名
DATA_NAME_MAC = "Data"                 # macOS 里 .app/Contents/Resources/Data
SHS = ["sharedassets0.assets", "sharedassets2.assets", "sharedassets6.assets"]
LANG = "lang-zh-s"
STASH_DIR = "ObraDinnCN-installer"      # 放在游戏目录里（用户看得见、能自己备份）
RECORD = "install-record.json"

_LAY: dict = {"name": DATA_NAME_WIN}    # 当前布局：数据目录相对 game 的名字
DLL_REL = Path(DATA_NAME_WIN) / "Managed" / "Assembly-CSharp.dll"
SHS_REL = Path(DATA_NAME_WIN)
SA_REL = Path(DATA_NAME_WIN) / "StreamingAssets"


def _rel(*parts: str) -> Path:
    """按当前布局拼游戏内相对路径"""
    name = _LAY["name"]
    return Path(name, *parts) if name else Path(*parts)


def _apply_layout(data_name: str) -> None:
    """把当前布局切成 data_name（"ObraDinn_Data" / "Data" / ""）：重算所有 rel 路径"""
    global DLL_REL, SHS_REL, SA_REL, OUR_FILES
    _LAY["name"] = data_name
    DLL_REL = _rel("Managed", "Assembly-CSharp.dll")
    SHS_REL = Path(data_name) if data_name else Path(".")
    SA_REL = _rel("StreamingAssets")
    OUR_FILES = [DLL_REL,
                 SHS_REL / "sharedassets0.assets",
                 SHS_REL / "sharedassets2.assets",
                 SHS_REL / "sharedassets6.assets",
                 SA_REL / LANG]

# ---- 字体：A = 注入游戏用（子集化，身份名已按游戏 donor 恢复）；B = GUI 用（随便挑）----
FONT_A = {                                          # Font 对象名 -> 包内文件
    "SourceHanSerif-SemiBold": ["fonts/A-SourceHanSerifSC-SemiBold-subset.otf",
                                "../out/verify/SourceHanSerif-SemiBold.otf"],
    "851tegaki_zatsu_normal_0883": ["fonts/A-851tegaki_zatsu_normal_0883-subset.otf",
                                    "../out/verify/851tegaki_zatsu_normal_0883.otf"],
}

LEVELS = ("v1", "v2", "v3", "v4", "v5")
NAME_AXIS = {"v1": "zh", "v2": "zh", "v3": "en", "v4": "refined", "v5": "refined"}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def human(n: int) -> str:
    for u, d in (("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= d:
            return "%.2f %s" % (n / d, u)
    return "%d B" % n


_report: list[str] = []


def say(m: str = "") -> None:
    """打一行日志 + 收进报告。

    ★ 打印永远不能把流程搞崩（踩过一次，代价很大）：控制台编码在 Windows 上可能是
      GBK（双击没问题，但 stdout 被重定向/管道时 Python 会按 locale 建流），
      而日志里有 ✓/✗ 这类字符 → `UnicodeEncodeError`。更阴的是它**是 ValueError
      的子类**，会被上层 `except (ValueError, OSError)` 当成“可以处理的错误”接住，
      接住时再打一次日志又抛 → 整个安装线程当场死掉，界面只显示“流程失败”。
      所以这里自己兵来将挡：编不出来就替换成 ?，绝不向外抛。
    """
    try:
        print(m, flush=True)          # 控制台直出
    except (UnicodeEncodeError, OSError, ValueError):
        try:
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            print(m.encode(enc, "replace").decode(enc, "replace"), flush=True)
        except Exception:                             # noqa: BLE001
            pass
    _report.append(m)             # 同时进报告文件（GBK 控制台会把中文弄乱，读文件才准）


# ---------------------------------------------------------------------------
# 演示模式（DEMO）
#   为「测试 GUI 本身」而设：流程、日志、状态判定全部照跑，但**不向任何地方落盘**——
#   不写游戏文件、不建 ObraDinnCN-installer、不写 record、不跑会写盘的 langtool 子命令。
#   所有写入都只能经过下面三个函数，所以开关只有一个。
# ---------------------------------------------------------------------------
DEMO = False


def demo_note(what: str) -> None:
    say("    （演示）%s" % what)


def mkdirs(p: Path) -> None:
    if not DEMO:
        p.mkdir(parents=True, exist_ok=True)


def put_bytes(p: Path, data: bytes, what: str = "") -> None:
    """统一落盘口（字节）"""
    if DEMO:
        demo_note("不写 %s%s（%s）" % (p.name, ("  " + what) if what else "", human(len(data))))
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def put_file(src: Path, dst: Path, what: str = "") -> None:
    """统一落盘口（整文件复制）"""
    if DEMO:
        demo_note("不覆盖 %s%s（源 %s，%s）"
                  % (dst.name, ("  " + what) if what else "", src.name,
                     human(src.stat().st_size)))
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


# ===========================================================================
# 1. 找游戏目录
# ===========================================================================
def _is_data_dir(d: Path) -> bool:
    """这个目录本身就是 Unity 数据目录？（有 Managed/Assembly-CSharp.dll + sharedassets0）"""
    try:
        return ((d / "Managed" / "Assembly-CSharp.dll").is_file()
                and (d / "sharedassets0.assets").is_file())
    except OSError:
        return False


def _find_layout(root: Path) -> str | None:
    """root 里有没有标准数据目录？返回它相对 root 的名字（Windows: ObraDinn_Data；mac: Data）

    只认「子目录」形式 —— 认到 root 自己会改变 stash 位置，把已装用户的还原路径弄丢。
    """
    for name in (DATA_NAME_WIN, DATA_NAME_MAC):
        if _is_data_dir(root / name):
            return name
    return None


def looks_like_game(d: Path) -> bool:
    """d = 容器（装有数据目录的那个文件夹）或者数据目录本身"""
    try:
        return _find_layout(d) is not None or _is_data_dir(d)
    except OSError:
        return False


def _app_containers(p: Path) -> list[Path]:
    """macOS：p（或它上一级）里有哪些 .app，返回它们的 …/Contents/Resources

    ★ Steam 在 mac 上的形态是 `<库>/steamapps/common/<游戏名>/<游戏名>.app` ——
      用户（或探测器）很容易只指到**装着 .app 的那个文件夹**，得能自己钻进去。
    """
    out: list[Path] = []
    for root in (p, p.parent):
        try:
            out += [a / "Contents" / "Resources" for a in sorted(root.glob("*.app"))]
        except OSError:
            continue
    return out


def game_root(p: Path | str) -> Path | None:
    """归一化游戏目录，同时**把布局定下来**。

    接受这些给法（GUI 的目录选择器给哪种都不奇怪）：
      · Windows：游戏根目录（里面有 ObraDinn_Data）或 ObraDinn_Data 本身
      · macOS  ：<X>.app、<X>.app/Contents/Resources、…/Contents/Resources/Data，
                 以及**装着 .app 的那个文件夹**（Steam 的常见形态）
    返回的是「容器」（Windows=游戏根，mac=…/Contents/Resources），后面的 rel 路径都相对它。
    """
    p = Path(p).expanduser()
    # ① 先试「p 就是容器」（含 mac 的 .app 形式）—— 顺序不能乱：
    #    这几种会走 _find_layout（只认子目录），保持 Windows 既有行为不变（stash 位置不挪）
    containers = [p, p.parent,
                  p / "Contents" / "Resources",
                  p.parent / "Contents" / "Resources"]
    # ② 再试「p 里面（或上一级）有个 .app」—— 排后面，不干扰上面几种
    containers += _app_containers(p)
    seen: list[Path] = []
    for c in containers:
        if c in seen:
            continue
        seen.append(c)
        name = _find_layout(c)
        if name is not None:
            _apply_layout(name)
            return c
    # ③ 兜底：p（或它的 mac 形式）本身就是数据目录
    for c in [p, p / "Contents" / "Resources" / "Data", p.parent]:
        try:
            if _is_data_dir(c):
                _apply_layout("")
                return c
        except OSError:
            continue
    return None


def steam_libraries() -> list[Path]:
    """找所有 Steam 库目录：Windows 读注册表；macOS 用 ~/Library/Application Support/Steam。
       两边都会再解析 libraryfolders.vdf 拿额外的库盘。
    """
    out: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg                                 # type: ignore[import-not-found]
            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        v = winreg.QueryValueEx(k, "SteamPath" if hive else "InstallPath")[0]
                    out.append(Path(v))
                except OSError:
                    pass
        except Exception:                                 # noqa: BLE001
            pass
    if sys.platform == "darwin":
        mac = Path.home() / "Library" / "Application Support" / "Steam"
        if mac.is_dir():
            out.append(mac)
    libs = list(out)
    for s in list(out):
        vdf = s / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            txt = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in txt.splitlines():
            if '"path"' in line:
                p = line.split('"path"')[1].strip().strip('"').replace("\\\\", "\\")
                if p:
                    libs.append(Path(p))
    return libs


def detect_game(explicit: str | None = None) -> tuple[Path | None, str]:
    """返回 (游戏根目录, 说明)。explicit 给了就只认它（但要校验）"""
    if explicit:
        g = game_root(explicit)
        if g is not None:
            return g, "手工指定"
        return None, ("手工指定的目录不像 ObraDinn（没找到 Managed/%s 或 sharedassets0.assets，"
                      "Windows 与 macOS 两种布局都试过了）" % DLL_REL.name)
    cands: list[Path] = []
    for lib in steam_libraries():
        cands += [lib / "steamapps" / "common" / "ObraDinn",
                  lib / "steamapps" / "common" / "Return of the Obra Dinn"]
    for env, sub in (("ProgramFiles(x86)", "Steam"), ("ProgramFiles", "Steam")):
        import os
        base = os.environ.get(env)
        if base:
            cands.append(Path(base) / sub / "steamapps" / "common" / "ObraDinn")
    if sys.platform == "darwin":
        # macOS：Steam 库 + 直接装在 /Applications 的情况（.app 里面才是游戏）
        cands += [Path("/Applications") / "Return of the Obra Dinn.app",
                  Path("/Applications") / "ObraDinn.app"]
    # 环境变量可直接给游戏目录
    import os
    if os.environ.get("OBRADINN_GAME"):
        cands.insert(0, Path(os.environ["OBRADINN_GAME"]))
    for c in cands:
        g = game_root(c)
        if g is not None:
            return g, "自动检测"
    return None, "没找到游戏目录（可在 GUI 里手选，或用 --game 指定）"


# ===========================================================================
# 2. 清单 / stash
# ===========================================================================
@dataclass
class Record:
    game: str = ""
    created: float = 0.0
    options: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)      # 相对路径 -> {orig_sha, ours_sha, note}

    @staticmethod
    def load(game: Path) -> "Record":
        p = game / STASH_DIR / RECORD
        if p.is_file():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                return Record(game=d.get("game", str(game)), created=d.get("created", 0.0),
                              options=d.get("options", {}), files=d.get("files", {}))
            except Exception:                             # noqa: BLE001
                pass
        return Record(game=str(game))

    def save(self, game: Path) -> None:
        if DEMO:                       # 演示模式不落盘
            return
        p = game / STASH_DIR / RECORD
        p.parent.mkdir(parents=True, exist_ok=True)
        self.game = str(game)
        p.write_text(json.dumps({"game": self.game, "created": self.created,
                                 "options": self.options, "files": self.files},
                                ensure_ascii=False, indent=2), encoding="utf-8")


def stash_path(game: Path, rel: Path) -> Path:
    return game / STASH_DIR / "original" / rel


def ensure_stash(game: Path, rec: Record, rel: Path) -> None:
    """首次动手前把原文件存进 stash（存过就不动 —— 语义：我们发现它时的样子）"""
    src = game / rel
    if not src.is_file():
        return
    if DEMO:
        if not stash_path(game, rel).is_file():
            demo_note("会先备份 %s（%s）" % (rel.as_posix(), human(src.stat().st_size)))
        return
    dst = stash_path(game, rel)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.is_file():
        shutil.copy2(src, dst)
    key = rel.as_posix()
    if key not in rec.files:
        rec.files[key] = {"orig_sha": sha(dst), "note": "stash"}
        rec.save(game)


# 安装会碰的全部文件（判断“这是不是我们自己装的”只看这几个）
# ★ 内容按当前布局生成 —— 见 _apply_layout()
OUR_FILES = [DLL_REL,
             SHS_REL / "sharedassets0.assets",
             SHS_REL / "sharedassets2.assets",
             SHS_REL / "sharedassets6.assets",
             SA_REL / LANG]


def mark_installed(game: Path, rec: Record, only: set[Path] | None = None) -> None:
    """把本次装出来的 sha 记进 record —— 换台机器/换个脚本装，哈希对不上也能认出是自己装的
       （UnityPy 重复保存同一份 shs 不能保证字节完全相同，所以光靠 known-hashes.json 不够）

    ★ `only` = **本次真的写过的文件**（不传 = 全量，旧行为）。
      踩过：字体那一步因缺模块直接跳过，但 mark_installed 还是把原版 shs0/2 的 sha 记成了
      「我们的产物」→ 状态表把**没打补丁的原版**报成 ours，比“未知”还危险。（mac 上实测）
    """
    for rel in OUR_FILES:
        if only is not None and rel not in only:
            continue
        p = game / rel
        if not p.is_file():
            continue
        rec.files.setdefault(rel.as_posix(), {})["ours_sha"] = sha(p)
    rec.save(game)


# ===========================================================================
# 3. 状态判定
# ===========================================================================
@dataclass
class FileState:
    rel: str
    exists: bool
    sha: str
    verdict: str          # vanilla / ours / other / unknown / missing
    detail: str = ""
    action: str = ""


def known_hashes() -> dict:
    p = DATA / "known-hashes.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                 # noqa: BLE001
            pass
    return {}


# ---- 难度补丁的字节级判据（hardcore/PATCH-SPEC.md 的锚点）----
DIFF_ANCHOR = bytes.fromhex("11061a3b0800000011061840")   # 整份 DLL 里唯一
DIFF_B2 = bytes.fromhex("020807195D9A")                   # B2 打过之后（音效索引取模）


def detect_level(game: Path) -> tuple[int, str]:
    """**只读**地读出游戏当前的难度档 —— 本补丁从不修改难度。

    玩家可能自己用过 hardcore 那套难度补丁（或从未打过）：我们按 DLL 里实际的批大小
    去写对应的那 4 条文案。认不出锚点（不认识的游戏 build）就按原版 3 人批。
    """
    dll = game / DLL_REL
    if not dll.is_file():
        return 3, "找不到 DLL，按原版 3 人批"
    lv, _b2 = dll_difficulty_level(dll)
    if lv is None:
        return 3, "认不出难度锚点（游戏版本未知），按原版 3 人批"
    info = difficulty_info(lv)
    return lv, "检测到难度 %d%s%s" % (lv, ("（%s）" % info["label"]) if info else "",
                                      "" if lv == 3 else "，文案按它写")


def dll_difficulty_level(dll: Path) -> tuple[int | None, bool]:
    """直接从 DLL 字节里读难度档位 —— 不依赖 langtool。

    锚点前面是 `13 07`（stloc.s V_7），再前面就是档位常量：原版 `19`(ldc.i4.3)、
    58 档 `1f 3a`(ldc.i4.s 58)。返回 (档位, 是否含 B2 补丁)；认不出就 (None, False)。
    """
    try:
        data = dll.read_bytes()
    except OSError:
        return None, False
    i = data.find(DIFF_ANCHOR)
    if i < 0 or data.find(DIFF_ANCHOR, i + 1) >= 0:      # 锚点必须唯一
        return None, False
    j = i - 2
    if data[j:j + 2] != b"\x13\x07":                     # stloc.s V_7
        return None, False
    k = j - 1                                            # ldc.i4 指令的**最后一个字节**
    b = data[k]
    # 歧义：`1d` 既是 ldc.i4.7 本身，也可能是 `1f 1d`(=ldc.i4.s 29) 的操作数。
    # 用**合法档位集合**消歧义（hardcore 现行档位，7 已拆成 6 和 9）。
    legal = {int(l.get("level", -2)) for l in difficulty_table().get("levels", [])}
    cands: list[int] = []
    if k >= 1 and data[k - 1] == 0x1F:
        cands.append(int.from_bytes(data[k:k + 1], "big", signed=True))    # ldc.i4.s xx
    if k >= 4 and data[k - 4] == 0x20:
        cands.append(int.from_bytes(data[k - 3:k + 1], "little", signed=True))
    if 0x16 <= b <= 0x1E:
        cands.append(b - 0x16)                                             # ldc.i4.0 .. 8
    lv: int | None = None
    for c in cands:
        if c in legal:
            lv = c
            break
    if lv is None and cands:
        lv = cands[0]
    return lv, data.find(DIFF_B2) >= 0


def in_known(v, h: str) -> bool:
    """已知哈希表里的值可以是单个 sha、list[sha] 或 {sha: 说明}"""
    if not h:
        return False
    if isinstance(v, str):
        return v == h
    if isinstance(v, (list, tuple, set)):
        return h in v
    if isinstance(v, dict):
        return h in v
    return False


def our_font_sizes() -> set[int]:
    """包内字体子集 A 的字节长度 —— 用来判 shs0/2 是否已是我们的产物
       （比哈希稳：同一支子集由不同脚本注入，文件级 sha 会不同，但字体长度不会）"""
    out = set()
    for nm in FONT_A:
        p = font_A(nm)
        if p is not None:
            out.add(p.stat().st_size)
    return out


def _unity_env(path: Path):
    """给 UnityPy 一份**临时副本**再让它解析。

    坑：UnityPy 解析后会一直占着文件句柄（它自己的 reader 不保证关），
    Windows 下别人就删不掉/改不了那个文件（沙盒重建时报 WinError 32 就是这个）。
    副本固定在系统临时目录里、同名覆盖，不往游戏目录写东西。
    """
    import UnityPy                                     # type: ignore[import-not-found]
    TMP.mkdir(parents=True, exist_ok=True)
    t = TMP / (path.name + ".u3d")
    shutil.copy2(path, t)
    return UnityPy.load(str(t))


def injected_fonts(p: Path) -> tuple[list[int], list[str]]:
    """读 shs 里 Font 对象的 m_FontData 长度 -> (长度集, 字体名集)"""
    sizes: list[int] = []
    names: list[str] = []
    try:
        env = _unity_env(p)
        for o in env.objects:
            if o.type.name != "Font":
                continue
            try:
                d = o.read()
            except Exception:                            # noqa: BLE001
                continue
            fd = getattr(d, "m_FontData", None)
            if fd:
                sizes.append(len(bytes(fd)))
            names.append(str(getattr(d, "m_Name", "")))
    except Exception:                                    # noqa: BLE001
        pass
    return sizes, names


def dll_verdict(game: Path) -> tuple[str, str]:
    """用 langtool 的三道 --check 判 DLL 状态（原版/已打 wrap/已打难度/已装钩子）"""
    lt = langtool()
    dll = game / DLL_REL
    if not dll.is_file():
        return "missing", "找不到 DLL"
    if lt is None:
        return "unknown", "包内没有 langtool，无法判定"
    tags = []
    wrap = run(lt_cmd(lt, "patchwrap", str(dll), "--check"), quiet=True).returncode
    tags.append("wrap" if wrap == 0 else "no-wrap")
    rv = run(lt_cmd(lt, "revealhook", str(dll), "--check"), quiet=True).returncode
    tags.append("revealhook" if rv == 0 else "no-revealhook")   # 仅作信息：instructor 自己会处理
    lv, b2 = dll_difficulty_level(dll)
    if lv == 3 and not b2:
        pass                                                 # 原版档位 = 没打难度
    elif lv is not None:
        info = difficulty_info(lv)
        tags.append("难度%s(%s)" % (lv, info.get("label", "?")))
    if wrap != 0 and rv != 0 and lv == 3:
        return "vanilla", "原版（未打 wrap；难度仍是原版 %d 人批）" % (lv or 3)
    return "ours", "已打补丁: " + ", ".join(t for t in tags if not t.startswith("no-"))


def inspect_state(game: Path) -> list[FileState]:
    rec = Record.load(game)
    kh = known_hashes()
    inst = {k: (v or {}).get("ours_sha") for k, v in (rec.files or {}).items()}

    def is_installed(rel: str, h: str) -> bool:
        """本机上次安装写入的 sha（最强证据：这就是我们自己装的）。
           但若已等于「我们发现它时的样子」，说明已还原 → 不算我们的。"""
        info = (rec.files or {}).get(rel) or {}
        if h and info.get("orig_sha") == h:
            return False
        return bool(h) and inst.get(rel) == h

    out: list[FileState] = []
    # DLL（永不整文件还原，只叠加）
    v, det = dll_verdict(game)
    dll = game / DLL_REL
    out.append(FileState(DLL_REL.as_posix(), dll.is_file(), sha(dll) if dll.is_file() else "",
                         v, det, "叠加 wrap（幂等）"))
    # shs0/2（只改 Font 对象）
    fsizes = our_font_sizes()
    for i, nm in enumerate(SHS[:2]):
        p = game / SHS_REL / nm
        h = sha(p) if p.is_file() else ""
        if not p.is_file():
            out.append(FileState((SHS_REL / nm).as_posix(), False, "", "missing",
                                 "找不到文件", "安装时会报错——请验证游戏文件完整性"))
            continue
        rel = (SHS_REL / nm).as_posix()
        if is_installed(rel, h):
            st, det = "ours", "本机安装的产物（record 里有记录）"
        elif in_known(kh.get("shs", {}).get(nm), h):
            st, det = "ours", "已知产物（与已知哈希一致）"
        else:
            sizes, names = injected_fonts(p)
            hit = [s for s in sizes if s in fsizes] if fsizes else []
            if hit and names:
                st = "ours"
                det = "字体已是我们的子集（%s）" % ", ".join(
                    "%s=%s" % (n, human(s)) for n, s in zip(names, sizes))
            elif in_known(kh.get("official", {}).get(nm), h):
                st, det = "vanilla", "原版（未注入过字体）"
            else:
                st = "unknown"
                det = "非已知产物（可能是原版、别人的改动或损坏）—— 需要你确认"
        out.append(FileState((SHS_REL / nm).as_posix(), True, h, st, det,
                             "注入字体子集（只动 Font 对象，别的改动保留）"))
    # shs6（整文件替换）
    p6 = game / SHS_REL / "sharedassets6.assets"
    h6 = sha(p6) if p6.is_file() else ""
    our6 = kh.get("shs", {}).get("sharedassets6.assets")
    if not p6.is_file():
        st6, det6 = "missing", "找不到文件"
    elif is_installed((SHS_REL / "sharedassets6.assets").as_posix(), h6):
        st6, det6 = "ours", "本机安装的产物（预生成版）"
    elif in_known(our6, h6):
        st6, det6 = "ours", "已知产物（预生成版）"
    elif in_known(kh.get("official", {}).get("sharedassets6.assets"), h6):
        st6, det6 = "vanilla", "原版（13 KB）"
    else:
        st6, det6 = "unknown", "非已知产物 —— 需要你确认"
    out.append(FileState((SHS_REL / "sharedassets6.assets").as_posix(), p6.is_file(), h6, st6,
                         det6,
                         "整文件替换为预生成版（13 KB；UnityPy 不能写这个文件）"))
    # lang-zh-s
    lp = game / SA_REL / LANG
    hl = sha(lp) if lp.is_file() else ""
    if not lp.is_file():
        stl, detl = "missing", "找不到文件"
    elif hl == kh.get("official_lang"):
        stl, detl = "vanilla", "官方原版"
    elif is_installed((SA_REL / LANG).as_posix(), hl):
        stl, detl = "ours", "本机安装的产物（record 里有记录）"
    elif hl in (kh.get("langpack") or {}):
        stl, detl = "ours", (kh.get("langpack") or {})[hl]
    else:
        stl, detl = "other", "官方或被他方改过（不认识这份）"
    out.append(FileState((SA_REL / LANG).as_posix(), lp.is_file(), hl, stl, detl,
                         "以包内官方包重建（不依赖机器上那份）"))
    # stash 状态
    return out


# ===========================================================================
# 4. 工具与随包资源
# ===========================================================================
def langtool() -> Path | None:
    """找 langtool —— ★ **候选顺序跟平台走**（踩过：mac 上先找到 langtool.exe 就 Exec format error）。

    Windows：assets/langtool/langtool.exe（包内）
    macOS  ：assets/langtool/langtool（打包时由 build_release 把对应架构那份改名而来的）
             → assets/langtool/langtool-macos-{arm64|x64}（开发树里的原名）
    两个平台都再回落到开发树上的 .dll（走 dotnet，仅开发用）。
    """
    if sys.platform == "darwin":
        arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
        cands = [ASSETS / "langtool" / "langtool",
                 ASSETS / "langtool" / ("langtool-macos-%s" % arch)]
    elif sys.platform == "win32":
        cands = [ASSETS / "langtool" / "langtool.exe", ASSETS / "langtool" / "langtool"]
    else:
        cands = [ASSETS / "langtool" / "langtool"]
    cands.append(ROOT / "hardcore" / "langtool" / "bin" / "Release" / "net8.0" / "langtool.dll")
    for c in cands:
        if c.is_file():
            if sys.platform != "win32" and not os.access(c, os.X_OK):
                # 开发树里从 tar/zip 出来的二进制常常丢了可执行位，顺手补上；
                # ★ 但 .app 包内不能改：会破坏（ad-hoc）签名封印（所以排除 .app 路径）
                if ".app" not in str(c):
                    try:
                        os.chmod(c, 0o755)
                    except OSError:
                        pass
            return c
    return None


def run(cmd: list[str], quiet: bool = False) -> subprocess.CompletedProcess:
    kw = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
    r = subprocess.run(cmd, **kw)
    if not quiet and r.stdout:
        for ln in r.stdout.splitlines()[-6:]:
            say("    " + ln)
    return r


def lt_cmd(lt: Path, *args: str) -> list[str]:
    """langtool 可能是 .exe（自包含发布）也可能是 .dll（开发树里）—— dll 要走 dotnet"""
    base = ["dotnet", str(lt)] if lt.suffix.lower() == ".dll" else [str(lt)]
    return base + list(args)


def asset_candidates(rel_candidates: list[str]) -> Path | None:
    for c in rel_candidates:
        p = (ASSETS / c).resolve() if not c.startswith("../") else (PKG / c).resolve()
        if p.is_file():
            return p
    return None


def font_A(name: str) -> Path | None:
    return asset_candidates(FONT_A.get(name, []))


def langpack_base(game: Path | None = None) -> Path | None:
    """语言包重建的基底 —— 它只提供**容器结构**，文本 100% 由我们的 TSV 决定
    （实测：TSV 含全部 985 条 key，与官方包的 key 集一一对应）。

    Windows：包内官方中文包（绝不用机器上那份 —— 它可能已被改过）
    macOS  ：**必须用机器自己那份**。StreamingAssets/lang-* 是 UnityFS 资源包（AssetBundle），
             是**平台相关**的（实测 mac 那份 3505083 B / 985 条 key，但其中 455 条文本与
             Windows 版的官方包不同 —— 是另一个修订版的译文）。把 Windows 构建的包塞进
             mac 客户端有读不了的风险，所以 mac 上拿机器那份当壳，文本依旧全量来自我们的 TSV：
             结果**文本与 Windows 版完全一致**，只是壳子是 mac 自己的。
    """
    if sys.platform == "darwin" and game is not None:
        own = game / SA_REL / LANG
        if own.is_file():
            return own
    return asset_candidates(["lang-zh-s-official", "../originalassets/langpacks/lang-zh-s"])


def langpack_tsv(version: str, harm: str, dialog: str) -> Path | None:
    return asset_candidates(["packs/zh-s-%s-%s-%s.tsv" % (version, harm, dialog),
                             "../out/packs/zh-s-%s-%s-%s.tsv" % (version, harm, dialog)])


def texture(rel: str) -> Path | None:
    return asset_candidates(["textures/" + rel, "../out/textures/" + rel,
                             "../Textures/" + rel])


def shs6_prebuilt() -> Path | None:
    """包内那份 sharedassets6.assets —— 现在它是**文本来源**，不是要整文件拷过去的成品
    （见 step_shs6 的说明：整文件替换在 mac 上是错的）。"""
    return asset_candidates(["sharedassets6.assets", "../out/assets/sharedassets6.assets",
                             "../originalassets/sharedassets6.assets"])


# ---- 鸣谢文本（sharedassets6.assets）：文本块的定位与替换 --------------------
#   这个文件是 SerializedFile，最后那个 MonoBehaviour 里存着一串
#   `#credits_*` -> 文本（`int32 长度 + UTF-8 + 4 对齐`）。改长度只需同步两处尺寸：
#     · 头部 file_size（偏移 4，**大端**）
#     · metadata 里该对象的 byteSize（该文件在偏移 184，**小端**）
#   —— 这两条都是 CN_Refined/assets/inject_credits.py 里用「复现旧产物」反推并验证过的；
#      这里把它移植进来，但**不确定的偏移要自检**（见 _shs6_sizes）。
CREDITS_PREFIX = b"#credits_"


def _u_read(buf: bytes | bytearray, off: int) -> tuple[str, int] | None:
    """读一个 Unity 串：int32(LE) 长度 + UTF-8 + 4 对齐填充 -> (文本, 下一个偏移)"""
    if off < 0 or off + 4 > len(buf):
        return None
    n = struct.unpack_from("<i", buf, off)[0]
    if not (0 <= n <= 65535) or off + 4 + n > len(buf):
        return None
    raw = bytes(buf[off + 4:off + 4 + n])
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(not c.isprintable() and c not in "\r\n\t" for c in s):
        return None
    return s, off + 4 + n + ((-n) % 4)


def _find_text_block(buf: bytes | bytearray, key: str) -> tuple[int, str, int] | None:
    """定位某条鸣谢文本的块 -> (前缀偏移, 旧文本, 块总长)。

    规则（与 inject_credits.find_text_block 一致）：从 ID 串尾往后，找第一个
    「4 对齐、int32 长度>0、后面那 n 字节是合法可打印 UTF-8」的位置。
    ★ ID 必须**精确**匹配：`#credits_voice` 是 `#credits_voice_add` 的前缀，
      不检查串尾的 \x00 会认错条目（踩过）。
    """
    kb = (key if key.startswith("#") else "#" + key).encode()
    start = 0
    while True:
        o = buf.find(kb, start)
        if o < 0:
            return None
        start = o + 1
        if o + len(kb) < len(buf) and buf[o + len(kb)] != 0:
            continue                                  # 只是别人 id 的前缀，不是它
        id_end = o + len(kb)
        for p in range(id_end, min(len(buf) - 8, id_end + 64)):
            if p % 4:
                continue
            n = struct.unpack_from("<i", buf, p)[0]
            if n <= 0 or p + 4 + n > len(buf):
                continue
            try:
                s = bytes(buf[p + 4:p + 4 + n]).decode("utf-8")
            except UnicodeDecodeError:
                continue
            if any(not c.isprintable() and c not in "\r\n\t" for c in s):
                continue
            return p, s, 4 + n + ((-n) % 4)
        return None


def credits_edits() -> dict[str, str]:
    """从包内预生成件里读出「每条鸣谢应该是什么文本」= 我们要做的编辑集。

    只有能定位到非空文本的条目才算（实测这个文件里真正带文本的就一条：
    `credits_loc_chinese_s` —— 其余条目的文本在语言包里，不在这里）。
    """
    src = shs6_prebuilt()
    if src is None:
        return {}
    buf = src.read_bytes()
    out: dict[str, str] = {}
    off = 0
    while True:
        p = buf.find(CREDITS_PREFIX, off)
        if p < 0:
            break
        off = p + 1
        rid = _u_read(buf, p - 4)
        if not rid or not rid[0].startswith("#credits_"):
            continue
        hit = _find_text_block(buf, rid[0])
        if hit and hit[1]:
            out[rid[0]] = hit[1]
    return out


def _shs6_sizes(buf: bytes | bytearray) -> tuple[int, int, int]:
    """找出 (file_size 偏移, byteSize 偏移, 旧 byteSize) —— 带自检。

    自检依据：这个 MonoBehaviour 是**最后一个对象**，它的数据一直顶到文件尾，
    所以 `byteSize == 文件长度 - 对象数据起点`，即数据起点 = len - byteSize 必须
    ≥ data_offset 且 4 对齐。184 那个偏移就是这么被反推出来的；万一换个平台/版本
    对不上，就在 metadata 区里搜唯一满足该关系的值。
    """
    data_off = struct.unpack_from(">I", buf, 12)[0]
    fs_off = 4
    cands = [184] + [i for i in range(16, data_off - 4, 4) if i != 184]
    for off in cands:
        bs = struct.unpack_from("<I", buf, off)[0]
        start = len(buf) - bs
        if bs and start >= data_off and start % 4 == 0 and start <= len(buf):
            return fs_off, off, bs
    raise ValueError("找不到 byteSize 字段（文件结构不是预期的？）")


def _inject_credits(buf: bytearray, edits: dict[str, str], log: list[str]) -> tuple[int, int]:
    """就地替换鸣谢文本块，并同步两处尺寸。返回 (改动条数, 总字节差)。"""
    total = 0
    n_changed = 0
    for key in sorted(edits):
        text = edits[key]
        hit = _find_text_block(buf, key)
        if hit is None:
            log.append("  ⚠ 机器那份里找不到 %s，跳过" % key)
            continue
        pfx, old, blen = hit
        if old == text:
            continue                                  # 已经是我们的文本 → 幂等
        nb = text.encode("utf-8")
        pad = (-len(nb)) % 4
        block = struct.pack("<i", len(nb)) + nb + b"\x00" * pad
        buf[pfx:pfx + blen] = block
        total += len(block) - blen
        n_changed += 1
        log.append("  %s：%d → %d 字节（%+d）" % (key, blen, len(block), len(block) - blen))
    if total:
        fs_off, bs_off, old_bs = _shs6_sizes(buf)
        fs = struct.unpack_from(">I", buf, fs_off)[0]
        struct.pack_into(">I", buf, fs_off, fs + total)
        struct.pack_into("<I", buf, bs_off, old_bs + total)
        log.append("  同步尺寸：file_size %d → %d（大端）；byteSize %d → %d（小端）"
                   % (fs, fs + total, old_bs, old_bs + total))
    return n_changed, total


def _tsv_rows(p: Path) -> int:
    """数一下 TSV 里有几条字符串（首行是 # 注释、末尾可能空行）"""
    try:
        return sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
                   if ln and not ln.startswith("#"))
    except OSError:
        return 0


# ---- 难度表（data/difficulty.json，由 tools/gen_difficulty.py 生成）----
#   批大小写死在哪、哪些键要跟着改，见 hardcore/PATCH-SPEC.md
DEFAULT_KEYS = ["welldone_3_first", "welldone_3_more",
                "help_faceclear_fates0", "help_faceclear_fates1"]


def difficulty_table() -> dict:
    p = DATA / "difficulty.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                 # noqa: BLE001
            pass
    return {}


def difficulty_info(level: int) -> dict:
    for lv in difficulty_table().get("levels", []):
        try:
            if int(lv.get("level", -999)) == int(level):
                return lv
        except (TypeError, ValueError):
            continue
    return {}


def apply_difficulty(text: str, level: int, log: list[str] | None = None) -> tuple[str, int]:
    """把 TSV 里 4 个难度键的中文数字换成目标档位。

    内容与 hardcore 的 `_lang/out/lv<N>/edits-zh-s.txt` 一致，但我们**只换数字**，
    保留自己的措辞（TSV 里写死的是原版「三」）。3 = 原版 → 不动。
    """
    import re
    tab = difficulty_table()
    zh = (difficulty_info(level) or {}).get("zh", "")
    if not zh or zh == "三":
        return text, 0
    keys = set(tab.get("keys") or DEFAULT_KEYS)
    num = "[" + (tab.get("num_chars") or "〇一二三四五六七八九十百两") + "]+"
    out: list[str] = []
    n = 0
    for ln in text.splitlines():
        head, sep, val = ln.partition("\t")
        if sep and head in keys:
            new = re.sub(num + "(?=[个人])", zh, val)
            if new != val:
                n += 1
                ln = head + sep + new
            elif log is not None:
                log.append("  ⚠ 难度键 %s 里没找到中文数字，未改写" % head)
        out.append(ln)
    return "\n".join(out) + "\n", n


def tmp_donor(game: Path, name: str, data: bytes) -> Path | None:
    """把游戏内嵌字体存成临时文件，当身份名 donor 用"""
    if not data:
        return None
    d = game / STASH_DIR / "build"
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("donor-%s" % name)
    p.write_bytes(data)
    return p


# ===========================================================================
# 5. 各步骤
# ===========================================================================
def step_fonts(game: Path, rec: Record, log: list[str]) -> bool:
    """把字体子集 A 注入游戏 shs0/2 的 Font 对象（只动 m_FontData）"""
    import importlib
    sys.path.insert(0, str(PKG.parent / "assets"))
    try:
        import UnityPy                                      # type: ignore[import-not-found]
        MS = importlib.import_module("make_subset_fonts")    # 身份名工具
    except Exception as e:                                   # noqa: BLE001
        log.append("  ✗ 缺依赖（UnityPy / fontTools）: %s" % e)
        return False
    jobs = {"sharedassets0.assets": ["SourceHanSerif-SemiBold"],
            "sharedassets2.assets": ["851tegaki_zatsu_normal_0883"]}
    ok = True
    for shs, names in jobs.items():
        p = game / SHS_REL / shs
        if not p.is_file():
            log.append("  ✗ 缺 %s" % shs)
            ok = False
            continue
        ensure_stash(game, rec, SHS_REL / shs)
        env = _unity_env(p)
        done = []
        for o in env.objects:
            if o.type.name != "Font":
                continue
            d = o.read()
            nm = getattr(d, "m_Name", "")
            if nm not in names:
                continue
            fp = font_A(nm)
            if fp is None:
                log.append("  ✗ 包内没有 %s 的子集字体 A" % nm)
                ok = False
                continue
            data = fp.read_bytes()
            # ★ 身份名必须能对上 Font 对象的 m_FontNames，否则 Unity 会把整支字体回落到系统字体
            #   （这个坑踩过两次：换成 SC 源后 family 变成 'Source Han Serif Simplified Chinese'）
            #   对不上就用**游戏内嵌**那支做 donor 现场恢复。
            try:
                from fontTools.ttLib import TTFont                    # type: ignore
                idf = MS.identity_of(TTFont(fp, lazy=True))
                want = list(getattr(d, "m_FontNames", []) or [])
                cand = [idf["cff_family"], idf["name1"], idf["cff_font"], idf["name6"]]
                if not any(c and c in want for c in cand):
                    donor = tmp_donor(game, nm, bytes(d.m_FontData))
                    if donor is not None:
                        f2 = TTFont(fp, lazy=True)
                        MS.restore_identity(f2, donor)
                        import io
                        buf = io.BytesIO()
                        f2.save(buf)
                        data = buf.getvalue()
                        log.append("  %s: 身份名与 m_FontNames=%s 不符 → 已按游戏内 donor 恢复"
                                   % (nm, want))
            except Exception as e:                                   # noqa: BLE001
                log.append("  ⚠ %s 身份名校验跳过（%s）" % (nm, e))
            before = len(d.m_FontData)
            d.m_FontData = list(data)
            d.save()
            done.append((nm, before, len(data), fp.name))
        data_out = env.file.save()
        if done:
            put_bytes(p, data_out, "注入字体子集 A")
        if DEMO and done:
            say("    （演示）%s 不会被修改" % shs)
        for nm, a, b, src in done:
            log.append("  %s: %s  %s → %s  (%s)"
                       % (shs, nm, human(a), human(b), src))
        if not done:
            log.append("  ✗ %s 里没找到目标 Font 对象" % shs)
            ok = False
    return ok


def step_shs6(game: Path, rec: Record, log: list[str]) -> bool:
    """鸣谢文本：把文本块**注入机器上那份** sharedassets6.assets

    ★ 为什么不整文件替换（原来的做法，已在 mac 上证实是错的）：
      包内那份预生成件是 **Windows 构建**出来的 SerializedFile，头部有 m_TargetPlatform
      （实测：Windows 那份 = 5，而这台 mac 上的那份 = 19）。把 Windows 的文件整份塞进
      mac 客户端风险很大 —— 这也正是 mac 上必须改成"就地注入"的原因。
      现在：基底 = **机器那份**（只提供容器结构），我们只替换里面的鸣谢文本块，
      于是天然保留了该文件的平台字段与别的工具对它的改动（与 DLL「只叠加」同一套哲学）。
    ★ 文本只在真的不同时才写 → 重复安装是幂等的。
    """
    edits = credits_edits()
    if not edits:
        log.append("  ✗ 包内没有可用的 sharedassets6.assets（拿不到鸣谢文本）")
        return False
    dst = game / SHS_REL / "sharedassets6.assets"
    if not dst.is_file():
        log.append("  ✗ 机器上没有 %s" % (SHS_REL / "sharedassets6.assets").as_posix())
        return False
    ensure_stash(game, rec, SHS_REL / "sharedassets6.assets")
    buf = bytearray(dst.read_bytes())
    try:
        n, delta = _inject_credits(buf, edits, log)
    except ValueError as e:
        log.append("  ✗ %s（这份文件的尺寸字段对不上，先别动它）" % e)
        return False
    if DEMO:
        demo_note("会用机器那份当基底，就地注入 %d 条鸣谢文本（不整文件替换）" % len(edits))
        log.append("  sharedassets6.assets：%s（演示：未写盘）"
                   % ("文本已是我们的版本" if n == 0 else "会改 %d 条文本" % n))
        return True
    if n == 0:
        log.append("  sharedassets6.assets：鸣谢文本已是我们的版本（幂等，跳过）")
        return True
    put_bytes(dst, bytes(buf), "鸣谢文本（就地注入）")
    log.append("  sharedassets6.assets：已注入 %d 条鸣谢文本，文件 %s（%+d 字节）"
               % (n, human(len(buf)), delta))
    return True


def step_langpack(game: Path, rec: Record, opt: "Options", level: int,
                  log: list[str]) -> bool:
    """用包内官方包 + 成品 TSV + 四张图，做出 lang-zh-s 并装进游戏

    `level` = **游戏当前**的难度档（只用于决定那 4 条批大小文案怎么写）。
    """
    import importlib
    base = langpack_base(game)     # mac 上用机器自己那份当壳（见该函数的说明）
    tsv = langpack_tsv(opt.version, "harm" if opt.harmonized else "unharm", opt.dialog)
    if base is None or tsv is None:
        log.append("  ✗ 缺资源（官方包 %s / TSV %s）" % (bool(base), bool(tsv)))
        return False
    lt = langtool()
    if lt is None:
        log.append("  ✗ 包内没有 langtool")
        return False
    ensure_stash(game, rec, SA_REL / LANG)
    tmp = game / STASH_DIR / "build"
    mkdirs(tmp)
    # ★ 难度：**只读**游戏当前档位，把 4 条批大小文案的中文数字写成对应的
    use_tsv = tsv
    try:
        new_text, nn = apply_difficulty(tsv.read_text(encoding="utf-8"), level, log)
        if nn:
            if DEMO:
                demo_note("会用按难度改写过的 TSV（%d 条批大小文案）" % nn)
            else:
                use_tsv = tmp / ("pack-lv%d.tsv" % level)
                use_tsv.write_text(new_text, encoding="utf-8")
            info = difficulty_info(level)
            log.append("  按当前难度 %s（%s）：改写 %d 条批大小文案"
                       % (level, info.get("label", "?"), nn))
        elif not difficulty_info(level):
            log.append("  ⚠ 难度 %s 不在档位表里 —— 语言包按原版「三」保留" % level)
    except Exception as e:                                  # noqa: BLE001
        log.append("  ⚠ 难度文案改写失败（%s），用原 TSV" % e)
    step1 = tmp / LANG
    axis = NAME_AXIS[opt.version]
    region = "harm" if opt.harmonized else "unharm"
    tex = {"ManifestCrew": "ManifestCrew-%s-%s.png" % (axis, region),
           "FolioSketch": "FolioSketch-%s.png" % region,
           "FolioDeck": "FolioDeck.png", "FolioChart": "FolioChart.png"}
    if DEMO:
        # 演示：不调 langtool set（它会写盘）、不重建包，但仍把要用的东西真的验一遍
        from PIL import Image                           # type: ignore[import-not-found]
        demo_note("会用包内官方包 + %s（%d 条字符串）重建 %s"
                  % (use_tsv.name, _tsv_rows(use_tsv), LANG))
        for nm, fn in tex.items():
            fp = texture(fn)
            if fp is None:
                log.append("  ✗ 缺图 %s" % fn)
                return False
            with Image.open(fp) as im:
                log.append("  图 %-13s ← %-34s %dx%d" % (nm, fn, im.size[0], im.size[1]))
        demo_note("不写 %s" % (SA_REL / LANG).as_posix())
        log.append("  %s ← 4 张图 + 字符串（演示：未写盘）" % LANG)
        return True
    r = run(lt_cmd(lt, "set", str(base), str(step1), str(use_tsv), "--pack=lzma"))
    if r.returncode != 0 or not step1.is_file():
        log.append("  ✗ langtool set 失败（返回码 %d）" % r.returncode)
        return False
    import UnityPy                                      # type: ignore[import-not-found]
    from PIL import Image                               # type: ignore[import-not-found]
    env = _unity_env(step1)
    n = 0
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        d = o.read()
        nm = getattr(d, "m_Name", "")
        fp = texture(tex[nm]) if nm in tex else None
        if fp is None:
            log.append("  ✗ 缺图 %s" % (tex.get(nm, nm)))
            return False
        img = Image.open(fp).convert("RGBA")
        if img.size != (d.m_Width, d.m_Height):
            log.append("  ✗ %s 尺寸不符 %s vs %sx%s" % (nm, img.size, d.m_Width, d.m_Height))
            return False
        d.set_image(img, target_format=UnityPy.enums.TextureFormat.RGBA32)
        d.save()
        n += 1
        log.append("  图 %-13s ← %s" % (nm, fp.name))
    out = game / SA_REL / LANG
    blob = env.file.save(packer="lzma")
    put_bytes(out, blob, "重建后的语言包")
    log.append("  %s ← %d 张图 + 985 条字符串   %s" % (LANG, n, human(len(blob))))
    return n == 4


def step_dll(game: Path, rec: Record, opt: "Options", log: list[str]) -> bool:
    """只在现有 DLL 上叠加 wrap（换行修补）（与其它补丁任意顺序兼容，见记忆）

    ★ 难度**不归我们管**：玩家用什么难度档就用什么，我们只读它去写文案。
      所以这里不再有任何 patchdll / 难度相关改动。
    """
    lt = langtool()
    dll = game / DLL_REL
    if lt is None or not dll.is_file():
        log.append("  ✗ 缺 langtool 或 DLL")
        return False
    ensure_stash(game, rec, DLL_REL)
    rc = run(lt_cmd(lt, "patchwrap", str(dll), "--check"), quiet=True).returncode
    if rc == 0:
        log.append("  DLL: wrap 已是 current（幂等，跳过）")
        return True
    if DEMO:
        demo_note("会给 DLL 打换行修补 wrap-1（不动难度）")
        log.append("  DLL: 现在没打 wrap，演示模式下不实际修改")
        return True
    out = game / STASH_DIR / "build" / "Assembly-CSharp.wrap.dll"
    out.parent.mkdir(parents=True, exist_ok=True)
    managed = str((game / DLL_REL).parent)
    r = run(lt_cmd(lt, "patchwrap", str(dll), str(out), "--deps=" + managed))
    if r.returncode != 0 or not out.is_file():
        log.append("  ✗ patchwrap 失败（返回码 %d）" % r.returncode)
        return False
    put_file(out, dll, "DLL 换行修补")
    log.append("  DLL: 已打 wrap-1  %s" % human(dll.stat().st_size if not DEMO else out.stat().st_size))
    return True


# ===========================================================================
# 6. 安装 / 还原
# ===========================================================================
@dataclass
class Options:
    version: str = "v5"          # v1..v5
    harmonized: bool = False     # True=和谐版
    dialog: str = "bi"           # bi | mono
    level: int | None = None     # 仅测试用：强制难度的文案档位；**None = 读游戏当前难度**


def _flush(log: list[str], n0: int) -> int:
    """把这一步新增的日志行即时说出来（不然它们会全堆到末尾，看着跳步）"""
    for ln in log[n0:]:
        say(ln)
    return len(log)


def install(game: Path, opt: Options, force: bool = False) -> tuple[bool, list[str]]:
    log: list[str] = []
    if not looks_like_game(game):
        return False, ["✗ %s 不像 ObraDinn 安装目录" % game]
    if DEMO:
        say("★ 演示模式：下面只是「将会做什么」，不会向任何地方写入")
        say("  （游戏目录、备份文件夹、record 都不会动）")
    # 动别人改过的文件之前必须显式确认（用户要求：未知状态不得默默继续）
    risky = [s for s in inspect_state(game) if s.verdict in ("unknown", "other")]
    if risky and not force:
        log.append("⚠ 现场有 %d 个文件既不是原版、也不是我们认识的产物：" % len(risky))
        for s in risky:
            log.append("   - %-42s [%s]  %s" % (s.rel, s.verdict, s.detail))
        log.append("  安装会在它们的**现有内容**上继续做（不会盖掉别人的改动）。")
        log.append("  确认无误请加 --force（GUI 里会弹确认框）。")
        return False, log
    rec = Record.load(game)
    if not rec.created:
        rec.created = time.time()
    _lt = langtool()
    say("langtool: %s%s" % (_lt if _lt else "✗ 缺（包内 assets/langtool/langtool.exe 或 mac 上的 assets/langtool/langtool）",
                            "" if (_lt and _lt.suffix.lower() in (".exe", "")) else "  ← 开发树上的，随包应为发布版"))
    # ★ 难度：**只读**（本补丁从不改难度；玩家用 hardcore 那套改成什么，我们就写什么文案）
    if opt.level is None:
        lv, lvmsg = detect_level(game)
    else:
        lv, lvmsg = int(opt.level), "测试强制档位 %s" % opt.level
    say("难度识别: %s" % lvmsg)
    rec.options = {"version": opt.version, "harmonized": opt.harmonized,
                   "dialog": opt.dialog, "level": lv}
    say("[1/4] 字体子集注入 sharedassets0/2")
    before = {rel: sha(game / rel) for rel in OUR_FILES}
    n = len(log)
    ok_f = step_fonts(game, rec, log)
    n = _flush(log, n)
    say("[2/4] 鸣谢文本（注入到 sharedassets6）")
    ok6 = step_shs6(game, rec, log)
    n = _flush(log, n)
    say("[3/4] 语言包 lang-zh-s")
    ok_l = step_langpack(game, rec, opt, lv, log)
    n = _flush(log, n)
    say("[4/4] DLL 打换行修补（不动难度）")
    ok_d = step_dll(game, rec, opt, log)
    n = _flush(log, n)
    ok = ok_f and ok6 and ok_l and ok_d
    # ★ 只把「确实写进去的」文件记成我们的：本步报成功、或字节真的变了（见 mark_installed 的说明）
    done: set[Path] = set()
    if ok_f:
        done |= {SHS_REL / "sharedassets0.assets", SHS_REL / "sharedassets2.assets"}
    if ok6:
        done.add(SHS_REL / "sharedassets6.assets")
    if ok_l:
        done.add(SA_REL / LANG)
    if ok_d:
        done.add(DLL_REL)
    for rel in OUR_FILES:
        if rel not in done and before.get(rel) != sha(game / rel):
            done.add(rel)
    mark_installed(game, rec, done)
    rec.files.setdefault("_meta", {})["last_install"] = {
        "t": time.time(), "ok": bool(ok), "options": rec.options}
    rec.save(game)
    if DEMO:
        say("")
        say("演示结束：以上都是计划，没有任何文件被修改 ✓")
    return ok, log


def restore(game: Path, remove_stash: bool = False) -> tuple[bool, list[str]]:
    """把 stash 写回 = 回到"我们动手之前"（别的工具的补丁原样保留）"""
    log: list[str] = []
    rec = Record.load(game)
    if DEMO and not rec.files:
        # 演示：这台机器没装过也把流程演一遍（假定“当前文件就是安装前状态”）
        rec.files = {rel.as_posix(): {"orig_sha": sha(game / rel), "note": "（演示假设）"}
                     for rel in OUR_FILES if (game / rel).is_file()}
        log.append("  （演示）没找到安装记录 —— 按「当前文件就是安装前状态」模拟一遍")
    if not rec.files:
        return False, ["✗ 没有 install-record.json —— 没东西可还原"]
    ok = True
    n_all = len([k for k in rec.files if not k.startswith("_")])
    n_done = 0
    for rel, info in sorted(rec.files.items()):
        if rel.startswith("_"):
            continue
        n_done += 1
        tag = "[还原 %d/%d]" % (n_done, n_all or n_done)
        src = stash_path(game, Path(rel))
        dst = game / rel
        if DEMO and (info.get("note") == "（演示假设）" or not src.is_file()):
            log.append("  %s %s（演示：无备份文件，按当前内容模拟）" % (tag, rel))
            continue
        if not src.is_file():
            log.append("  ⚠ stash 里缺 %s，跳过" % rel)
            ok = False
            continue
        if DEMO:
            log.append("  %s 会还原 %-36s %s（演示：未写盘）"
                       % (tag, rel, human(src.stat().st_size)))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        put_file(src, dst)
        good = sha(dst) == info.get("orig_sha")
        if good:
            info.pop("ours_sha", None)     # 已还原 → 不再是「我们的产物」（否则状态表会误报）
        log.append("  %s 还原 %-38s %s  sha=%s %s"
                   % (tag, rel, human(dst.stat().st_size), sha(dst)[:16],
                      "✓" if good else "✗ 与记录不符"))
        ok &= good
    rec.save(game)
    if ok and remove_stash:
        shutil.rmtree(game / STASH_DIR / "original", ignore_errors=True)
        log.append("  （已清空 stash/original，record 保留）")
    return ok, log


# ===========================================================================
# 7. CLI（输出同时写报告文件 —— PowerShell 控制台的中文会被 GBK 搞乱，读文件才准）
# ===========================================================================
OUTDIR = PKG / "out"


def rep(m: str = "") -> None:
    say(m)


def write_report(name: str) -> Path:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    p = OUTDIR / ("%s.txt" % name)
    p.write_text("\n".join(_report) + "\n", encoding="utf-8-sig")
    return p


def print_state(game: Path) -> bool:
    rep("状态判定")
    rep("=" * 92)
    rows = inspect_state(game)
    for s in rows:
        mark = {"vanilla": "原版", "ours": "我们的", "other": "他方/官方",
                "unknown": "未知", "missing": "缺失"}[s.verdict]
        rep("  %-44s [%-6s] %-10s %s" % (s.rel, mark, s.sha[:10], s.detail))
        rep("  %-44s   → %s" % ("", s.action))
    rec = Record.load(game)
    rep("")
    rep("stash: %s%s" % ("有（%d 个文件）" % len(rec.files) if rec.files else "还没有",
                        "  上次安装: %s" % rec.options if rec.options else ""))
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", help="游戏目录（不给就自动检测）")
    ap.add_argument("--state", action="store_true", help="只报状态")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--version", default="v5", choices=LEVELS)
    ap.add_argument("--harm", default="unharm", choices=["unharm", "harm"])
    ap.add_argument("--dialog", default="bi", choices=["bi", "mono"])
    lv_legal = [int(l["level"]) for l in difficulty_table().get("levels", [])] or [3, 4, 6, 9, 14, 29, 58]
    ap.add_argument("--level", type=int, default=None,
                    help="仅供测试：强制文案档位。正常不传 = 读游戏 DLL 里当前的难度（%s）"
                         % "/".join(str(x) for x in lv_legal))
    ap.add_argument("--force", action="store_true", help="现场有非原版/未知文件时也继续")
    ap.add_argument("--demo", action="store_true",
                    help="演示模式：流程与日志照跑，但不向任何地方写入（给 GUI/自测用）")
    a = ap.parse_args()

    global DEMO
    if a.demo:
        DEMO = True

    g_raw = a.game or ""
    game, how = detect_game(g_raw)
    if game is None:
        say("✗ " + how)
        return 2
    say("游戏目录: %s（%s）" % (game, how))
    if a.level is not None and a.level not in lv_legal:
        say("！ 测试用难度 %d 不在表里（%s）—— 语言包会按原版保留"
            % (a.level, "/".join(str(x) for x in lv_legal)))
    if a.state or not (a.install or a.restore):
        ok = print_state(game)
        p = write_report("state")
        say("报告: %s" % p)
        return 0 if ok else 1
    if a.restore:
        ok, log = restore(game)
        for ln in log:
            say(ln)
        say("还原%s" % ("完成 ✓" if ok else "有问题 ✗"))
        p = write_report("restore")
        say("报告: %s" % p)
        return 0 if ok else 1
    opt = Options(version=a.version, harmonized=(a.harm == "harm"),
                  dialog=a.dialog, level=a.level)
    say("安装选项: %s / %s / %s / 难度 %s"
        % (opt.version, "和谐" if opt.harmonized else "未和谐",
           "双语" if opt.dialog == "bi" else "单语",
           ("测试强制 %d" % opt.level) if opt.level is not None else "按游戏当前档位"))
    ok, log = install(game, opt, a.force)
    for ln in log:
        say(ln)
    say("")
    say("安装%s" % ("完成 ✓" if ok else "未完全成功 ✗"))
    print_state(game)
    p = write_report("install")
    say("报告: %s" % p)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
