using Bank.Modules.Loans.Application;

namespace Bank.Modules.Loans;

public static class LoansModule
{
    public static IServiceCollection AddLoansModule(this IServiceCollection services)
    {
        services.AddScoped<ILoanService, LoanService>();
        return services;
    }
}
