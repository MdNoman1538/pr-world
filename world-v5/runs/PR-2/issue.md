# PR-2: PR-2: Implement same-currency customer payments between bank accounts

**Story.** As an authenticated bank customer, I want to transfer whole-cent amounts in the same currency from one of my own accounts to any other account in the bank using an idempotency key and within the daily transfer limit, so that my payments are processed safely without duplicate transfers on retries.

## Acceptance criteria
- [ ] Authorization and Identity: Both POST api/payments and GET api/payments require the Customer policy (Policies.Customer), and PaymentService always identifies the caller using ICurrentUser.UserId rather than any user identifier from a request payload or query parameter.
- [ ] Ownership Check: Calling PayAsync where FromAccountId is not owned by ICurrentUser.UserId (verified via IAccountService) throws UnauthorizedAccessException and does not move money or persist a Payment.
- [ ] Amount Validation: Calling PayAsync with Amount less than or equal to 0, or with fractional cents (more than 2 decimal places, where Amount != Math.Round(Amount, 2, MidpointRounding.AwayFromZero)), throws ArgumentException and does not move money or persist a Payment.
- [ ] Currency Matching: Calling PayAsync where FromAccountId and ToAccountId have different currencies throws CurrencyMismatchException and does not move money or persist a Payment.
- [ ] Idempotency: Calling PayAsync with an IdempotencyKey already used by the same CustomerId returns the existing Payment record without calling ILedger.PostTransferAsync, without counting the amount again toward the daily limit, and without publishing another PaymentCompleted event; identical IdempotencyKey values from different customers are treated independently.
- [ ] Daily Transfer Limit: Before moving money, PayAsync sums the CustomerId's completed payments whose CreatedAt falls within the current UTC calendar day (using IClock.UtcNow); if that sum plus request.Amount exceeds BankSettings.DailyTransferLimit, PayAsync throws DailyLimitExceededException and does not move money or persist a Payment, whereas a total exactly equal to BankSettings.DailyTransferLimit is permitted.
- [ ] Insufficient Funds: If the source account has insufficient funds when posting via ILedger.PostTransferAsync, InsufficientFundsException is thrown and no Completed Payment is persisted.
- [ ] Ledger Posting and Persistence: On valid payment execution, money moves exclusively via ILedger.PostTransferAsync(FromAccountId, ToAccountId, Amount, Reference) without modifying Account.Balance directly; the Payment is saved to BankDbContext.Payments with Status = PaymentStatus.Completed (updated through an entity method with a private setter), TransferId set to the returned ledger transfer ID, Currency set to the accounts' currency, CustomerId = ICurrentUser.UserId, and CreatedAt = IClock.UtcNow.
- [ ] Domain Event: Upon completing a new payment, PaymentService publishes PaymentCompleted(PaymentId, CustomerId, Amount, Currency, OccurredAt) using IClock.UtcNow via IEventBus.PublishAsync, containing no personal data such as Reference or customer PII.
- [ ] Querying Payments: GET api/payments calls IPaymentService.ForCustomerAsync with ICurrentUser.UserId and returns only the authenticated customer's Payment records.
- [ ] Module Registration and Public Contract: The Payments module implements the agreed Domain types (PaymentStatus, Payment, PaymentCompleted) and Application types (PaymentRequest, DailyLimitExceededException, IPaymentService, PaymentService), adds DbSet<Payment> Payments to BankDbContext, and registers via PaymentsModule.AddPaymentsModule in Program.cs.

## Out of scope
- Cross-currency payments and foreign exchange (FX) conversion.
- Payment holding, fraud or compliance review workflows, or rejection state transitions (PaymentStatus.Held and PaymentStatus.Rejected).
- Scheduled, future-dated, or recurring payments.
- External bank transfers outside the bank's own accounts.
- Payment cancellation, reversals, refunds, or transaction fees.
- Customer-specific daily transfer limits overriding BankSettings.DailyTransferLimit.
- Staff, Compliance, or Admin endpoints for viewing or managing customer payments.

## Risks
- Concurrent Duplicate Requests: Two simultaneous requests with the same CustomerId and IdempotencyKey could both pass an application-level existence check and trigger duplicate ledger transfers unless enforced by a unique database constraint on (CustomerId, IdempotencyKey).
- Daily Limit Race Condition: Concurrent payments from the same customer could each read the same prior daily total and collectively exceed BankSettings.DailyTransferLimit if not serialized or checked transactionally.
- Partial Failure Across Ledger and Payments Storage: If ILedger.PostTransferAsync commits a transfer but persisting the Payment fails (or vice versa), the customer's balance and payment history become inconsistent.
- Idempotency Key Reuse with Different Parameters: If a client reuses an IdempotencyKey with a different ToAccountId or Amount, returning the original Payment could mask a client bug or mislead the customer.
- Broken Access Control (IDOR): Relying on a caller-supplied CustomerId instead of ICurrentUser.UserId in either PayAsync or GET api/payments could allow unauthorized transfers or exposure of other customers' payment histories.
- Clock and Timezone Drift: Using DateTime.Now or DateTimeOffset.UtcNow directly instead of IClock.UtcNow in UTC calendar day calculations could cause inconsistent daily limit enforcement around midnight UTC and break deterministic testing.

## Public contract
```
namespace Bank.Modules.Payments.Domain:
  enum PaymentStatus { Completed, Held, Rejected }
  sealed class Payment { Guid Id; string IdempotencyKey; string CustomerId; Guid FromAccountId; Guid ToAccountId;
                         decimal Amount; string Currency; PaymentStatus Status; Guid? TransferId; string? Reference; DateTimeOffset CreatedAt }
  sealed record PaymentCompleted(Guid PaymentId, string CustomerId, decimal Amount, string Currency, DateTimeOffset OccurredAt) : IDomainEvent
namespace Bank.Modules.Payments.Application:
  sealed record PaymentRequest(string IdempotencyKey, Guid FromAccountId, Guid ToAccountId, decimal Amount, string? Reference)
  sealed class DailyLimitExceededException : InvalidOperationException
  interface IPaymentService {
    Task<Payment> PayAsync(PaymentRequest request, CancellationToken ct = default);
        // from-account not owned by the caller -> UnauthorizedAccessException; amount <= 0 or not whole cents -> ArgumentException;
        // same caller + same key -> the existing payment, no new money movement; over the daily limit -> DailyLimitExceededException;
        // insufficient funds -> InsufficientFundsException (from the Ledger); different currencies -> CurrencyMismatchException
    Task<IReadOnlyList<Payment>> ForCustomerAsync(string customerId, CancellationToken ct = default); }
  sealed class PaymentService(BankDbContext db, ILedger ledger, IAccountService accounts, ICurrentUser user, IClock clock,
                              BankSettings settings, IEventBus bus) : IPaymentService
BankDbContext gets: DbSet<Payment> Payments
HTTP: POST api/payments, GET api/payments (Customer policy)
```

## Allowed scope
- `src/Bank.Api/Modules/Payments/**`
- `src/Bank.Api/Data/BankDbContext.cs`
- `src/Bank.Api/Program.cs`

_Brief from the product owner:_ A customer can send money from one of their own accounts to any other account in the bank. Every payment request carries an idempotency key chosen by the app; if the same customer sends the same key again (for example after a timeout), the bank returns the first payment and does not move money again. Customers can send at most the daily transfer limit from BankSettings per calendar day (UTC). Amounts must be positive whole cents. In this PR both accounts must have the same currency.
