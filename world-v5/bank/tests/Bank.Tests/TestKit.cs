using Bank.Data;
using Bank.Modules.Accounts.Domain;
using Bank.Modules.Auth.Application;
using Bank.Modules.Ledger.Application;
using Bank.Modules.Ledger.Domain;
using Bank.Modules.Notifications.Application;
using Bank.Shared.Events;
using Bank.Shared.Settings;
using Bank.Shared.Time;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;

namespace Bank.Tests;

/// <summary>Helpers every test may use. Tests build state through these helpers and public services,
/// never through reflection or private members.</summary>
public static class TestKit
{
    /// <summary>A fresh in-memory SQLite database with the full schema, including the bank's own accounts.</summary>
    public static BankDbContext Db()
    {
        var connection = new SqliteConnection("DataSource=:memory:");
        connection.Open();
        var db = new BankDbContext(new DbContextOptionsBuilder<BankDbContext>().UseSqlite(connection).Options);
        db.Database.EnsureCreated();
        return db;
    }

    /// <summary>Adds a customer account (owner, currency) and, if balance &gt; 0, funds it through the Ledger
    /// from the bank's Suspense account. Returns the account id.</summary>
    public static Guid Account(BankDbContext db, string ownerId, decimal balance = 0m, string currency = "EUR")
    {
        var account = new Account
        {
            OwnerId = ownerId,
            Currency = currency,
            Iban = "FI00TEST" + Guid.NewGuid().ToString("N")[..10],
            OpenedAt = new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero),
        };
        db.Accounts.Add(account);
        db.SaveChanges();
        if (balance > 0)
            Ledger(db).PostTransferAsync(BankAccounts.For(BankAccountKind.Suspense, currency), account.Id, balance, "test funding")
                .GetAwaiter().GetResult();
        return account.Id;
    }

    /// <summary>The account's current balance, read fresh from the database.</summary>
    public static decimal Balance(BankDbContext db, Guid accountId)
    {
        db.ChangeTracker.Clear();
        return db.Accounts.AsNoTracking().Single(a => a.Id == accountId).Balance;
    }

    /// <summary>A real Ledger over the test database (events go to <paramref name="bus"/> or nowhere).</summary>
    public static ILedger Ledger(BankDbContext db, IEventBus? bus = null, IClock? clock = null) =>
        new Bank.Modules.Ledger.Application.Ledger(db, bus ?? new RecordingBus(), clock ?? new FakeClock());

    /// <summary>Bank settings with the given overrides.</summary>
    public static BankSettings Settings(string defaultCurrency = "EUR", decimal dailyTransferLimit = 10_000m) =>
        new() { DefaultCurrency = defaultCurrency, DailyTransferLimit = dailyTransferLimit };
}

/// <summary>A signed-in user with fixed roles.</summary>
public sealed class FakeUser : ICurrentUser
{
    private readonly string[] _roles;

    public FakeUser(string userId, params string[] roles)
    {
        UserId = userId;
        _roles = roles;
    }

    public string UserId { get; set; }
    public bool IsInRole(string role) => _roles.Contains(role);
}

/// <summary>A clock the test controls. Starts at 2026-03-15 10:00 UTC.</summary>
public sealed class FakeClock : IClock
{
    public DateTimeOffset UtcNow { get; set; } = new(2026, 3, 15, 10, 0, 0, TimeSpan.Zero);
    public void Advance(TimeSpan by) => UtcNow = UtcNow.Add(by);
}

/// <summary>Records published events instead of delivering them.</summary>
public sealed class RecordingBus : IEventBus
{
    public List<IDomainEvent> Events { get; } = new();

    public Task PublishAsync<TEvent>(TEvent e, CancellationToken ct = default) where TEvent : IDomainEvent
    {
        Events.Add(e);
        return Task.CompletedTask;
    }
}

/// <summary>Records notifications instead of sending them.</summary>
public sealed class RecordingNotifier : INotifier
{
    public List<(string CustomerId, string Message)> Sent { get; } = new();

    public Task NotifyAsync(string customerId, string message, CancellationToken ct = default)
    {
        Sent.Add((customerId, message));
        return Task.CompletedTask;
    }
}
