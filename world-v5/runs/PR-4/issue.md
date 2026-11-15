# PR-4: PR-4: Fees for cross-currency payments and pre-payment quote

**Story.** As a bank customer making a cross-currency payment, I want to see the applicable fee, exchange rate, and credited amount in a quote before paying, and have the fee charged transparently in my currency on top of the payment amount only when my balance covers the total.

## Acceptance criteria
- [ ] A new Fees module is created under src/Bank.Api/Modules/Fees with Application/Fee.cs (sealed record Fee(decimal Amount, string Currency)), Application/IFeeCalculator.cs, Application/FeeCalculator.cs (sealed class FeeCalculator(IFxService fx) : IFeeCalculator), and FeesModule.cs registered in Program.cs above // MODULES:.
- [ ] IFeeCalculator.Quote(amount, fromCurrency, toCurrency) returns Fee(0m, fromCurrency) when fromCurrency equals toCurrency (case-insensitive).
- [ ] For cross-currency calls (fromCurrency != toCurrency) with amount > 0, IFeeCalculator.Quote calculates 0.2% of amount (amount * 0.002m), converts the 0.50 EUR minimum and 20.00 EUR maximum into fromCurrency via IFxService, rounds the raw fee and converted bounds to 2 decimal places using Math.Round(x, 2, MidpointRounding.AwayFromZero), and clamps the fee between the converted min and max in fromCurrency.
- [ ] If amount <= 0, IFeeCalculator.Quote and IPaymentService quote/pay operations reject the request with a validation error (HTTP 400 Bad Request at the API layer).
- [ ] PaymentQuote(decimal Amount, string Currency, decimal Fee, decimal CreditedAmount, string CreditedCurrency, decimal Rate) is added to Bank.Modules.Payments.Application, and IPaymentService exposes Quote / QuoteAsync(Guid fromAccountId, Guid toAccountId, decimal amount) returning the fee, FX rate (1m for same-currency), and rounded CreditedAmount without modifying balances or persisting a Payment.
- [ ] GET api/payments/quote?from={fromAccountId}&to={toAccountId}&amount={amount} is decorated with [Authorize(Policy = Policies.Customer)], uses ICurrentUser.UserId and IAccountService.IsOwnerAsync to verify the caller owns the from account (returning 403 Forbidden if not owner and 404 Not Found if either account does not exist), and returns HTTP 200 with the PaymentQuote JSON.
- [ ] Payment entity adds a decimal Fee property persisted in BankDbContext, and PaymentService accepts IFeeCalculator in its constructor immediately after IFxService.
- [ ] When executing a payment, PaymentService checks that the payer account balance is at least amount + fee before posting any ledger transfers; if balance < amount + fee, the payment fails with insufficient funds, no Payment is completed, and zero transfers are posted to either the recipient, FxClearing, or FeeIncome.
- [ ] When a cross-currency payment succeeds with Fee > 0, PaymentService posts the fee transfer in the payer's currency via ILedger.PostTransferAsync from the payer account to BankAccounts.For(BankAccountKind.FeeIncome, fromAccount.Currency), alongside the payment transfer(s), so the payer is debited amount + fee in total; for same-currency payments (Fee == 0), no FeeIncome transfer is posted.

## Out of scope
- Quote locking, FX rate reservation, or guaranteed quote expiration windows (execution uses live FX rates at payment time).
- Customer-tier fee discounts, fee waivers, promotional codes, or configurable fee percentages/caps in BankSettings or database.
- Charging fees on same-currency payments, loan disbursements/repayments, or internal bank transfers.
- Fee refunds or reversals on disputed or cancelled payments.
- Frontend or UI components for displaying the quote.

## Risks
- Non-atomic multi-leg ledger posting: if the principal/FX transfer succeeds and the FeeIncome transfer fails (or vice versa), customer balances and bank FeeIncome accounts will fall out of sync unless wrapped in a single database transaction and pre-validated for amount + fee.
- Rounding discrepancies: inconsistent rounding between FeeCalculator, PaymentQuote, and PaymentService (such as failing to use MidpointRounding.AwayFromZero) could cause a 1-cent mismatch between the quoted fee and the debited fee.
- IDOR on quote endpoint: omitting ownership verification on the from account in GET api/payments/quote would allow an authenticated customer to enumerate other customers' account IDs and currencies.
- Rate movement between quote and execution: because quotes are non-binding, an FX rate shift before payment submission could change the converted EUR fee bounds or CreditedAmount.
- Unsupported currency handling: calling BankAccounts.For(BankAccountKind.FeeIncome, currency) with a currency outside EUR, SEK, or USD would fail at runtime if account currency validation is missing.

## Public contract
```
namespace Bank.Modules.Fees.Application:
  sealed record Fee(decimal Amount, string Currency)
  interface IFeeCalculator { Fee Quote(decimal amount, string fromCurrency, string toCurrency); }
  sealed class FeeCalculator(IFxService fx) : IFeeCalculator
namespace Bank.Modules.Payments.Application:
  sealed record PaymentQuote(decimal Amount, string Currency, decimal Fee, decimal CreditedAmount, string CreditedCurrency, decimal Rate)
  IPaymentService adds: PaymentQuote Quote(Guid fromAccountId, Guid toAccountId, decimal amount)  -- async variant allowed: Task<PaymentQuote> QuoteAsync(...)
Payment gets: decimal Fee
PaymentService gets IFeeCalculator as a constructor argument (after IFxService).
HTTP: GET api/payments/quote?from=&to=&amount=
```

## Allowed scope
- `src/Bank.Api/Modules/Fees/**`
- `src/Bank.Api/Modules/Payments/**`
- `src/Bank.Api/Program.cs`

_Brief from the product owner:_ Payments in the same currency stay free. A cross-currency payment costs 0.2% of the amount, at least 0.50 EUR and at most 20.00 EUR (both limits converted to the payment's currency), rounded to cents. The fee is charged in the payer's currency, on top of the amount, and goes to the bank's FeeIncome account. The customer must be able to see the fee and the converted amount before paying (a quote). If the payer cannot cover amount + fee, nothing is paid.
