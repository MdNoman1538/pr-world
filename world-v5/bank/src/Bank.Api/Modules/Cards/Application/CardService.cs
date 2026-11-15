using System.Collections.Concurrent;
using Bank.Data;
using Bank.Modules.Accounts.Application;
using Bank.Modules.Auth.Application;
using Bank.Modules.Cards.Domain;
using Bank.Modules.Ledger.Application;
using Bank.Modules.Ledger.Domain;
using Bank.Shared.Events;
using Bank.Shared.Time;
using Microsoft.EntityFrameworkCore;

namespace Bank.Modules.Cards.Application;

public sealed record CardAuthorisation(bool Approved, string? DeclineReason, Guid? TransferId);

public interface ICardService
{
    Task<Card> IssueAsync(Guid accountId, CancellationToken ct = default);
    Task<Card> FreezeAsync(Guid cardId, CancellationToken ct = default);
    Task<Card> UnfreezeAsync(Guid cardId, CancellationToken ct = default);
    Task<Card> CancelAsync(Guid cardId, CancellationToken ct = default);
    Task<CardAuthorisation> AuthoriseAsync(Guid cardId, decimal amount, string merchant, CancellationToken ct = default);
}

public sealed class CardService : ICardService
{
    private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> AccountLocks = new();

    private readonly BankDbContext _db;
    private readonly ILedger _ledger;
    private readonly IAccountService _accounts;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly IEventBus _bus;

    public CardService(
        BankDbContext db,
        ILedger ledger,
        IAccountService accounts,
        ICurrentUser user,
        IClock clock,
        IEventBus bus)
    {
        _db = db;
        _ledger = ledger;
        _accounts = accounts;
        _user = user;
        _clock = clock;
        _bus = bus;
    }

    public async Task<Card> IssueAsync(Guid accountId, CancellationToken ct = default)
    {
        var customerId = _user.UserId;
        if (!await _accounts.IsOwnerAsync(accountId, customerId, ct))
            throw new UnauthorizedAccessException("Account is not owned by the caller.");

        var number = GenerateCardNumber();
        var last4 = number[^4..];

        var card = new Card
        {
            AccountId = accountId,
            CustomerId = customerId,
            Number = number,
            Last4 = last4,
            PerTransactionLimit = 2000m,
        };

        _db.Cards.Add(card);
        await _db.SaveChangesAsync(ct);
        await _bus.PublishAsync(new CardIssued(card.Id, customerId, last4, _clock.UtcNow), ct);
        return card;
    }

    public async Task<Card> FreezeAsync(Guid cardId, CancellationToken ct = default)
    {
        var card = await GetOwnedCardAsync(cardId, ct);
        card.Freeze();
        await _db.SaveChangesAsync(ct);
        return card;
    }

    public async Task<Card> UnfreezeAsync(Guid cardId, CancellationToken ct = default)
    {
        var card = await GetOwnedCardAsync(cardId, ct);
        card.Unfreeze();
        await _db.SaveChangesAsync(ct);
        return card;
    }

    public async Task<Card> CancelAsync(Guid cardId, CancellationToken ct = default)
    {
        var card = await GetOwnedCardAsync(cardId, ct);
        card.Cancel();
        await _db.SaveChangesAsync(ct);
        return card;
    }

    public async Task<CardAuthorisation> AuthoriseAsync(Guid cardId, decimal amount, string merchant, CancellationToken ct = default)
    {
        var roundedAmount = Math.Round(amount, 2, MidpointRounding.AwayFromZero);
        if (roundedAmount <= 0m)
            throw new ArgumentOutOfRangeException(nameof(amount), "Amount must be positive.");

        var card = await _db.Cards.FirstOrDefaultAsync(c => c.Id == cardId, ct)
            ?? throw new KeyNotFoundException($"Card {cardId} not found.");

        if (card.Status != CardStatus.Active)
        {
            const string reason = "card not active";
            await _bus.PublishAsync(new CardPaymentDeclined(card.Id, reason, _clock.UtcNow), ct);
            return new CardAuthorisation(false, reason, null);
        }

        if (roundedAmount > card.PerTransactionLimit)
        {
            const string reason = "over limit";
            await _bus.PublishAsync(new CardPaymentDeclined(card.Id, reason, _clock.UtcNow), ct);
            return new CardAuthorisation(false, reason, null);
        }

        var merchantName = merchant ?? "";
        var accountLock = AccountLocks.GetOrAdd(card.AccountId, _ => new SemaphoreSlim(1, 1));
        Guid? transferId;
        string currency;

        await accountLock.WaitAsync(ct);
        try
        {
            var account = await _accounts.GetAsync(card.AccountId, ct)
                ?? throw new KeyNotFoundException($"Account {card.AccountId} not found.");
            currency = account.Currency;
            var suspenseAccountId = BankAccounts.For(BankAccountKind.Suspense, currency);
            var reference = string.IsNullOrWhiteSpace(merchantName)
                ? $"Card payment {card.Last4}"
                : $"Card payment {card.Last4}: {merchantName}";

            try
            {
                transferId = await _ledger.PostTransferAsync(
                    card.AccountId,
                    suspenseAccountId,
                    roundedAmount,
                    reference,
                    ct);
            }
            catch (InsufficientFundsException)
            {
                transferId = null;
            }
        }
        finally
        {
            accountLock.Release();
        }

        if (transferId is null)
        {
            const string reason = "insufficient funds";
            await _bus.PublishAsync(new CardPaymentDeclined(card.Id, reason, _clock.UtcNow), ct);
            return new CardAuthorisation(false, reason, null);
        }

        await _bus.PublishAsync(
            new CardPaymentAuthorised(card.Id, roundedAmount, currency, merchantName, _clock.UtcNow),
            ct);
        return new CardAuthorisation(true, null, transferId);
    }

    private async Task<Card> GetOwnedCardAsync(Guid cardId, CancellationToken ct)
    {
        var card = await _db.Cards.FirstOrDefaultAsync(c => c.Id == cardId, ct)
            ?? throw new KeyNotFoundException($"Card {cardId} not found.");
        if (card.CustomerId != _user.UserId)
            throw new UnauthorizedAccessException("Card is not owned by the caller.");
        return card;
    }

    private static string GenerateCardNumber() =>
        "4" + Random.Shared.NextInt64(0, 1_000_000_000_000_000L).ToString("D15");
}
