using Bank.Data;
using Bank.Modules.Ledger.Domain;
using Bank.Shared.Events;
using Bank.Shared.Time;
using Microsoft.EntityFrameworkCore;

namespace Bank.Modules.Ledger.Application;

/// <summary>The only way money moves. Every posting is double-entry and in one currency.</summary>
public interface ILedger
{
    /// <summary>Moves <paramref name="amount"/> between two accounts of the SAME currency and returns the transfer id.
    /// Throws InsufficientFundsException if a customer account would go below zero,
    /// CurrencyMismatchException if the currencies differ, ArgumentOutOfRangeException if amount is not positive.</summary>
    Task<Guid> PostTransferAsync(Guid fromAccountId, Guid toAccountId, decimal amount, string reference, CancellationToken ct = default);

    /// <summary>Entries of one account with fromInclusive &lt;= CreatedAt &lt; toExclusive, oldest first.</summary>
    Task<IReadOnlyList<LedgerEntry>> EntriesAsync(Guid accountId, DateTimeOffset fromInclusive, DateTimeOffset toExclusive, CancellationToken ct = default);
}

public sealed class InsufficientFundsException : InvalidOperationException
{
    public InsufficientFundsException(Guid accountId) : base($"Account {accountId} has insufficient funds.") { }
}

public sealed class CurrencyMismatchException : InvalidOperationException
{
    public CurrencyMismatchException(string from, string to) : base($"Cannot post {from} to a {to} account: convert first.") { }
}

public sealed class Ledger : ILedger
{
    private readonly BankDbContext _db;
    private readonly IEventBus _bus;
    private readonly IClock _clock;

    public Ledger(BankDbContext db, IEventBus bus, IClock clock)
    {
        _db = db;
        _bus = bus;
        _clock = clock;
    }

    public async Task<Guid> PostTransferAsync(Guid fromAccountId, Guid toAccountId, decimal amount, string reference, CancellationToken ct = default)
    {
        if (amount <= 0)
            throw new ArgumentOutOfRangeException(nameof(amount), "Amount must be positive.");
        if (decimal.Round(amount, 2) != amount)
            throw new ArgumentException("Amount must be whole cents.", nameof(amount));
        if (fromAccountId == toAccountId)
            throw new InvalidOperationException("Cannot transfer to the same account.");

        var from = await _db.Accounts.FindAsync(new object[] { fromAccountId }, ct)
                   ?? throw new KeyNotFoundException($"Account {fromAccountId} not found.");
        var to = await _db.Accounts.FindAsync(new object[] { toAccountId }, ct)
                 ?? throw new KeyNotFoundException($"Account {toAccountId} not found.");
        if (from.Currency != to.Currency)
            throw new CurrencyMismatchException(from.Currency, to.Currency);
        if (!from.AllowOverdraft && from.Balance < amount)
            throw new InsufficientFundsException(fromAccountId);

        var now = _clock.UtcNow;
        var transferId = Guid.NewGuid();
        from.Balance -= amount;
        to.Balance += amount;
        _db.LedgerEntries.Add(new LedgerEntry { TransferId = transferId, AccountId = fromAccountId, Amount = -amount, Currency = from.Currency, BalanceAfter = from.Balance, Reference = reference, CreatedAt = now });
        _db.LedgerEntries.Add(new LedgerEntry { TransferId = transferId, AccountId = toAccountId, Amount = amount, Currency = to.Currency, BalanceAfter = to.Balance, Reference = reference, CreatedAt = now });
        await _db.SaveChangesAsync(ct);

        await _bus.PublishAsync(new TransferPosted(transferId, fromAccountId, toAccountId, amount, from.Currency, reference, now), ct);
        return transferId;
    }

    public async Task<IReadOnlyList<LedgerEntry>> EntriesAsync(Guid accountId, DateTimeOffset fromInclusive, DateTimeOffset toExclusive, CancellationToken ct = default) =>
        await _db.LedgerEntries
            .Where(e => e.AccountId == accountId && e.CreatedAt >= fromInclusive && e.CreatedAt < toExclusive)
            .OrderBy(e => e.CreatedAt)
            .ToListAsync(ct);
}
