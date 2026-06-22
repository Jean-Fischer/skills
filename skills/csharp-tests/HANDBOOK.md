# C# Test Handbook

## Scope

This handbook contains the fuller test guidance that belongs with the `csharp-tests` skill.
It is intended for C# test code rather than production code.

The source material behind these notes is centered on xUnit and NSubstitute, with the same general style expected for related test code in the repository.

---

## Test framework and libraries

The source guidance says to use **xUnit** together with **NSubstitute** for mocking.
It also lists alternatives:

| Library | Suggested role |
| --- | --- |
| NSubstitute | Preferred default for new projects |
| FakeItEasy | Acceptable alternative |
| Moq | Acceptable only for existing projects, and pinned to a compatible version (4.18.x or 4.20.2+) |

The core emphasis is to test behavior rather than implementation details.

---

## Test naming

The source guidance uses a BDD-style naming pattern.

### Class and file names

Test files should normally follow the class under test, such as `PipelineServiceTests`.

### Method names

The method name pattern is:

`GivenContext_WhenAction_ExpectedResult`

Examples of the style the source calls out:
- `WhenValidRequest_ProcessDataAsync_ReturnsParsedResponse`
- `GivenEmptyInput_ProcessDataAsync_ThrowsArgumentException`

The intent is that the test name itself tells the story of the scenario and outcome.

---

## Test organization

The source guidance recommends:
- fields at the top of the class
- fields sorted alphabetically by name after the underscore prefix
- `readonly` where possible
- the system under test named `_sut`
- utility methods placed after the constructor and before the test methods
- test methods grouped by behavior
- test methods sorted alphabetically within a behavior group
- shared mock setup in the constructor
- scenario-specific setup in the test method itself

A small example of the field-order idea:
- `_httpClient` should appear before `_sut` when the alphabetical order puts it first

---

## Assertions and test style

The source guidance prefers:
- one assertion per test when practical
- related assertions that validate the same behavior are acceptable
- assertions about observable behavior rather than internals
- no verification of logger mocks

It also encourages the use of:
- `[Theory]` with `[InlineData]` for simple parameterized cases
- `[MemberData]` for more complex data sets

The general style is BDD-friendly and favors Arrange / Act / Assert clarity.

---

## Mocking patterns

The source material uses NSubstitute patterns such as:

```csharp
var service = Substitute.For<IDataService>();
var options = Substitute.For<IOptions<Config>>();

service.GetAsync(Arg.Any<int>()).Returns(Task.FromResult(data));
options.Value.Returns(new Config { Endpoint = "https://api.test" });

service.Process(Arg.Is<Request>(r => r.Id > 0)).Returns(result);

await service.Received(1).SaveAsync(Arg.Any<Data>());
service.DidNotReceive().Delete(Arg.Any<int>());
```

General test-double guidance from the source:
- prefer the project’s chosen mocking library
- mock the boundaries that need isolation
- avoid mocking internal logic that ought to be tested directly
- keep interaction checks focused on behavior that matters

---

## Async tests

The source guidance treats async tests carefully.

Use these practices:
- await async calls explicitly
- avoid fire-and-forget logic
- make cancellation behavior explicit when relevant
- keep async setup and teardown clear
- keep timing assumptions to a minimum

---

## Lifecycle and setup

The source recommends `IAsyncLifetime` for per-test setup and cleanup.

Its meaning in the source guidance is:
- `InitializeAsync` runs before each test
- `DisposeAsync` runs after each test

The source also suggests base classes when several test classes share setup logic.

Base class conventions:
- name the shared base `*TestsBase`
- name derived classes in a scenario-oriented style such as `ClassUnderTest_GivenContext` or `ClassUnderTest_WhenAction`
- define reusable fake types once in the base class

---

## Test data

Keep test data small and readable.

Prefer:
- the smallest input that demonstrates the behavior
- explicit data in the test when that is clearer
- simple helper objects over massive fixture blobs

Avoid:
- huge shared fixtures that hide what the test needs
- complicated setup that makes the assertion hard to see
- data that is not directly relevant to the behavior being tested

---

## Stability rules

Tests should be deterministic and isolated.

Be cautious with:
- time-based behavior
- randomness
- filesystem dependencies
- network dependencies
- database state
- shared global state
- order dependence
- exact call-count assertions when they are not essential

If a test is flaky, simplify it before adding more moving parts.

---

## Detailed example

The example below is an original rewrite that shows the same general style as the source: xUnit, NSubstitute, a fake HTTP handler, readable naming, one focused behavior per test, and a simple class under test.

```csharp
public class EndpointDataProcessorTests
{
    private readonly HttpClient _httpClient;
    private readonly TestHttpMessageHandler _httpHandler = new();
    private readonly IOptions<PipelineOptions> _options;
    private readonly EndpointDataProcessor<FakeSource, FakeResult> _sut;

    public EndpointDataProcessorTests()
    {
        _options = Substitute.For<IOptions<PipelineOptions>>();
        _options.Value.Returns(new PipelineOptions { EndpointUri = "https://test.example/api" });

        _httpClient = new HttpClient(_httpHandler);
        _sut = new EndpointDataProcessor<FakeSource, FakeResult>(_options, _httpClient);
    }

    [Fact]
    public async Task WhenValidRequest_ProcessDataAsync_ReturnsParsedResponse()
    {
        // Arrange
        var expected = new FakeResult { Result = "Processed", Score = 0.95 };
        _httpHandler.Response = new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(JsonSerializer.Serialize(expected))
        };

        // Act
        var actual = await _sut.ProcessDataAsync(new FakeSource { Id = 1 }, CancellationToken.None);

        // Assert
        Assert.NotNull(actual);
        Assert.Equivalent(expected, actual);
    }

    [Fact]
    public async Task WhenServerError_ProcessDataAsync_ThrowsHttpRequestException()
    {
        // Arrange
        _httpHandler.Response = new HttpResponseMessage(HttpStatusCode.InternalServerError);

        // Act & Assert
        await Assert.ThrowsAsync<HttpRequestException>(
            () => _sut.ProcessDataAsync(new FakeSource { Id = 1 }, CancellationToken.None));
    }

    public record FakeSource
    {
        public int Id { get; init; }
    }

    public record FakeResult
    {
        public string? Result { get; init; }
        public double Score { get; init; }
    }

    private class TestHttpMessageHandler : HttpMessageHandler
    {
        public HttpResponseMessage Response { get; set; } = new(HttpStatusCode.OK);

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken) => Task.FromResult(Response);
    }
}
```

---

## Practical reminders

When you edit tests, always check whether the repository already has a preferred style for:
- xUnit vs another framework
- NSubstitute vs another mocking library
- method naming
- file naming
- fixture setup patterns
- whether tests should prefer strict or loose interaction checks

If the repository already has a solid style, follow it.
If it does not, the source guidance strongly prefers xUnit and NSubstitute as the default direction.
