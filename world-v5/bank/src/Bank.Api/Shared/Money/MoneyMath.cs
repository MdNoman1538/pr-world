namespace Bank.Shared.Money;

public static class MoneyMath
{
    public static decimal ToCents(decimal amount) =>
        Math.Round(amount, 2, MidpointRounding.AwayFromZero);
}
