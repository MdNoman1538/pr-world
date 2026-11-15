namespace Bank.Modules.Fees.Application;

public interface IFeeCalculator
{
    Fee Quote(decimal amount, string fromCurrency, string toCurrency);
}
