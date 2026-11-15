# PR-1: PR-1: Customer onboarding and identity checks (KYC)

**Story.** As a new customer, I want to register my personal identity details for compliance review so that once verified I am eligible to open a bank account, while ensuring underage or unverified applicants are blocked.

## Acceptance criteria
- [ ] Domain types exist in Bank.Modules.Customers.Domain: enum KycStatus { Pending, Verified, Rejected }, sealed class Customer (with parameterless constructor, Id, FullName, Email, [Pii] NationalId, [Pii] DateOfBirth, Status with private setter defaulting to Pending, DecidedBy, RegisteredAt, Verify(string officerId), Reject(string officerId)), and sealed record IDomainEvent types CustomerRegistered(string CustomerId, DateTimeOffset OccurredAt), CustomerVerified(string CustomerId, string VerifiedBy, DateTimeOffset OccurredAt), and CustomerRejected(string CustomerId, string RejectedBy, DateTimeOffset OccurredAt).
- [ ] Customer.Verify(officerId) and Customer.Reject(officerId) transition Status from Pending to Verified or Rejected respectively and set DecidedBy to officerId; invoking either method when Status is not Pending throws InvalidOperationException.
- [ ] ICustomerService.RegisterAsync registers a Customer for the signed-in user (Id = ICurrentUser.UserId) with Status = KycStatus.Pending and RegisteredAt = IClock.UtcNow, persists it to BankDbContext.Customers, and publishes CustomerRegistered via IEventBus.
- [ ] ICustomerService.RegisterAsync throws ArgumentException if FullName, Email, or NationalId is null/empty/whitespace, or if the applicant is under 18 years old on IClock.UtcNow's date (turning 18 on that exact calendar date is accepted; one day younger is rejected); it throws InvalidOperationException if a Customer with ICurrentUser.UserId already exists.
- [ ] ICustomerService.VerifyAsync(customerId) and RejectAsync(customerId) throw UnauthorizedAccessException if the caller does not have the Compliance role or if ICurrentUser.UserId equals customerId (no self-verification or self-rejection), and throw KeyNotFoundException if customerId does not exist.
- [ ] On successful VerifyAsync or RejectAsync, the Customer status and DecidedBy are persisted to BankDbContext.Customers and CustomerVerified or CustomerRejected is published via IEventBus.
- [ ] ICustomerService.GetAsync(customerId) returns the matching Customer from BankDbContext.Customers or null when not found.
- [ ] KycAccountOpeningRule implements IAccountOpeningRule and throws UnauthorizedAccessException if the target customer does not exist in BankDbContext.Customers or has Status other than KycStatus.Verified.
- [ ] BankDbContext declares DbSet<Customer> Customers above the // TABLES: marker, CustomersModule registers ICustomerService (CustomerService) and IAccountOpeningRule (KycAccountOpeningRule), and AddCustomersModule is registered in Program.cs above // MODULES:.
- [ ] HTTP endpoints are exposed with [ApiController] and explicit [Authorize(Policy = ...)] attributes: POST api/customers (Customer policy, derives user id solely from ICurrentUser), GET api/customers/me (Customer policy, returns current user's customer), POST api/customers/{id}/verify (Compliance policy), and POST api/customers/{id}/reject (Compliance policy).
- [ ] NationalId and DateOfBirth are marked with [Pii] on Customer and never appear in domain events, exception messages, or logs; all timestamps and age checks use IClock.UtcNow rather than DateTime.Now or DateTimeOffset.UtcNow.

## Out of scope
- Integration with external identity verification providers, document uploads, or automated KYC/sanctions/PEP screening.
- Updating customer profile or PII fields after registration, or re-applying after a Rejected status.
- Compliance officer queue, search, or list endpoints for browsing Pending registrations.
- Customer notifications (email, SMS, or push) upon registration, verification, or rejection.
- Account creation endpoints, deposit/transfer flows, or any ledger/monetary operations.
- Customer deletion or GDPR data erasure workflows.

## Risks
- Self-verification bypass: if VerifyAsync or RejectAsync fails to enforce both the Compliance role and officerId != customerId, an insider or compromised compliance account could approve their own KYC.
- Unverified account opening: if KycAccountOpeningRule is not wired as IAccountOpeningRule or fails open for missing, Pending, or Rejected customers, unverified or underage users could open accounts.
- PII exposure: logging request bodies, embedding NationalId or DateOfBirth in exception messages, or adding PII fields to domain events would leak sensitive personal data.
- Incorrect age calculation: using DateTime.UtcNow instead of IClock.UtcNow or approximating 18 years as 365 * 18 days could allow underage applicants on leap years or wrongly reject eligible 18-year-olds.
- Audit trail corruption: allowing direct mutation of Status or DecidedBy without going through Pending-only domain methods could overwrite compliance decisions.
- Identity spoofing: trusting a user id from the HTTP request body instead of ICurrentUser.UserId in POST api/customers could allow one user to register or block another user's identity.

## Public contract
```
namespace Bank.Modules.Customers.Domain:
  enum KycStatus { Pending, Verified, Rejected }
  sealed class Customer { string Id (the user id, primary key); string FullName; string Email; [Pii] string NationalId;
                          [Pii] DateOnly DateOfBirth; KycStatus Status { get; private set; } (starts Pending); string? DecidedBy;
                          DateTimeOffset RegisteredAt;
                          void Verify(string officerId); void Reject(string officerId) }   // only from Pending, else InvalidOperationException
  sealed record CustomerRegistered(string CustomerId, DateTimeOffset OccurredAt) : IDomainEvent
  sealed record CustomerVerified(string CustomerId, string VerifiedBy, DateTimeOffset OccurredAt) : IDomainEvent
  sealed record CustomerRejected(string CustomerId, string RejectedBy, DateTimeOffset OccurredAt) : IDomainEvent
namespace Bank.Modules.Customers.Application:
  sealed record RegisterCustomerRequest(string FullName, string Email, string NationalId, DateOnly DateOfBirth)
  interface ICustomerService {
    Task<Customer> RegisterAsync(RegisterCustomerRequest request, CancellationToken ct = default);  // for the signed-in user;
        // already registered -> InvalidOperationException; under 18 on IClock's date -> ArgumentException; empty fields -> ArgumentException
    Task<Customer> VerifyAsync(string customerId, CancellationToken ct = default);   // compliance officer only, never themselves -> UnauthorizedAccessException; unknown -> KeyNotFoundException
    Task<Customer> RejectAsync(string customerId, CancellationToken ct = default);   // same rules as VerifyAsync
    Task<Customer?> GetAsync(string customerId, CancellationToken ct = default); }
  sealed class CustomerService(BankDbContext db, ICurrentUser user, IClock clock, IEventBus bus) : ICustomerService
  sealed class KycAccountOpeningRule(BankDbContext db) : IAccountOpeningRule   // not Verified (or unknown) -> UnauthorizedAccessException
CustomersModule registers ICustomerService and KycAccountOpeningRule as IAccountOpeningRule.
BankDbContext gets: DbSet<Customer> Customers
HTTP: POST api/customers (register yourself), GET api/customers/me, POST api/customers/{id}/verify, POST api/customers/{id}/reject (Compliance policy)
```

## Allowed scope
- `src/Bank.Api/Modules/Customers/**`
- `src/Bank.Api/Data/BankDbContext.cs`
- `src/Bank.Api/Program.cs`

_Brief from the product owner:_ New customers register with their full name, e-mail, national identity number and date of birth. Customers must be at least 18. A compliance officer reviews each registration and verifies or rejects it; nobody can verify themselves. A customer who is not verified cannot open an account. National id and date of birth are personal data and must never appear in events, logs or messages.
