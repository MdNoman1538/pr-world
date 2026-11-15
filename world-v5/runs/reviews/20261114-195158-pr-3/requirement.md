# PR-3: PR-3: Currency exchange service and cross-currency payments

**Story.** As a bank customer, I want to make payments between accounts in different supported currencies (EUR, SEK, USD) with consistent exchange rates and EUR-equivalent daily transfer limits, so that I can transfer money across currencies reliably.

## Acceptance criteria
- [ ] Create the Fx module under src/Bank.Api/Modules/Fx/ with Bank.Modules.Fx.Application.IFxService and sealed class FxService : IFxService (parameterless constructor), and register it via FxModule.AddFxModule in Program.cs above the // MODULES: line.
- [ ] IFxService.Rate(fromCurrency, toCurrency) returns 1 for identical supported currencies (EUR, SEK, USD) and throws ArgumentException if either currency is null, empty, or not one of EUR, SEK, USD.
- [ ] IFxService.Rate uses fixed base rates 1 EUR = 11.50 SEK and 1 EUR = 1.08 USD; inverse pairs use 1 / 11.50 (SEK to EUR) and 1 / 1.08 (USD to EUR); cross pairs triangulate through EUR (SEK to USD converts SEK to EUR then EUR to USD; USD to SEK converts USD to EUR then EUR to SEK).
- [ ] IFxService.Convert(amount, fromCurrency, toCurrency) converts the amount using the pair rate (triangulating through EUR for non-EUR pairs) and rounds the final result to 2 decimal places using Math.Round(..., 2, MidpointRounding.AwayFromZero); throws ArgumentException for unknown currencies.
- [ ] Payment entity in Bank.Modules.Payments.Domain adds public settable properties decimal CreditedAmount, string CreditedCurrency, and decimal Rate; for same-currency payments CreditedAmount equals Amount, CreditedCurrency equals payee/payer currency, and Rate equals 1.
- [ ] PaymentService accepts IFxService as a constructor parameter immediately after BankSettings.
- [ ] Cross-currency payments between supported currencies (EUR, SEK, USD) are allowed and no longer throw CurrencyMismatchException.
- [ ] For a cross-currency payment, PaymentService moves funds solely via ILedger.PostTransferAsync: it debits the payer account for Amount in the payer currency to BankAccounts.For(BankAccountKind.FxClearing, payerCurrency) and credits the payee account for CreditedAmount in the payee currency from BankAccounts.For(BankAccountKind.FxClearing, payeeCurrency); Account.Balance is never modified directly.
- [ ] For a same-currency payment, funds continue to move directly from the payer account to the payee account via ILedger.PostTransferAsync with CreditedAmount = Amount and Rate = 1.
- [ ] Daily transfer limit enforcement (BankSettings.DailyTransferLimit) evaluates all payments in their EUR equivalent using IFxService (converting each payment's debited amount from its currency to EUR) and rejects any payment that would cause the customer's daily total in EUR to exceed DailyTransferLimit.
- [ ] Existing security rules remain enforced: payment endpoints keep [Authorize(Policy = Policies.X)], caller identity is read only from ICurrentUser (never request body), account ownership is checked via IAccountService.IsOwnerAsync, timestamps use IClock.UtcNow, and no PII is written to logs, events, or error messages.
- [ ] Automated xUnit tests cover FxService (same currency returning 1, EUR/SEK/USD direct and inverse pairs, SEK<->USD triangulation, half-away-from-zero rounding to 2 decimals, ArgumentException on unknown currency), cross-currency PaymentService flows (including FxClearing ledger transfers and Payment properties CreditedAmount, CreditedCurrency, Rate), and EUR-equivalent daily transfer limit enforcement.

## Out of scope
- HTTP API controller or endpoints for querying FX rates or quoting currency conversions.
- Dynamic, external, or database-stored FX rates and admin endpoints to update exchange rates.
- FX spreads, conversion commissions, or FeeIncome ledger postings on currency exchange.
- Support for any currencies other than EUR, SEK, and USD.
- Historical rate tables, FX position reporting, or revaluation of FxClearing balances.

## Risks
- Partial ledger failure between the two PostTransferAsync calls (debiting payer to FxClearing succeeding while crediting payee from FxClearing fails) could leave funds stranded in FxClearing and misstate customer balances.
- Rounding or precision differences during EUR triangulation (such as rounding an intermediate EUR amount versus rounding only the final credited amount) could cause unexpected customer amounts or FxClearing ledger imbalances.
- Very small cross-currency payment amounts could round CreditedAmount down to 0.00, leading to failed zero-amount ledger postings or customer confusion.
- Inconsistent EUR conversion of prior same-day payments when computing the daily total could allow customers to bypass DailyTransferLimit or be wrongly blocked.
- Forgetting to update the database schema or seed/test data for the new Payment properties (CreditedAmount, CreditedCurrency, Rate) could cause EF Core runtime or persistence failures.

## Public contract
```
namespace Bank.Modules.Fx.Application:
  interface IFxService {
    decimal Rate(string fromCurrency, string toCurrency);                 // same currency -> 1; unknown currency -> ArgumentException
    decimal Convert(decimal amount, string fromCurrency, string toCurrency); }   // rounded to cents, MidpointRounding.AwayFromZero
  sealed class FxService : IFxService     // no constructor arguments
Payment gets: decimal CreditedAmount; string CreditedCurrency; decimal Rate   (same currency: CreditedAmount = Amount, Rate = 1)
PaymentService gets IFxService as a constructor argument (after BankSettings): cross-currency payments no longer throw CurrencyMismatchException.
```

## Allowed scope
- `src/Bank.Api/Modules/Fx/**`
- `src/Bank.Api/Modules/Payments/**`
- `src/Bank.Api/Program.cs`
- `src/Bank.Api/Data/BankDbContext.cs`

_Brief from the product owner:_ The bank holds EUR, SEK and USD. Add exchange rates: 1 EUR = 11.50 SEK and 1 EUR = 1.08 USD; other pairs go through EUR (SEK to USD = from SEK to EUR, then EUR to USD). Converted amounts are rounded to cents, half away from zero. Payments may now go between accounts in different currencies: the payer is debited in their currency, the payee is credited the converted amount, and the money passes through the bank's FxClearing account of each currency. The daily transfer limit now counts every payment in its EUR equivalent.
