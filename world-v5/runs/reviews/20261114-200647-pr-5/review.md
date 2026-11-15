# AI review · pr-5 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-5** · Owner: **Md Abdullah Al Noman**

> Merge locked: Security: Safety Blocker(s) found; Tests: Tests failed; Correctness: 1 Blocker(s) Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

This PR implements the Cards module (PR-5), providing debit card issuance and lifecycle management (freeze, unfreeze, cancel) for customer accounts, as well as payment authorisation endpoints for staff/card networks. Payments verify card status, enforce a 2000 transaction limit, and transfer funds to a Suspense account via the ledger on approval.

Requirement alignment: **partial**

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Data/BankDbContext.cs:3-3 | unclear | - | radar failed |
| H02 | src/Bank.Api/Data/BankDbContext.cs:23-23 | unclear | - | radar failed |
| H03 | src/Bank.Api/Modules/Cards/Api/CardsController.cs:1-141 | unclear | - | radar failed |
| H04 | src/Bank.Api/Modules/Cards/Application/CardService.cs:1-182 | unclear | - | radar failed |
| H05 | src/Bank.Api/Modules/Cards/CardsModule.cs:1-12 | unclear | - | radar failed |
| H06 | src/Bank.Api/Modules/Cards/Domain/Card.cs:1-53 | unclear | - | radar failed |
| H07 | src/Bank.Api/Program.cs:5-5 | unclear | - | radar failed |
| H08 | src/Bank.Api/Program.cs:31-31 | unclear | - | radar failed |
| H09 | tests/Bank.Tests/Cards/CardTests.cs:1-372 | unclear | - | radar failed |

## Second opinion on Critical findings (validator panel)

- C01: 1 of 1 reviewers say real → not enough votes
- S01: 1 of 1 reviewers say real → not enough votes

## Investigator

- C01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- S01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten

## Not checked (never counted as passed)

- specialist.tests · Cards · not part of Essential coverage
- specialist.architecture · Cards · not part of Essential coverage
- specialist.maintainability · Cards · not part of Essential coverage
- specialist.performance · Cards · not part of Essential coverage
- validator_panel · Cards · not part of Essential coverage
- investigator · Cards · not part of Essential coverage
- requirement_check · Cards · not part of Essential coverage
- radar · Cards · not part of Essential coverage
- fixer · Cards · not part of Essential coverage
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

Noise funnel: 7 proposed by specialists → 7 with verified evidence (0 hallucinated dropped) → 0 removed by validator → 7 shown (incl. 0 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | HUMAN CHECK | Requirement match is partial: While domain entities, events, and CardService business logic largely match the specification, placing [Authorize(Policy = Policies.Customer)] at the CardsController class level forces Authorise to require both Customer and Staff policies, preventing Staff/network callers from accessing the authorisation endpoint. In addition, the automated test suite failed execution. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Data/BankDbContext.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)<br>src/Bank.Api/Modules/Cards/Api/CardsController.cs: area 'Cards' is high (Card payments and card numbers)<br>src/Bank.Api/Modules/Cards/Api/CardsController.cs: content rule 'authorization attribute changed' matched → high<br>src/Bank.Api/Modules/Cards/Application/CardService.cs: area 'Cards' is high (Card payments and card numbers) |
| Why | VERIFIED | Linked to a requirement |
| Security | BLOCKED | Safety Blocker(s) found<br>S01 src/Bank.Api/Modules/Cards/Api/CardsController.cs:17 |
| Build | VERIFIED | Build succeeded |
| Tests | BLOCKED | Tests failed<br>Failed!  - Failed:     2, Passed:   144, Skipped:     0, Total:   146, Duration: 1 s - Bank.Tests.dll (net10.0) |
| Correctness | BLOCKED | 1 Blocker(s)<br>C01 src/Bank.Api/Modules/Cards/Api/CardsController.cs:17 |
| Architecture | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>A01 src/Bank.Api/Modules/Cards/Application/CardService.cs:27 |
| Maintainability | VERIFIED | No blocking issue |
| Performance | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>P01 src/Bank.Api/Modules/Cards/Application/CardService.cs:27 |
| Impact | VERIFIED | 46 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (7 shown, 0 filtered as noise)

- **[Blocker] C01 · Class-level Customer authorization policy blocks Staff access to Authorise endpoint** (correctness, specialist:correctness · confidence 0.98) `src/Bank.Api/Modules/Cards/Api/CardsController.cs:17`

  CardsController is decorated with [Authorize(Policy = Policies.Customer)] at the class level, while Authorise is decorated with [Authorize(Policy = Policies.Staff)]. In ASP.NET Core, controller- and action-level authorization attributes are evaluated conjunctively (logical AND), so Authorise requires both Customer and Staff policies. Staff or card-network callers lacking the Customer policy will receive HTTP 403 Forbidden.

  ```
  [Authorize(Policy = Policies.Customer)]
  ```

  Requirement: Card payment authorisation (POST api/cards/{id}/authorise, Staff policy): Calls ICardService.AuthoriseAsync(cardId, amount, merchant) with no customer ownership check.

  Suggested fix: Remove [Authorize(Policy = Policies.Customer)] from the CardsController class and place [Authorize(Policy = Policies.Customer)] individually on Issue, Freeze, Unfreeze, and Cancel.

- **[Blocker] S01 · Class-level Customer authorization policy blocks Staff from payment authorisation** (safety, specialist:safety · confidence 0.95) `src/Bank.Api/Modules/Cards/Api/CardsController.cs:17`

  CardsController is decorated with `[Authorize(Policy = Policies.Customer)]` at class level. In ASP.NET Core, action-level Authorize attributes are additive to class-level attributes, requiring callers of `Authorise` to satisfy both Customer and Staff policies simultaneously. Staff callers and card-network callers without Customer credentials will be denied with HTTP 403 Forbidden.

  ```
  [Authorize(Policy = Policies.Customer)]
  public sealed class CardsController : ControllerBase
  ```

  Requirement: Card payment authorisation (POST api/cards/{id}/authorise, Staff policy): Calls ICardService.AuthoriseAsync(cardId, amount, merchant) with no customer ownership check.

  Suggested fix: Remove `[Authorize(Policy = Policies.Customer)]` from the controller class declaration and apply it explicitly to `Issue`, `Freeze`, `Unfreeze`, and `Cancel`, leaving `Authorise` restricted only to `Policies.Staff`.

- **[ShouldFix] A01 · Ad-hoc static in-memory account locking introduces memory leak and ineffective concurrency control** (architecture, specialist:architecture · confidence 0.85) `src/Bank.Api/Modules/Cards/Application/CardService.cs:27`

  CardService introduces a static unbounded ConcurrentDictionary to lock account IDs during payment authorisation. This leaks SemaphoreSlim instances permanently in memory across the process lifecycle and provides no synchronization across multi-instance deployments; ledger operations should rely on database and ledger transactional guarantees.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> AccountLocks = new();
  ```

  Requirement: Authorisation approval rules: When the card is Active, rounded amount is within 2000m, and the account has sufficient funds, funds move strictly via ILedger.PostTransferAsync from card.AccountId to BankAccounts.For(BankAccountKind.Suspense, account.Currency) for the rounded amount.

  Suggested fix: Remove AccountLocks and rely on ILedger.PostTransferAsync and database transactional/concurrency mechanisms to handle transfer concurrency.

- **[ShouldFix] P01 · Static AccountLocks dictionary grows indefinitely, leaking SemaphoreSlim instances** (performance, specialist:performance · confidence 0.85) `src/Bank.Api/Modules/Cards/Application/CardService.cs:27`

  AccountLocks stores a SemaphoreSlim instance for every account processed by AuthoriseAsync in a static ConcurrentDictionary without eviction or cleanup. In a long-running service processing authorisations across many customer accounts, this dictionary grows monotonically and permanently retains SemaphoreSlim objects in memory.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> AccountLocks = new();
  ```

  Suggested fix: Remove in-memory static semaphore locks in favor of database/ledger concurrency controls, or utilize a bounded/evicting lock manager to prevent unbounded memory growth.

- **[ShouldFix] S02 · Debit card numbers generated using cryptographically weak PRNG** (safety, specialist:safety · confidence 0.90) `src/Bank.Api/Modules/Cards/Application/CardService.cs:180`

  Card numbers are sensitive financial identifiers generated using `Random.Shared`. Because `Random.Shared` is a non-cryptographic PRNG, an attacker observing generated card numbers could determine internal PRNG state and predict card numbers issued to other users.

  ```
  private static string GenerateCardNumber() =>
  "4" + Random.Shared.NextInt64(0, 1_000_000_000_000_000L).ToString("D15");
  ```

  Requirement: Creates an Active Card with a generated 16-digit Number annotated with [Pii]

  Suggested fix: Use `System.Security.Cryptography.RandomNumberGenerator.GetInt64(0, 1_000_000_000_000_000L)` instead of `Random.Shared` to generate unpredictable card numbers.

- **[ShouldFix] T01 · CardsController and HTTP endpoints have zero test coverage** (tests, specialist:tests · confidence 0.95) `src/Bank.Api/Modules/Cards/Api/CardsController.cs:15`

  CardsController and its endpoints (Issue, Freeze, Unfreeze, Cancel, Authorise) have no test references. Route handling, status code mappings (e.g., Forbid on UnauthorizedAccessException), authorization policies (Customer vs Staff), and DTO response masking are not verified by tests.

  ```
  [ApiController]
  [Route("api/cards")]
  [Authorize(Policy = Policies.Customer)]
  public sealed class CardsController : ControllerBase
  ```

  Requirement: HTTP: POST api/cards, POST api/cards/{id}/freeze|unfreeze|cancel (Customer policy); POST api/cards/{id}/authorise (Staff policy, stands in for the card network)

  Suggested fix: Add integration or controller tests verifying route mapping, policy enforcement (Customer and Staff policies), DTO responses, and HTTP status codes.

- **[ShouldFix] T02 · Overly broad exception assertion in AuthoriseAsync negative amount test** (tests, specialist:tests · confidence 0.90) `tests/Bank.Tests/Cards/CardTests.cs:253`

  The test asserts ThrowsAnyAsync<Exception> instead of the specific ArgumentOutOfRangeException thrown by CardService. AuthoriseAsync. This allows any unintended failure (such as NullReferenceException or KeyNotFoundException) to pass unnoticed.

  ```
  await Assert.ThrowsAnyAsync<Exception>(() => service.AuthoriseAsync(card.Id, amount, "Merchant"));
  ```

  Requirement: Amounts less than or equal to 0 after rounding are rejected.

  Suggested fix: Replace Assert.ThrowsAnyAsync<Exception> with Assert.ThrowsAsync<ArgumentOutOfRangeException>.

## What the AI refused to decide, and why

- **Root cause of dotnet_test suite failure** (specialist:correctness): The sensor output reports that tests failed (exit 1), but standard error, stack traces, and failure messages from the test runner were not included in the context.
- **dotnet_test failure diagnosis** (specialist:architecture): Deterministic sensor reported 'dotnet_test: Tests failed (exit 1)', but specific test failure logs and stack traces are not provided in the review context.
- **Root cause of test failure** (specialist:safety): The test failure output from `dotnet_test` was not provided in the context, and tests/Bank.Tests/Cards/CardTests.cs is truncated after line 285.
- **Coverage of remaining decline rules in CardTests.cs** (specialist:tests): tests/Bank.Tests/Cards/CardTests.cs is truncated at line 285 (file is 372 lines long), so tests for 'over limit' and 'insufficient funds' decline scenarios cannot be inspected directly from the provided context.
- **Root cause of the automated test failure reported by the test runner** (specialist:maintainability): Test runner output/stack traces are not included in the review context, and tests/Bank.Tests/Cards/CardTests.cs is truncated after line 285.
- **Throughput and latency impact of in-memory account locking under high concurrency** (specialist:performance): Evaluating whether per-account SemaphoreSlim locking introduces unacceptable lock contention or latency bottlenecks under peak card authorisation load requires load testing and benchmark data that cannot be determined from code inspection alone.
- **Noise filtering** (validator): Validator call failed; findings are shown unvalidated.

## What was NOT checked

- Scope vs approved plan (no --plan given)
- Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})
- Part of tests/Bank.Tests/Cards/CardTests.cs (context truncated)

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
- src/Bank.Api/Modules/Cards/Api/CardsController.cs: area 'Cards' is high (Card payments and card numbers)
- src/Bank.Api/Modules/Cards/Api/CardsController.cs: content rule 'authorization attribute changed' matched → high
- src/Bank.Api/Modules/Cards/Application/CardService.cs: area 'Cards' is high (Card payments and card numbers)
- src/Bank.Api/Modules/Cards/CardsModule.cs: area 'Cards' is high (Card payments and card numbers)
- src/Bank.Api/Modules/Cards/Domain/Card.cs: area 'Cards' is high (Card payments and card numbers)
- src/Bank.Api/Program.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)
- Large change (764 lines > 400) → one tier up

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
- Not checked: Scope vs approved plan (no --plan given); Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}); Part of tests/Bank.Tests/Cards/CardTests.cs (context truncated)
- Residual risk I accept: ______________________________
- Signed: ______________________ (owner)   ______________________ (second signer)

---
Run `20261114-200647-pr-5` · 2026-11-14T18:11:50+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 7

Settings: balanced preset · default essential · Full on high-risk · 15 plugins ran · #b5e52429b2df
Model calls: 17 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
