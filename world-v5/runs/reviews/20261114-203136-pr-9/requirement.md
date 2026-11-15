# PR-9: PR-9: Update BankSettings for Swedish launch (SEK default currency and 5,000 EUR daily transfer limit)

**Story.** As the bank preparing for the Swedish launch and complying with regulatory guidance, I want Bank.Shared.Settings.BankSettings updated so that new accounts default to SEK and the daily transfer limit is reduced from 10,000 to 5,000 EUR equivalent for all customers, with no other behavioral changes.

## Acceptance criteria
- [ ] Bank.Shared.Settings.BankSettings has DefaultCurrency set to "SEK" (changed from "EUR").
- [ ] Bank.Shared.Settings.BankSettings has DailyTransferLimit set to 5_000m (decimal 5000.00, changed from 10_000m).
- [ ] Bank.Shared.Settings.BankSettings SupportedCurrencies remains unchanged (EUR, SEK, USD).
- [ ] When an authenticated Customer (or authorized Staff/Admin role per existing account creation policy) creates a new account without specifying a currency, the created account uses DefaultCurrency ("SEK").
- [ ] When an authenticated Customer (or authorized role) creates a new account explicitly specifying another supported currency (such as "EUR" or "USD"), the account is still created in that requested supported currency.
- [ ] Existing accounts retain their previously assigned currencies and balances; only newly created accounts without an explicit currency default to "SEK".
- [ ] For any Customer initiating transfers, the cumulative daily transfer limit check enforces 5_000m EUR equivalent (using decimal arithmetic and Math.Round(x, 2, MidpointRounding.AwayFromZero) where EUR equivalent conversion applies): a transfer causing the daily total to equal 5,000.00 EUR equivalent succeeds, while a transfer causing the daily total to exceed 5,000.00 EUR equivalent (e.g., 5,000.01 EUR equivalent or a second transfer pushing the UTC day total above 5,000.00) is rejected with the existing daily limit validation error and posts no ledger movement.
- [ ] Authorization policies, roles, current user identity resolution via ICurrentUser, and UTC day boundary calculation via IClock remain unchanged; no customer or role can bypass the 5,000m daily transfer limit unless already permitted by existing policy.
- [ ] All existing modules and tests that depend on BankSettings continue to pass after updating any test assertions that previously assumed EUR default or 10,000m limit.

## Out of scope
- Converting or migrating existing customer accounts from EUR or USD to SEK.
- Adding new currencies or removing existing currencies from SupportedCurrencies.
- Introducing per-customer, tiered, or role-specific daily transfer limits.
- Adding an API endpoint or UI to edit BankSettings at runtime.
- Modifying FX conversion rates, fee schedules, interest rates, or loan rules.
- Changing account creation or transfer authorization policies or adding new user roles.

## Risks
- Any module that hardcoded "EUR" or 10_000m instead of injecting BankSettings would create accounts in the wrong currency or allow transfers above the 5,000 EUR regulatory cap, causing a compliance breach.
- Existing automated tests or downstream integrations that assert "EUR" as the default account currency or 10,000 as the transfer limit will break unless aligned with BankSettings.
- Rounding differences during non-EUR to EUR equivalent conversion near the 5,000.00 boundary could cause slight limit overruns or unexpected rejections if AwayFromZero cent rounding is not applied consistently.
- Customers attempting legitimate transfers between 5,000.01 and 10,000.00 EUR equivalent immediately after deployment will be rejected, risking support incidents if not communicated prior to launch.

## Public contract
```
BankSettings: DefaultCurrency = "SEK"; DailyTransferLimit = 5_000m; SupportedCurrencies unchanged.
```

## Allowed scope
- `src/Bank.Api/Shared/Settings/BankSettings.cs`

_Brief from the product owner:_ We launch in Sweden next week. New accounts must default to SEK instead of EUR, and following the regulator's guidance the daily transfer limit drops from 10,000 to 5,000 (EUR equivalent) for all customers. Nothing else changes.
