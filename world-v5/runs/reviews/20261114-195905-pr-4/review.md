# AI review · pr-4 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-4** · Owner: **Md Abdullah Al Noman**

> Merge locked: Tests: Tests failed; Correctness: 2 Blocker(s) Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

This PR implements PR-4 by introducing the Fees module (IFeeCalculator/FeeCalculator), adding the GET api/payments/quote endpoint, and integrating fee calculation and FeeIncome ledger posting into PaymentService. It aims to provide pre-payment fee and exchange rate quotes and charge the applicable cross-currency fee from the payer upon payment execution.

Requirement alignment: **partial**

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Modules/Fees/Application/Fee.cs:1-3 | unclear | - | radar failed |
| H02 | src/Bank.Api/Modules/Fees/Application/FeeCalculator.cs:1-33 | unclear | - | radar failed |
| H03 | src/Bank.Api/Modules/Fees/Application/IFeeCalculator.cs:1-6 | unclear | - | radar failed |
| H04 | src/Bank.Api/Modules/Fees/FeesModule.cs:1-12 | unclear | - | radar failed |
| H05 | src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:21-24 | unclear | - | radar failed |
| H06 | src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:40-66 | unclear | - | radar failed |
| H07 | src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:109-112 | unclear | - | radar failed |
| H08 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:4-4 | unclear | - | radar failed |
| H09 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:19-20 | unclear | - | radar failed |
| H10 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:34-34 | unclear | - | radar failed |
| H11 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:48-48 | unclear | - | radar failed |
| H12 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:59-59 | unclear | - | radar failed |
| H13 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:69-69 | unclear | - | radar failed |
| H14 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:73-85 | unclear | - | radar failed |
| H15 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:98-127 | unclear | - | radar failed |
| H16 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:139-139 | unclear | - | radar failed |
| H17 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:142-143 | unclear | - | radar failed |
| H18 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:163-164 | unclear | - | radar failed |
| H19 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:190-192 | unclear | - | radar failed |
| H20 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:224-234 | unclear | - | radar failed |
| H21 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:243-243 | unclear | - | radar failed |
| H22 | src/Bank.Api/Modules/Payments/Domain/Payment.cs:25-25 | unclear | - | radar failed |
| H23 | src/Bank.Api/Program.cs:6-6 | unclear | - | radar failed |
| H24 | src/Bank.Api/Program.cs:29-29 | unclear | - | radar failed |
| H25 | tests/Bank.Tests/Fees/FeeTests.cs:1-62 | unclear | - | radar failed |

## Second opinion on Critical findings (validator panel)

- C01: 0 of 1 reviewers say real → not enough votes
- C02: 0 of 1 reviewers say real → not enough votes

## Investigator

- C01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- C02: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten

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

Noise funnel: 8 proposed by specialists → 8 with verified evidence (0 hallucinated dropped) → 0 removed by validator → 8 shown (incl. 0 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | HUMAN CHECK | Requirement match is partial: While the core Fees module and quote API structure are implemented, PaymentService.QuoteAsync fails to round CreditedAmount as required, and the balance check before payment execution bypasses accounts that allow overdraft instead of strictly verifying that balance >= amount + fee. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Modules/Fees/Application/Fee.cs: area 'Fees' is high (What the bank charges customers)<br>src/Bank.Api/Modules/Fees/Application/FeeCalculator.cs: area 'Fees' is high (What the bank charges customers)<br>src/Bank.Api/Modules/Fees/Application/IFeeCalculator.cs: area 'Fees' is high (What the bank charges customers)<br>src/Bank.Api/Modules/Fees/FeesModule.cs: area 'Fees' is high (What the bank charges customers) |
| Why | VERIFIED | Linked to a requirement |
| Security | VERIFIED | No secrets, no unverified packages, no safety findings |
| Build | VERIFIED | Build succeeded |
| Tests | BLOCKED | Tests failed<br>Failed!  - Failed:     2, Passed:   121, Skipped:     0, Total:   123, Duration: 1 s - Bank.Tests.dll (net10.0) |
| Correctness | BLOCKED | 2 Blocker(s)<br>C01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:114<br>C02 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:190 |
| Architecture | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>A01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:73 |
| Maintainability | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>M01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:73 |
| Performance | VERIFIED | No blocking issue |
| Impact | VERIFIED | 14 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (8 shown, 0 filtered as noise)

- **[Blocker] C01 · PaymentService.QuoteAsync returns unrounded CreditedAmount** (correctness, specialist:correctness · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:114`

  The requirement specifies that Quote/QuoteAsync must return a rounded CreditedAmount. In QuoteAsync, cross-currency creditedAmount is assigned the raw output of _fx.Convert without rounding to 2 decimal places using MidpointRounding.AwayFromZero.

  ```
  var creditedAmount = sameCurrency
  ? amount
  : _fx.Convert(amount, fromAccount.Currency, toAccount.Currency);
  ```

  Requirement: PaymentQuote(decimal Amount, string Currency, decimal Fee, decimal CreditedAmount, string CreditedCurrency, decimal Rate) is added to Bank.Modules.Payments.Application, and IPaymentService exposes Quote / QuoteAsync(Guid fromAccountId, Guid toAccountId, decimal amount) returning the fee, FX rate (1m for same-currency), and rounded CreditedAmount without modifying balances or persisting a Payment.

  Suggested fix: Round the converted amount to two decimal places: var creditedAmount = sameCurrency ? amount : Math.Round(_fx.Convert(amount, fromAccount.Currency, toAccount.Currency), 2, MidpointRounding.AwayFromZero);

- **[Blocker] C02 · Payer balance validation bypasses accounts where AllowOverdraft is true** (correctness, specialist:correctness · confidence 0.90) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:190`

  PaymentService.PayAsync checks !fromAccount.AllowOverdraft before verifying balance < request.Amount + fee.Amount. If AllowOverdraft is true, the check is skipped, allowing payments when balance < amount + fee contrary to acceptance criteria.

  ```
  if (!fromAccount.AllowOverdraft && fromAccount.Balance < request.Amount + fee.Amount)
  throw new InsufficientFundsException(request.FromAccountId);
  ```

  Requirement: When executing a payment, PaymentService checks that the payer account balance is at least amount + fee before posting any ledger transfers; if balance < amount + fee, the payment fails with insufficient funds, no Payment is completed, and zero transfers are posted to either the recipient, FxClearing, or FeeIncome.

  Suggested fix: Remove !fromAccount.AllowOverdraft and check balance unconditionally: if (fromAccount.Balance < request.Amount + fee.Amount) throw new InsufficientFundsException(request.FromAccountId);

- **[ShouldFix] A01 · Redundant constructor tightly couples PaymentService to concrete FeeCalculator** (architecture, specialist:architecture · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:73`

  PaymentService defines an unrequested constructor overload that directly instantiates new FeeCalculator(fx). This bypasses dependency injection and tightly couples the Payments module directly to a concrete class in the Fees module rather than depending solely on the IFeeCalculator abstraction.

  ```
  public PaymentService(
  BankDbContext db,
  ILedger ledger,
  IAccountService accounts,
  ICurrentUser user,
  IClock clock,
  BankSettings settings,
  IFxService fx,
  IEventBus bus)
  : this(db, ledger, accounts, user, clock, settings, fx, new FeeCalculator(fx), bus)
  {
  }
  ```

  Requirement: Payment entity adds a decimal Fee property persisted in BankDbContext, and PaymentService accepts IFeeCalculator in its constructor immediately after IFxService.

  Suggested fix: Remove the overloaded 8-parameter constructor in PaymentService and require IFeeCalculator to be supplied via the primary 9-parameter constructor.

- **[ShouldFix] C03 · Redundant constructor tightly couples PaymentService to concrete FeeCalculator** (correctness, specialist:correctness · confidence 0.85) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:73`

  An unrequested 8-parameter PaymentService constructor instantiates concrete FeeCalculator directly via new FeeCalculator(fx). This bypasses DI abstraction and introduces redundant constructor overloads.

  ```
  public PaymentService(
  BankDbContext db,
  ILedger ledger,
  IAccountService accounts,
  ICurrentUser user,
  IClock clock,
  BankSettings settings,
  IFxService fx,
  IEventBus bus)
  : this(db, ledger, accounts, user, clock, settings, fx, new FeeCalculator(fx), bus)
  {
  }
  ```

  Requirement: Payment entity adds a decimal Fee property persisted in BankDbContext, and PaymentService accepts IFeeCalculator in its constructor immediately after IFxService.

  Suggested fix: Remove the redundant 8-parameter constructor and let DI resolve IFeeCalculator through the primary 9-parameter constructor.

- **[ShouldFix] M01 · Redundant constructor tightly couples PaymentService to concrete FeeCalculator** (maintainability, specialist:maintainability · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:73`

  PaymentService introduces an overloaded constructor that directly instantiates 'new FeeCalculator(fx)'. This bypasses dependency injection and tightly couples the service to a concrete implementation, contradicting the requirement to inject IFeeCalculator.

  ```
  public PaymentService(
  BankDbContext db,
  ILedger ledger,
  IAccountService accounts,
  ICurrentUser user,
  IClock clock,
  BankSettings settings,
  IFxService fx,
  IEventBus bus)
  : this(db, ledger, accounts, user, clock, settings, fx, new FeeCalculator(fx), bus)
  {
  }
  ```

  Requirement: Payment entity adds a decimal Fee property persisted in BankDbContext, and PaymentService accepts IFeeCalculator in its constructor immediately after IFxService.

  Suggested fix: Remove the 8-parameter constructor that instantiates new FeeCalculator(fx) and ensure callers supply IFeeCalculator via the primary 9-parameter constructor.

- **[ShouldFix] T03 · Insufficient funds check covering amount plus fee and fee transfer posting are untested** (tests, specialist:tests · confidence 0.90) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:190`

  PaymentService.PayAsync checks that balance >= amount + fee and posts a fee transfer to FeeIncome on cross-currency payments, but no tests verify that payments fail when balance covers amount but not amount + fee, or that FeeIncome is credited upon success.

  ```
  if (!fromAccount.AllowOverdraft && fromAccount.Balance < request.Amount + fee.Amount)
  throw new InsufficientFundsException(request.FromAccountId);
  ```

  Requirement: When executing a payment, PaymentService checks that the payer account balance is at least amount + fee before posting any ledger transfers; if balance < amount + fee, the payment fails with insufficient funds, no Payment is completed, and zero transfers are posted to either the recipient, FxClearing, or FeeIncome.

  Suggested fix: Add test cases in payment test suite verifying that a payment fails with InsufficientFundsException when balance < amount + fee, and that fee transfer to FeeIncome is executed when successful.

- **[ShouldFix] T01 · FeeCalculator calculation and clamping logic has no test coverage** (tests, specialist:tests · confidence 0.95) `tests/Bank.Tests/Fees/FeeTests.cs:24`

  FeeTests only asserts on a manually created Fee record rather than invoking FeeCalculator.Quote. Core business rules—including 0.2% fee calculation, EUR 0.50 min and EUR 20.00 max FX conversion and clamping, rounding AwayFromZero, same-currency 0 fees, and non-positive amount rejection—are completely untested.

  ```
  public void Fee_record_allows_zero_fee_for_same_currency()
  {
  var fee = new Fee(0m, "SEK");
  
  Assert.Equal(0m, fee.Amount);
  Assert.Equal("SEK", fee.Currency);
  }
  ```

  Requirement: IFeeCalculator.Quote(amount, fromCurrency, toCurrency) returns Fee(0m, fromCurrency) when fromCurrency equals toCurrency (case-insensitive).

  Suggested fix: Add unit tests exercising FeeCalculator.Quote with a mock or real IFxService to verify same-currency zero fee, cross-currency fee calculation, min/max clamping, rounding, and negative/zero amount validation.

- **[ShouldFix] T02 · QuoteAsync and quote endpoint behavior are not tested** (tests, specialist:tests · confidence 0.90) `tests/Bank.Tests/Fees/FeeTests.cs:33`

  PaymentQuote_record_preserves_all_fields_and_value_equality tests only record constructor properties rather than IPaymentService.QuoteAsync or PaymentsController.Quote. Behavior such as caller account ownership checks, 404 on missing account, currency rate lookups, and non-persistence of quotes is unverified.

  ```
  public void PaymentQuote_record_preserves_all_fields_and_value_equality()
  {
  var quote = new PaymentQuote(1000m, "EUR", 2.00m, 11400.00m, "SEK", 11.40m);
  var same = new PaymentQuote(1000m, "EUR", 2.00m, 11400.00m, "SEK", 11.40m);
  
  Assert.Equal(1000m, quote.Amount);
  Assert.Equal("EUR", quote.Currency);
  Assert.Equal(2.00m, quote.Fee);
  Assert.Equal(11400.00m, quote.CreditedAmount);
  Assert.Equal("SEK", quote.CreditedCurrency);
  Assert.Equal(11.40m, quote.Rate);
  Assert.Equal(quote, same);
  }
  ```

  Requirement: PaymentQuote(decimal Amount, string Currency, decimal Fee, decimal CreditedAmount, string CreditedCurrency, decimal Rate) is added to Bank.Modules.Payments.Application, and IPaymentService exposes Quote / QuoteAsync(Guid fromAccountId, Guid toAccountId, decimal amount) returning the fee, FX rate (1m for same-currency), and rounded CreditedAmount without modifying balances or persisting a Payment.

  Suggested fix: Add unit and integration tests covering PaymentService.QuoteAsync and GET api/payments/quote for valid quotes, non-owner 403, and missing account 404 responses.

## What the AI refused to decide, and why

- **Root cause of dotnet_test failure** (specialist:correctness): The deterministic sensors report that dotnet_test failed (exit 1), but the test output, stack trace, and failing test names are not included in the provided review context.
- **Reason for dotnet_test test failure** (specialist:architecture): Test output logs and failing test assertions are not provided in the review context.
- **Deterministic test run failure** (specialist:safety): dotnet_test failed with exit code 1, but test execution logs, failure stack traces, and test implementations outside FeeTests.cs are not provided in the review context.
- **dotnet_test execution failure cause** (specialist:tests): The test execution failure is reported in the sensor summary (exit 1), but standard error/output logs and failing test names are omitted from the review context.
- **CreditedAmount rounding behavior in QuoteAsync** (specialist:maintainability): The implementation relies on IFxService.Convert to calculate CreditedAmount, but the concrete implementation of IFxService is outside the provided diff context, so whether CreditedAmount is rounded to 2 decimal places cannot be verified.
- **Transaction locking duration and ledger throughput under concurrent load** (specialist:performance): Evaluating whether holding an EF Core database transaction across three sequential ledger transfers (source debit, clearing credit/debit, and fee transfer) creates connection pool or lock contention requires load testing and database benchmarks not present in static context.
- **Deterministic test failure investigation** (specialist:performance): Test output logs and error traces are not included in the review context, preventing analysis of the failing unit test.
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
| removed_guards | yes | pass: No validation/guard lines removed (log: `evidence/removed_guards.txt`) |
| risky_code | yes | pass: 0 pattern hit(s) in added code (log: `evidence/risky_code.txt`) |
| dotnet_build | yes | pass: Build succeeded (log: `evidence/dotnet_build.log`) |
| dotnet_test | yes | FAIL: Tests failed (exit 1) (log: `evidence/dotnet_test.log`) |

## Risk tier reasons (rulebook)

- src/Bank.Api/Modules/Fees/Application/Fee.cs: area 'Fees' is high (What the bank charges customers)
- src/Bank.Api/Modules/Fees/Application/FeeCalculator.cs: area 'Fees' is high (What the bank charges customers)
- src/Bank.Api/Modules/Fees/Application/IFeeCalculator.cs: area 'Fees' is high (What the bank charges customers)
- src/Bank.Api/Modules/Fees/FeesModule.cs: area 'Fees' is high (What the bank charges customers)
- src/Bank.Api/Modules/Payments/Api/PaymentsController.cs: area 'Payments' is high (Customer money leaves the account)
- src/Bank.Api/Modules/Payments/Api/PaymentsController.cs: content rule 'authorization attribute changed' matched → high
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
Run `20261114-195905-pr-4` · 2026-11-14T18:03:43+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 9

Settings: balanced preset · default essential · Full on high-risk · 15 plugins ran · #b5e52429b2df
Model calls: 17 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
