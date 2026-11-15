# PR-8: PR-8: Monthly account statements (API and StatementService)

**Story.** As a bank customer or authorized staff member, I want to retrieve a monthly account statement for a given calendar month in UTC, showing the opening balance, chronological ledger entries with running balances, and the closing balance, so that account activity and balances can be accurately reviewed.

## Acceptance criteria
- [ ] Implement Bank.Modules.Statements following the module layout (Api, Application, StatementsModule) and register AddStatementsModule in Program.cs above the // MODULES: marker.
- [ ] Expose the agreed public contract in namespace Bank.Modules.Statements.Application: StatementLine(DateTimeOffset At, decimal Amount, decimal BalanceAfter, string Reference), Statement(Guid AccountId, int Year, int Month, string Currency, decimal OpeningBalance, decimal ClosingBalance, IReadOnlyList<StatementLine> Lines), IStatementService with ForMonthAsync(Guid accountId, int year, int month, CancellationToken ct = default), and StatementService(ILedger ledger, IAccountService accounts, ICurrentUser user).
- [ ] Expose GET api/accounts/{id}/statements/{year}/{month} on a controller decorated with [ApiController] and [Authorize(Policy = Policies.Customer)], returning HTTP 200 OK with the Statement payload.
- [ ] Month boundaries are strictly UTC: include entries with timestamp >= YYYY-MM-01T00:00:00Z and < (YYYY-MM-01 + 1 month)T00:00:00Z; entries at exactly 00:00:00Z on the 1st of the next month belong to the next month and are excluded.
- [ ] Invalid calendar inputs (such as month < 1 or > 12, or year < 1 or > 9999) are rejected with ArgumentOutOfRangeException (mapped to HTTP 400 Bad Request).
- [ ] OpeningBalance equals the sum of all ledger entries for the account strictly before YYYY-MM-01T00:00:00Z (0.00m if none), rounded to 2 decimal places using Math.Round(x, 2, MidpointRounding.AwayFromZero).
- [ ] Lines are ordered chronologically by At ascending, and each line's BalanceAfter equals the prior balance plus that line's signed Amount, rounded to 2 decimal places with MidpointRounding.AwayFromZero.
- [ ] ClosingBalance equals OpeningBalance plus the sum of all Line Amounts in the month (when there are no entries in the month, Lines is empty and ClosingBalance equals OpeningBalance), and Statement.Currency matches the account's currency.
- [ ] If the account does not exist, ForMonthAsync throws KeyNotFoundException (mapped to HTTP 404 Not Found).
- [ ] If the current user is neither the owner of the account (via IAccountService.IsOwnerAsync) nor in a staff role (Teller, LoanOfficer, ComplianceOfficer, or Admin in Bank.Modules.Auth.Roles), ForMonthAsync throws UnauthorizedAccessException (mapped to HTTP 403 Forbidden).
- [ ] Unauthenticated requests to GET api/accounts/{id}/statements/{year}/{month} are rejected with HTTP 401 Unauthorized.
- [ ] Statement generation is strictly read-only: it never modifies Account.Balance and never posts ledger transfers.

## Out of scope
- Exporting or rendering statements as PDF, CSV, HTML, or other downloadable file formats.
- Persisting or caching generated monthly statement snapshots in a database table or emailing statements to customers.
- Custom date range queries, rolling 30-day statements, or timezone conversions outside UTC.
- Pagination, sorting options, or filtering of statement lines by amount or reference.
- Charging statement fees or performing currency conversions.

## Risks
- Broken object-level authorization (IDOR) if ownership or staff-role verification is flawed, allowing a customer to view another customer's balances and transaction references.
- Off-by-one boundary bugs at month rollover (e.g., using <= instead of < for next month's 1st at 00:00 UTC or using local time instead of UTC), causing entries at midnight UTC to be duplicated across months or omitted and breaking OpeningBalance + month entries = ClosingBalance.
- Non-deterministic line ordering when multiple ledger entries share the same At timestamp, producing inconsistent BalanceAfter values across calls.
- Using Account.Balance directly instead of computing OpeningBalance and ClosingBalance from ledger history, which would fail for past months or after subsequent transactions.
- Precision or rounding discrepancies if non-decimal arithmetic is used or Math.Round(..., 2, MidpointRounding.AwayFromZero) is omitted.
- Performance degradation if an account has a large ledger history and entries are not filtered or queried efficiently.

## Public contract
```
namespace Bank.Modules.Statements.Application:
  sealed record StatementLine(DateTimeOffset At, decimal Amount, decimal BalanceAfter, string Reference)
  sealed record Statement(Guid AccountId, int Year, int Month, string Currency, decimal OpeningBalance, decimal ClosingBalance,
                          IReadOnlyList<StatementLine> Lines)
  interface IStatementService { Task<Statement> ForMonthAsync(Guid accountId, int year, int month, CancellationToken ct = default); }
      // unknown account -> KeyNotFoundException; not owner and not staff (teller, loan officer, compliance officer, admin) -> UnauthorizedAccessException
  sealed class StatementService(ILedger ledger, IAccountService accounts, ICurrentUser user) : IStatementService
HTTP: GET api/accounts/{id}/statements/{year}/{month} (Customer)
```

## Allowed scope
- `src/Bank.Api/Modules/Statements/**`
- `src/Bank.Api/Program.cs`

_Brief from the product owner:_ A customer can get a statement for one of their accounts for a calendar month: the opening balance, every entry of the month with the balance after it, and the closing balance. The month runs from the 1st at 00:00 UTC up to (not including) the 1st of the next month. Opening balance + the month's entries = closing balance. Staff can read any statement; customers only their own.
