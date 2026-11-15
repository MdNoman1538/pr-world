# AI review · pr-11 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-11** · Owner: **Md Abdullah Al Noman**

> Merge locked: Tests: Tests failed; Correctness: 2 Blocker(s) Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

This pull request configures a composite unique database index on (CustomerId, IdempotencyKey) in EF Core and updates PaymentService.PayAsync to handle duplicate and concurrent payment requests idempotently. The goal is to prevent customers from being double-charged upon retried or concurrent payment submissions as reported in support ticket #4711.

Requirement alignment: **partial**

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Data/BankDbContext.cs:56-57 | unclear | - | radar failed |
| H02 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:1-3 | unclear | - | radar failed |
| H03 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:6-6 | unclear | - | radar failed |
| H04 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:16-16 | unclear | - | radar failed |
| H05 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:46-49 | unclear | - | radar failed |
| H06 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:144-146 | unclear | - | radar failed |
| H07 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:158-158 | unclear | - | radar failed |
| H08 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:164-241 | unclear | - | radar failed |
| H09 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:245-246 | unclear | - | radar failed |
| H10 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:252-252 | unclear | - | radar failed |
| H11 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:258-258 | unclear | - | radar failed |
| H12 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:266-266 | unclear | - | radar failed |
| H13 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:275-275 | unclear | - | radar failed |
| H14 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:280-280 | unclear | - | radar failed |
| H15 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:283-302 | unclear | - | radar failed |
| H16 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:310-310 | unclear | - | radar failed |
| H17 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:322-322 | unclear | - | radar failed |
| H18 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:329-329 | unclear | - | radar failed |
| H19 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:340-340 | unclear | - | radar failed |
| H20 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:344-344 | unclear | - | radar failed |
| H21 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:345-345 | unclear | - | radar failed |
| H22 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:349-349 | unclear | - | radar failed |
| H23 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:351-355 | unclear | - | radar failed |
| H24 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:357-357 | unclear | - | radar failed |
| H25 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:360-364 | unclear | - | radar failed |
| H26 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:366-366 | unclear | - | radar failed |
| H27 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:372-372 | unclear | - | radar failed |
| H28 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:379-390 | unclear | - | radar failed |
| H29 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:398-398 | unclear | - | radar failed |
| H30 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:400-408 | unclear | - | radar failed |
| H31 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:410-410 | unclear | - | radar failed |
| H32 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:413-451 | unclear | - | radar failed |

## Second opinion on Critical findings (validator panel)

- C01: 1 of 1 reviewers say real → not enough votes
- C02: 0 of 1 reviewers say real → not enough votes

## Investigator

- C01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- C02: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten

## Not checked (never counted as passed)

- requirement_check · (all touched) · requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho

Noise funnel: 11 proposed by specialists → 11 with verified evidence (0 hallucinated dropped) → 0 removed by validator → 11 shown (incl. 0 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | HUMAN CHECK | Requirement match is partial: While the composite unique index is configured on BankDbContext and amount rounding is applied, test execution failed (dotnet_test exit 1). The implementation leaves payments in a held status without completing them, and the DbUpdateException handling immediately rethrows when a concurrent transaction has not yet committed. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Data/BankDbContext.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)<br>src/Bank.Api/Modules/Payments/Application/PaymentService.cs: area 'Payments' is high (Customer money leaves the account) |
| Why | VERIFIED | Linked to a requirement |
| Security | HUMAN CHECK | Safety concerns to check<br>S01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:46 |
| Build | VERIFIED | Build succeeded |
| Tests | BLOCKED | Tests failed<br>Failed!  - Failed:     4, Passed:   249, Skipped:     0, Total:   253, Duration: 3 s - Bank.Tests.dll (net10.0) |
| Correctness | BLOCKED | 2 Blocker(s)<br>C01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:298<br>C02 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:368 |
| Architecture | VERIFIED | No blocking issue; 2 ShouldFix noted (does not hold the merge)<br>A02 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:46<br>A01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:400 |
| Maintainability | VERIFIED | No blocking issue; 2 ShouldFix noted (does not hold the merge)<br>M01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:46<br>M02 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:400 |
| Performance | VERIFIED | No blocking issue; 3 ShouldFix noted (does not hold the merge)<br>P01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:46<br>P02 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:226<br>P03 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:232 |
| Impact | VERIFIED | 7 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (11 shown, 0 filtered as noise)

- **[Blocker] C01 · Payment entity is placed on hold and never completed or persisted as successful** (correctness, specialist:correctness · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:298`

  PaymentService calls payment.Hold() before saving the payment entity, but never transitions the payment to completed after the ledger transfers succeed. As a result, the payment remains in a held status in the database and is returned in an incomplete state to callers.

  ```
  payment.Hold();
  
  _db.Payments.Add(payment);
  await _db.SaveChangesAsync(ct);
  ```

  Requirement: When IPaymentService.PayAsync is called sequentially by the same customer with an IdempotencyKey that already exists for that CustomerId, it returns the existing first payment without calling ILedger.PostTransferAsync or moving money again.

  Suggested fix: Remove payment.Hold() or update the payment state to completed and persist the changes after ILedger.PostTransferAsync operations succeed.

- **[Blocker] C02 · Unique constraint exception handler fails to retrieve in-flight payment and throws** (correctness, specialist:correctness · confidence 0.92) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:368`

  When a concurrent request catches a DbUpdateException unique constraint violation, the winning request is still executing ILedger transfers and has not yet committed its transaction. The losing request immediately queries for the existing payment via AsNoTracking, finds null because the winning transaction is uncommitted, and throws an unhandled exception instead of returning the payment.

  ```
  var concurrent = await _db.Payments.AsNoTracking().FirstOrDefaultAsync(
  p => p.CustomerId == customerId && p.IdempotencyKey == request.IdempotencyKey,
  ct);
  if (concurrent is not null)
  return (concurrent, false);
  
  throw;
  ```

  Requirement: When two requests with the same CustomerId and IdempotencyKey execute concurrently, at most one payment record is persisted and ILedger.PostTransferAsync is called at most once (with decimal amount rounded using Math.Round(x, 2, MidpointRounding.AwayFromZero)); the second request handles the database unique constraint violation and returns the existing first payment rather than failing with an unhandled exception.

  Suggested fix: Commit or release the idempotency reservation record before moving to non-transactional ledger transfers, or implement a retry/poll mechanism to wait for the concurrent transaction to commit before querying.

- **[ShouldFix] A02 · Unbounded static semaphore dictionary introduces stateful memory leak in application service** (architecture, specialist:architecture · confidence 0.92) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:46`

  IdempotencyLocks stores a SemaphoreSlim instance for every processed customer and idempotency key without any removal or cache expiration policy. This introduces stateful in-process synchronization that will leak memory over time and does not coordinate across multi-instance API deployments.

  ```
  private static readonly ConcurrentDictionary<string, SemaphoreSlim> IdempotencyLocks = new();
  ```

  Requirement: When two requests with the same CustomerId and IdempotencyKey execute concurrently, at most one payment record is persisted and ILedger.PostTransferAsync is called at most once (with decimal amount rounded using Math.Round(x, 2, MidpointRounding.AwayFromZero)); the second request handles the database unique constraint violation and returns the existing first payment rather than failing with an unhandled exception.

  Suggested fix: Remove the static IdempotencyLocks semaphore map. Let concurrent executions attempt persistence and handle the database unique constraint violation as specified in the acceptance criteria.

- **[ShouldFix] A01 · PaymentService leaks SQLite engine and connection-level locking into application layer** (architecture, specialist:architecture · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:400`

  PaymentService imports Microsoft.Data.Sqlite and implements provider-specific write serialization via GetSqliteWriteLock and SQLite connection tracking. Application services should remain decoupled from underlying database engine implementations and let EF Core and database transactions manage concurrency.

  ```
  private SemaphoreSlim? GetSqliteWriteLock()
  {
  if (!_db.Database.IsRelational() || !_db.Database.IsSqlite() || _db.Database.CurrentTransaction is not null)
  return null;
  ```

  Requirement: When two requests with the same CustomerId and IdempotencyKey execute concurrently, at most one payment record is persisted and ILedger.PostTransferAsync is called at most once (with decimal amount rounded using Math.Round(x, 2, MidpointRounding.AwayFromZero)); the second request handles the database unique constraint violation and returns the existing first payment rather than failing with an unhandled exception.

  Suggested fix: Remove SQLite-specific write locks and connection inspections from PaymentService. Rely on standard EF Core transaction management and DbUpdateException handling.

- **[ShouldFix] C03 · Unbounded static dictionary IdempotencyLocks causes a memory leak** (correctness, specialist:correctness · confidence 0.90) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:46`

  IdempotencyLocks stores a new SemaphoreSlim for every customerId and IdempotencyKey pair and never evicts or removes keys. Under ongoing production traffic, this static collection will grow monotonically and leak memory.

  ```
  private static readonly ConcurrentDictionary<string, SemaphoreSlim> IdempotencyLocks = new();
  ```

  Suggested fix: Remove in-memory static semaphores in favor of database constraint enforcement, or ensure semaphores are removed from the dictionary after execution.

- **[ShouldFix] M01 · Unbounded memory growth in static IdempotencyLocks dictionary** (maintainability, specialist:maintainability · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:46`

  IdempotencyLocks stores a SemaphoreSlim for every unique customer and idempotency key combination but never removes them. In a long-running service, this static dictionary will grow indefinitely and leak memory.

  ```
  private static readonly ConcurrentDictionary<string, SemaphoreSlim> IdempotencyLocks = new();
  ```

  Suggested fix: Remove the semaphore entry when the operation finishes (or when no callers are queued) rather than accumulating entries permanently in a static dictionary.

- **[ShouldFix] M02 · SQLite-specific concurrency workarounds coupled to application service** (maintainability, specialist:maintainability · confidence 0.90) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:400`

  PaymentService inspects low-level database connection properties and maintains static SQLite file/connection locks inside GetSqliteWriteLock. Mixing database provider-specific synchronization into the application domain increases maintenance overhead and breaks separation of concerns.

  ```
  private SemaphoreSlim? GetSqliteWriteLock()
  {
  if (!_db.Database.IsRelational() || !_db.Database.IsSqlite() || _db.Database.CurrentTransaction is not null)
  return null;
  ```

  Suggested fix: Rely on database transaction semantics or isolate database-engine test workarounds outside the core PaymentService.

- **[ShouldFix] P01 · Unbounded static ConcurrentDictionary leaks memory over time** (performance, specialist:performance · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:46`

  The static dictionary `IdempotencyLocks` caches a `SemaphoreSlim` for every processed idempotency key without any removal, TTL, or eviction. In a long-running service processing continuous payment traffic, this causes unbounded memory growth.

  ```
  private static readonly ConcurrentDictionary<string, SemaphoreSlim> IdempotencyLocks = new();
  ```

  Requirement: When two requests with the same CustomerId and IdempotencyKey execute concurrently, at most one payment record is persisted and ILedger.PostTransferAsync is called at most once

  Suggested fix: Clean up entries when processing completes (e.g., via `TryRemove`), or rely on the unique database constraint and transaction isolation rather than an unbounded static dictionary.

- **[ShouldFix] P02 · Redundant duplicate query for existing payment on execution path** (performance, specialist:performance · confidence 0.90) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:226`

  PaymentService queries the database for existing payments with the same CustomerId and IdempotencyKey at lines 173-175 under the lock, and then executes the exact same query again at lines 226-228 inside ExecuteIdempotentPaymentAsync without any intervening state change, introducing redundant database round-trips.

  ```
  var existing = await _db.Payments.AsNoTracking().FirstOrDefaultAsync(
  p => p.CustomerId == customerId && p.IdempotencyKey == request.IdempotencyKey,
  ct);
  ```

  Requirement: When IPaymentService.PayAsync is called sequentially by the same customer with an IdempotencyKey that already exists for that CustomerId, it returns the existing first payment without calling ILedger.PostTransferAsync or moving money again.

  Suggested fix: Eliminate the second query in ExecuteIdempotentPaymentAsync and rely on the result checked immediately beforehand in PayAsync.

- **[ShouldFix] P03 · Consecutive redundant database round-trips reloading account balance** (performance, specialist:performance · confidence 0.88) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:232`

  The method reloads `fromAccount` from the database via ReloadAsync and then immediately queries Accounts a second time for Balance and AllowOverdraft. This creates two consecutive round-trips to read the same account state on every payment.

  ```
  if (_db.Entry(fromAccount).State != EntityState.Detached)
  await _db.Entry(fromAccount).ReloadAsync(ct);
  
  var latestAccount = await _db.Accounts.AsNoTracking()
  .Where(a => a.Id == request.FromAccountId)
  .Select(a => new { a.Balance, a.AllowOverdraft })
  .FirstOrDefaultAsync(ct);
  ```

  Suggested fix: Use either ReloadAsync or the projected AsNoTracking query to inspect the latest account balance, rather than executing both.

- **[ShouldFix] S01 · Unbounded memory growth in static IdempotencyLocks dictionary (Resource Exhaustion)** (safety, specialist:safety · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:46`

  PaymentService registers a SemaphoreSlim in the static dictionary IdempotencyLocks for every distinct customer and idempotency key combination. Because entries are never evicted or removed after the lock is released, untrusted user-supplied idempotency keys accumulate indefinitely, leading to memory exhaustion and denial of service (CWE-400).

  ```
  private static readonly ConcurrentDictionary<string, SemaphoreSlim> IdempotencyLocks = new();
  ```

  Suggested fix: Evict the key from IdempotencyLocks once execution completes, or rely on database-level unique constraints and transactions for concurrency control rather than an unbounded static cache.

## What the AI refused to decide, and why

- **Exact failure details of the failing xUnit test suite** (specialist:correctness): Test output logs and error traces from the failed dotnet_test execution are not provided in the review context.
- **Domain methods on the Payment entity** (specialist:correctness): Payment.cs is outside the shown context, preventing inspection of the internal state machine transitions associated with Hold().
- **Root cause of dotnet_test failure** (specialist:architecture): Test runner output, error stack traces, and test files are not present in the provided context.
- **Reason for automated test suite failure** (specialist:safety): The sensor reported dotnet_test exit 1, but test files and test execution logs are outside the provided context, preventing verification of which assertion failed.
- **Domain status implications of payment.Hold()** (specialist:safety): Payment.cs is outside the shown context, so whether payment.Hold() leaves the entity in an invalid or incomplete state cannot be verified from the diff alone.
- **Automated xUnit test quality and test coverage verification** (specialist:tests): No test files were modified or included in the review context (test files were outside the agent's allowed scope), and all modified production members show zero test references in the code graph, preventing inspection of test assertions, negative scenarios, or isolation.
- **Exact cause of dotnet_test failure** (specialist:maintainability): Test runner output and failure stack traces were not provided in the review context.
- **Deterministic test failure diagnosis** (specialist:performance): Test output, failure stack traces, and test files are not present in the provided context, preventing definitive diagnosis of the failing test.
- **Noise filtering** (validator): Validator call failed; findings are shown unvalidated.

## What was NOT checked

- Scope vs approved plan (no --plan given)
- Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})
- Part of src/Bank.Api/Modules/Payments/Application/PaymentService.cs (context truncated)

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
- src/Bank.Api/Modules/Payments/Application/PaymentService.cs: area 'Payments' is high (Customer money leaves the account)

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
- Must be checked by a human: What, Where, Security
- Not checked: Scope vs approved plan (no --plan given); Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}); Part of src/Bank.Api/Modules/Payments/Application/PaymentService.cs (context truncated)
- Residual risk I accept: ______________________________
- Signed: ______________________ (owner)   ______________________ (second signer)

---
Run `20261114-204439-pr-11` · 2026-11-14T18:49:53+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 2

Settings: balanced preset · default essential · Full on high-risk · 15 plugins ran · #b5e52429b2df
Model calls: 17 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
