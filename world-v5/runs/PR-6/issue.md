# PR-6: PR-6: Term deposits module (open, mature, and early break)

**Story.** As a bank customer, I want to lock funds into a 3, 6, or 12-month term deposit at a fixed annual interest rate and either collect my principal plus simple interest at maturity or break the deposit early to recover my principal only, so that I can earn predictable interest on locked savings.

## Acceptance criteria
- [ ] Module and persistence follow Nordbank conventions: Bank.Modules.Deposits with Domain, Application, Api layers, DepositsModule.AddDepositsModule registered in Program.cs above // MODULES:, and DbSet<TermDeposit> TermDeposits registered in BankDbContext above // TABLES:.
- [ ] Public contract matches the agreed types and signatures in Bank.Modules.Deposits.Domain (DepositStatus, TermDeposit with parameterless constructor and private setter on Status, DepositOpened, DepositClosed) and Bank.Modules.Deposits.Application (IDepositService, DepositService).
- [ ] Opening a deposit via POST api/deposits (Policies.Customer) or IDepositService.OpenAsync verifies via IAccountService.IsOwnerAsync that ICurrentUser.UserId owns accountId; non-owners throw UnauthorizedAccessException.
- [ ] OpenAsync validates principal >= 500m and termMonths is 3 (2.0% annual rate), 6 (2.5% annual rate), or 12 (3.0% annual rate); any principal below 500m or other term length throws ArgumentException.
- [ ] OpenAsync derives CustomerId from ICurrentUser.UserId and Currency from the source account, transfers principal from accountId to BankAccounts.For(BankAccountKind.DepositHolding, currency) via ILedger.PostTransferAsync, sets OpenedAt = clock.UtcNow, MaturesAt = OpenedAt.AddMonths(termMonths), Status = DepositStatus.Open, InterestPaid = 0m, persists the TermDeposit, and publishes DepositOpened.
- [ ] Maturing a deposit via POST api/deposits/{id}/mature (Policies.Staff) or IDepositService.MatureAsync performs no owner check and throws InvalidOperationException if the deposit is not Open or if clock.UtcNow < MaturesAt.
- [ ] MatureAsync computes simple interest using decimal arithmetic as Math.Round(Principal * (AnnualRatePercent / 100m) * TermMonths / 12m, 2, MidpointRounding.AwayFromZero), transfers Principal from DepositHolding to AccountId and InterestPaid from InterestExpense to AccountId in the deposit's currency via ILedger.PostTransferAsync, transitions Status to DepositStatus.Matured, sets InterestPaid, and publishes DepositClosed with Early = false.
- [ ] Breaking a deposit via POST api/deposits/{id}/break (Policies.Customer) or IDepositService.BreakAsync checks that ICurrentUser.UserId owns the deposit (throwing UnauthorizedAccessException otherwise) and throws InvalidOperationException if Status is not DepositStatus.Open.
- [ ] BreakAsync transfers Principal only from DepositHolding to AccountId via ILedger.PostTransferAsync, transitions Status to DepositStatus.BrokenEarly with InterestPaid = 0m, and publishes DepositClosed with Early = true.
- [ ] All time checks use IClock.UtcNow (never DateTime.Now or DateTimeOffset.UtcNow), all currency movement goes through ILedger.PostTransferAsync without editing Account.Balance directly, and no PII is included in domain events or logs.
- [ ] Automated xUnit tests verify: 3/6/12-month rate mapping and interest rounding half away from zero, principal < 500 and invalid term rejection, owner enforcement on open and break, Staff-only maturity enforcement, rejection of premature maturity, rejection of breaking or maturing an already closed deposit, and ledger balances across Customer, DepositHolding, and InterestExpense accounts.

## Out of scope
- Background scheduler or automatic timer job to invoke MatureAsync automatically at maturity
- Partial withdrawals from an active term deposit or topping up an existing deposit
- Early-break penalty fees beyond forfeiting accrued interest
- Automatic renewal or rollover of principal and interest into a new term deposit at maturity
- Custom or promotional interest rates and terms other than 3, 6, or 12 months
- Query/GET endpoints for listing or fetching term deposits
- Tax withholding or reporting on interest paid

## Risks
- Double-payout or race condition: concurrent MatureAsync and BreakAsync calls (or repeated calls) on the same Open deposit could pay out principal or interest twice if state transitions and persistence are not strictly guarded.
- Partial failure between ledger and database: if ILedger.PostTransferAsync succeeds for principal or interest but saving the TermDeposit status fails (or vice versa), bank internal accounts (DepositHolding, InterestExpense) and deposit state will become inconsistent.
- Interest calculation defects: integer division on TermMonths / 12, omitting division by 100m on AnnualRatePercent, or using banker's rounding instead of MidpointRounding.AwayFromZero would miscalculate customer payouts.
- Authorization bypass: allowing a Customer to invoke the Staff mature endpoint or failing to verify deposit/account ownership on open and break could allow unauthorized locking of another user's funds or premature interest payout.
- Premature maturity or test flakiness: bypassing IClock or evaluating MaturesAt inaccurately could allow customers to collect unearned interest before the term ends.
- Currency mismatch: using BankSettings.DefaultCurrency instead of the source account's Currency when addressing DepositHolding or InterestExpense would fail or corrupt multi-currency ledger entries.

## Public contract
```
namespace Bank.Modules.Deposits.Domain:
  enum DepositStatus { Open, Matured, BrokenEarly }
  sealed class TermDeposit { Guid Id; string CustomerId; Guid AccountId; decimal Principal; string Currency; int TermMonths;
                             decimal AnnualRatePercent; DateTimeOffset OpenedAt; DateTimeOffset MaturesAt; DepositStatus Status; decimal InterestPaid }
  sealed record DepositOpened(Guid DepositId, string CustomerId, decimal Principal, int TermMonths, DateTimeOffset OccurredAt) : IDomainEvent
  sealed record DepositClosed(Guid DepositId, string CustomerId, decimal InterestPaid, bool Early, DateTimeOffset OccurredAt) : IDomainEvent
namespace Bank.Modules.Deposits.Application:
  interface IDepositService {
    Task<TermDeposit> OpenAsync(Guid accountId, decimal principal, int termMonths, CancellationToken ct = default);
        // not owner -> UnauthorizedAccessException; principal < 500 or term not 3/6/12 -> ArgumentException
    Task<TermDeposit> MatureAsync(Guid depositId, CancellationToken ct = default);   // before MaturesAt or not Open -> InvalidOperationException (runs as a bank job: no owner check)
    Task<TermDeposit> BreakAsync(Guid depositId, CancellationToken ct = default); }  // owner only; not Open -> InvalidOperationException
  sealed class DepositService(BankDbContext db, ILedger ledger, IAccountService accounts, ICurrentUser user, IClock clock, IEventBus bus) : IDepositService
BankDbContext gets: DbSet<TermDeposit> TermDeposits
HTTP: POST api/deposits, POST api/deposits/{id}/break (Customer); POST api/deposits/{id}/mature (Staff)
```

## Allowed scope
- `src/Bank.Api/Modules/Deposits/**`
- `src/Bank.Api/Data/BankDbContext.cs`
- `src/Bank.Api/Program.cs`

_Brief from the product owner:_ Customers can lock money in a term deposit for 3, 6 or 12 months at 2.0%, 2.5% or 3.0% a year; the minimum is 500. Opening moves the money from their account to the bank's DepositHolding account. At maturity the customer gets the principal back plus simple interest (principal x rate x months / 12, rounded to cents half away from zero) paid from InterestExpense. Breaking a deposit before maturity returns the principal only. Only the owner can open or break.
