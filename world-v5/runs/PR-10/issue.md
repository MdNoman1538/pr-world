# PR-10: PR-10: Centralize cent rounding in shared Bank.Shared.Money.MoneyMath helper

**Story.** As a bank developer, I want one shared MoneyMath.ToCents rounding helper used across the Fx, Fees, Deposits, and Loans modules so that cent rounding is defined in a single place without changing any amounts seen by customers.

## Acceptance criteria
- [ ] A public static class MoneyMath is defined in namespace Bank.Shared.Money (in its own file, one public type per file) with signature public static decimal ToCents(decimal amount).
- [ ] MoneyMath.ToCents rounds decimal values to 2 decimal places using MidpointRounding.AwayFromZero: ToCents(2.345m) returns 2.35m, ToCents(-2.345m) returns -2.35m, ToCents(0.005m) returns 0.01m, ToCents(-0.005m) returns -0.01m, ToCents(0m) returns 0.00m, and exact-cent amounts like 12.34m remain 12.34m.
- [ ] All cent-rounding calls in the Fx, Fees, Deposits, and Loans modules use MoneyMath.ToCents, and no direct Math.Round(..., 2, ...) or duplicate cent-rounding helper remains in those four modules.
- [ ] Rounding occurs at the exact same calculation steps as before the refactor so that every customer-facing and ledger-posted amount in Fx conversions, Fee charges, Deposit interest/operations, and Loan calculations is identical to pre-refactor amounts.
- [ ] Existing role-based authorization policies (Customer, Staff, LoanOfficer, Compliance, Admin), ownership checks, and error behaviors (such as 400/401/403/404 responses) in Fx, Fees, Deposits, and Loans remain completely unchanged.
- [ ] Unit tests cover MoneyMath.ToCents for positive, negative, zero, midpoint away-from-zero, and unchanged 2-decimal inputs, and existing plus regression tests in Fx, Fees, Deposits, and Loans pass with identical monetary results.

## Out of scope
- Changing rounding precision, currency-specific decimal places (e.g., 0 or 3 decimals), or midpoint rounding strategy.
- Refactoring rounding in modules other than Fx, Fees, Deposits, and Loans.
- Adding extra methods or types to Bank.Shared.Money beyond MoneyMath.ToCents(decimal amount) (such as Money value objects, currency formatting, or allocation helpers).
- Modifying API contracts, DTOs, database tables, authorization rules, or adding new NuGet packages.

## Risks
- Implementing MoneyMath.ToCents with MidpointRounding.ToEven (the default in Math.Round) instead of MidpointRounding.AwayFromZero would misround half-cent amounts (e.g., 2.345 to 2.34 instead of 2.35) and cause 1-cent discrepancies in customer balances or bank income accounts.
- Changing the order or point at which rounding is applied during Fx, Fees, Deposits, or Loans calculations could subtly alter amounts charged to or paid to customers.
- Missing one or more inline rounding expressions in Fx, Fees, Deposits, or Loans would leave inconsistent rounding behavior across the codebase.
- Mishandling negative values (such as reversals, fees, or adjustments) could violate symmetric half-away-from-zero behavior (-2.345 to -2.35) and create ledger posting mismatches.

## Public contract
```
namespace Bank.Shared.Money:
  static class MoneyMath { static decimal ToCents(decimal amount); }   // rounds to 2 decimals, half away from zero (2.345 -> 2.35, -2.345 -> -2.35)
```

## Allowed scope
- `src/Bank.Api/Shared/Money/**`
- `src/Bank.Api/Modules/Fx/**`
- `src/Bank.Api/Modules/Fees/**`
- `src/Bank.Api/Modules/Deposits/**`
- `src/Bank.Api/Modules/Loans/**`

_Brief from the product owner:_ Rounding to cents is written separately in several modules. Create one shared helper and use it in the Fx, Fees, Deposits and Loans modules. This is a refactor: no customer may see a different amount afterwards.
