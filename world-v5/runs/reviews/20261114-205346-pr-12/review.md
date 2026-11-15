# AI review · pr-12 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-12** · Owner: **Md Abdullah Al Noman**

> Merge locked: Security: Safety Blocker(s) found; Tests: Tests failed; Correctness: 5 Blocker(s) Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

This pull request implements PR-12 to hold outgoing payments of 5,000 EUR or more to new payees for compliance review. It introduces IPaymentReviewService, PaymentReviewService, and review endpoints in PaymentsController, along with domain events PaymentHeld, PaymentReleased, and PaymentRejected. However, the implementation omits transferring funds into Suspense upon hold, debits the payer instead of Suspense upon release, and omits the refund transfer upon rejection.

Requirement alignment: **partial**

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:1-1 | unclear | - | radar failed |
| H02 | src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:11-12 | unclear | - | radar failed |
| H03 | src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:34-35 | unclear | - | radar failed |
| H04 | src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:37-37 | unclear | - | radar failed |
| H05 | src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:40-40 | unclear | - | radar failed |
| H06 | src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:43-43 | unclear | - | radar failed |
| H07 | src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:104-186 | unclear | - | radar failed |
| H08 | src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:1-231 | unclear | - | radar failed |
| H09 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:12-12 | unclear | - | radar failed |
| H10 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:20-20 | unclear | - | radar failed |
| H11 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:48-49 | unclear | - | radar failed |
| H12 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:62-62 | unclear | - | radar failed |
| H13 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:65-65 | unclear | - | radar failed |
| H14 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:75-75 | unclear | - | radar failed |
| H15 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:86-86 | unclear | - | radar failed |
| H16 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:98-98 | unclear | - | radar failed |
| H17 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:100-113 | unclear | - | radar failed |
| H18 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:226-241 | unclear | - | radar failed |
| H19 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:310-310 | unclear | - | radar failed |
| H20 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:318-325 | unclear | - | radar failed |
| H21 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:346-346 | unclear | - | radar failed |
| H22 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:348-377 | unclear | - | radar failed |
| H23 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:379-388 | unclear | - | radar failed |
| H24 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:390-391 | unclear | - | radar failed |
| H25 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:393-393 | unclear | - | radar failed |
| H26 | src/Bank.Api/Modules/Payments/Application/PaymentService.cs:498-502 | unclear | - | radar failed |
| H27 | src/Bank.Api/Modules/Payments/Domain/Payment.cs:44-44 | unclear | - | radar failed |
| H28 | src/Bank.Api/Modules/Payments/Domain/Payment.cs:51-51 | unclear | - | radar failed |
| H29 | src/Bank.Api/Modules/Payments/Domain/Payment.cs:58-63 | unclear | - | radar failed |
| H30 | src/Bank.Api/Modules/Payments/PaymentsModule.cs:10-10 | unclear | - | radar failed |
| H31 | tests/Bank.Tests/Payments/FraudHoldTests.cs:1-151 | unclear | - | radar failed |

## Second opinion on Critical findings (validator panel)

- C05: 1 of 1 reviewers say real → not enough votes
- C02: 0 of 1 reviewers say real → not enough votes
- C03: 0 of 1 reviewers say real → not enough votes
- C04: 1 of 1 reviewers say real → not enough votes
- C01: 0 of 1 reviewers say real → not enough votes
- S02: 0 of 1 reviewers say real → not enough votes
- S03: 0 of 1 reviewers say real → not enough votes
- S01: 0 of 1 reviewers say real → not enough votes

## Investigator

- C05: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- C02: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- C03: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- C04: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- C01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- S02: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- S03: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
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

Noise funnel: 22 proposed by specialists → 22 with verified evidence (0 hallucinated dropped) → 1 removed by validator → 21 shown (incl. 0 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | HUMAN CHECK | Requirement match is partial: While domain events, review service interfaces, and HTTP endpoints were added, the core suspense accounting mechanism is missing: funds are never transferred to Suspense when payments are held, ReleaseAsync transfers from the payer rather than Suspense, RejectAsync does not refund funds from Suspense to the payer, and payments are unconditionally marked as Held before checking the hold condition. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Modules/Payments/Api/PaymentsController.cs: area 'Payments' is high (Customer money leaves the account)<br>src/Bank.Api/Modules/Payments/Api/PaymentsController.cs: content rule 'authorization attribute changed' matched → high<br>src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs: area 'Payments' is high (Customer money leaves the account)<br>src/Bank.Api/Modules/Payments/Application/PaymentService.cs: area 'Payments' is high (Customer money leaves the account) |
| Why | VERIFIED | Linked to a requirement |
| Security | BLOCKED | Safety Blocker(s) found<br>S02 src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:71<br>S03 src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:177<br>S01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:346 |
| Build | VERIFIED | Build succeeded |
| Tests | BLOCKED | Tests failed<br>Failed!  - Failed:     4, Passed:   269, Skipped:     0, Total:   273, Duration: 1 s - Bank.Tests.dll (net10.0) |
| Correctness | BLOCKED | 5 Blocker(s)<br>C05 src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:104<br>C02 src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:71<br>C03 src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:177<br>C04 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:341 |
| Architecture | VERIFIED | No blocking issue; 5 ShouldFix noted (does not hold the merge)<br>A04 src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:31<br>A05 src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:25<br>A02 src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:71<br>A03 src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:177 |
| Maintainability | VERIFIED | No blocking issue; 2 ShouldFix noted (does not hold the merge)<br>M02 src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:174<br>M01 src/Bank.Api/Modules/Payments/Application/PaymentService.cs:341 |
| Performance | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>P01 src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:25 |
| Impact | VERIFIED | 27 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (21 shown, 1 filtered as noise)

- **[Blocker] C05 · Compliance review endpoints require Customer authorization policy** (correctness, specialist:correctness · confidence 0.95) `src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:104`

  PaymentsController has [Authorize(Policy = Policies.Customer)] on the class level. In ASP.NET Core, action-level [Authorize] attributes are evaluated alongside class-level attributes, meaning compliance officers without the Customer role will receive HTTP 403 Forbidden on held, release, and reject endpoints.

  ```
  [HttpGet("held")]
  [Authorize(Policy = Policies.Compliance)]
  public async Task<ActionResult<IEnumerable<PaymentDto>>> Held(CancellationToken ct)
  ```

  Requirement: HTTP endpoints GET api/payments/held, POST api/payments/{id}/release, and POST api/payments/{id}/reject are protected with [Authorize(Policy = Policies.Compliance)], use ICurrentUser rather than request-body user IDs, and use IClock.UtcNow for all timestamps.

  Suggested fix: Move the compliance endpoints to a separate dedicated controller (e.g., PaymentReviewController) protected with [Authorize(Policy = Policies.Compliance)], or remove the class-level [Authorize(Policy = Policies.Customer)] attribute from PaymentsController and apply it per-action.

- **[Blocker] C02 · ReleaseAsync transfers funds from payer account instead of Suspense account** (correctness, specialist:correctness · confidence 1.00) `src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:71`

  In ReleaseAsync, funds are transferred from payment.FromAccountId directly to the payee and FeeIncome accounts instead of transferring from BankAccounts.For(BankAccountKind.Suspense, currency). This bypasses the Suspense account and attempts to debit the customer account a second time.

  ```
  transferId = await ledger.PostTransferAsync(
  payment.FromAccountId,
  payment.ToAccountId,
  Math.Round(payment.Amount, 2, MidpointRounding.AwayFromZero),
  reference,
  ct);
  ```

  Requirement: On ReleaseAsync, ILedger.PostTransferAsync transfers amount from BankAccounts.For(BankAccountKind.Suspense, currency) to the payee's account and (if fee > 0) transfers fee from Suspense to BankAccounts.For(BankAccountKind.FeeIncome, currency), transitions the payment status from Held to Completed, publishes PaymentReleased(PaymentId, user.UserId, clock.UtcNow), and notifies the customer via INotifier.

  Suggested fix: Use BankAccounts.For(BankAccountKind.Suspense, payment.Currency) as the source account for both payee transfer and fee transfer in ReleaseAsync.

- **[Blocker] C03 · RejectAsync does not return funds from Suspense account to payer** (correctness, specialist:correctness · confidence 1.00) `src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:177`

  RejectAsync updates the payment status to Rejected but never executes a ledger transfer. Funds held in Suspense for the rejected payment are never refunded to the payer's account.

  ```
  payment.Reject();
  await db.SaveChangesAsync(ct);
  ```

  Requirement: On RejectAsync, ILedger.PostTransferAsync transfers (amount + fee) from BankAccounts.For(BankAccountKind.Suspense, currency) back to the payer's account, transitions the payment status from Held to Rejected, publishes PaymentRejected(PaymentId, user.UserId, clock.UtcNow), and notifies the customer via INotifier without exposing PII.

  Suggested fix: In RejectAsync, invoke ledger.PostTransferAsync transferring (amount + fee) from BankAccounts.For(BankAccountKind.Suspense, payment.Currency) to payment.FromAccountId before saving and committing.

- **[Blocker] C04 · Payment.Hold() is called unconditionally for all payments** (correctness, specialist:correctness · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:341`

  All payments are transitioned to Held and saved to the database prior to evaluating if the payment should actually be held. If an error occurs prior to completion or if concurrent queries inspect the database, normal payments are incorrectly recorded and exposed as Held.

  ```
  payment.Hold();
  
  _db.Payments.Add(payment);
  await _db.SaveChangesAsync(ct);
  ```

  Requirement: Payments under 5,000.00 EUR equivalent, or payments to an account the customer has previously completed a payment to, are not held and execute normally.

  Suggested fix: Only call payment.Hold() when shouldHold is true. For normal payments, leave status as Pending until payment.Complete(transferId) is called.

- **[Blocker] C01 · Held payments do not transfer funds to the Suspense account** (correctness, specialist:correctness · confidence 1.00) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:346`

  When a payment qualifies for review (shouldHold is true), the code skips the standard transfer block but never posts a transfer to move (amount + fee) from the payer to the Suspense account. Payer funds remain in their account unreserved while the payment is held.

  ```
  if (!shouldHold)
  {
  ```

  Requirement: When a payment is held, ILedger.PostTransferAsync transfers (amount + fee) in the payment's currency from the payer's account to BankAccounts.For(BankAccountKind.Suspense, currency); no funds are transferred to the payee or FeeIncome while Held.

  Suggested fix: Add an else branch when shouldHold is true that calls ledger.PostTransferAsync transferring (amount + fee.Amount) from request.FromAccountId to BankAccounts.For(BankAccountKind.Suspense, fromAccount.Currency).

- **[Blocker] S02 · Releasing a held payment transfers from payer account instead of Suspense** (safety, specialist:safety · confidence 1.00) `src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:71`

  ReleaseAsync transfers payment.Amount and payment.Fee from payment.FromAccountId rather than the Suspense account. If funds had been held in Suspense, this would double-debit the customer and leave Suspense funds stranded.

  ```
  transferId = await ledger.PostTransferAsync(
  payment.FromAccountId,
  payment.ToAccountId,
  Math.Round(payment.Amount, 2, MidpointRounding.AwayFromZero),
  reference,
  ct);
  ```

  Requirement: On ReleaseAsync, ILedger.PostTransferAsync transfers amount from BankAccounts.For(BankAccountKind.Suspense, currency) to the payee's account and (if fee > 0) transfers fee from Suspense to BankAccounts.For(BankAccountKind.FeeIncome, currency)

  Suggested fix: Use BankAccounts.For(BankAccountKind.Suspense, payment.Currency) as the source account for both the payee transfer and the fee income transfer.

- **[Blocker] S03 · Rejecting a held payment does not refund funds from Suspense to payer** (safety, specialist:safety · confidence 1.00) `src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:177`

  RejectAsync marks the payment status as Rejected but fails to post any ledger transfer. Funds sequestered in the Suspense account are never returned to the customer's account.

  ```
  payment.Reject();
  await db.SaveChangesAsync(ct);
  ```

  Requirement: On RejectAsync, ILedger.PostTransferAsync transfers (amount + fee) from BankAccounts.For(BankAccountKind.Suspense, currency) back to the payer's account, transitions the payment status from Held to Rejected, publishes PaymentRejected(PaymentId, user.UserId, clock.UtcNow), and notifies the customer via INotifier without exposing PII.

  Suggested fix: Call ledger.PostTransferAsync in RejectAsync to transfer (payment.Amount + payment.Fee) from BankAccounts.For(BankAccountKind.Suspense, payment.Currency) back to payment.FromAccountId.

- **[Blocker] S01 · Held payments do not transfer funds to the Suspense account** (safety, specialist:safety · confidence 1.00) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:346`

  When a payment qualifies for compliance hold, PaymentService marks it as Held but completely skips calling ILedger.PostTransferAsync. The customer's funds remain in their account instead of being sequestered in Suspense, allowing the customer to withdraw or spend the money during review.

  ```
  if (!shouldHold)
  {
  ```

  Requirement: When a payment is held, ILedger.PostTransferAsync transfers (amount + fee) in the payment's currency from the payer's account to BankAccounts.For(BankAccountKind.Suspense, currency); no funds are transferred to the payee or FeeIncome while Held.

  Suggested fix: Add an else branch when shouldHold is true to invoke ledger.PostTransferAsync transferring (amount + fee) from request.FromAccountId to BankAccounts.For(BankAccountKind.Suspense, fromAccount.Currency).

- **[ShouldFix] A04 · Class-level Customer authorization policy blocks Compliance endpoints** (architecture, specialist:architecture · confidence 0.95 · Capped at Major: a architecture finding is never Critical on its own) `src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:31`

  In ASP.NET Core, authorization attributes combine additively. Because PaymentsController is decorated with [Authorize(Policy = Policies.Customer)] at the class level, adding [Authorize(Policy = Policies.Compliance)] on Held, Release, and Reject requires callers to satisfy both policies, rejecting compliance officers with 403 Forbidden.

  ```
  [Authorize(Policy = Policies.Customer)]
  public sealed class PaymentsController : ControllerBase
  ```

  Requirement: HTTP endpoints GET api/payments/held, POST api/payments/{id}/release, and POST api/payments/{id}/reject are protected with [Authorize(Policy = Policies.Compliance)], use ICurrentUser rather than request-body user IDs, and use IClock.UtcNow for all timestamps.

  Suggested fix: Move the compliance endpoints to a dedicated controller (e.g. PaymentReviewController) or apply [Authorize(Policy = Policies.Customer)] only to customer-facing actions.

- **[ShouldFix] A05 · Unbounded static ConcurrentDictionary leaks SemaphoreSlim instances** (architecture, specialist:architecture · confidence 0.85) `src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:25`

  PaymentLocks stores a SemaphoreSlim per Guid payment ID but never removes entries after completion or failure. In a long-running process, this dictionary grows without bound.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> PaymentLocks = new();
  ```

  Suggested fix: Rely on database-level row locking or remove the semaphore key when lock count reaches zero to avoid unbounded memory growth.

- **[ShouldFix] A02 · ReleaseAsync debits payer account instead of Suspense account** (architecture, specialist:architecture · confidence 0.99 · Capped at Major: a architecture finding is never Critical on its own) `src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:71`

  ReleaseAsync transfers money from payment.FromAccountId directly to the payee and FeeIncome. Under the Suspense accounting model, the customer's funds were already debited upon hold, so releasing must transfer amount and fee out of the Suspense account.

  ```
  transferId = await ledger.PostTransferAsync(
  payment.FromAccountId,
  payment.ToAccountId,
  Math.Round(payment.Amount, 2, MidpointRounding.AwayFromZero),
  reference,
  ct);
  ```

  Requirement: On ReleaseAsync, ILedger.PostTransferAsync transfers amount from BankAccounts.For(BankAccountKind.Suspense, currency) to the payee's account and (if fee > 0) transfers fee from Suspense to BankAccounts.For(BankAccountKind.FeeIncome, currency)

  Suggested fix: Use BankAccounts.For(BankAccountKind.Suspense, payment.Currency) as the source account for ledger transfers in ReleaseAsync.

- **[ShouldFix] A03 · RejectAsync omits required ledger refund from Suspense account** (architecture, specialist:architecture · confidence 0.99 · Capped at Major: a architecture finding is never Critical on its own) `src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:177`

  RejectAsync transitions the payment status to Rejected in the database but executes no ledger transfer whatsoever. The held funds (amount + fee) are never returned to the payer's account.

  ```
  payment.Reject();
  await db.SaveChangesAsync(ct);
  ```

  Requirement: On RejectAsync, ILedger.PostTransferAsync transfers (amount + fee) from BankAccounts.For(BankAccountKind.Suspense, currency) back to the payer's account, transitions the payment status from Held to Rejected, publishes PaymentRejected(PaymentId, user.UserId, clock.UtcNow), and notifies the customer via INotifier without exposing PII.

  Suggested fix: In RejectAsync, post a ledger transfer of (payment.Amount + payment.Fee) from BankAccounts.For(BankAccountKind.Suspense, payment.Currency) to payment.FromAccountId before saving.

- **[ShouldFix] A01 · Held payments bypass Suspense account in hold workflow** (architecture, specialist:architecture · confidence 0.99 · Capped at Major: a architecture finding is never Critical on its own) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:346`

  When shouldHold is true, PaymentService marks the payment as Held but completely skips posting any ledger transfer. The requirement specifies that (amount + fee) must be transferred from the payer's account to the bank's Suspense account upon hold.

  ```
  if (!shouldHold)
  {
  ```

  Requirement: When a payment is held, ILedger.PostTransferAsync transfers (amount + fee) in the payment's currency from the payer's account to BankAccounts.For(BankAccountKind.Suspense, currency); no funds are transferred to the payee or FeeIncome while Held.

  Suggested fix: When shouldHold is true, call ILedger.PostTransferAsync to transfer amount + fee from request.FromAccountId to BankAccounts.For(BankAccountKind.Suspense, fromAccount.Currency).

- **[ShouldFix] M02 · Manual JSON stream reading bypasses ASP.NET Core model binding** (maintainability, specialist:maintainability · confidence 0.90) `src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:174`

  The controller introduces ReadOptionalJsonBodyAsync to manually read Request.Body with a StreamReader and deserialize RejectPaymentRequest. This reinvents standard MVC model binding, introduces unnecessary custom plumbing, and increases controller maintenance overhead.

  ```
  private async Task<T?> ReadOptionalJsonBodyAsync<T>(CancellationToken ct)
  ```

  Requirement: HTTP endpoints GET api/payments/held, POST api/payments/{id}/release, and POST api/payments/{id}/reject are protected with [Authorize(Policy = Policies.Compliance)], use ICurrentUser rather than request-body user IDs, and use IClock.UtcNow for all timestamps.

  Suggested fix: Replace ReadOptionalJsonBodyAsync with standard ASP.NET Core model binding using [FromBody] RejectPaymentRequest? request in the Reject action signature.

- **[ShouldFix] M01 · Unconditional call to payment.Hold() misrepresents domain lifecycle** (maintainability, specialist:maintainability · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentService.cs:341`

  Every new payment is transitioned to Held status and saved to the database regardless of whether it meets hold criteria. Only after saving is shouldHold checked to conditionally complete the payment, which distorts the domain lifecycle and introduces redundant database round-trips for normal payments.

  ```
  payment.Hold();
  ```

  Requirement: When a customer initiates a payment whose amount in EUR equivalent is 5,000.00 EUR or more ... to a destination account that the customer has no prior Completed payment to, PaymentService sets the payment status to Held via a domain state-transition method on Payment (with a private setter on status).

  Suggested fix: Only call payment.Hold() when shouldHold evaluates to true; otherwise, keep the payment in its initial state and complete it directly.

- **[ShouldFix] P01 · Unbounded memory growth from static SemaphoreSlim dictionary** (performance, specialist:performance · confidence 0.95) `src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:25`

  PaymentLocks retains a SemaphoreSlim for every payment ID passed to ReleaseAsync or RejectAsync without any eviction or removal mechanism. In long-running processes, this causes continuous memory accumulation.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> PaymentLocks = new();
  ```

  Suggested fix: Use a bounded cache, clean up keys after releasing the lock if no waiters remain, or rely on database-level row locking/optimistic concurrency rather than an unbounded static dictionary.

- **[ShouldFix] S04 · Class-level Customer authorization policy blocks Compliance endpoints** (safety, specialist:safety · confidence 0.95) `src/Bank.Api/Modules/Payments/Api/PaymentsController.cs:31`

  In ASP.NET Core, Authorize attributes at the class and action level combine additively. Because PaymentsController is decorated with [Authorize(Policy = Policies.Customer)], compliance officers accessing Held, Release, or Reject must satisfy both Customer and Compliance policies, resulting in HTTP 403 Forbidden for officers without Customer role permissions.

  ```
  [Authorize(Policy = Policies.Customer)]
  public sealed class PaymentsController : ControllerBase
  ```

  Requirement: HTTP endpoints GET api/payments/held, POST api/payments/{id}/release, and POST api/payments/{id}/reject are protected with [Authorize(Policy = Policies.Compliance)], use ICurrentUser rather than request-body user IDs, and use IClock.UtcNow for all timestamps.

  Suggested fix: Move the compliance endpoints to a separate controller (e.g. PaymentReviewController) protected only with [Authorize(Policy = Policies.Compliance)], or apply Customer policy to specific customer action methods rather than the entire controller class.

- **[ShouldFix] S05 · Static PaymentLocks dictionary grows without bound** (safety, specialist:safety · confidence 0.90) `src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs:25`

  PaymentReviewService creates and stores a SemaphoreSlim in a static ConcurrentDictionary for every reviewed paymentId without ever removing entries, introducing unbounded memory growth over the lifetime of the application.

  ```
  private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> PaymentLocks = new();
  ```

  Suggested fix: Clean up locks when no longer contested or use a bounded cache/evicting lock store.

- **[ShouldFix] T01 · No test coverage for payment hold evaluation or Suspense transfer in PaymentService** (tests, specialist:tests · confidence 1.00 · Capped at Major: a tests finding is never Critical on its own) `tests/Bank.Tests/Payments/FraudHoldTests.cs:11`

  The test suite in FraudHoldTests tests only IPaymentReviewService guard paths and contains no unit or integration tests for PaymentService.PayAsync. Consequently, critical requirements—holding payments >= 5,000 EUR to new payees, routing funds to Suspense, and allowing smaller or repeat payments through—are completely unverified.

  ```
  public sealed class FraudHoldTests
  ```

  Requirement: When a customer initiates a payment whose amount in EUR equivalent is 5,000.00 EUR or more (calculated using decimal arithmetic and rounded with Math.Round(x, 2, MidpointRounding.AwayFromZero)) to a destination account that the customer has no prior Completed payment to, PaymentService sets the payment status to Held via a domain state-transition method on Payment (with a private setter on status).

  Suggested fix: Add unit tests for PaymentService.PayAsync asserting that payments >= 5,000 EUR to new payees transition to Held, post transfers to the Suspense account, publish PaymentHeld, and leave regular or repeat payments in Completed.

- **[ShouldFix] T02 · Missing tests for successful execution of ReleaseAsync and RejectAsync** (tests, specialist:tests · confidence 1.00 · Capped at Major: a tests finding is never Critical on its own) `tests/Bank.Tests/Payments/FraudHoldTests.cs:65`

  FraudHoldTests only checks exception handling for missing payments, wrong roles, and blank rejection reasons. There are zero tests asserting that ReleaseAsync and RejectAsync successfully complete transfers from Suspense, update payment status to Completed/Rejected, and publish domain events.

  ```
  public async Task ReleaseAsync_throws_UnauthorizedAccessException_for_non_compliance_roles(string role)
  ```

  Requirement: On ReleaseAsync, ILedger.PostTransferAsync transfers amount from BankAccounts.For(BankAccountKind.Suspense, currency) to the payee's account and (if fee > 0) transfers fee from Suspense to BankAccounts.For(BankAccountKind.FeeIncome, currency), transitions the payment status from Held to Completed, publishes PaymentReleased(PaymentId, user.UserId, clock.UtcNow), and notifies the customer via INotifier.

  Suggested fix: Add tests for successful ReleaseAsync and RejectAsync flows asserting that ledger transfers source funds from Suspense, payment statuses update appropriately, and domain events/notifications are dispatched.

- **[ShouldFix] T03 · Missing negative tests for self-decision and non-Held status checks** (tests, specialist:tests · confidence 0.95) `tests/Bank.Tests/Payments/FraudHoldTests.cs:65`

  The requirement mandates that an officer attempting to release or reject their own payment throws UnauthorizedAccessException, and attempting to release or reject non-Held payments throws InvalidOperationException. FraudHoldTests omits tests for these validation branches.

  ```
  public async Task ReleaseAsync_throws_UnauthorizedAccessException_for_non_compliance_roles(string role)
  ```

  Requirement: ReleaseAsync verifies the payment exists (throwing KeyNotFoundException if not), verifies the payment status is Held (throwing InvalidOperationException otherwise), and verifies payment.CustomerId is not equal to ICurrentUser.UserId (throwing UnauthorizedAccessException if an officer attempts to release their own payment).

  Suggested fix: Add test cases covering self-release/self-rejection by matching customer ID with current user ID, as well as attempting release/rejection on Pending, Completed, or Rejected payments.

## What the AI refused to decide, and why

- **Policy definition mapping for Policies.Customer and Policies.Compliance** (specialist:correctness): The file defining Policies and role claim mappings in Bank.Modules.Auth is outside the provided context.
- **Policies.Compliance definition and alignment with Roles.ComplianceOfficer** (specialist:architecture): The definition of Policies.Compliance and its policy registration in Program.cs/AuthModule were not modified in this PR and are outside the diff context.
- **Reason for dotnet_test failure** (specialist:safety): Test output logs and specific failure stack traces from dotnet_test were not provided in the review context.
- **PaymentsController HTTP route integration tests** (specialist:tests): No test fixtures or web application factories for the API layer were included in the diff to evaluate controller routing and authorization filters in an integrated HTTP environment.
- **dotnet_test failure diagnosis** (specialist:maintainability): Test output logs and error stack traces from the test runner were not included in the review context.
- **Controller-level authorization policy interaction** (specialist:maintainability): Whether class-level [Authorize(Policy = Policies.Customer)] blocks compliance officers accessing [Authorize(Policy = Policies.Compliance)] actions depends on policy definitions in Program.cs, which is outside the shown context.
- **Index efficiency of payee payment history check** (specialist:performance): Cannot determine whether the AnyAsync query on CustomerId, ToAccountId, and Status performs an index scan or full table scan without access to the database migrations/indexes.
- **Throughput impact of StreamReader.ReadToEndAsync in ReadOptionalJsonBodyAsync** (specialist:performance): Allocating string copies of the request body vs streaming cannot be established as a measurable regression without runtime benchmarks.
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

- src/Bank.Api/Modules/Payments/Api/PaymentsController.cs: area 'Payments' is high (Customer money leaves the account)
- src/Bank.Api/Modules/Payments/Api/PaymentsController.cs: content rule 'authorization attribute changed' matched → high
- src/Bank.Api/Modules/Payments/Application/PaymentReviewService.cs: area 'Payments' is high (Customer money leaves the account)
- src/Bank.Api/Modules/Payments/Application/PaymentService.cs: area 'Payments' is high (Customer money leaves the account)
- src/Bank.Api/Modules/Payments/Domain/Payment.cs: area 'Payments' is high (Customer money leaves the account)
- src/Bank.Api/Modules/Payments/PaymentsModule.cs: area 'Payments' is high (Customer money leaves the account)
- Large change (626 lines > 400) → one tier up

## Filtered out before you saw them (audit)

| ID | Source | Title | Why it was filtered |
| --- | --- | --- | --- |
| P02 | specialist:performance | Read-only listing query tracks entities in EF change tracker | Nit suppressed by policy (gates.show_nits=false) |

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
- Not checked: Scope vs approved plan (no --plan given); Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}); Part of src/Bank.Api/Modules/Payments/Application/PaymentService.cs (context truncated)
- Residual risk I accept: ______________________________
- Signed: ______________________ (owner)   ______________________ (second signer)

---
Run `20261114-205346-pr-12` · 2026-11-14T18:58:34+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 6

Settings: balanced preset · default essential · Full on high-risk · 15 plugins ran · #b5e52429b2df
Model calls: 35 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
