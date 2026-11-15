# PR-11: PR-11: Enforce idempotent payment processing for retries and concurrent requests

**Story.** As a Nordbank customer using the mobile app, I want retried or concurrent payment requests with the same idempotency key to be processed only once so that I am never charged twice when a request times out.

## Acceptance criteria
- [ ] No public method signatures are changed; IPaymentService.PayAsync retains its existing signature, authorization checks (Policies.Customer and ICurrentUser.UserId), and account ownership checks via IAccountService.IsOwnerAsync.
- [ ] The Payment database table enforces a composite unique index on (CustomerId, IdempotencyKey) via EF Core configuration so duplicate keys for the same customer are rejected at the database level.
- [ ] CustomerId used for idempotency scoping is always sourced from ICurrentUser.UserId and never from request DTOs.
- [ ] When IPaymentService.PayAsync is called sequentially by the same customer with an IdempotencyKey that already exists for that CustomerId, it returns the existing first payment without calling ILedger.PostTransferAsync or moving money again.
- [ ] When two requests with the same CustomerId and IdempotencyKey execute concurrently, at most one payment record is persisted and ILedger.PostTransferAsync is called at most once (with decimal amount rounded using Math.Round(x, 2, MidpointRounding.AwayFromZero)); the second request handles the database unique constraint violation and returns the existing first payment rather than failing with an unhandled exception.
- [ ] Idempotency keys are strictly scoped per customer: two different customers submitting the same IdempotencyKey each succeed independently with their own payments, and one customer cannot read another customer's payment by reusing their IdempotencyKey.
- [ ] If the first attempt fails before committing a valid payment (for example, validation error, insufficient balance, or unauthorized account), no idempotency record locks out a subsequent valid request or no money is moved via ILedger.
- [ ] Automated xUnit tests verify sequential retry behavior, concurrent identical requests against SQLite enforcing the unique index, cross-customer key isolation, and that ILedger.PostTransferAsync is invoked exactly once for duplicate requests.

## Out of scope
- Changing the public signature of IPaymentService.PayAsync, HTTP controller routes, or DTO contracts.
- Adding idempotency key expiration, TTL policies, or background cleanup jobs.
- Validating or rejecting payload mismatches when the same idempotency key is reused with a different amount or target account (returning 409/422).
- Introducing distributed locks, external caching (such as Redis), or new NuGet packages.
- Data remediation or refunds for historical duplicate payments referenced in support ticket #4711.

## Risks
- Calling ILedger.PostTransferAsync before atomically persisting or reserving the unique (CustomerId, IdempotencyKey) database record would allow two concurrent threads to both transfer money before one fails on the unique constraint.
- Catching DbUpdateException too broadly without verifying it is a unique constraint violation on (CustomerId, IdempotencyKey) could mask real persistence errors or return incorrect responses.
- Creating the unique index on IdempotencyKey alone rather than (CustomerId, IdempotencyKey) would allow one customer's key to block another customer's payment or leak another customer's payment data.
- Re-querying the existing payment within a poisoned EF Core change tracker or uncommitted transaction after a unique constraint failure in SQLite could cause stale state or secondary exceptions.
- Sourcing CustomerId from a request payload instead of ICurrentUser.UserId would allow spoofing and unauthorized access to another customer's payment result.

## Public contract
```
No public signature changes. IPaymentService.PayAsync keeps its behaviour; a repeated key returns the first payment.
```

## Allowed scope
- `src/Bank.Api/Modules/Payments/**`
- `src/Bank.Api/Data/BankDbContext.cs`

_Brief from the product owner:_ Support ticket #4711: a customer was charged twice for one payment after the mobile app retried a request that had timed out. Make sure a payment request with the same idempotency key from the same customer can never move money twice, also when two identical requests arrive at the same moment. The database must enforce it as well (a unique index on customer + idempotency key).
