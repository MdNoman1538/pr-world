# PR-5: PR-5: Implement Debit Cards Module (Issue, Lifecycle, and Payment Authorisation)

**Story.** As a bank customer, I want to obtain a debit card for my account and freeze, unfreeze, or permanently cancel it, and as the bank acting on card network requests, I want to authorise or decline card payments against card status, per-transaction limit, and account balance while holding authorised funds in Suspense.

## Acceptance criteria
- [ ] Module structure and registration: Cards module lives under src/Bank.Api/Modules/Cards with Api, Application, Domain folders and CardsModule.cs, registered in Program.cs above // MODULES: and DbSet<Card> Cards added to BankDbContext above // TABLES:.
- [ ] Card issuance (POST api/cards, Customer policy): Authenticated customer calls ICardService.IssueAsync(accountId). Caller ownership is verified via IAccountService.IsOwnerAsync(accountId, currentUser.UserId); non-owners receive UnauthorizedAccessException. Creates an Active Card with a generated 16-digit Number annotated with [Pii], Last4 equal to the last 4 digits of Number, PerTransactionLimit of 2000m, CustomerId from ICurrentUser.UserId, and publishes CardIssued(CardId, CustomerId, Last4, clock.UtcNow).
- [ ] Card lifecycle (POST api/cards/{id}/freeze, /unfreeze, /cancel, Customer policy): FreezeAsync, UnfreezeAsync, and CancelAsync verify card.CustomerId == currentUser.UserId via ICurrentUser (throwing UnauthorizedAccessException otherwise) and invoke Card.Freeze(), Card.Unfreeze(), or Card.Cancel().
- [ ] Card state machine: CardStatus is Active, Frozen, or Cancelled with a private setter on Card.Status. Once Cancelled, any call to Freeze(), Unfreeze(), or Cancel() throws InvalidOperationException.
- [ ] Card payment authorisation (POST api/cards/{id}/authorise, Staff policy): Calls ICardService.AuthoriseAsync(cardId, amount, merchant) with no customer ownership check. Input amount is decimal and rounded to 2 decimal places using Math.Round(amount, 2, MidpointRounding.AwayFromZero). Amounts less than or equal to 0 after rounding are rejected.
- [ ] Authorisation decline rules (returned as CardAuthorisation(false, reason, null) with HTTP 200, not thrown as errors, and publishing CardPaymentDeclined(CardId, reason, clock.UtcNow)): (1) if Card.Status is not Active, decline with reason "card not active"; (2) if rounded amount exceeds Card.PerTransactionLimit (2000m in the account currency), decline with reason "over limit"; (3) if the account lacks sufficient funds when posting the transfer, decline with reason "insufficient funds".
- [ ] Authorisation approval rules: When the card is Active, rounded amount is within 2000m, and the account has sufficient funds, funds move strictly via ILedger.PostTransferAsync from card.AccountId to BankAccounts.For(BankAccountKind.Suspense, account.Currency) for the rounded amount. Returns CardAuthorisation(true, null, transferId) and publishes CardPaymentAuthorised(CardId, roundedAmount, account.Currency, merchant, clock.UtcNow).
- [ ] PII protection and data handling: Card.Number is marked [Pii] and is never returned in any API response DTO, domain event, log message, or error message; API responses expose only Last4. All timestamps use IClock.UtcNow and Account.Balance is never modified directly.

## Out of scope
- Payment settlement, clearing, capture, refunds, or reversals out of the Suspense account.
- Custom or user-configurable per-transaction limits, daily/monthly spending caps, or ATM/cash withdrawal limits.
- PIN generation or verification, CVV/CVC handling, card expiry dates, or physical card production and shipping.
- Multi-currency card payments or FX conversion during authorisation.
- GET endpoints for listing cards or retrieving card details, and replacing or reissuing cancelled cards.
- Direct integration with external card schemes (Visa, Mastercard) or ISO 8583 messaging.

## Risks
- PII leakage: Returning Card.Number in API DTOs or logging full 16-digit card numbers would expose personal data and violate banking security standards.
- Authorization bypass or misconfiguration: Omitting ownership checks on Issue, Freeze, Unfreeze, or Cancel allows one customer to tamper with another customer's cards, while mistakenly adding an ownership check to AuthoriseAsync would break Staff/card-network authorisations.
- Double-spend / overdraft race condition: If balance verification and ILedger.PostTransferAsync are not atomic under concurrent AuthoriseAsync calls, multiple simultaneous payments could overdraw the customer's account.
- Broken terminal state enforcement: Allowing a Cancelled card to be unfrozen or used for payments enables fraudulent transactions on permanently closed cards.
- Incorrect ledger currency or error handling: Posting to Suspense in a hardcoded currency instead of the linked account's currency would corrupt ledger balances, and throwing HTTP exceptions on declines instead of returning CardAuthorisation would break card-network protocol expectations.
- Rounding discrepancies: Failing to apply MidpointRounding.AwayFromZero consistently before both the 2000m limit check and the ledger transfer could allow fractional-cent amounts to bypass limits or fail settlement.

## Public contract
```
namespace Bank.Modules.Cards.Domain:
  enum CardStatus { Active, Frozen, Cancelled }
  sealed class Card { Guid Id; Guid AccountId; string CustomerId; [Pii] string Number (16 digits); string Last4;
                      CardStatus Status { get; private set; }; decimal PerTransactionLimit (2000);
                      void Freeze(); void Unfreeze(); void Cancel(); }   // Cancelled is final: any change after it -> InvalidOperationException
  sealed record CardIssued(Guid CardId, string CustomerId, string Last4, DateTimeOffset OccurredAt) : IDomainEvent
  sealed record CardPaymentAuthorised(Guid CardId, decimal Amount, string Currency, string Merchant, DateTimeOffset OccurredAt) : IDomainEvent
  sealed record CardPaymentDeclined(Guid CardId, string Reason, DateTimeOffset OccurredAt) : IDomainEvent
namespace Bank.Modules.Cards.Application:
  sealed record CardAuthorisation(bool Approved, string? DeclineReason, Guid? TransferId)   // reasons: "card not active", "over limit", "insufficient funds"
  interface ICardService {
    Task<Card> IssueAsync(Guid accountId, CancellationToken ct = default);   // account not owned by caller -> UnauthorizedAccessException
    Task<Card> FreezeAsync(Guid cardId, CancellationToken ct = default);     // owner only -> UnauthorizedAccessException
    Task<Card> UnfreezeAsync(Guid cardId, CancellationToken ct = default);
    Task<Card> CancelAsync(Guid cardId, CancellationToken ct = default);
    Task<CardAuthorisation> AuthoriseAsync(Guid cardId, decimal amount, string merchant, CancellationToken ct = default); }  // card network: no owner check
  sealed class CardService(BankDbContext db, ILedger ledger, IAccountService accounts, ICurrentUser user, IClock clock, IEventBus bus) : ICardService
BankDbContext gets: DbSet<Card> Cards
HTTP: POST api/cards, POST api/cards/{id}/freeze|unfreeze|cancel (Customer policy); POST api/cards/{id}/authorise (Staff policy, stands in for the card network)
```

## Allowed scope
- `src/Bank.Api/Modules/Cards/**`
- `src/Bank.Api/Data/BankDbContext.cs`
- `src/Bank.Api/Program.cs`

_Brief from the product owner:_ Customers can get a debit card for one of their accounts, freeze it (for example when it is lost), unfreeze it, and cancel it for good. The card network asks the bank to authorise card payments: the bank approves only if the card is active, the amount is within the card's per-transaction limit (2,000 in the account's currency) and the account has the money; approved amounts move to the bank's Suspense account until settlement. Declines are answers, not errors. The full card number is personal data; only the last four digits may be shown or sent.
