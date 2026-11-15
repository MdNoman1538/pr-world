# AI review · pr-7 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-7** · Owner: **Md Abdullah Al Noman**

> Merge locked: Security: Safety Blocker(s) found; Tests: Tests failed; Correctness: 1 Blocker(s) Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

This pull request implements the Loans module for PR-7, allowing customers to apply for fixed-rate loans with monthly annuity payments and requiring loan officers to independently review, approve, or reject loan applications under four-eyes control. When approved, loan principal is disbursed to the customer's account from the bank's loan funding account in the matching currency via the ledger. The PR also includes entity persistence, module wiring, controller endpoints, and xUnit test coverage.

Requirement alignment: **partial**

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Data/BankDbContext.cs:7-7 | unclear | - | radar failed |
| H02 | src/Bank.Api/Data/BankDbContext.cs:27-27 | unclear | - | radar failed |
| H03 | src/Bank.Api/Modules/Loans/Api/LoansController.cs:1-166 | unclear | - | radar failed |
| H04 | src/Bank.Api/Modules/Loans/Application/LoanService.cs:1-221 | unclear | - | radar failed |
| H05 | src/Bank.Api/Modules/Loans/Domain/Loan.cs:1-53 | unclear | - | radar failed |
| H06 | src/Bank.Api/Modules/Loans/LoansModule.cs:1-12 | unclear | - | radar failed |
| H07 | src/Bank.Api/Program.cs:11-11 | unclear | - | radar failed |
| H08 | src/Bank.Api/Program.cs:35-35 | unclear | - | radar failed |
| H09 | tests/Bank.Tests/Loans/LoanTests.cs:1-314 | unclear | - | radar failed |

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

Noise funnel: 10 proposed by specialists → 10 with verified evidence (0 hallucinated dropped) → 0 removed by validator → 10 shown (incl. 0 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | HUMAN CHECK | Requirement match is partial: The four-eyes validation rule is missing in ILoanService.ApproveAsync: it does not check whether the approving officer is the borrower (loan.CustomerId == officerId), violating a core requirement and causing automated test failures. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Data/BankDbContext.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)<br>src/Bank.Api/Modules/Loans/Api/LoansController.cs: area 'Loans' is high (Credit decisions and payouts)<br>src/Bank.Api/Modules/Loans/Api/LoansController.cs: content rule 'authorization attribute changed' matched → high<br>src/Bank.Api/Modules/Loans/Application/LoanService.cs: area 'Loans' is high (Credit decisions and payouts) |
| Why | VERIFIED | Linked to a requirement |
| Security | BLOCKED | Safety Blocker(s) found<br>S01 src/Bank.Api/Modules/Loans/Application/LoanService.cs:131 |
| Build | VERIFIED | Build succeeded |
| Tests | BLOCKED | Tests failed<br>Failed!  - Failed:     4, Passed:   189, Skipped:     0, Total:   193, Duration: 1 s - Bank.Tests.dll (net10.0) |
| Correctness | BLOCKED | 1 Blocker(s)<br>C01 src/Bank.Api/Modules/Loans/Application/LoanService.cs:128 |
| Architecture | VERIFIED | No blocking issue; 2 ShouldFix noted (does not hold the merge)<br>A01 src/Bank.Api/Modules/Loans/Api/LoansController.cs:29<br>A02 src/Bank.Api/Modules/Loans/Application/LoanService.cs:35 |
| Maintainability | VERIFIED | No blocking issue |
| Performance | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>P01 src/Bank.Api/Modules/Loans/Application/LoanService.cs:35 |
| Impact | VERIFIED | 41 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (10 shown, 0 filtered as noise)

- **[Blocker] C01 · Missing four-eyes check in LoanService.ApproveAsync** (correctness, specialist:correctness · confidence 1.00) `src/Bank.Api/Modules/Loans/Application/LoanService.cs:128`

  ApproveAsync does not verify whether the approving officer is also the applicant (loan.CustomerId == officerId). This allows loan officers to approve their own loans and disburse funds to themselves, violating the four-eyes requirement and causing test failure.

  ```
  loan = await _db.Loans.FirstOrDefaultAsync(l => l.Id == loanId, ct)
  ?? throw new KeyNotFoundException($"Loan {loanId} not found.");
  
  if (loan.Status != LoanStatus.Submitted)
  throw new InvalidOperationException($"Cannot approve loan in status {loan.Status}.");
  ```

  Requirement: POST api/loans/{id}/approve (Policies.LoanOfficer) calls ILoanService.ApproveAsync, which throws KeyNotFoundException if not found, UnauthorizedAccessException if the caller is not in Roles.LoanOfficer or if caller UserId equals Loan.CustomerId (four-eyes check), and InvalidOperationException if Loan.Status is not Submitted.

  Suggested fix: Add `if (loan.CustomerId == officerId) throw new UnauthorizedAccessException("Loan officers cannot approve their own loan.");` immediately after loading the loan.

- **[Blocker] S01 · Missing four-eyes check allows loan officers to approve their own loans** (safety, specialist:safety · confidence 1.00) `src/Bank.Api/Modules/Loans/Application/LoanService.cs:131`

  ApproveAsync does not verify whether loan.CustomerId matches the caller's officerId before disbursing funds. A loan officer with a customer account can approve their own application and trigger unauthorized principal payout.

  ```
  if (loan.Status != LoanStatus.Submitted)
  throw new InvalidOperationException($"Cannot approve loan in status {loan.Status}.");
  
  var account = await _accounts.GetAsync(loan.DisbursementAccountId, ct)
  ```

  Requirement: POST api/loans/{id}/approve (Policies.LoanOfficer) calls ILoanService.ApproveAsync, which throws KeyNotFoundException if not found, UnauthorizedAccessException if the caller is not in Roles.LoanOfficer or if caller UserId equals Loan.CustomerId (four-eyes check), and InvalidOperationException if Loan.Status is not Submitted.

  Suggested fix: Add `if (loan.CustomerId == officerId) throw new UnauthorizedAccessException("Loan officers cannot approve their own loan.");` prior to initiating disbursement.

- **[ShouldFix] A01 · Class-level Customer policy blocks LoanOfficer access to Approve and Reject endpoints** (architecture, specialist:architecture · confidence 0.95 · Capped at Major: a architecture finding is never Critical on its own) `src/Bank.Api/Modules/Loans/Api/LoansController.cs:29`

  In ASP.NET Core, authorization attributes combine additively. Placing [Authorize(Policy = Policies.Customer)] on the controller class forces all actions—including Approve and Reject—to require both Policies.Customer and Policies.LoanOfficer. Loan officers without the Customer role will receive 403 Forbidden, violating the API specification.

  ```
  [ApiController]
  [Route("api/loans")]
  [Authorize(Policy = Policies.Customer)]
  public sealed class LoansController : ControllerBase
  ```

  Requirement: POST api/loans/{id}/approve (Policies.LoanOfficer) calls ILoanService.ApproveAsync, which throws KeyNotFoundException if not found, UnauthorizedAccessException if the caller is not in Roles.LoanOfficer or if caller UserId equals Loan.CustomerId (four-eyes check), and InvalidOperationException if Loan.Status is not Submitted.

  Suggested fix: Remove [Authorize(Policy = Policies.Customer)] from the LoansController class and apply it directly to Apply and Get actions so Approve and Reject only require Policies.LoanOfficer.

- **[ShouldFix] A02 · Static LoanLocks creates an unbounded memory leak and ineffective distributed synchronization** (architecture, specialist:architecture · confidence 0.90) `src/Bank.Api/Modules/Loans/Application/LoanService.cs:35`

  LoanService stores SemaphoreSlim instances in a static ConcurrentDictionary keyed by loanId without any cleanup or eviction, leaking memory over the lifetime of the process. In-memory semaphores also fail to prevent concurrency races across multiple service instances in a distributed deployment.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> LoanLocks = new();
  ```

  Suggested fix: Remove the in-memory SemaphoreSlim dictionary and rely on database transactions and status checks (or a distributed lock if multi-node serialization is required).

- **[ShouldFix] C02 · Class-level Customer policy on LoansController restricts LoanOfficer endpoints** (correctness, specialist:correctness · confidence 0.95) `src/Bank.Api/Modules/Loans/Api/LoansController.cs:31`

  LoansController is decorated with [Authorize(Policy = Policies.Customer)] at the class level. In ASP.NET Core, class-level and action-level authorization attributes combine, requiring callers of Approve and Reject to satisfy both Policies.Customer and Policies.LoanOfficer, which denies loan officers who do not also possess the Customer role.

  ```
  [Authorize(Policy = Policies.Customer)]
  public sealed class LoansController : ControllerBase
  ```

  Requirement: POST api/loans/{id}/approve (Policies.LoanOfficer) calls ILoanService.ApproveAsync

  Suggested fix: Remove [Authorize(Policy = Policies.Customer)] from the controller class and place it specifically on the Apply and Get action methods.

- **[ShouldFix] P01 · Unbounded memory retention in static LoanLocks dictionary** (performance, specialist:performance · confidence 0.90) `src/Bank.Api/Modules/Loans/Application/LoanService.cs:35`

  LoanLocks accumulates a SemaphoreSlim instance for every approved or rejected loan ID in a static ConcurrentDictionary without eviction or disposal. In a running service, this creates an unbounded memory leak as loan volume increases over time.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> LoanLocks = new();
  ```

  Suggested fix: Use database row-level locking or an entity concurrency token instead of an unbounded in-memory static semaphore dictionary, or remove keys when work completes.

- **[ShouldFix] S02 · Unbounded static dictionary for per-loan locks creates memory leak** (safety, specialist:safety · confidence 0.85) `src/Bank.Api/Modules/Loans/Application/LoanService.cs:35`

  LoanLocks statically retains a SemaphoreSlim instance for every processed loanId without eviction or cleanup. In long-running service instances, this causes monotonically increasing memory consumption.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> LoanLocks = new();
  ```

  Requirement: Double disbursement race condition: concurrent approval requests could disburse principal multiple times if the Submitted status transition and persistence are not atomic.

  Suggested fix: Rely on database transactions with concurrency tokens/optimistic concurrency on the Loan entity, or remove entries from LoanLocks when locks are no longer in use.

- **[ShouldFix] T02 · LoansController endpoints and status code translations lack test coverage** (tests, specialist:tests · confidence 0.90) `src/Bank.Api/Modules/Loans/Api/LoansController.cs:32`

  LoansController introduces four HTTP endpoints (POST api/loans, GET api/loans/{id}, POST api/loans/{id}/approve, POST api/loans/{id}/reject), custom JSON body reading, and exception-to-HTTP-status mappings (400, 403, 404, 409). None of these actions or controller behaviors are covered by any unit or integration tests.

  ```
  public sealed class LoansController : ControllerBase
  {
  private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
  
  private readonly ILoanService _loans;
  
  public LoansController(ILoanService loans) => _loans = loans;
  ```

  Requirement: POST api/loans (Policies.Customer) delegates to ILoanService.ApplyAsync using ICurrentUser.UserId as CustomerId and IClock.UtcNow as AppliedAt, ignoring any user id supplied in request bodies.

  Suggested fix: Add controller unit tests or integration tests verifying routing, authorization policy enforcement, status code mappings, and request body deserialization for all four endpoints.

- **[ShouldFix] T03 · Loan domain entity invalid state transitions are not directly tested** (tests, specialist:tests · confidence 0.85) `src/Bank.Api/Modules/Loans/Domain/Loan.cs:30`

  The acceptance criteria requires testing invalid state transitions, and the Loan domain entity defines Approve and Reject methods that validate Status == LoanStatus.Submitted. However, no tests execute Loan.Approve or Loan.Reject directly on the domain model to verify state transition guards independently of LoanService.

  ```
  public void Approve(string officerId, string? note)
  {
  if (Status != LoanStatus.Submitted)
  throw new InvalidOperationException($"Cannot approve loan in status {Status}.");
  Status = LoanStatus.Disbursed;
  DecidedBy = officerId;
  DecisionNote = note;
  }
  ```

  Requirement: Loan entity in Bank.Modules.Loans.Domain owns Status (LoanStatus: Submitted, Rejected, Disbursed) with a private setter, transitions state only via domain methods that validate current status, and includes a parameterless constructor and public settable non-status properties.

  Suggested fix: Add domain unit tests verifying that calling Approve or Reject directly on a Loan instance that is already Disbursed or Rejected throws InvalidOperationException.

- **[ShouldFix] T01 · Annuity rounding test does not test midpoint rounding half-away-from-zero** (tests, specialist:tests · confidence 0.95) `tests/Bank.Tests/Loans/LoanTests.cs:60`

  The test Apply_accepts_inclusive_boundaries_and_rounds_annuity_away_from_zero claims to verify that payments round half-away-from-zero, but none of the test cases calculate a monthly payment ending in a half-cent midpoint (.XX5). For the inputs tested (169.3496..., 858.374..., 542.628...), MidpointRounding.ToEven and MidpointRounding.AwayFromZero produce identical results, so the test would pass even if banker's rounding or default rounding were used.

  ```
  [Theory]
  [InlineData(1000, 6, 169.35)]
  [InlineData(10000, 12, 858.37)]
  [InlineData(50000, 120, 542.63)]
  public async Task Apply_accepts_inclusive_boundaries_and_rounds_annuity_away_from_zero(
  decimal principal, int termMonths, decimal expectedMonthlyPayment)
  ```

  Requirement: ILoanService.ApplyAsync sets AnnualRatePercent to 5.5m and calculates MonthlyPayment using the standard monthly annuity formula P * r / (1 - (1 + r)^(-n)) with monthly rate r = 0.055m / 12m, rounded to 2 decimal places using Math.Round(value, 2, MidpointRounding.AwayFromZero).

  Suggested fix: Add a test case with principal and term values where the third decimal digit of the calculated annuity is exactly 5, ensuring that AwayFromZero rounding behaves differently from default ToEven rounding.

## What the AI refused to decide, and why

- **Distributed concurrency safety across multiple API instances** (specialist:correctness): LoanService uses an in-memory ConcurrentDictionary with SemaphoreSlim for concurrency locking. Whether single-instance or multi-node deployment guarantees are expected for double-disbursement prevention cannot be determined from the shown context.
- **End-to-end HTTP pipeline authorization behavior** (specialist:architecture): The test suite only includes unit tests calling LoanService directly; there are no WebApplicationFactory or integration tests verifying ASP.NET Core authorization middleware handling of the controller attributes.
- **Distributed race condition handling across multiple service replicas** (specialist:safety): In-process SemaphoreSlim only serializes concurrent calls within a single process. Whether multi-node deployments rely on database row locking or distributed locks cannot be determined without cluster deployment configuration and database isolation level settings.
- **Remaining tests in tests/Bank.Tests/Loans/LoanTests.cs after line 267** (specialist:tests): The file slice was truncated at line 267, preventing full inspection of Reject_enforces_role_four_eyes_reason_and_submitted_status and any subsequent test assertions.
- **ASP.NET Core policy and route attribute enforcement at runtime** (specialist:tests): Runtime authorization middleware behavior cannot be verified without WebApplicationFactory or HTTP integration tests, which are not present in the change.
- **Memory retention in static LoanLocks ConcurrentDictionary** (specialist:maintainability): LoanService stores SemaphoreSlim instances in a static ConcurrentDictionary keyed by LoanId without eviction. Determining whether this causes unacceptable memory growth requires a benchmark under production-scale load.
- **Comprehensive dotnet_test failure diagnostics** (specialist:maintainability): The deterministic sensor indicates test suite failure (exit 1), but raw execution logs and stack traces were not provided in the review context.
- **Throughput and database contention during concurrent disbursements** (specialist:performance): Evaluating whether holding an open database transaction across account lookup and ledger posting creates unacceptable lock contention requires workload benchmarking and database configuration details not present in the code context.
- **Noise filtering** (validator): Validator call failed; findings are shown unvalidated.

## What was NOT checked

- Scope vs approved plan (no --plan given)
- Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})
- Part of tests/Bank.Tests/Loans/LoanTests.cs (context truncated)

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
- src/Bank.Api/Modules/Loans/Api/LoansController.cs: area 'Loans' is high (Credit decisions and payouts)
- src/Bank.Api/Modules/Loans/Api/LoansController.cs: content rule 'authorization attribute changed' matched → high
- src/Bank.Api/Modules/Loans/Application/LoanService.cs: area 'Loans' is high (Credit decisions and payouts)
- src/Bank.Api/Modules/Loans/Domain/Loan.cs: area 'Loans' is high (Credit decisions and payouts)
- src/Bank.Api/Modules/Loans/LoansModule.cs: area 'Loans' is high (Credit decisions and payouts)
- src/Bank.Api/Program.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)
- Large change (770 lines > 400) → one tier up

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
- Not checked: Scope vs approved plan (no --plan given); Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}); Part of tests/Bank.Tests/Loans/LoanTests.cs (context truncated)
- Residual risk I accept: ______________________________
- Signed: ______________________ (owner)   ______________________ (second signer)

---
Run `20261114-202124-pr-7` · 2026-11-14T18:24:55+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 7

Settings: balanced preset · default essential · Full on high-risk · 15 plugins ran · #b5e52429b2df
Model calls: 17 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
