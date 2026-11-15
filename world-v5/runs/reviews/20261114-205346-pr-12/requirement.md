# PR-12: PR-12: Hold large payments to new payees for compliance review

**Story.** As a compliance officer at Nordbank, I want outgoing payments of 5,000 EUR equivalent or more to a payee account the customer has not paid before to be placed in Held status with funds moved to Suspense until a compliance officer releases or rejects them, so that potential fraud is stopped before funds leave the bank.

## Acceptance criteria
- [ ] When a customer initiates a payment whose amount in EUR equivalent is 5,000.00 EUR or more (calculated using decimal arithmetic and rounded with Math.Round(x, 2, MidpointRounding.AwayFromZero)) to a destination account that the customer has no prior Completed payment to, PaymentService sets the payment status to Held via a domain state-transition method on Payment (with a private setter on status).
- [ ] When a payment is held, ILedger.PostTransferAsync transfers (amount + fee) in the payment's currency from the payer's account to BankAccounts.For(BankAccountKind.Suspense, currency); no funds are transferred to the payee or FeeIncome while Held.
- [ ] When a payment is held, PaymentService publishes PaymentHeld(PaymentId, CustomerId, Amount, Currency, clock.UtcNow) via IEventBus and notifies the customer via INotifier (injected after IFeeCalculator) that the payment is being checked, without including any PII.
- [ ] Payments under 5,000.00 EUR equivalent, or payments to an account the customer has previously completed a payment to, are not held and execute normally.
- [ ] PaymentReviewService implements IPaymentReviewService with constructor (BankDbContext db, ILedger ledger, ICurrentUser user, IClock clock, IEventBus bus, INotifier notifier).
- [ ] All IPaymentReviewService methods (HeldAsync, ReleaseAsync, RejectAsync) enforce that ICurrentUser is in the Compliance role, throwing UnauthorizedAccessException otherwise.
- [ ] HeldAsync returns all payments currently in Held status.
- [ ] ReleaseAsync verifies the payment exists (throwing KeyNotFoundException if not), verifies the payment status is Held (throwing InvalidOperationException otherwise), and verifies payment.CustomerId is not equal to ICurrentUser.UserId (throwing UnauthorizedAccessException if an officer attempts to release their own payment).
- [ ] On ReleaseAsync, ILedger.PostTransferAsync transfers amount from BankAccounts.For(BankAccountKind.Suspense, currency) to the payee's account and (if fee > 0) transfers fee from Suspense to BankAccounts.For(BankAccountKind.FeeIncome, currency), transitions the payment status from Held to Completed, publishes PaymentReleased(PaymentId, user.UserId, clock.UtcNow), and notifies the customer via INotifier.
- [ ] RejectAsync validates that reason is non-empty (throwing ArgumentException if null or whitespace), verifies the payment exists (KeyNotFoundException if not), verifies status is Held (InvalidOperationException if not), and verifies payment.CustomerId != user.UserId (UnauthorizedAccessException on own payment).
- [ ] On RejectAsync, ILedger.PostTransferAsync transfers (amount + fee) from BankAccounts.For(BankAccountKind.Suspense, currency) back to the payer's account, transitions the payment status from Held to Rejected, publishes PaymentRejected(PaymentId, user.UserId, clock.UtcNow), and notifies the customer via INotifier without exposing PII.
- [ ] HTTP endpoints GET api/payments/held, POST api/payments/{id}/release, and POST api/payments/{id}/reject are protected with [Authorize(Policy = Policies.Compliance)], use ICurrentUser rather than request-body user IDs, and use IClock.UtcNow for all timestamps.

## Out of scope
- Per-customer or admin-configurable review thresholds or payee allowlists/whitelists.
- Automatic expiry or timeout of Held payments if no compliance officer acts.
- Four-eyes or multi-officer approval workflows for releasing or rejecting a payment.
- Customer-initiated cancellation or editing of a payment while it is in Held status.
- Pagination, filtering, or bulk release/reject endpoints on GET api/payments/held.
- Cross-currency settlement inside Suspense (all transfers for a payment occur in the payment's single currency).

## Risks
- Concurrent release or reject calls on the same Held payment could result in double payouts from Suspense or overdrafting the Suspense account if state transitions and database updates are not protected against concurrency.
- Non-atomic failure between ledger transfers (Suspense to payee, Suspense to FeeIncome, or Suspense back to payer) and saving the updated Payment status could leave ledger balances and payment status out of sync.
- Rounding or FX conversion errors near the 5,000.00 EUR boundary could allow large fraudulent payments to bypass review or leave residual cents stranded in Suspense.
- Counting prior Held, Rejected, or Failed payments as 'previously paid' would allow an attacker to bypass review by submitting a failed or rejected payment to the same payee first.
- Omitting the self-decision or role check in PaymentReviewService could allow a compliance officer to approve their own payment or an unauthorized caller to invoke review methods directly.
- Including customer PII or raw rejection text containing personal data in PaymentHeld, PaymentReleased, PaymentRejected events, logs, or notifications would violate bank privacy rules.

## Public contract
```
namespace Bank.Modules.Payments.Domain:
  sealed record PaymentHeld(Guid PaymentId, string CustomerId, decimal Amount, string Currency, DateTimeOffset OccurredAt) : IDomainEvent
  sealed record PaymentReleased(Guid PaymentId, string ReleasedBy, DateTimeOffset OccurredAt) : IDomainEvent
  sealed record PaymentRejected(Guid PaymentId, string RejectedBy, DateTimeOffset OccurredAt) : IDomainEvent
namespace Bank.Modules.Payments.Application:
  interface IPaymentReviewService {
    Task<IReadOnlyList<Payment>> HeldAsync(CancellationToken ct = default);
    Task<Payment> ReleaseAsync(Guid paymentId, CancellationToken ct = default);   // compliance officer only; own payment -> UnauthorizedAccessException; not Held -> InvalidOperationException
    Task<Payment> RejectAsync(Guid paymentId, string reason, CancellationToken ct = default); }
  sealed class PaymentReviewService(BankDbContext db, ILedger ledger, ICurrentUser user, IClock clock, IEventBus bus, INotifier notifier) : IPaymentReviewService
PaymentService gets INotifier as a constructor argument (after IFeeCalculator).
HTTP: GET api/payments/held, POST api/payments/{id}/release|reject (Compliance)
```

## Allowed scope
- `src/Bank.Api/Modules/Payments/**`
- `src/Bank.Api/Program.cs`

_Brief from the product owner:_ To fight fraud, a payment of 5,000 EUR or more (EUR equivalent) to an account the customer has never paid before is held: the money (amount + fee) leaves the payer's account and waits in the bank's Suspense account, the payment status is Held, and the customer is told it is being checked. A compliance officer then releases it (the payee is credited) or rejects it (the payer gets everything back). Officers cannot decide on their own payments.
