# PR-7: PR-7: Loans module with annuity calculation and four-eyes approval

**Story.** As a verified customer, I want to apply for a fixed-rate loan disbursed to one of my accounts and be notified of the decision, so that I can borrow funds safely while a different loan officer independently reviews and approves or rejects my application.

## Acceptance criteria
- [ ] Module Bank.Modules.Loans is implemented with Api, Application, Domain layers, LoansModule registration in Program.cs, and DbSet<Loan> Loans added to BankDbContext.
- [ ] Loan entity in Bank.Modules.Loans.Domain owns Status (LoanStatus: Submitted, Rejected, Disbursed) with a private setter, transitions state only via domain methods that validate current status, and includes a parameterless constructor and public settable non-status properties.
- [ ] POST api/loans (Policies.Customer) delegates to ILoanService.ApplyAsync using ICurrentUser.UserId as CustomerId and IClock.UtcNow as AppliedAt, ignoring any user id supplied in request bodies.
- [ ] ILoanService.ApplyAsync validates that Principal is between 1000m and 50000m inclusive and TermMonths is between 6 and 120 inclusive, throwing ArgumentException when out of range.
- [ ] ILoanService.ApplyAsync verifies via IAccountService.IsOwnerAsync that DisbursementAccountId belongs to the caller, throwing UnauthorizedAccessException if not owned.
- [ ] ILoanService.ApplyAsync sets AnnualRatePercent to 5.5m and calculates MonthlyPayment using the standard monthly annuity formula P * r / (1 - (1 + r)^(-n)) with monthly rate r = 0.055m / 12m, rounded to 2 decimal places using Math.Round(value, 2, MidpointRounding.AwayFromZero).
- [ ] ILoanService.ApplyAsync persists the Loan in Submitted status and publishes LoanSubmitted via IEventBus.PublishAsync.
- [ ] GET api/loans/{id} (Policies.Customer) calls ILoanService.GetAsync, which throws KeyNotFoundException if the loan does not exist, and throws UnauthorizedAccessException if the caller is neither the Loan.CustomerId nor in Roles.LoanOfficer.
- [ ] POST api/loans/{id}/approve (Policies.LoanOfficer) calls ILoanService.ApproveAsync, which throws KeyNotFoundException if not found, UnauthorizedAccessException if the caller is not in Roles.LoanOfficer or if caller UserId equals Loan.CustomerId (four-eyes check), and InvalidOperationException if Loan.Status is not Submitted.
- [ ] ILoanService.ApproveAsync transitions the loan to Disbursed, records DecidedBy (caller UserId) and optional DecisionNote, resolves the disbursement account currency via IAccountService.GetAsync, and transfers Principal from BankAccounts.For(BankAccountKind.LoanFunding, account.Currency) to Loan.DisbursementAccountId via ILedger.PostTransferAsync.
- [ ] ILoanService.ApproveAsync publishes LoanApproved via IEventBus.PublishAsync and notifies the customer via INotifier with a message containing no personal data (no name, email, account details, or other PII).
- [ ] POST api/loans/{id}/reject (Policies.LoanOfficer) calls ILoanService.RejectAsync, which enforces the same LoanOfficer role, four-eyes check (UnauthorizedAccessException), and Submitted status check (InvalidOperationException), and throws ArgumentException if reason is null, empty, or whitespace.
- [ ] ILoanService.RejectAsync transitions the loan to Rejected, records DecidedBy and DecisionNote, publishes LoanRejected via IEventBus.PublishAsync, and notifies the customer via INotifier without any personal data in the message.
- [ ] Automated xUnit tests cover range validation, annuity rounding, ownership enforcement, four-eyes rejection of self-approval/self-rejection, invalid state transitions, ledger disbursement in the account currency, domain event publishing, and PII-free notifications.

## Out of scope
- Loan repayment processing, installment collection, or amortization schedule generation.
- Collection or search endpoints such as GET api/loans for listing or filtering multiple loans.
- Variable interest rates, custom interest rates per customer, credit scoring, or external KYC verification workflows.
- Cross-currency loan disbursement or FX conversion between LoanFunding and the disbursement account.
- Early loan payoff, loan restructuring, or cancellation of a submitted loan by the customer.

## Risks
- Four-eyes control bypass: if a loan officer can approve or reject their own loan, internal fraud or unauthorized fund disbursement becomes possible.
- Double disbursement race condition: concurrent approval requests could disburse principal multiple times if the Submitted status transition and persistence are not atomic.
- Currency mismatch or ledger failure: using the wrong currency for BankAccounts.For(BankAccountKind.LoanFunding, currency) instead of the disbursement account's currency will fail or corrupt accounting balances.
- Annuity calculation or rounding error: using floating-point math instead of decimal or incorrect rounding mode could misstate monthly payments and cause regulatory or customer disputes.
- PII leakage: including customer identifiers, names, or account information in INotifier messages or logs violates bank privacy and compliance rules.

## Public contract
```
namespace Bank.Modules.Loans.Domain:
  enum LoanStatus { Submitted, Rejected, Disbursed }
  sealed class Loan { Guid Id; string CustomerId; Guid DisbursementAccountId; decimal Principal; int TermMonths; decimal AnnualRatePercent;
                      decimal MonthlyPayment; LoanStatus Status; string? DecidedBy; string? DecisionNote; DateTimeOffset AppliedAt }
  sealed record LoanSubmitted(Guid LoanId, string CustomerId, decimal Principal, DateTimeOffset OccurredAt) : IDomainEvent
  sealed record LoanApproved(Guid LoanId, string CustomerId, decimal Principal, DateTimeOffset OccurredAt) : IDomainEvent
  sealed record LoanRejected(Guid LoanId, string CustomerId, DateTimeOffset OccurredAt) : IDomainEvent
namespace Bank.Modules.Loans.Application:
  sealed record LoanApplication(Guid DisbursementAccountId, decimal Principal, int TermMonths)
  interface ILoanService {
    Task<Loan> ApplyAsync(LoanApplication application, CancellationToken ct = default);
        // out-of-range amount/term -> ArgumentException; account not owned by caller -> UnauthorizedAccessException
    Task<Loan> GetAsync(Guid loanId, CancellationToken ct = default);     // unknown -> KeyNotFoundException; not owner and not loan officer -> UnauthorizedAccessException
    Task<Loan> ApproveAsync(Guid loanId, string? note, CancellationToken ct = default);
        // not a loan officer, or the officer is the borrower -> UnauthorizedAccessException; not Submitted -> InvalidOperationException
    Task<Loan> RejectAsync(Guid loanId, string reason, CancellationToken ct = default); }   // same rules; empty reason -> ArgumentException
  sealed class LoanService(BankDbContext db, ILedger ledger, IAccountService accounts, ICurrentUser user, IClock clock,
                           IEventBus bus, INotifier notifier) : ILoanService
BankDbContext gets: DbSet<Loan> Loans
HTTP: POST api/loans, GET api/loans/{id} (Customer); POST api/loans/{id}/approve|reject (LoanOfficer)
```

## Allowed scope
- `src/Bank.Api/Modules/Loans/**`
- `src/Bank.Api/Data/BankDbContext.cs`
- `src/Bank.Api/Program.cs`

_Brief from the product owner:_ A verified customer applies for a loan of 1,000-50,000 over 6-120 months, paid out to one of their own accounts, at 5.5% a year. The monthly payment uses the annuity formula, rounded to cents half away from zero. Customers can see their own loans; loan officers can see all. A loan officer approves or rejects a submitted loan with a note; an officer must never decide on their own loan. Approval pays the principal from the bank's LoanFunding account (in the account's currency) and the loan becomes Disbursed; the customer is notified without any personal data in the message.
