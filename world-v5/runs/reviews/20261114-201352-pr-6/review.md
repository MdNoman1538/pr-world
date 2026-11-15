# AI review · pr-6 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-6** · Owner: **Md Abdullah Al Noman**

> Merge locked: Security: Safety Blocker(s) found; Tests: Tests failed; Correctness: 1 Blocker(s) Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

PR-6 introduces the Term Deposits module (open, mature, and early break) for Nordbank. It provides domain entities, application services, and HTTP endpoints allowing customers to lock funds for 3, 6, or 12 months with fixed annual interest, mature deposits with simple interest paid out to their account, or break deposits early to retrieve principal only.

Requirement alignment: **partial**

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Data/BankDbContext.cs:5-5 | unclear | - | radar failed |
| H02 | src/Bank.Api/Data/BankDbContext.cs:25-25 | unclear | - | radar failed |
| H03 | src/Bank.Api/Modules/Deposits/Api/DepositsController.cs:1-115 | unclear | - | radar failed |
| H04 | src/Bank.Api/Modules/Deposits/Application/DepositService.cs:1-238 | unclear | - | radar failed |
| H05 | src/Bank.Api/Modules/Deposits/DepositsModule.cs:1-12 | unclear | - | radar failed |
| H06 | src/Bank.Api/Modules/Deposits/Domain/TermDeposit.cs:1-51 | unclear | - | radar failed |
| H07 | src/Bank.Api/Program.cs:7-7 | unclear | - | radar failed |
| H08 | src/Bank.Api/Program.cs:33-33 | unclear | - | radar failed |
| H09 | tests/Bank.Tests/Deposits/DepositTests.cs:1-333 | unclear | - | radar failed |

## Second opinion on Critical findings (validator panel)

- C01: 1 of 1 reviewers say real → not enough votes
- S01: 1 of 1 reviewers say real → not enough votes

## Investigator

- C01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- S01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten

## Not checked (never counted as passed)

- specialist.tests · Tests · not part of Essential coverage
- specialist.architecture · Tests · not part of Essential coverage
- specialist.maintainability · Tests · not part of Essential coverage
- specialist.performance · Tests · not part of Essential coverage
- validator_panel · Tests · not part of Essential coverage
- investigator · Tests · not part of Essential coverage
- requirement_check · Tests · not part of Essential coverage
- radar · Tests · not part of Essential coverage
- fixer · Tests · not part of Essential coverage
- requirement_check · (all touched) · requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho

Noise funnel: 9 proposed by specialists → 9 with verified evidence (0 hallucinated dropped) → 0 removed by validator → 9 shown (incl. 0 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | HUMAN CHECK | Requirement match is partial: While domain logic and service layer operations align well with the specification, the HTTP controller applies Policies.Customer at the class level. In ASP.NET Core, class-level authorization applies conjunctively with action-level authorization, preventing Staff users from calling the Staff-only POST api/deposits/{id}/mature endpoint unless they also have Customer credentials. This also explains test failures on staff maturity enforcement. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Data/BankDbContext.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)<br>src/Bank.Api/Modules/Deposits/Api/DepositsController.cs: area 'Deposits' is medium (Savings and interest)<br>src/Bank.Api/Modules/Deposits/Api/DepositsController.cs: content rule 'authorization attribute changed' matched → high<br>src/Bank.Api/Modules/Deposits/Application/DepositService.cs: area 'Deposits' is medium (Savings and interest) |
| Why | VERIFIED | Linked to a requirement |
| Security | BLOCKED | Safety Blocker(s) found<br>S01 src/Bank.Api/Modules/Deposits/Api/DepositsController.cs:26 |
| Build | VERIFIED | Build succeeded |
| Tests | BLOCKED | Tests failed<br>Failed!  - Failed:     2, Passed:   171, Skipped:     0, Total:   173, Duration: 1 s - Bank.Tests.dll (net10.0) |
| Correctness | BLOCKED | 1 Blocker(s)<br>C01 src/Bank.Api/Modules/Deposits/Api/DepositsController.cs:26 |
| Architecture | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>A01 src/Bank.Api/Modules/Deposits/Api/DepositsController.cs:26 |
| Maintainability | VERIFIED | No blocking issue |
| Performance | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>P01 src/Bank.Api/Modules/Deposits/Application/DepositService.cs:24 |
| Impact | VERIFIED | 39 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (9 shown, 0 filtered as noise)

- **[Blocker] C01 · Controller-level Customer policy prevents Staff from calling mature endpoint** (correctness, specialist:correctness · confidence 0.98) `src/Bank.Api/Modules/Deposits/Api/DepositsController.cs:26`

  DepositsController is annotated with [Authorize(Policy = Policies.Customer)] at the class level, which ASP.NET Core applies conjunctively with the action-level [Authorize(Policy = Policies.Staff)] on the Mature endpoint. Consequently, Staff users who do not have the Customer role receive a 403 Forbidden response when attempting to mature deposits.

  ```
  [Authorize(Policy = Policies.Customer)]
  ```

  Requirement: Maturing a deposit via POST api/deposits/{id}/mature (Policies.Staff) or IDepositService.MatureAsync performs no owner check and throws InvalidOperationException if the deposit is not Open or if clock.UtcNow < MaturesAt.

  Suggested fix: Remove [Authorize(Policy = Policies.Customer)] from the DepositsController class declaration. The Open and Break endpoints already declare [Authorize(Policy = Policies.Customer)] on their respective actions.

- **[Blocker] S01 · Controller-level Customer policy blocks Staff access to Mature endpoint** (safety, specialist:safety · confidence 0.95) `src/Bank.Api/Modules/Deposits/Api/DepositsController.cs:26`

  In ASP.NET Core, [Authorize] attributes are evaluated additively across class and action levels. Because DepositsController is decorated with [Authorize(Policy = Policies.Customer)], the Mature action decorated with [Authorize(Policy = Policies.Staff)] requires callers to satisfy both policies, returning HTTP 403 Forbidden to staff accounts and preventing staff execution.

  ```
  [Authorize(Policy = Policies.Customer)]
  ```

  Requirement: Maturing a deposit via POST api/deposits/{id}/mature (Policies.Staff) or IDepositService.MatureAsync performs no owner check and throws InvalidOperationException if the deposit is not Open or if clock.UtcNow < MaturesAt.

  Suggested fix: Remove [Authorize(Policy = Policies.Customer)] from the class declaration (or replace it with [Authorize] without policy), as Open, Mature, and Break already specify their respective Customer and Staff policies on each action method.

- **[ShouldFix] A01 · Controller-level Customer authorization policy blocks Staff from mature endpoint** (architecture, specialist:architecture · confidence 0.95 · Capped at Major: a architecture finding is never Critical on its own) `src/Bank.Api/Modules/Deposits/Api/DepositsController.cs:26`

  In ASP.NET Core, authorization attributes combine additively. Because `[Authorize(Policy = Policies.Customer)]` is declared on DepositsController, the `Mature` action requires both `Policies.Customer` and `Policies.Staff`, which prevents pure Staff users from maturing deposits.

  ```
  [Authorize(Policy = Policies.Customer)]
  ```

  Requirement: Maturing a deposit via POST api/deposits/{id}/mature (Policies.Staff) or IDepositService.MatureAsync performs no owner check and throws InvalidOperationException if the deposit is not Open or if clock.UtcNow < MaturesAt.

  Suggested fix: Remove `[Authorize(Policy = Policies.Customer)]` from the controller class level (or replace with bare `[Authorize]`), keeping explicit policy checks on individual actions (`Open` and `Break` already specify `Policies.Customer`).

- **[ShouldFix] C02 · Unbounded memory growth in DepositLocks ConcurrentDictionary** (correctness, specialist:correctness · confidence 0.90) `src/Bank.Api/Modules/Deposits/Application/DepositService.cs:24`

  DepositLocks stores a SemaphoreSlim for each deposit ID processed in MatureAsync and BreakAsync but never removes entries. Over the lifetime of the application, this static collection will grow unbounded as term deposits are matured or broken.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> DepositLocks = new();
  ```

  Suggested fix: Clean up unused semaphores using TryRemove once the lock is released and no other threads are waiting, or use a size-bounded eviction cache.

- **[ShouldFix] P01 · Unbounded memory accumulation in static DepositLocks dictionary** (performance, specialist:performance · confidence 0.95) `src/Bank.Api/Modules/Deposits/Application/DepositService.cs:24`

  DepositLocks stores a SemaphoreSlim instance for every deposit ID passed to MatureAsync or BreakAsync without an eviction or cleanup mechanism. Because entries are added before confirming whether the deposit exists and are never pruned, this results in continuous memory growth over time and creates a potential resource exhaustion vector.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> DepositLocks = new();
  ```

  Suggested fix: Use keyed lock striping or a size-bounded/sliding cache with eviction, or rely on database-level row locking / concurrency tokens rather than an unbounded static dictionary.

- **[ShouldFix] S02 · Static DepositLocks dictionary leaks memory over time** (safety, specialist:safety · confidence 0.85) `src/Bank.Api/Modules/Deposits/Application/DepositService.cs:24`

  DepositService allocates a SemaphoreSlim for each deposit ID into a static ConcurrentDictionary that is never pruned. Every deposit that is matured or broken leaves an entry in memory indefinitely, causing unbounded resource consumption over the application's lifetime.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> DepositLocks = new();
  ```

  Requirement: Double-payout or race condition: concurrent MatureAsync and BreakAsync calls (or repeated calls) on the same Open deposit could pay out principal or interest twice if state transitions and persistence are not strictly guarded.

  Suggested fix: Rely on database transaction concurrency control (such as concurrency tokens or row versioning) rather than an unbounded in-memory static dictionary, or evict lock entries once transitions complete.

- **[ShouldFix] T02 · DepositsController endpoints and authorization policies have zero test coverage** (tests, specialist:tests · confidence 0.90) `src/Bank.Api/Modules/Deposits/Api/DepositsController.cs:26`

  DepositsController defines endpoints with class-level Policies.Customer and action-level Policies.Staff, but has zero test references across the test suite. The combination of class-level Customer policy with action-level Staff policy on Mature risks rejecting Staff callers unless explicitly verified by tests.

  ```
  [Authorize(Policy = Policies.Customer)]
  public sealed class DepositsController : ControllerBase
  ```

  Requirement: Maturing a deposit via POST api/deposits/{id}/mature (Policies.Staff) or IDepositService.MatureAsync performs no owner check and throws InvalidOperationException if the deposit is not Open or if clock.UtcNow < MaturesAt.

  Suggested fix: Add controller tests covering Open, Mature, and Break endpoints and verify the correct policies and status codes.

- **[ShouldFix] T03 · No test coverage for non-EUR multi-currency deposit lifecycle** (tests, specialist:tests · confidence 0.85) `tests/Bank.Tests/Deposits/DepositTests.cs:33`

  All test fixtures hardcode EUR accounts and verify ledger balances only in EUR. The requirement highlights multi-currency ledger routing to DepositHolding and InterestExpense as an operational risk, but non-EUR flows are unexercised.

  ```
  var accountId = TestKit.Account(db, "alice", 1000m, "EUR");
  ```

  Requirement: OpenAsync derives CustomerId from ICurrentUser.UserId and Currency from the source account, transfers principal from accountId to BankAccounts.For(BankAccountKind.DepositHolding, currency) via ILedger.PostTransferAsync

  Suggested fix: Add a test scenario creating and maturing a deposit with a non-EUR account (such as USD) to verify multi-currency holding and expense account routing.

- **[ShouldFix] T01 · Staff-only maturity enforcement required by acceptance criteria is not tested** (tests, specialist:tests · confidence 0.95 · Capped at Major: a tests finding is never Critical on its own) `tests/Bank.Tests/Deposits/DepositTests.cs:185`

  The acceptance criteria mandate automated xUnit tests verifying Staff-only maturity enforcement. Existing tests only invoke IDepositService.MatureAsync directly using a caller that still has the Customer role, without asserting that non-Staff callers are rejected.

  ```
  public async Task Mature_succeeds_without_owner_check_when_called_by_different_user()
  ```

  Requirement: Automated xUnit tests verify: 3/6/12-month rate mapping and interest rounding half away from zero, principal < 500 and invalid term rejection, owner enforcement on open and break, Staff-only maturity enforcement, rejection of premature maturity, rejection of breaking or maturing an already closed deposit, and ledger balances across Customer, DepositHolding, and InterestExpense accounts.

  Suggested fix: Add an integration or controller test verifying that POST api/deposits/{id}/mature permits Staff callers and returns Forbid or Unauthorized for Customer callers.

## What the AI refused to decide, and why

- **Exact dotnet_test failure details** (specialist:correctness): Test runner output and stack traces were not provided in the review context; the failure can only be inferred from code analysis of the requirement tests.
- **Reason for dotnet_test failure** (specialist:architecture): The test execution logs and failure stack traces are omitted from the deterministic sensor results, and tests/Bank.Tests/Deposits/DepositTests.cs is truncated in the AST slice context.
- **Exact failure reason for dotnet_test runner failure** (specialist:safety): The sensor reported exit code 1 without including test execution logs, failure traces, or names of failing tests, and the test suite file in the context is truncated.
- **Test assertions beyond line 291 of DepositTests.cs** (specialist:tests): The file tests/Bank.Tests/Deposits/DepositTests.cs was truncated after line 291 in the context, preventing verification of whether rejection of breaking an already broken deposit is covered.
- **Root cause of dotnet_test execution failure** (specialist:tests): The deterministic test runner reported exit code 1 without including runner standard output or stack traces.
- **Root cause of test suite failure (dotnet_test exit 1)** (specialist:maintainability): Deterministic sensors report that dotnet_test failed, but the exact test execution failure logs are not provided in the context, and DepositTests.cs is truncated in the AST slice.
- **Throughput and latency under high concurrency** (specialist:performance): Lock contention on DepositLocks and database transaction throughput cannot be conclusively evaluated without load test benchmarks.
- **Root cause of deterministic sensor test failure** (specialist:performance): The test execution console output was not provided in the review context, and the test file was truncated.
- **Noise filtering** (validator): Validator call failed; findings are shown unvalidated.

## What was NOT checked

- Scope vs approved plan (no --plan given)
- Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})
- Part of tests/Bank.Tests/Deposits/DepositTests.cs (context truncated)

## Deterministic sensors

| Sensor | Ran | Result |
| --- | --- | --- |
| secret_scan | yes | pass: No secret patterns in added lines (log: `evidence/secret_scan.txt`) |
| package_check | yes | pass: No package references added (log: `evidence/package_check.txt`) |
| test_integrity | yes | pass: No test files edited (log: `evidence/test_integrity.txt`) |
| removed_guards | yes | pass: No validation/guard lines removed (log: `evidence/removed_guards.txt`) |
| risky_code | yes | pass: 0 pattern hit(s) in added code (log: `evidence/risky_code.txt`) |
| dotnet_build | yes | pass: Build succeeded (log: `evidence/dotnet_build.log`) |
| dotnet_test | yes | FAIL: Tests failed (exit 1) (log: `evidence/dotnet_test.log`) |

## Risk tier reasons (rulebook)

- src/Bank.Api/Data/BankDbContext.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)
- src/Bank.Api/Modules/Deposits/Api/DepositsController.cs: area 'Deposits' is medium (Savings and interest)
- src/Bank.Api/Modules/Deposits/Api/DepositsController.cs: content rule 'authorization attribute changed' matched → high
- src/Bank.Api/Modules/Deposits/Application/DepositService.cs: area 'Deposits' is medium (Savings and interest)
- src/Bank.Api/Modules/Deposits/DepositsModule.cs: area 'Deposits' is medium (Savings and interest)
- src/Bank.Api/Modules/Deposits/Domain/TermDeposit.cs: area 'Deposits' is medium (Savings and interest)
- src/Bank.Api/Program.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)
- Large change (753 lines > 400) → one tier up

## Reviewer track record (from human feedback)

| Dimension | Accepted | Rejected | Escapes | Precision | Trust |
| --- | --- | --- | --- | --- | --- |
| architecture | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| correctness | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| maintainability | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| performance | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| safety | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| tests | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |

## Sign-off (to be completed by the named owner)

- Checked by AI and tools: Why, Build, Architecture, Maintainability, Performance, Impact
- Must be checked by a human: What, Where
- Not checked: Scope vs approved plan (no --plan given); Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}); Part of tests/Bank.Tests/Deposits/DepositTests.cs (context truncated)
- Residual risk I accept: ______________________________
- Signed: ______________________ (owner)   ______________________ (second signer)

---
Run `20261114-201352-pr-6` · 2026-11-14T18:18:30+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 7

Settings: balanced preset · default essential · Full on high-risk · 15 plugins ran · #b5e52429b2df
Model calls: 17 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
