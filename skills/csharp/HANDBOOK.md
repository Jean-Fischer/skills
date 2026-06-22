# C# Handbook

## Scope

This handbook records the fuller C# implementation guidance that belongs with the `csharp` skill.
It is meant for production C# code, not test code.

The source material behind these notes targets a modern .NET 10 / C# 14 toolchain.

---

## Project structure

A typical solution layout is:

```text
Solution.sln
Dockerfile
src/
  Project/
    Project.csproj
    Program.cs
  Project.Tests/
    Project.Tests.csproj
```

Key layout rules:
- keep the solution file and `Dockerfile` at the repository root
- place project directories under `src/`
- keep the directory name aligned with the `.csproj` name
- use a `*.Tests` suffix for test projects

Folder organization should grow with the codebase, not ahead of it.
When the repository is still small, a flatter layout is acceptable.
A rough rule of thumb from the source guidance is to keep everything at the root while the project is still very small, and only introduce deeper folders when they improve clarity.

When folders become useful, preferred domain-oriented names include:
- `Application`
- `Domain`
- `Infrastructure`
- `Services`
- `Repositories`
- `Controllers`

---

## Project configuration

### Target frameworks

The source guidance distinguishes these target shapes:

| Target | TFM | Intended use |
| --- | --- | --- |
| Cross-platform | `net10.0` | Console apps, libraries, and web APIs |
| Windows-specific | `net10.0-windows` | Windows desktop or platform-specific apps |
| Mobile/desktop platforms | `net10.0-{platform}` | Platform-specific mobile or desktop builds |

Example project file settings:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
```

The guidance explicitly prefers letting the SDK choose the default language version for the .NET line rather than pinning `LangVersion` manually.
Avoid using `LangVersion=latest` as a habit.

### Implicit usings

The source notes call out the namespaces commonly included by the SDK.

| SDK | Common implicit namespaces |
| --- | --- |
| `Microsoft.NET.Sdk` | `System`, `System.Collections.Generic`, `System.IO`, `System.Linq`, `System.Threading.Tasks` |
| `Microsoft.NET.Sdk.Web` | The base set plus `Microsoft.AspNetCore.*` and `Microsoft.Extensions.*` |

If you need a shared using everywhere, add it explicitly at project level:

```xml
<ItemGroup>
  <Using Include="System.Text.Json" />
</ItemGroup>
```

Use `Directory.Build.props` for shared configuration across a multi-project solution.

---

## Managing projects

Useful `dotnet` commands from the source material:

```bash
dotnet new list
dotnet new xunit -n Project.Tests
dotnet sln add ./src/Project/Project.csproj
dotnet add reference ./src/Shared/Shared.csproj
dotnet add package Newtonsoft.Json --version 13.0.3
dotnet build && dotnet test
```

If the solution already includes a package version you need, reuse that version instead of introducing a different one.

---

## Coding conventions

### Naming

| Element | Convention | Example |
| --- | --- | --- |
| Classes and files | `PascalCase` | `UserService.cs` |
| Interfaces | `IPascalCase` | `IRepository` |
| Methods and properties | `PascalCase` | `ProcessAsync` |
| Fields | `camelCase` | `_logger`, `isActive` |
| Base classes | `PascalCaseBase` | `WidgetBase` |
| Type parameters | `TName` | `TEntity` |

Treat these as the source defaults; local repository conventions can still override them if the codebase already uses a different field style.

### Member ordering

The source guidance orders members as follows:

1. `const`
2. `static readonly`
3. `readonly`
4. instance fields
5. constructors
6. properties
7. methods

Within each group, the recommended access order is:

`public` → `protected` → `private` → `internal`

The suggested keyword order is:

`[access] [static] [readonly] [async] [override|virtual|abstract] [partial]`

### Variables and constructors

Use `var` when the type is obvious from the right-hand side.
Use target-typed `new()` when the left side already declares the type.

```csharp
var service = new UserService();
Dictionary<string, int> lookup = new();
```

Primary constructors are preferred when initialization is straightforward.
Use a regular constructor when validation needs to happen before assignment or when overloads are necessary.

The source also favors modern collection syntax such as collection expressions and spread expressions:

```csharp
int[] numbers = [1, 2, 3];
var extended = [..numbers, 4, 5];
```

Prefer early returns over deeply nested branching.

---

## Code documentation

Public and protected members should carry XML documentation in the source style.

Document with:
- `<see cref="..."/>` for inline references
- `<inheritdoc/>` on implementations and overrides
- `<inheritdoc cref="..."/>` when the default inheritance lookup is not enough
- `<exception cref="...">` when a method can throw in a meaningful way
- `<param>` for every parameter
- `<returns>` for non-void members

A good comment explains intent, contract, or edge cases.
A poor comment just repeats the code.

Interface implementations can often use `<inheritdoc/>` rather than duplicating the same XML.

---

## Namespaces

File-scoped namespaces are preferred.
Keep namespaces aligned with the folder structure.

```csharp
namespace Company.Project.Feature;

public class Example { }
```

---

## Nullable reference types

Enable nullable reference types at project level with `<Nullable>enable</Nullable>`.

Guidance from the source:
- use `?` for nullable types
- use `required` when a property must be set but has no constructor initialization
- use the nullable attributes for more complex cases when needed
- avoid null-forgiving `!` except where there is a good reason

The main situations that justify `!` in the source guidance are:
- framework APIs without proper annotations
- test code that has already established the non-null condition
- cases where a prior guard or validation guarantees non-null

---

## Additional conventions

The source guidance also prefers:
- `Span<T>` and `ReadOnlySpan<T>` for array-style operations when appropriate
- `out var` for `TryGetValue`-style patterns
- `System.Threading.Lock` with `EnterScope()` for synchronization
- omitting explicit types on lambda parameters when the context is clear

---

## Detailed example

The example below is an original rewrite that demonstrates the same conventions: file-scoped namespaces, using aliases, generic types, primary constructors, a lock, the `field` keyword, `required` members, and `inheritdoc`.

```csharp
namespace Contoso.Inventory.Widgets;

using CatalogIndex = Dictionary<string, object>;

/// <summary>Defines behavior for a widget pipeline.</summary>
public interface IWidgetPipeline
{
    Task RunAsync(CancellationToken cancellationToken);
}

/// <summary>Base type for pipelines that process items into collections.</summary>
public abstract class WidgetPipelineBase<TInput, TOutput>(ILogger logger, IReadOnlyList<string> labels)
    where TInput : class
    where TOutput : IEnumerable<TInput>
{
    protected static readonly int DefaultLimit = 10;
    protected readonly ILogger Logger = logger;
    private readonly Lock _gate = new();
    private readonly IReadOnlyList<string> _labels = labels;

    protected int processedCount;

    public IReadOnlyList<string> Labels => _labels;

    public string? LastItemId
    {
        get => field;
        protected set => field = value?.Trim();
    }

    public int Process(TInput item)
    {
        if (item is null) return 0;

        using (_gate.EnterScope())
        {
            var result = Transform(item);
            processedCount += [..result].Count;
            return processedCount;
        }
    }

    protected abstract TOutput Transform(TInput item);
}

/// <summary>Pipeline that stores processed items in a stack.</summary>
public class StackWidgetPipeline<TInput>(ILogger<StackWidgetPipeline<TInput>> logger, IRepository<TInput> repository)
    : WidgetPipelineBase<TInput, Stack<TInput>>(logger, ["first", "second"]), IWidgetPipeline
    where TInput : class
{
    private readonly IRepository<TInput> _repository = repository;

    /// <inheritdoc/>
    public async Task RunAsync(CancellationToken cancellationToken)
    {
        if (cancellationToken.IsCancellationRequested) return;

        var items = await _repository.GetAllAsync(cancellationToken);
        foreach (var item in items)
            Process(item);

        Logger.LogInformation("Processed {Count} items", processedCount);
    }

    /// <inheritdoc/>
    protected override Stack<TInput> Transform(TInput item)
    {
        Stack<TInput> result = new();
        result.Push(item);
        LastItemId = item.GetHashCode().ToString();
        return result;
    }
}
```

---

## Things to keep in mind

These notes come from a modern C# baseline.
If your repository is pinned to older framework versions, keep the underlying principles but adapt the syntax and packages to the version you actually support.

The key ideas remain:
- stay aligned with the repository style
- keep the code readable
- avoid unnecessary layers
- validate changes with build and tests
