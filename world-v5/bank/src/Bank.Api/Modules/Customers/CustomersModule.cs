using Bank.Modules.Accounts.Application;
using Bank.Modules.Customers.Application;

namespace Bank.Modules.Customers;

public static class CustomersModule
{
    public static IServiceCollection AddCustomersModule(this IServiceCollection services)
    {
        services.AddScoped<ICustomerService, CustomerService>();
        services.AddScoped<IAccountOpeningRule, KycAccountOpeningRule>();
        return services;
    }
}
