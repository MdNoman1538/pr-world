// Cartographer: reads a C# repo with Roslyn and writes world.json (the facts of the world).
// Facts only: every thing and link carries file:line proof. Meaning (descriptions) is added later by AI, separately.
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace Cartographer;

using Obj = System.Collections.Generic.Dictionary<string, object?>;

public static class Program
{
    public static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.Error.WriteLine("usage: Cartographer <repo-root> <out.json> [commit]");
            return 2;
        }
        var world = new World(Path.GetFullPath(args[0]), args.Length > 2 ? args[2] : "");
        world.Build();
        File.WriteAllText(args[1], world.ToJson());
        Console.WriteLine($"cartographer: {world.Nodes.Count} things, {world.Edges.Count} links, {world.Unresolved} unresolved calls -> {args[1]}");
        return 0;
    }
}

public sealed class World
{
    private static readonly string[] GlobalUsings =
    {
        "System", "System.Collections.Generic", "System.IO", "System.Linq", "System.Net.Http", "System.Net.Http.Json",
        "System.Threading", "System.Threading.Tasks", "Microsoft.AspNetCore.Builder", "Microsoft.AspNetCore.Hosting",
        "Microsoft.AspNetCore.Http", "Microsoft.AspNetCore.Routing", "Microsoft.Extensions.Configuration",
        "Microsoft.Extensions.DependencyInjection", "Microsoft.Extensions.Hosting", "Microsoft.Extensions.Logging",
    };
    private static readonly HashSet<string> WriteOps = new() { "Add", "AddAsync", "AddRange", "AddRangeAsync", "Update", "UpdateRange", "Remove", "RemoveRange", "Attach" };
    private static readonly HashSet<string> Verbs = new() { "HttpGet", "HttpPost", "HttpPut", "HttpDelete", "HttpPatch" };

    private readonly string _root;
    private readonly string _commit;
    public readonly List<Obj> Nodes = new();
    public readonly List<Obj> Edges = new();
    private readonly Dictionary<string, Obj> _byId = new();
    private readonly Dictionary<string, Obj> _edgeIdx = new();
    private readonly Dictionary<string, INamedTypeSymbol> _types = new();
    private readonly Obj _flows = new();
    private readonly Obj _dataflow = new();
    private readonly Obj _files = new();
    private readonly Obj _constitutions = new();
    // properties/fields with a default value (settings, limits, rates): code that reads them gets a "uses" link
    private readonly HashSet<string> _defaults = new();
    private readonly Dictionary<string, string> _tables = new();        // DbSet property id -> table id
    private readonly Dictionary<string, string> _entityTable = new();   // entity type id -> table id
    private readonly Dictionary<string, List<string>> _di = new();      // service type display -> impl type ids
    private List<SyntaxTree> _trees = new();
    private CSharpCompilation _comp = null!;
    public int Unresolved;
    private int _dropped;

    public World(string root, string commit)
    {
        _root = root;
        _commit = commit;
    }

    private IEnumerable<SyntaxTree> SourceTrees => _trees.Where(t => t.FilePath != "__globalusings.cs");

    public void Build()
    {
        var sep = Path.DirectorySeparatorChar;
        var files = Directory.EnumerateFiles(_root, "*.cs", SearchOption.AllDirectories)
            .Where(f => !f.Contains($"{sep}bin{sep}") && !f.Contains($"{sep}obj{sep}") && !f.Contains($"{sep}.git{sep}"))
            .OrderBy(f => f, StringComparer.Ordinal).ToList();
        var opts = new CSharpParseOptions(LanguageVersion.Latest);
        foreach (var f in files)
        {
            var rel = Rel(f);
            var text = File.ReadAllText(f);
            _files[rel] = text;
            _trees.Add(CSharpSyntaxTree.ParseText(text, opts, rel));
        }
        _trees.Add(CSharpSyntaxTree.ParseText(string.Join("\n", GlobalUsings.Select(u => $"global using global::{u};")), opts, "__globalusings.cs"));
        foreach (var md in Directory.EnumerateFiles(_root, "CONSTITUTION.md", SearchOption.AllDirectories))
            _constitutions[ModuleOf(Rel(md)).module] = File.ReadAllText(md);

        _comp = CSharpCompilation.Create("World", _trees, References(),
            new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary, nullableContextOptions: NullableContextOptions.Enable));

        foreach (var tree in SourceTrees) DeclareTypes(tree);
        FindTables();
        FindStateMachines();
        FindRegistrations();
        foreach (var tree in SourceTrees) WalkBodies(tree);
        LinkTypes();
        FindEndpoints();
    }

    // ------------------------------------------------------------------ references
    private IEnumerable<MetadataReference> References()
    {
        var paths = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        void Add(string p)
        {
            var n = Path.GetFileNameWithoutExtension(p);
            if (!paths.ContainsKey(n)) paths[n] = p;
        }
        foreach (var p in ((AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES") as string) ?? "").Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
            Add(p);
        try
        {
            // ASP.NET Core shared framework lives next to the runtime this tool runs on: .../shared/Microsoft.AspNetCore.App/<ver>
            var core = Path.GetDirectoryName(typeof(object).Assembly.Location)!;
            var sharedRoot = Path.GetDirectoryName(Path.GetDirectoryName(core)!)!;
            var asp = Path.Combine(sharedRoot, "Microsoft.AspNetCore.App");
            if (Directory.Exists(asp))
            {
                var major = Path.GetFileName(core).Split('.')[0];
                var dirs = Directory.GetDirectories(asp)
                    .OrderByDescending(d => Version.TryParse(Path.GetFileName(d).Split('-')[0], out var v) ? v : new Version(0, 0)).ToList();
                var pick = dirs.FirstOrDefault(d => Path.GetFileName(d).Split('.')[0] == major) ?? dirs.FirstOrDefault();
                if (pick != null) foreach (var p in Directory.GetFiles(pick, "*.dll")) Add(p);
            }
        }
        catch (Exception e)
        {
            Console.Error.WriteLine("cartographer: ASP.NET reference lookup failed: " + e.Message);
        }
        // NuGet assemblies (EF Core, xunit) from the bank's build output
        foreach (var dir in Directory.EnumerateDirectories(_root, "bin", SearchOption.AllDirectories))
            foreach (var p in Directory.EnumerateFiles(dir, "*.dll", SearchOption.AllDirectories))
                if (!Path.GetFileName(p).StartsWith("Bank.")) Add(p);
        var refs = new List<MetadataReference>();
        foreach (var p in paths.Values)
        {
            try { refs.Add(MetadataReference.CreateFromFile(p)); }
            catch { /* not a managed assembly */ }
        }
        return refs;
    }

    // ------------------------------------------------------------------ helpers
    private string Rel(string full) => Path.GetRelativePath(_root, full).Replace('\\', '/');

    private static (string module, string layer) ModuleOf(string rel)
    {
        var p = rel.Split('/');
        var i = Array.IndexOf(p, "Modules");
        if (i >= 0 && i + 1 < p.Length)
            return (p[i + 1], i + 3 < p.Length ? p[i + 2] : (p[^1].EndsWith(".md") ? "Docs" : "Wiring"));
        if (p[0] == "tests") return ("Tests", p.Length > 3 ? p[2] : "Tests");
        if (p[0] == "src" && p.Length > 3) return ("Platform", p[2]);
        return ("Platform", "Host");
    }

    private static string IdOf(ISymbol s)
    {
        var o = s is IMethodSymbol m ? (m.ReducedFrom ?? m).OriginalDefinition : s.OriginalDefinition;
        return o.GetDocumentationCommentId() ?? o.ToDisplayString();
    }

    private static (int, int) Lines(SyntaxNode n)
    {
        var span = n.GetLocation().GetLineSpan();
        return (span.StartLinePosition.Line + 1, span.EndLinePosition.Line + 1);
    }

    private static string Short(string s, int max = 110)
    {
        s = Regex.Replace(s, @"\s+", " ").Trim();
        return s.Length > max ? s[..(max - 1)] + "…" : s;
    }

    private static List<string> AttrNames(SyntaxNode n)
    {
        IEnumerable<AttributeListSyntax> lists = n switch
        {
            MemberDeclarationSyntax m => m.AttributeLists,
            ParameterSyntax p => p.AttributeLists,
            _ => Enumerable.Empty<AttributeListSyntax>(),
        };
        return lists.SelectMany(l => l.Attributes).Select(a =>
        {
            var name = a.Name.ToString().Split('.').Last();
            return name.EndsWith("Attribute") ? name[..^9] : name;
        }).ToList();
    }

    private static string? DocSummary(SyntaxNode n)
    {
        var trivia = n.GetLeadingTrivia().ToFullString();
        var m = Regex.Match(trivia, @"<summary>(.*?)</summary>", RegexOptions.Singleline);
        if (!m.Success) return null;
        var s = Regex.Replace(m.Groups[1].Value, @"<see cref=""(?:[A-Z]:)?([^""]+)""\s*/>", "$1");
        s = Regex.Replace(s, @"///", " ");
        s = Regex.Replace(s, @"<[^>]+>", "");
        return Short(s, 300);
    }

    private static string Vis(ISymbol s) => s.DeclaredAccessibility.ToString().ToLowerInvariant();

    private string EnsureLayer(string module, string layer)
    {
        var mid = "module:" + module;
        if (!_byId.ContainsKey(mid)) AddNode(mid, "module", module, null, module, null, null, 0, 0, new Obj());
        var lid = $"layer:{module}/{layer}";
        if (!_byId.ContainsKey(lid)) AddNode(lid, "layer", layer, mid, module, layer, null, 0, 0, new Obj());
        return lid;
    }

    private Obj AddNode(string id, string kind, string name, string? parent, string module, string? layer, string? file, int line, int endLine, Obj attrs)
    {
        if (_byId.TryGetValue(id, out var existing)) return existing;
        var n = new Obj
        {
            ["id"] = id, ["kind"] = kind, ["name"] = name, ["parent"] = parent, ["module"] = module, ["layer"] = layer,
            ["file"] = file, ["line"] = line, ["end_line"] = endLine, ["attrs"] = attrs,
        };
        Nodes.Add(n);
        _byId[id] = n;
        return n;
    }

    private void AddEdge(string source, string target, string kind, SyntaxNode? at, string certainty = "proven")
    {
        if (source == target) return;
        if (!_byId.ContainsKey(source) || !_byId.ContainsKey(target))
        {
            _dropped++;
            return;
        }
        var key = source + "|" + target + "|" + kind;
        if (_edgeIdx.TryGetValue(key, out var e))
        {
            e["count"] = (int)e["count"]! + 1;
            return;
        }
        var line = at != null ? Lines(at).Item1 : 0;
        e = new Obj
        {
            ["source"] = source, ["target"] = target, ["kind"] = kind, ["file"] = at?.SyntaxTree.FilePath,
            ["line"] = line, ["certainty"] = certainty, ["count"] = 1,
        };
        Edges.Add(e);
        _edgeIdx[key] = e;
    }

    private static Obj AttrsOf(Obj node) => (Obj)node["attrs"]!;

    // ------------------------------------------------------------------ declarations
    private void DeclareTypes(SyntaxTree tree)
    {
        var model = _comp.GetSemanticModel(tree);
        var rel = tree.FilePath;
        var (module, layer) = ModuleOf(rel);
        var isTest = module == "Tests";
        foreach (var decl in tree.GetRoot().DescendantNodes().OfType<BaseTypeDeclarationSyntax>())
        {
            if (model.GetDeclaredSymbol(decl) is not INamedTypeSymbol t) continue;
            var parent = t.ContainingType != null ? IdOf(t.ContainingType) : EnsureLayer(module, layer);
            var typeKind = decl switch
            {
                RecordDeclarationSyntax r => r.ClassOrStructKeyword.IsKind(SyntaxKind.StructKeyword) ? "record struct" : "record",
                InterfaceDeclarationSyntax => "interface",
                EnumDeclarationSyntax => "enum",
                StructDeclarationSyntax => "struct",
                _ => "class",
            };
            var bases = new List<string>();
            if (t.BaseType != null && t.BaseType.SpecialType != SpecialType.System_Object && t.TypeKind == TypeKind.Class)
                bases.Add(t.BaseType.ToDisplayString());
            bases.AddRange(t.Interfaces.Select(i => i.ToDisplayString()));
            var header = Short(decl.WithAttributeLists(default).ToString().Split('{')[0], 160);
            var (l1, l2) = Lines(decl);
            var id = IdOf(t);
            AddNode(id, "type", t.Name, parent, module, layer, rel, l1, l2, new Obj
            {
                ["type_kind"] = typeKind, ["namespace"] = t.ContainingNamespace?.ToDisplayString(), ["visibility"] = Vis(t),
                ["static"] = t.IsStatic, ["sealed"] = t.IsSealed, ["is_test"] = isTest, ["bases"] = bases,
                ["attributes"] = AttrNames(decl), ["is_event"] = t.AllInterfaces.Any(i => i.Name == "IDomainEvent"),
                ["summary"] = DocSummary(decl), ["signature"] = header,
                ["is_controller"] = t.Name.EndsWith("Controller") || AttrNames(decl).Contains("ApiController"),
            });
            _types[id] = t;
            foreach (var m in t.GetMembers()) DeclareMember(m, t, module, layer, rel, isTest);
        }
    }

    private void DeclareMember(ISymbol m, INamedTypeSymbol owner, string module, string layer, string file, bool isTest)
    {
        if (m is INamedTypeSymbol) return;
        if (m.IsImplicitlyDeclared && m is not IPropertySymbol) return;
        var syntaxRef = m.DeclaringSyntaxReferences.FirstOrDefault();
        if (syntaxRef == null) return;
        string kind;
        switch (m)
        {
            case IMethodSymbol { MethodKind: MethodKind.Ordinary }: kind = "method"; break;
            case IMethodSymbol { MethodKind: MethodKind.Constructor }: kind = "ctor"; break;
            case IPropertySymbol: kind = "property"; break;
            case IFieldSymbol: kind = "field"; break;
            default: return;
        }
        var syn = syntaxRef.GetSyntax();
        var declNode = syn is VariableDeclaratorSyntax ? syn.Parent?.Parent ?? syn : syn;   // field -> FieldDeclaration
        var (l1, l2) = Lines(declNode);
        var attrNames = AttrNames(declNode);
        var attrs = new Obj
        {
            ["visibility"] = Vis(m), ["static"] = m.IsStatic, ["is_test"] = isTest, ["attributes"] = attrNames,
            ["summary"] = DocSummary(declNode),
        };
        switch (m)
        {
            case IMethodSymbol ms:
                var ps = ms.Parameters.Select(p => $"{p.Type.ToDisplayString()} {p.Name}").ToList();
                attrs["returns"] = ms.ReturnType.ToDisplayString();
                attrs["async"] = ms.IsAsync;
                attrs["params"] = ps;
                attrs["signature"] = kind == "ctor" ? $"{owner.Name}({string.Join(", ", ps)})" : $"{ms.ReturnType.ToDisplayString()} {ms.Name}({string.Join(", ", ps)})";
                attrs["is_test_case"] = attrNames.Contains("Fact") || attrNames.Contains("Theory");
                break;
            case IPropertySymbol p:
                if (declNode is PropertyDeclarationSyntax { Initializer: { } pin })
                {
                    attrs["initializer"] = Short(pin.Value.ToString());
                    _defaults.Add(IdOf(m));
                }
                attrs["type"] = p.Type.ToDisplayString();
                attrs["pii"] = attrNames.Contains("Pii");
                attrs["setter"] = p.SetMethod == null ? "none" : Vis(p.SetMethod);
                attrs["signature"] = $"{p.Type.ToDisplayString()} {p.Name}";
                break;
            case IFieldSymbol f:
                if (syn is VariableDeclaratorSyntax { Initializer: { } fin } && owner.TypeKind != TypeKind.Enum)
                {
                    attrs["initializer"] = Short(fin.Value.ToString());
                    _defaults.Add(IdOf(m));
                }
                attrs["type"] = f.Type.ToDisplayString();
                attrs["const"] = f.IsConst;
                attrs["readonly"] = f.IsReadOnly;
                attrs["enum_member"] = owner.TypeKind == TypeKind.Enum;
                attrs["signature"] = owner.TypeKind == TypeKind.Enum ? f.Name : $"{f.Type.ToDisplayString()} {f.Name}";
                break;
        }
        AddNode(IdOf(m), kind, kind == "ctor" ? owner.Name : m.Name, IdOf(owner), module, layer, file, l1, l2, attrs);
    }

    // ------------------------------------------------------------------ database
    private void FindTables()
    {
        foreach (var tree in SourceTrees)
        {
            var model = _comp.GetSemanticModel(tree);
            foreach (var prop in tree.GetRoot().DescendantNodes().OfType<PropertyDeclarationSyntax>())
            {
                if (prop.Type is not GenericNameSyntax g || g.Identifier.Text != "DbSet" || g.TypeArgumentList.Arguments.Count != 1) continue;
                if (model.GetDeclaredSymbol(prop) is not IPropertySymbol ps) continue;
                var entity = model.GetTypeInfo(g.TypeArgumentList.Arguments[0]).Type as INamedTypeSymbol;
                var tableId = "table:" + prop.Identifier.Text;
                var layerId = EnsureLayer("Database", "Tables");
                var (l1, l2) = Lines(prop);
                AddNode(tableId, "table", prop.Identifier.Text, layerId, "Database", "Tables", tree.FilePath, l1, l2, new Obj
                {
                    ["entity"] = entity != null ? IdOf(entity) : null,
                    ["entity_name"] = entity?.Name ?? g.TypeArgumentList.Arguments[0].ToString(),
                    ["dbset"] = IdOf(ps),
                });
                _tables[IdOf(ps)] = tableId;
                if (entity == null) continue;
                _entityTable[IdOf(entity)] = tableId;
                AddEdge(IdOf(entity), tableId, "maps", prop);
                foreach (var p in entity.GetMembers().OfType<IPropertySymbol>().Where(p => !p.IsStatic && p.DeclaringSyntaxReferences.Length > 0))
                {
                    var syn = p.DeclaringSyntaxReferences[0].GetSyntax();
                    var (c1, c2) = Lines(syn);
                    var colId = $"{tableId}.{p.Name}";
                    AddNode(colId, "column", p.Name, tableId, "Database", "Tables", syn.SyntaxTree.FilePath, c1, c2, new Obj
                    {
                        ["type"] = p.Type.ToDisplayString(), ["pii"] = AttrNames(syn).Contains("Pii"), ["property"] = IdOf(p),
                    });
                    AddEdge(IdOf(p), colId, "maps", syn);
                }
            }
        }
    }

    // ------------------------------------------------------------------ state machines (convention: static AllowedTransitions + TransitionTo)
    private void FindStateMachines()
    {
        foreach (var tree in SourceTrees)
        {
            var model = _comp.GetSemanticModel(tree);
            foreach (var v in tree.GetRoot().DescendantNodes().OfType<VariableDeclaratorSyntax>().Where(v => v.Identifier.Text == "AllowedTransitions"))
            {
                var init = v.Initializer?.Value;
                if (init == null) continue;
                var owner = model.GetDeclaredSymbol(v)?.ContainingType;
                foreach (var assign in init.DescendantNodes().OfType<AssignmentExpressionSyntax>())
                {
                    if (assign.Left is not ImplicitElementAccessSyntax iea) continue;
                    var fromExpr = iea.ArgumentList.Arguments.FirstOrDefault()?.Expression;
                    if (fromExpr == null || model.GetSymbolInfo(fromExpr).Symbol is not IFieldSymbol from) continue;
                    var fromId = EnsureState(from, owner);
                    foreach (var ma in assign.Right.DescendantNodesAndSelf().OfType<MemberAccessExpressionSyntax>())
                        if (model.GetSymbolInfo(ma).Symbol is IFieldSymbol to && SymbolEqualityComparer.Default.Equals(to.ContainingType, from.ContainingType))
                            AddEdge(fromId, EnsureState(to, owner), "transitions", ma);
                }
            }
        }
    }

    private string EnsureState(IFieldSymbol f, INamedTypeSymbol? owner)
    {
        var id = $"state:{f.ContainingType.Name}.{f.Name}";
        if (_byId.ContainsKey(id)) return id;
        var syn = f.DeclaringSyntaxReferences.FirstOrDefault()?.GetSyntax();
        var (l1, l2) = syn != null ? Lines(syn) : (0, 0);
        var enumId = IdOf(f.ContainingType);
        _byId.TryGetValue(enumId, out var en);
        if (en != null) AttrsOf(en)["state_machine"] = true;
        if (owner != null && _byId.TryGetValue(IdOf(owner), out var ow)) AttrsOf(ow)["states_enum"] = enumId;
        AddNode(id, "state", f.Name, enumId, (en?["module"] as string) ?? "Platform", en?["layer"] as string, syn?.SyntaxTree.FilePath, l1, l2, new Obj
        {
            ["machine"] = f.ContainingType.Name, ["owner"] = owner != null ? IdOf(owner) : null,
            ["initial"] = f.ConstantValue is int i && i == 0,
        });
        return id;
    }

    // ------------------------------------------------------------------ dependency injection registrations
    private void FindRegistrations()
    {
        foreach (var tree in SourceTrees)
        {
            var model = _comp.GetSemanticModel(tree);
            foreach (var inv in tree.GetRoot().DescendantNodes().OfType<InvocationExpressionSyntax>())
            {
                if (inv.Expression is not MemberAccessExpressionSyntax { Name: GenericNameSyntax gn }) continue;
                if (gn.Identifier.Text is not ("AddScoped" or "AddTransient" or "AddSingleton") || gn.TypeArgumentList.Arguments.Count != 2) continue;
                var svc = model.GetTypeInfo(gn.TypeArgumentList.Arguments[0]).Type;
                var impl = model.GetTypeInfo(gn.TypeArgumentList.Arguments[1]).Type;
                if (svc == null || impl == null) continue;
                var key = svc.ToDisplayString();
                if (!_di.TryGetValue(key, out var list)) _di[key] = list = new List<string>();
                list.Add(IdOf(impl));
                if (_byId.TryGetValue(IdOf(impl), out var implNode))
                {
                    var regs = AttrsOf(implNode).TryGetValue("registered_as", out var r) && r is List<string> l ? l : new List<string>();
                    regs.Add($"{gn.Identifier.Text[3..].ToLowerInvariant()} {key}");
                    AttrsOf(implNode)["registered_as"] = regs;
                }
                var wiring = inv.Ancestors().OfType<MethodDeclarationSyntax>().FirstOrDefault();
                if (wiring != null && model.GetDeclaredSymbol(wiring) is { } ws) AddEdge(IdOf(ws), IdOf(impl), "registers", inv);
            }
        }
    }

    // ------------------------------------------------------------------ bodies: calls, events, state triggers, table access, flow, data flow
    private void WalkBodies(SyntaxTree tree)
    {
        var model = _comp.GetSemanticModel(tree);
        foreach (var decl in tree.GetRoot().DescendantNodes().Where(n => n is BaseMethodDeclarationSyntax or PropertyDeclarationSyntax))
        {
            var sym = model.GetDeclaredSymbol(decl);
            if (sym == null) continue;
            var srcId = IdOf(sym);
            if (!_byId.ContainsKey(srcId)) continue;
            SyntaxNode? body = decl switch
            {
                BaseMethodDeclarationSyntax b => (SyntaxNode?)b.Body ?? b.ExpressionBody,
                PropertyDeclarationSyntax p => (SyntaxNode?)p.ExpressionBody ?? p.AccessorList,
                _ => null,
            };
            if (body == null) continue;
            var fx = Effects(body, model, sym);
            foreach (var c in fx.calls) AddEdge(srcId, c.id, "calls", c.at, c.certainty);
            foreach (var e in fx.publishes) AddEdge(srcId, e.id, "publishes", e.at);
            foreach (var s in fx.triggers) AddEdge(srcId, s.id, "triggers", s.at);
            foreach (var t in fx.tables) AddEdge(srcId, t.id, t.write ? "writes" : "reads", t.at);
            foreach (var u in fx.uses) AddEdge(srcId, u.id, "uses", u.at);
            if (decl is BaseMethodDeclarationSyntax)
            {
                _flows[srcId] = body is BlockSyntax block ? Steps(block, model, sym) : new List<object> { StepObj("return", "=> " + Short(body.ToString().TrimStart('=', '>', ' ')), body, model, sym) };
                _dataflow[srcId] = DataFlow(decl, model);
            }
        }
    }

    private sealed record Hit(string id, SyntaxNode at, string certainty = "proven");
    private sealed record TableHit(string id, bool write, SyntaxNode at);

    private (List<Hit> calls, List<Hit> publishes, List<Hit> triggers, List<TableHit> tables, List<Hit> uses) Effects(SyntaxNode scope, SemanticModel model, ISymbol owner)
    {
        var uses = new List<Hit>();
        var calls = new List<Hit>();
        var pubs = new List<Hit>();
        var trig = new List<Hit>();
        var tabs = new List<TableHit>();
        foreach (var inv in scope.DescendantNodesAndSelf().OfType<InvocationExpressionSyntax>())
        {
            var si = model.GetSymbolInfo(inv);
            if ((si.Symbol ?? si.CandidateSymbols.FirstOrDefault()) is not IMethodSymbol target)
            {
                Unresolved++;
                continue;
            }
            var tid = IdOf(target);
            if (_byId.ContainsKey(tid)) calls.Add(new Hit(tid, inv, si.Symbol != null ? "proven" : "candidate"));
            var args = inv.ArgumentList.Arguments;
            if (target.Name == "PublishAsync" && args.Count > 0 && model.GetTypeInfo(args[0].Expression).Type is { } et)
                pubs.Add(new Hit(IdOf(et.OriginalDefinition), inv));
            if (target.Name == "TransitionTo" && args.Count > 0 && model.GetSymbolInfo(args[0].Expression).Symbol is IFieldSymbol { ContainingType.TypeKind: TypeKind.Enum } f)
                trig.Add(new Hit($"state:{f.ContainingType.Name}.{f.Name}", inv));
        }
        // methods like Submit() that call TransitionTo with a constant are triggers too (one level)
        foreach (var name in scope.DescendantNodesAndSelf().OfType<SimpleNameSyntax>())
        {
            var s = model.GetSymbolInfo(name).Symbol;
            if (s is IPropertySymbol or IFieldSymbol && _defaults.Contains(IdOf(s)) && !SymbolEqualityComparer.Default.Equals(s.ContainingType, owner.ContainingType))
                uses.Add(new Hit(IdOf(s), name));
            if (s is IPropertySymbol p && _tables.TryGetValue(IdOf(p), out var tableId))
            {
                var expr = name.Parent is MemberAccessExpressionSyntax ma && ma.Name == name ? (SyntaxNode)ma : name;
                var write = expr.Parent is MemberAccessExpressionSyntax op && op.Expression == expr && WriteOps.Contains(op.Name.Identifier.Text) && op.Parent is InvocationExpressionSyntax;
                tabs.Add(new TableHit(tableId, write, name));
            }
        }
        foreach (var asg in scope.DescendantNodesAndSelf().OfType<AssignmentExpressionSyntax>())
        {
            if (asg.Left is not MemberAccessExpressionSyntax left) continue;
            if (model.GetSymbolInfo(left).Symbol is not IPropertySymbol prop) continue;
            if (SymbolEqualityComparer.Default.Equals(prop.ContainingType, owner.ContainingType)) continue;
            if (_entityTable.TryGetValue(IdOf(prop.ContainingType), out var t)) tabs.Add(new TableHit(t, true, asg));
        }
        return (calls, pubs, trig, tabs, uses);
    }

    private Obj StepObj(string kind, string text, SyntaxNode node, SemanticModel model, ISymbol owner, SyntaxNode? effectsOn = null)
    {
        var fx = Effects(effectsOn ?? node, model, owner);
        return new Obj
        {
            ["kind"] = kind, ["text"] = text, ["line"] = Lines(node).Item1,
            ["calls"] = fx.calls.Select(c => c.id).Distinct().ToList(),
            ["publishes"] = fx.publishes.Select(c => c.id).Distinct().ToList(),
            ["triggers"] = fx.triggers.Select(c => c.id).Distinct().ToList(),
            ["tables"] = fx.tables.Select(t => (t.write ? "writes " : "reads ") + t.id).Distinct().ToList(),
        };
    }

    private List<object> Steps(StatementSyntax s, SemanticModel model, ISymbol owner) =>
        s is BlockSyntax b ? b.Statements.Select(x => (object)Step(x, model, owner)).ToList() : new List<object> { Step(s, model, owner) };

    private Obj Step(StatementSyntax s, SemanticModel model, ISymbol owner)
    {
        switch (s)
        {
            case IfStatementSyntax i:
                var o = StepObj("if", "if (" + Short(i.Condition.ToString(), 90) + ")", i, model, owner, i.Condition);
                o["then"] = Steps(i.Statement, model, owner);
                o["else"] = i.Else != null ? Steps(i.Else.Statement, model, owner) : new List<object>();
                return o;
            case ForEachStatementSyntax fe:
                var f1 = StepObj("loop", $"for each {fe.Identifier.Text} in {Short(fe.Expression.ToString(), 60)}", fe, model, owner, fe.Expression);
                f1["body"] = Steps(fe.Statement, model, owner);
                return f1;
            case ForStatementSyntax fs:
                var f2 = StepObj("loop", "for (" + Short($"{fs.Declaration}; {fs.Condition}; {string.Join(", ", fs.Incrementors)}", 80) + ")", fs, model, owner, (SyntaxNode?)fs.Condition ?? fs);
                f2["body"] = Steps(fs.Statement, model, owner);
                return f2;
            case WhileStatementSyntax ws:
                var f3 = StepObj("loop", "while (" + Short(ws.Condition.ToString(), 80) + ")", ws, model, owner, ws.Condition);
                f3["body"] = Steps(ws.Statement, model, owner);
                return f3;
            case TryStatementSyntax t:
                var tr = StepObj("try", "try", t, model, owner, t.Block.OpenBraceToken.Parent!.ChildNodes().FirstOrDefault() ?? t);
                tr["calls"] = new List<string>();
                tr["publishes"] = new List<string>();
                tr["triggers"] = new List<string>();
                tr["tables"] = new List<string>();
                tr["body"] = Steps(t.Block, model, owner);
                tr["catches"] = t.Catches.Select(c => (object)new Obj
                {
                    ["text"] = "catch " + Short(c.Declaration?.ToString() ?? "", 60), ["line"] = Lines(c).Item1, ["body"] = Steps(c.Block, model, owner),
                }).ToList();
                return tr;
            case UsingStatementSyntax u:
                var us = StepObj("using", "using (" + Short(u.Declaration?.ToString() ?? u.Expression?.ToString() ?? "", 80) + ")", u, model, owner, (SyntaxNode?)u.Declaration ?? u.Expression ?? (SyntaxNode)u);
                us["body"] = Steps(u.Statement, model, owner);
                return us;
            case BlockSyntax b:
                var bl = new Obj { ["kind"] = "block", ["text"] = "{ }", ["line"] = Lines(b).Item1, ["body"] = Steps(b, model, owner) };
                return bl;
            case ReturnStatementSyntax r:
                return StepObj("return", Short(r.ToString()), r, model, owner);
            case ThrowStatementSyntax th:
                return StepObj("throw", Short(th.ToString()), th, model, owner);
            default:
                return StepObj("step", Short(s.ToString()), s, model, owner);
        }
    }

    private List<object> DataFlow(SyntaxNode decl, SemanticModel model)
    {
        var vars = new Dictionary<ISymbol, Obj>(SymbolEqualityComparer.Default);
        Obj Var(ISymbol s, string kind, string type)
        {
            if (!vars.TryGetValue(s, out var v))
                vars[s] = v = new Obj { ["name"] = s.Name, ["kind"] = kind, ["type"] = type, ["writes"] = new List<int>(), ["reads"] = new List<int>() };
            return v;
        }
        void Mark(Obj v, string key, int line)
        {
            var l = (List<int>)v[key]!;
            if (!l.Contains(line)) l.Add(line);
        }
        if (decl is BaseMethodDeclarationSyntax bm)
            foreach (var p in bm.ParameterList.Parameters)
                if (model.GetDeclaredSymbol(p) is IParameterSymbol ps) Mark(Var(ps, "parameter", ps.Type.ToDisplayString()), "writes", Lines(p).Item1);
        foreach (var n in decl.DescendantNodes())
        {
            switch (n)
            {
                case VariableDeclaratorSyntax vd when model.GetDeclaredSymbol(vd) is ILocalSymbol ls:
                    var v = Var(ls, "local", ls.Type.ToDisplayString());
                    if (vd.Initializer != null) Mark(v, "writes", Lines(vd).Item1);
                    break;
                case SingleVariableDesignationSyntax sd when model.GetDeclaredSymbol(sd) is ILocalSymbol ls2:
                    Mark(Var(ls2, "local", ls2.Type.ToDisplayString()), "writes", Lines(sd).Item1);
                    break;
                case ForEachStatementSyntax fe when model.GetDeclaredSymbol(fe) is ILocalSymbol ls3:
                    Mark(Var(ls3, "local", ls3.Type.ToDisplayString()), "writes", Lines(fe).Item1);
                    break;
                case IdentifierNameSyntax id:
                    var s = model.GetSymbolInfo(id).Symbol;
                    Obj? target = s switch
                    {
                        ILocalSymbol l => Var(l, "local", l.Type.ToDisplayString()),
                        IParameterSymbol p => Var(p, "parameter", p.Type.ToDisplayString()),
                        IFieldSymbol f when !f.IsConst && f.ContainingType.TypeKind != TypeKind.Enum => Var(f, f.IsStatic ? "static field" : "field", f.Type.ToDisplayString()),
                        _ => null,
                    };
                    if (target == null) break;
                    SyntaxNode expr = id.Parent is MemberAccessExpressionSyntax ma && ma.Name == id && ma.Expression is ThisExpressionSyntax ? ma : id;
                    var isWrite = expr.Parent switch
                    {
                        AssignmentExpressionSyntax a => a.Left == expr,
                        PostfixUnaryExpressionSyntax => true,
                        PrefixUnaryExpressionSyntax pre => pre.IsKind(SyntaxKind.PreIncrementExpression) || pre.IsKind(SyntaxKind.PreDecrementExpression),
                        ArgumentSyntax arg => !arg.RefKindKeyword.IsKind(SyntaxKind.None) && arg.RefKindKeyword.IsKind(SyntaxKind.OutKeyword),
                        _ => false,
                    };
                    Mark(target, isWrite ? "writes" : "reads", Lines(id).Item1);
                    if (expr.Parent is AssignmentExpressionSyntax ca && ca.Left == expr && !ca.IsKind(SyntaxKind.SimpleAssignmentExpression))
                        Mark(target, "reads", Lines(id).Item1);   // x += y reads x too
                    break;
            }
        }
        return vars.Values.OrderBy(v => ((List<int>)v["writes"]!).Concat((List<int>)v["reads"]!).DefaultIfEmpty(0).Min())
            .Select(v =>
            {
                ((List<int>)v["writes"]!).Sort();
                ((List<int>)v["reads"]!).Sort();
                return (object)v;
            }).ToList();
    }

    // ------------------------------------------------------------------ type relations
    private void LinkTypes()
    {
        foreach (var (id, t) in _types)
        {
            var at = t.DeclaringSyntaxReferences.FirstOrDefault()?.GetSyntax();
            if (t.BaseType != null && t.TypeKind == TypeKind.Class && t.BaseType.SpecialType != SpecialType.System_Object)
                AddEdge(id, IdOf(t.BaseType.OriginalDefinition), "inherits", at);
            foreach (var i in t.Interfaces)
            {
                AddEdge(id, IdOf(i.OriginalDefinition), "implements", at);
                if (i.Name == "IEventHandler" && i.TypeArguments.Length == 1)
                {
                    var handle = t.GetMembers("HandleAsync").FirstOrDefault();
                    AddEdge(handle != null ? IdOf(handle) : id, IdOf(i.TypeArguments[0].OriginalDefinition), "subscribes", at);
                }
            }
            foreach (var iface in t.AllInterfaces)
                foreach (var member in iface.GetMembers().Where(x => x is IMethodSymbol or IPropertySymbol))
                {
                    var impl = t.FindImplementationForInterfaceMember(member);
                    if (impl == null || impl.DeclaringSyntaxReferences.Length == 0) continue;
                    var registered = _di.TryGetValue(iface.ToDisplayString(), out var impls) && impls.Contains(id);
                    AddEdge(IdOf(member), IdOf(impl), "resolves", impl.DeclaringSyntaxReferences[0].GetSyntax(), registered ? "proven" : "resolved");
                }
            foreach (var ctor in t.InstanceConstructors.Where(c => c.DeclaringSyntaxReferences.Length > 0))
                foreach (var p in ctor.Parameters)
                    AddEdge(id, IdOf(p.Type.OriginalDefinition), "injects", ctor.DeclaringSyntaxReferences[0].GetSyntax());
        }
    }

    // ------------------------------------------------------------------ HTTP endpoints + authorization
    private void FindEndpoints()
    {
        foreach (var tree in SourceTrees)
        {
            var model = _comp.GetSemanticModel(tree);
            var (module, layer) = ModuleOf(tree.FilePath);
            foreach (var cls in tree.GetRoot().DescendantNodes().OfType<ClassDeclarationSyntax>())
            {
                if (model.GetDeclaredSymbol(cls) is not INamedTypeSymbol t) continue;
                var baseRoute = AttrArg(cls.AttributeLists, "Route", model) ?? "";
                var classAuth = Auth(cls.AttributeLists, model);
                foreach (var m in cls.Members.OfType<MethodDeclarationSyntax>())
                {
                    if (model.GetDeclaredSymbol(m) is not IMethodSymbol ms) continue;
                    foreach (var a in m.AttributeLists.SelectMany(l => l.Attributes))
                    {
                        var an = a.Name.ToString().Replace("Attribute", "");
                        if (!Verbs.Contains(an)) continue;
                        var verb = an[4..].ToUpperInvariant();
                        var tmpl = a.ArgumentList?.Arguments.FirstOrDefault(x => x.NameEquals == null) is { } arg ? model.GetConstantValue(arg.Expression).Value as string ?? "" : "";
                        var route = "/" + string.Join("/", new[] { baseRoute.Trim('/'), tmpl.Trim('/') }.Where(x => x.Length > 0));
                        var methodAuth = Auth(m.AttributeLists, model);
                        var auth = methodAuth.Contains("anonymous") ? new List<string> { "anonymous" } : classAuth.Concat(methodAuth).Distinct().ToList();
                        var id = $"endpoint:{verb} {route}";
                        var (l1, _) = Lines(a);
                        AddNode(id, "endpoint", $"{verb} {route}", IdOf(t), module, layer, tree.FilePath, l1, l1, new Obj
                        {
                            ["verb"] = verb, ["route"] = route, ["auth"] = auth, ["protected"] = auth.Count > 0 && !auth.Contains("anonymous"),
                            ["handler"] = IdOf(ms),
                        });
                        AddEdge(id, IdOf(ms), "routes", a);
                    }
                }
            }
        }
    }

    private static string? AttrArg(SyntaxList<AttributeListSyntax> lists, string name, SemanticModel model)
    {
        var a = lists.SelectMany(l => l.Attributes).FirstOrDefault(x => x.Name.ToString().Replace("Attribute", "") == name);
        var arg = a?.ArgumentList?.Arguments.FirstOrDefault(x => x.NameEquals == null);
        return arg == null ? null : model.GetConstantValue(arg.Expression).Value as string;
    }

    private static List<string> Auth(SyntaxList<AttributeListSyntax> lists, SemanticModel model)
    {
        var result = new List<string>();
        foreach (var a in lists.SelectMany(l => l.Attributes))
        {
            var n = a.Name.ToString().Replace("Attribute", "");
            if (n == "AllowAnonymous") result.Add("anonymous");
            if (n != "Authorize") continue;
            var any = false;
            foreach (var arg in a.ArgumentList?.Arguments ?? default)
            {
                var value = model.GetConstantValue(arg.Expression).Value as string ?? arg.Expression.ToString();
                var key = arg.NameEquals?.Name.Identifier.Text ?? "Policy";
                result.Add($"{key.ToLowerInvariant()}:{value}");
                any = true;
            }
            if (!any) result.Add("authenticated");
        }
        return result;
    }

    // ------------------------------------------------------------------ output
    public string ToJson()
    {
        var errors = _comp.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error).ToList();
        var doc = new Obj
        {
            ["schema"] = "bank-world/1", ["generated_by"] = "roslyn", ["commit"] = _commit, ["generated_at"] = DateTimeOffset.UtcNow,
            ["nodes"] = Nodes, ["edges"] = Edges, ["flows"] = _flows, ["dataflow"] = _dataflow, ["files"] = _files,
            ["constitutions"] = _constitutions,
            ["stats"] = new Obj
            {
                ["unresolved_calls"] = Unresolved, ["dropped_links"] = _dropped, ["compile_errors"] = errors.Count,
                ["first_errors"] = errors.Take(15).Select(e => e.ToString()).ToList(),
            },
        };
        return JsonSerializer.Serialize(doc);
    }
}
