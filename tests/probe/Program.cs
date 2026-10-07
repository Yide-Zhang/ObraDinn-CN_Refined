// 断行规则差分测试台。
//
// 用法: WrapProbe <Assembly-CSharp.dll> <结果文件> [<Managed 目录>]
//
// 目的：把「就地改出来的 CanBreakAfter」与「参照 build（css 那版）的 CanBreakAfter」
// 在**真实执行**下逐位比对，而不是只比反编译文本。
//
// 关键设计 —— 被测方法一个字节都不动：
//   CanBreakAfter 唯一的外部依赖是 Lang.loadedLanguage.isAsian。所以只在**探针副本**里
//   做三件事，全都在 Lang 侧：
//     1) Lang..cctor 置空。它要 new Language(...)，而 Language..ctor 里带 Unity 的
//        internal call —— 在 .NET 里直接
//        「SecurityException: ECall methods must be packaged into a system module」。
//     2) isAsian 去掉 initonly，好让外面反射写值。
//     3) get_loadedLanguage 换成 `return Lang.__probeLoaded;`，配合上面 2) 就能精确
//        控制 isAsian ∈ {true, false}（不再需要构造 Language，也就不碰 Unity）。
//   CanBreakAfter / PopLine / kCantStart / kCantTrail 全部保持原样。
//
// 语料包含：手写真实文案 + 两张禁则表里的**每个字符**放进各种上下文 + 小字符集笛卡尔积。
// 结论全部写文件（UTF-8），stdout 只留 ASCII，避开控制台乱码。
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.Serialization;
using System.Text;
using Mono.Cecil;
using Mono.Cecil.Cil;

internal static class WrapProbe
{
    private static string s_managed;

    private static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.Error.WriteLine("用法: WrapProbe <Assembly-CSharp.dll> <结果文件> [<Managed 目录>]");
            return 2;
        }

        var dll = Path.GetFullPath(args[0]);
        var outTxt = Path.GetFullPath(args[1]);
        s_managed = args.Length > 2 ? args[2] : Path.GetDirectoryName(dll);

        // ★ 上一次运行留下的探针副本删不掉：Assembly.LoadFrom 会锁住文件，要等进程退出
        //   才释放，所以下面 finally 里那次删除必然失败。开跑前先扫一遍旧的（此刻已解锁）。
        foreach (var stale in Directory.GetFiles(Path.GetTempPath(), "wrapprobe_*.dll"))
        {
            try { File.Delete(stale); } catch { /* ignore */ }
        }

        var probeDll = Path.Combine(Path.GetTempPath(),
            "wrapprobe_" + Guid.NewGuid().ToString("N") + ".dll");
        try
        {
            BuildProbe(dll, probeDll);
            // 先读进内存再跑：Run 内部用字节加载，跑完文件就能立刻删掉
            var rows = Run(probeDll);
            try { File.Delete(probeDll); } catch { /* ignore */ }
            File.WriteAllLines(outTxt, rows, new UTF8Encoding(false));
            Console.WriteLine("cases=" + rows.Count + " -> " + outTxt);
            return 0;
        }
        finally
        {
            try { if (File.Exists(probeDll)) { File.Delete(probeDll); } } catch { /* ignore */ }
        }
    }

    // ------------------------------------------------------------------ 探针副本
    private static void BuildProbe(string dll, string probeDll)
    {
        var resolver = new DefaultAssemblyResolver();
        var dir = Path.GetDirectoryName(dll);
        if (!string.IsNullOrEmpty(dir)) { resolver.AddSearchDirectory(dir); }
        if (!string.IsNullOrEmpty(s_managed)) { resolver.AddSearchDirectory(s_managed); }

        using (var asm = AssemblyDefinition.ReadAssembly(dll, new ReaderParameters
        {
            ReadSymbols = false,
            InMemory = true,
            AssemblyResolver = resolver,
        }))
        {
            var lang = FindType(asm, "Lang");
            if (lang == null) { throw new InvalidOperationException("找不到 Lang"); }
            var inner = FindNested(lang, "Language");
            if (inner == null) { throw new InvalidOperationException("找不到 Lang/Language"); }

            // (1) Lang..cctor 置空
            var cctor = FindMethod(lang, ".cctor", 0);
            if (cctor != null)
            {
                ResetBody(cctor, 1);
                cctor.Body.GetILProcessor().Append(Instruction.Create(OpCodes.Ret));
            }

            // (2) isAsian 去掉 initonly
            var isAsian = FindField(inner, "isAsian");
            if (isAsian == null) { throw new InvalidOperationException("找不到 Lang/Language::isAsian"); }
            isAsian.Attributes &= ~Mono.Cecil.FieldAttributes.InitOnly;

            // (3) get_loadedLanguage -> return __probeLoaded;
            var fLoaded = new FieldDefinition("__probeLoaded",
                Mono.Cecil.FieldAttributes.Public | Mono.Cecil.FieldAttributes.Static, inner);
            lang.Fields.Add(fLoaded);

            var getter = FindMethod(lang, "get_loadedLanguage", 0);
            if (getter == null) { throw new InvalidOperationException("找不到 Lang.get_loadedLanguage"); }
            ResetBody(getter, 1);
            var il = getter.Body.GetILProcessor();
            il.Append(Instruction.Create(OpCodes.Ldsfld, fLoaded));
            il.Append(Instruction.Create(OpCodes.Ret));

            asm.Write(probeDll, new WriterParameters { WriteSymbols = false });
        }
    }

    // ------------------------------------------------------------------ 跑语料
    private static List<string> Run(string probeDll)
    {
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            var simple = new AssemblyName(e.Name).Name;
            foreach (var cand in new[] { simple + ".dll", "lib" + simple + ".dll" })
            {
                var p = Path.Combine(s_managed, cand);
                if (File.Exists(p)) { return Assembly.LoadFrom(p); }
            }
            return null;
        };

        // ★ 用字节加载而不是 Assembly.LoadFrom：LoadFrom 会**锁住**文件
        //   （Windows 上删不掉），每跑一次就在 %TEMP% 留一个垃圾；字节加载无此副作用。
        var asm = Assembly.Load(File.ReadAllBytes(probeDll));
        var lang = asm.GetType("Lang", true);
        var inner = asm.GetType("Lang+Language", true);
        var fLoaded = lang.GetField("__probeLoaded",
            BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
        var fIsAsian = inner.GetField("isAsian",
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        var tw = asm.GetType("TextWrap", true);
        var canBreak = tw.GetMethod("CanBreakAfter",
            BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
        if (canBreak == null) { throw new InvalidOperationException("找不到 TextWrap.CanBreakAfter"); }

        var fStart = tw.GetField("kCantStart", BindingFlags.Static | BindingFlags.NonPublic);
        var fTrail = tw.GetField("kCantTrail", BindingFlags.Static | BindingFlags.NonPublic);
        var kanji = new List<char>();
        foreach (var o in new[] { fStart.GetValue(null), fTrail.GetValue(null) })
        {
            var en = o as IEnumerable;
            if (en == null) { continue; }
            foreach (var c in en) { kanji.Add((char)c); }
        }

        var corpus = Corpus(kanji);
        var rows = new List<string>();
        foreach (var asian in new[] { true, false })
        {
            var inst = FormatterServices.GetUninitializedObject(inner);
            fIsAsian.SetValue(inst, asian);
            fLoaded.SetValue(null, inst);

            var flag = asian ? 1 : 0;
            foreach (var text in corpus)
            {
                for (var i = -1; i <= text.Length + 1; i++)
                {
                    string r;
                    try
                    {
                        var v = canBreak.Invoke(null, new object[] { text, i });
                        r = v is bool b && b ? "1" : "0";
                    }
                    catch (Exception ex)
                    {
                        // 原版对越界下标会抛 —— 这本身就是我们要修的毛病，如实记下
                        r = "EX:" + ex.GetType().Name;
                    }
                    rows.Add(flag + "\t" + i + "\t" + r + "\t" + Escape(text));
                }
            }
        }
        return rows;
    }

    // ------------------------------------------------------------------ 语料
    private static List<string> Corpus(List<char> kanji)
    {
        var list = new List<string>
        {
            "选 ObraDinn.exe 所在的目录——里面应当有一个 ObraDinn_Data 文件夹。",
            "这是 0.5 秒的测试，well-known 的连字符，以及 A/B 这样的路径。",
            "难度补丁器前端（单文件 HTML，内联 CSS/JS，无外部依赖）。",
            "只允许 font_dir() 下的字体文件，防目录穿越。",
            "刻意安排，不要掉队！",
            "界面字体目录。用的是存档工具同款的两款字体（已子集化）。",
            "A1b2C3 O'Brien don't co-operate e.g. i.e. 3.14 U.S.A. 100%",
            "a - b . c _ d ' e，中-文中.文中",
            "（）【】「」『』，。！？；：",
            "e2e-test patchdll Win64 x86_64 --deps=abc",
        };

        // 1) 两张禁则表里的每个字符 × 各种上下文
        foreach (var c in kanji)
        {
            list.Add("a" + c + "b");
            list.Add("1" + c + "2");
            list.Add("中" + c + "文");
            list.Add("abc" + c + "def");
            list.Add(c + "中文");
            list.Add("中文" + c);
            list.Add("ab" + c + c + "cd");
            list.Add("0" + c + "0");
        }

        // 2) 小字符集笛卡尔积 —— 覆盖「前一个字符 × 后一个字符」的所有组合
        const string small = "abz09-._' 中，。！—…ABC\"";
        foreach (var a in small)
        {
            foreach (var b in small)
            {
                list.Add("x" + a + b + "yz");
            }
        }
        return list;
    }

    // ------------------------------------------------------------------ 小工具
    private static void ResetBody(MethodDefinition m, int maxStack)
    {
        var b = m.Body;
        b.Instructions.Clear();
        b.ExceptionHandlers.Clear();
        b.Variables.Clear();
        b.MaxStackSize = maxStack;
    }

    private static string Escape(string s)
    {
        return s.Replace("\\", "\\\\").Replace("\t", "\\t").Replace("\r", "\\r")
                .Replace("\n", "\\n");
    }

    private static TypeDefinition FindType(AssemblyDefinition asm, string name)
    {
        foreach (var mod in asm.Modules)
        {
            foreach (var t in mod.GetTypes())
            {
                if (t.Name == name || t.FullName == name) { return t; }
            }
        }
        return null;
    }

    private static TypeDefinition FindNested(TypeDefinition outer, string name)
    {
        foreach (var t in outer.NestedTypes)
        {
            if (t.Name == name) { return t; }
        }
        return null;
    }

    private static MethodDefinition FindMethod(TypeDefinition type, string name, int paramCount)
    {
        foreach (var m in type.Methods)
        {
            if (m.Name == name && m.Parameters.Count == paramCount) { return m; }
        }
        return null;
    }

    private static FieldDefinition FindField(TypeDefinition type, string name)
    {
        foreach (var f in type.Fields)
        {
            if (f.Name == name) { return f; }
        }
        return null;
    }
}
