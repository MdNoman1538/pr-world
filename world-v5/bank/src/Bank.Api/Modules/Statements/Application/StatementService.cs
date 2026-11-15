using Bank.Modules.Accounts.Application;
using Bank.Modules.Auth;
using Bank.Modules.Auth.Application;
using Bank.Modules.Ledger.Application;

namespace Bank.Modules.Statements.Application;

public sealed record StatementLine(DateTimeOffset At, decimal Amount, decimal BalanceAfter, string Reference);

public sealed record Statement(
    Guid AccountId,
    int Year,
    int Month,
    string Currency,
    decimal OpeningBalance,
    decimal ClosingBalance,
    IReadOnlyList<StatementLine> Lines);

public interface IStatementService
{
    Task<Statement> ForMonthAsync(Guid accountId, int year, int month, CancellationToken ct = default);
}

public sealed class StatementService(ILedger ledger, IAccountService accounts, ICurrentUser user) : IStatementService
{
    public async Task<Statement> ForMonthAsync(Guid accountId, int year, int month, CancellationToken ct = default)
    {
        if (year < 1 || year > 9999)
            throw new ArgumentOutOfRangeException(nameof(year), "Year must be between 1 and 9999.");
        if (month < 1 || month > 12)
            throw new ArgumentOutOfRangeException(nameof(month), "Month must be between 1 and 12.");

        var account = await accounts.GetAsync(accountId, ct)
            ?? throw new KeyNotFoundException($"Account {accountId} not found.");

        var isAuthorized = IsStaff() || await accounts.IsOwnerAsync(accountId, user.UserId, ct);
        if (!isAuthorized)
            throw new UnauthorizedAccessException("Caller is not authorized to view this statement.");

        var monthStart = new DateTimeOffset(year, month, 1, 0, 0, 0, TimeSpan.Zero);
        var monthEnd = year == 9999 && month == 12
            ? DateTimeOffset.MaxValue
            : monthStart.AddMonths(1);

        var priorEntries = await ledger.EntriesAsync(accountId, DateTimeOffset.MinValue, monthStart, ct);
        var openingBalance = Math.Round(priorEntries.Sum(e => e.Amount), 2, MidpointRounding.AwayFromZero);

        var monthEntries = await ledger.EntriesAsync(accountId, monthStart, monthEnd, ct);
        var orderedEntries = monthEntries.OrderBy(e => e.CreatedAt).ToList();

        var lines = new List<StatementLine>(orderedEntries.Count);
        var runningBalance = openingBalance;
        foreach (var entry in orderedEntries)
        {
            var amount = Math.Round(entry.Amount, 2, MidpointRounding.AwayFromZero);
            runningBalance = Math.Round(runningBalance + amount, 2, MidpointRounding.AwayFromZero);
            lines.Add(new StatementLine(entry.CreatedAt, amount, runningBalance, entry.Reference));
        }

        var closingBalance = Math.Round(openingBalance + lines.Sum(l => l.Amount), 2, MidpointRounding.AwayFromZero);

        return new Statement(
            accountId,
            year,
            month,
            account.Currency,
            openingBalance,
            closingBalance,
            lines);
    }

    private bool IsStaff() =>
        user.IsInRole(Roles.Teller) ||
        user.IsInRole(Roles.LoanOfficer) ||
        user.IsInRole(Roles.ComplianceOfficer) ||
        user.IsInRole(Roles.Admin);
}
