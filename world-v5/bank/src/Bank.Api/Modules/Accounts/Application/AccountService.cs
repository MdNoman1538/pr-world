using Bank.Data;
using Bank.Modules.Accounts.Domain;
using Bank.Modules.Auth.Application;
using Bank.Shared.Events;
using Bank.Shared.Settings;
using Bank.Shared.Time;
using Microsoft.EntityFrameworkCore;

namespace Bank.Modules.Accounts.Application;

public interface IAccountService
{
    Task<Account?> GetAsync(Guid accountId, CancellationToken ct = default);
    Task<bool> IsOwnerAsync(Guid accountId, string userId, CancellationToken ct = default);
    Task<IReadOnlyList<Account>> ForOwnerAsync(string ownerId, CancellationToken ct = default);
    /// <summary>Opens an account for the signed-in user. Null currency means BankSettings.DefaultCurrency.</summary>
    Task<Account> OpenAsync(string? currency, CancellationToken ct = default);
}

/// <summary>Extension point: other modules can veto opening an account (e.g. identity checks).</summary>
public interface IAccountOpeningRule
{
    Task EnsureMayOpenAsync(string ownerId, CancellationToken ct = default);
}

public sealed class AccountService : IAccountService
{
    private readonly BankDbContext _db;
    private readonly ICurrentUser _user;
    private readonly BankSettings _settings;
    private readonly IClock _clock;
    private readonly IEventBus _bus;
    private readonly IEnumerable<IAccountOpeningRule> _rules;

    public AccountService(BankDbContext db, ICurrentUser user, BankSettings settings, IClock clock, IEventBus bus,
        IEnumerable<IAccountOpeningRule> rules)
    {
        _db = db;
        _user = user;
        _settings = settings;
        _clock = clock;
        _bus = bus;
        _rules = rules;
    }

    public Task<Account?> GetAsync(Guid accountId, CancellationToken ct = default) =>
        _db.Accounts.FirstOrDefaultAsync(a => a.Id == accountId, ct);

    public Task<bool> IsOwnerAsync(Guid accountId, string userId, CancellationToken ct = default) =>
        _db.Accounts.AnyAsync(a => a.Id == accountId && a.OwnerId == userId, ct);

    public async Task<IReadOnlyList<Account>> ForOwnerAsync(string ownerId, CancellationToken ct = default) =>
        await _db.Accounts.Where(a => a.OwnerId == ownerId).ToListAsync(ct);

    public async Task<Account> OpenAsync(string? currency, CancellationToken ct = default)
    {
        var owner = _user.UserId;
        var cur = (currency ?? _settings.DefaultCurrency).ToUpperInvariant();
        if (!_settings.SupportedCurrencies.Contains(cur))
            throw new ArgumentException($"Currency {cur} is not supported.", nameof(currency));
        foreach (var rule in _rules)
            await rule.EnsureMayOpenAsync(owner, ct);

        var account = new Account
        {
            OwnerId = owner,
            Currency = cur,
            Iban = "FI" + Random.Shared.NextInt64(10_000_000_000_000_000, 99_999_999_999_999_999),
            OpenedAt = _clock.UtcNow,
        };
        _db.Accounts.Add(account);
        await _db.SaveChangesAsync(ct);
        await _bus.PublishAsync(new AccountOpened(account.Id, owner, cur, _clock.UtcNow), ct);
        return account;
    }
}
