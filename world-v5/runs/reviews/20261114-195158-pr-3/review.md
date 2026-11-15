# AI review · pr-3 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-3** · Owner: **Md Abdullah Al Noman**

> Merge locked: Tests: Tests failed; Correctness: 1 Blocker(s) Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

PR-3 implements currency exchange support (EUR, SEK, USD) by introducing IFxService and FxService with EUR triangulation and half-away-from-zero rounding. It extends the Payment entity with CreditedAmount, CreditedCurrency, and Rate, and updates PaymentService to support cross-currency transfers routed through FxClearing ledger accounts while converting amounts to EUR for daily transfer limit checks.

Requirement alignment: **partial**

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Modules/Fx/Application/FxService.cs:1-65 | unclear | - | radar failed |
| H02 | src/Bank.Api/Modules/Fx/FxModule.cs:1-12 | unclear | - | radar failed |
| H03 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:4-4 | unclear | - | radar failed |
| H04 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:6-6 | unclear | - | radar failed |
| H05 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:43-43 | unclear | - | radar failed |
| H06 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:53-53 | unclear | - | radar failed |
| H07 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:62-62 | unclear | - | radar failed |
| H08 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:66-77 | unclear | - | radar failed |
| H09 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:97-112 | unclear | - | radar failed |
| H10 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:125-125 | unclear | - | radar failed |
| H11 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:130-130 | unclear | - | radar failed |
| H12 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:133-136 | unclear | - | radar failed |
| H13 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:139-168 | unclear | - | radar failed |
| H14 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:178-180 | unclear | - | radar failed |
| H15 | src/Bank.Api/Modules/Payments/Domain/Payment.cs:25-27 | unclear | - | radar failed |
| H16 | src/Bank.Api/Program.cs:6-6 | unclear | - | radar failed |
| H17 | src/Bank.Api/Program.cs:27-27 | unclear | - | radar failed |
| H18 | tests/Bank.Tests/Fx/FxTests.cs:1-172 | unclear | - | radar failed |

## Second opinion on Critical findings (validator panel)

- C01: 1 of 1 reviewers say real → not enough votes

## Investigator

- C01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten

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

Noise funnel: 5 proposed by specialists → 5 with verified evidence (0 hallucinated dropped) → 0 removed by validator → 6 shown (incl. 1 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | HUMAN CHECK | Requirement match is partial: While the FxService calculations, DI registration, Payment entity properties, and PaymentService cross-currency ledger logic are implemented, the acceptance criteria explicitly require automated xUnit tests covering PaymentService cross-currency flows (including FxClearing transfers and Payment properties) and EUR-equivalent daily transfer limit enforcement. The added test file only tests FxService in isolation and a direct ledger transfer without exercising PaymentService. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Modules/Fx/Application/FxService.cs: area 'Fx' is high (Exchange rates decide how much money customers get)<br>src/Bank.Api/Modules/Fx/FxModule.cs: area 'Fx' is high (Exchange rates decide how much money customers get)<br>src/Bank.Api/Modules/Payments/Application/PaymentService.cs: area 'Payments' is high (Customer money leaves the account)<br>src/Bank.Api/Modules/Payments/Domain/Payment.cs: area 'Payments' is high (Customer money leaves the account) |
| Why | VERIFIED | Linked to a requirement |
| Security | VERIFIED | No secrets, no unverified packages, no safety findings |
| Build | VERIFIED | Build succeeded |
| Tests | BLOCKED | Tests failed<br>Failed!  - Failed:     1, Passed:   116, Skipped:     0, Total:   117, Duration: 1 s - Bank.Tests.dll (net10.0) |
| Correctness | BLOCKED | 1 Blocker(s)<br>C01 tests/Bank.Tests/Fx/FxTests.cs:147 |
| Architecture | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>A01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:66 |
| Maintainability | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>M01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:66 |
| Performance | VERIFIED | No blocking issue |
| Impact | VERIFIED | 21 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (6 shown, 0 filtered as noise)

- **[Blocker] C01 · Missing test coverage for PaymentService cross-currency flows and EUR daily limits** (correctness, specialist:correctness · confidence 0.95) `tests/Bank.Tests/Fx/FxTests.cs:147`

  The acceptance criteria explicitly require automated xUnit tests covering cross-currency PaymentService flows (verifying FxClearing ledger transfers and Payment properties CreditedAmount, CreditedCurrency, Rate) and EUR-equivalent daily transfer limit enforcement. However, FxTests only tests FxService in isolation and directly invokes ILedger without exercising PaymentService.PayAsync or daily transfer limit calculations.

  ```
  [Fact]
  public async Task FxClearing_accounts_exist_for_eur_sek_and_usd_and_settle_cross_currency_ledger_legs()
  {
  using var db = TestKit.Db();
  IFxService fx = new FxService();
  var ledger = TestKit.Ledger(db);
  var aliceEur = TestKit.Account(db, "alice", 100m, "EUR");
  ```

  Requirement: Automated xUnit tests cover FxService (same currency returning 1, EUR/SEK/USD direct and inverse pairs, SEK<->USD triangulation, half-away-from-zero rounding to 2 decimals, ArgumentException on unknown currency), cross-currency PaymentService flows (including FxClearing ledger transfers and Payment properties CreditedAmount, CreditedCurrency, Rate), and EUR-equivalent daily transfer limit enforcement.

  Suggested fix: Add test methods to Bank.Tests that instantiate PaymentService and call PayAsync across currencies to verify: (1) payer debited to FxClearing, (2) payee credited from FxClearing, (3) Payment entity properties CreditedAmount, CreditedCurrency, and Rate, and (4) rejection when daily payments exceed DailyTransferLimit in EUR equivalent.

- **[ShouldFix] A01 · Unrequested PaymentService constructor tightly couples to concrete FxService** (architecture, specialist:architecture · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:66`

  PaymentService adds a redundant 7-parameter constructor overload that directly instantiates 'new FxService()'. This violates YAGNI and dependency inversion principles, and introduces constructor ambiguity for dependency injection containers.

  ```
  public PaymentService(
  BankDbContext db,
  ILedger ledger,
  IAccountService accounts,
  ICurrentUser user,
  IClock clock,
  BankSettings settings,
  IEventBus bus)
  : this(db, ledger, accounts, user, clock, settings, new FxService(), bus)
  {
  ```

  Requirement: PaymentService accepts IFxService as a constructor parameter immediately after BankSettings.

  Suggested fix: Remove the 7-parameter constructor overload so PaymentService relies solely on dependency injection for IFxService.

- **[ShouldFix] D01 · Guard or validation removed** (correctness, sensor:removed_guards) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:97`

  A validation/throw line was removed (old line 81) and not re-added. Repeated AI refinement is known to strip boundary checks.

  ```
  throw new CurrencyMismatchException(fromAccount.Currency, toAccount.Currency);
  ```

  Suggested fix: Confirm the check is no longer needed, or restore it.

- **[ShouldFix] M01 · Redundant constructor tightly couples PaymentService to concrete FxService** (maintainability, specialist:maintainability · confidence 0.85) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:66`

  PaymentService defines an extra constructor overload that instantiates new FxService() directly as a default. This violates dependency inversion by coupling the service directly to the concrete FxService implementation instead of relying on the registered IFxService abstraction from dependency injection.

  ```
  public PaymentService(
  BankDbContext db,
  ILedger ledger,
  IAccountService accounts,
  ICurrentUser user,
  IClock clock,
  BankSettings settings,
  IEventBus bus)
  : this(db, ledger, accounts, user, clock, settings, new FxService(), bus)
  {
  }
  ```

  Requirement: PaymentService accepts IFxService as a constructor parameter immediately after BankSettings.

  Suggested fix: Remove the 7-parameter constructor overload and ensure callers supply IFxService via the 8-parameter constructor.

- **[ShouldFix] T02 · No test coverage for EUR-equivalent daily transfer limit enforcement in PaymentService** (tests, specialist:tests · confidence 0.95 · Capped at Major: a tests finding is never Critical on its own) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:133`

  PaymentService now converts historical same-day payments and the incoming payment request to EUR to validate against DailyTransferLimit. However, no automated tests exist to verify that cross-currency and multi-currency daily payment totals are correctly converted and that DailyLimitExceededException is thrown when the limit is breached.

  ```
  var todayTotalEur = todayPayments.Sum(p => _fx.Convert(p.Amount, p.Currency, "EUR"));
  var requestAmountEur = _fx.Convert(request.Amount, fromAccount.Currency, "EUR");
  
  if (todayTotalEur + requestAmountEur > _settings.DailyTransferLimit)
  throw new DailyLimitExceededException();
  ```

  Requirement: Automated xUnit tests cover FxService (same currency returning 1, EUR/SEK/USD direct and inverse pairs, SEK<->USD triangulation, half-away-from-zero rounding to 2 decimals, ArgumentException on unknown currency), cross-currency PaymentService flows (including FxClearing ledger transfers and Payment properties CreditedAmount, CreditedCurrency, Rate), and EUR-equivalent daily transfer limit enforcement.

  Suggested fix: Add tests for PaymentService.PayAsync that record completed payments in non-EUR currencies and assert that attempting an additional payment that exceeds DailyTransferLimit in EUR equivalent throws DailyLimitExceededException.

- **[ShouldFix] T01 · PaymentService cross-currency payment execution and Payment properties are not tested** (tests, specialist:tests · confidence 0.95 · Capped at Major: a tests finding is never Critical on its own) `tests/Bank.Tests/Fx/FxTests.cs:147`

  Acceptance criterion 12 requires automated test coverage for cross-currency PaymentService flows including FxClearing ledger transfers and Payment properties. The test in FxTests calls ILedger.PostTransferAsync directly instead of calling PaymentService.PayAsync, leaving PaymentService's dual-leg ledger orchestration, cross-currency validations, and Payment entity field mapping completely unexercised.

  ```
  [Fact]
  public async Task FxClearing_accounts_exist_for_eur_sek_and_usd_and_settle_cross_currency_ledger_legs()
  {
  using var db = TestKit.Db();
  IFxService fx = new FxService();
  var ledger = TestKit.Ledger(db);
  ```

  Requirement: Automated xUnit tests cover FxService (same currency returning 1, EUR/SEK/USD direct and inverse pairs, SEK<->USD triangulation, half-away-from-zero rounding to 2 decimals, ArgumentException on unknown currency), cross-currency PaymentService flows (including FxClearing ledger transfers and Payment properties CreditedAmount, CreditedCurrency, Rate), and EUR-equivalent daily transfer limit enforcement.

  Suggested fix: Add unit tests invoking PaymentService.PayAsync across different currencies (e.g. EUR to SEK, SEK to USD) that verify both ledger legs through BankAccounts.For(BankAccountKind.FxClearing, currency) and assert that CreditedAmount, CreditedCurrency, and Rate are correctly assigned and persisted.

## What the AI refused to decide, and why

- **EF Core decimal column precision and database schema mapping** (specialist:correctness): BankDbContext.cs is outside the shown context and was not modified in this PR, so whether EF Core model configuration specifies precision for Rate or CreditedAmount cannot be verified.
- **Database migration and schema upgrade compatibility for existing databases** (specialist:architecture): Program.cs relies on Database.EnsureCreated(), but migration scripts or relational schema management outside the shown context are not available to verify if existing persistence stores will receive the new Payment columns.
- **Dual ledger leg atomicity under partial failures** (specialist:safety): The ILedger implementation is outside the shown context. It cannot be verified whether PostTransferAsync operations participate in the EF Core transaction (lines 120-121) or if an external ledger failure on the second leg could leave funds stranded in FxClearing.
- **Pre-existing test suite failures regarding removed guards** (specialist:tests): Existing test code from prior pull requests that might assert CurrencyMismatchException is not visible in the provided file diffs and is already flagged by deterministic sensors.
- **External caller and test dependencies on the 7-parameter PaymentService constructor** (specialist:maintainability): Existing test files outside of tests/Bank.Tests/Fx/FxTests.cs are not included in the provided code context, so it cannot be confirmed whether other test classes rely on the fallback constructor to compile.
- **Throughput and database round-trip performance of in-memory daily limit evaluation under high payment volumes** (specialist:performance): Evaluating daily limits by pulling all completed daily payments for a customer and converting them in-memory avoids unsupported EF Core SQL translation, but its runtime impact under heavy payment volumes cannot be assessed without load testing and benchmarks.
- **Noise filtering** (validator): Validator call failed; findings are shown unvalidated.

## What was NOT checked

- Scope vs approved plan (no --plan given)
- Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})

## Deterministic sensors

| Sensor | Ran | Result |
| --- | --- | --- |
| secret_scan | yes | pass: No secret patterns in added lines (log: `evidence/secret_scan.txt`) |
| package_check | yes | pass: No package references added (log: `evidence/package_check.txt`) |
| test_integrity | yes | pass: No test files edited (log: `evidence/test_integrity.txt`) |
| removed_guards | yes | FAIL: 1 removed guard line(s) (log: `evidence/removed_guards.txt`) |
| risky_code | yes | pass: 0 pattern hit(s) in added code (log: `evidence/risky_code.txt`) |
| dotnet_build | yes | pass: Build succeeded (log: `evidence/dotnet_build.log`) |
| dotnet_test | yes | FAIL: Tests failed (exit 1) (log: `evidence/dotnet_test.log`) |

## Risk tier reasons (rulebook)

- src/Bank.Api/Modules/Fx/Application/FxService.cs: area 'Fx' is high (Exchange rates decide how much money customers get)
- src/Bank.Api/Modules/Fx/FxModule.cs: area 'Fx' is high (Exchange rates decide how much money customers get)
- src/Bank.Api/Modules/Payments/Application/PaymentService.cs: area 'Payments' is high (Customer money leaves the account)
- src/Bank.Api/Modules/Payments/Domain/Payment.cs: area 'Payments' is high (Customer money leaves the account)
- src/Bank.Api/Program.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)

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

- Checked by AI and tools: Why, Security, Build, Architecture, Maintainability, Performance, Impact
- Must be checked by a human: What, Where
- Not checked: Scope vs approved plan (no --plan given); Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})
- Residual risk I accept: ______________________________
- Signed: ______________________ (owner)   ______________________ (second signer)

---
Run `20261114-195158-pr-3` · 2026-11-14T17:56:08+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 6

Settings: balanced preset · default essential · Full on high-risk · 15 plugins ran · #b5e52429b2df
Model calls: 14 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
