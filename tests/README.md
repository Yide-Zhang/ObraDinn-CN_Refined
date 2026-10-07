# 断行补丁验证台

这套东西只做一件事：**用真实执行**证明 `Assembly-CSharp.dll` 里的中文断行规则
（`TextWrap.CanBreakAfter`）是我们要的那一版 —— 而不是靠读反编译文本猜。

本目录**不含 langtool 源码**：三个产品（存档工具 / 难度补丁 / 提示工具）共用
`hardcore/langtool` 这一个上游，这里只用它的构建产物。CN_Refined 发布时带一份
langtool 二进制。

## 文件

| 文件 | 干什么 |
|---|---|
| `probe/` | C# 探针。先产出一份**探针副本**（只把依赖 `Lang.get_loadedLanguage` 换成读注入字段，`CanBreakAfter` 逐字节原样），再 `Assembly.Load(字节)` 真跑语料 |
| `diff_wrap.py` | 比对两份探针结果：越界 / 少断 / 多断 / 异常 / 无法解释 分类统计，并要求「多断必须为 0、无法解释必须为 0」 |
| `ildiff.py` | 全量 IL 比对：证明一次补丁**只动了允许动的类型** |
| `matrix.py` | 三个补丁（`patchwrap` / `patchdll` / `revealhook`）九种叠加顺序的兼容性矩阵 |

## 依赖

* `hardcore/langtool` 已构建：`dotnet build hardcore/langtool/LangTool.csproj -c Release`
* `uabea-windows/Mono.Cecil.dll`（探针编译时引用）
* 游戏的 `ObraDinn_Data/Managed` —— `patchwrap` 写盘时 Cecil 要靠它解析 `UnityEngine.*`。
  默认写死在本机那份，别的机器用环境变量 `OBRADINN_MANAGED` 覆盖

## 素材（**不在本目录**，仍在工作区根）

| 路径 | 是什么 |
|---|---|
| `originalDLLWin/Assembly-CSharp.dll` | 当前游戏 build 的**纯净原版**（断行是老的，会被 Steam 校验完整性还原成它） |
| `patcher/assets/original/Assembly-CSharp.dll` | 断行**基准**那一版（css 那套语义） |
| `css/Assembly-CSharp/TextWrap.cs` | 基准**源码**（反编译产物） |

## 怎么跑

```powershell
# 1) 探针（对任意一份 Assembly-CSharp.dll 都能跑）
dotnet CN_Refined\tests\probe\bin\Release\net8.0\WrapProbe.dll <dll> <结果.txt> <Managed 目录>

# 2) 两份结果比对（exit 0 = 逐位一致）
python CN_Refined\tests\diff_wrap.py <A.txt> <B.txt> <A标签> <B标签> <详细.txt>

# 3) 全量 IL 比对（exit 0 = 改动没越界）
python CN_Refined\tests\ildiff.py <a.il> <b.il> <详细.txt> "TextWrap::"

# 4) 兼容性矩阵（exit 0 = 九种顺序全绿）
python CN_Refined\tests\matrix.py
```

IL 转储这样生成（`ilspycmd` 的 `-t` 过滤对 `-il` 不生效，整份 dump 正好用来做全量比对）：

```powershell
ilspycmd -il <dll> | Out-File -Encoding utf8 <a.il>
```

## 为什么探针要绕 `Lang`

`Lang.loadedLanguage` 是**手写属性**不是自动属性，getter 会去查 `Lang.languages` /
`LangPack`；而 `Lang..cctor` 里 `new Language(...)` 带 Unity 的 internal call，在 .NET 里
直接抛 `SecurityException: ECall methods must be packaged into a system module`。

所以探针只在副本里改三件**依赖侧**的事 —— `Lang..cctor` 置空、`Language::isAsian` 去掉
`initonly`、`get_loadedLanguage` 改成 `return Lang::__probeLoaded;` —— `CanBreakAfter`
一个字节都不动，测的就是产品里那份 IL。

## 语料

手写文案 + 两张禁则表（`kCantStart` / `kCantTrail`，从 DLL 里反射读出来，保证是真实的表）
每个字符 × 8 种上下文 + 22 字符笛卡尔积；每个下标都测一遍（含 `-1` / `len` / `len+1`
三种越界），`isAsian` 两种取值各跑一轮。合计 23174 用例。
