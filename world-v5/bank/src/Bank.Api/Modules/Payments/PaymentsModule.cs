using Bank.Modules.Payments.Application;

namespace Bank.Modules.Payments;

public static class PaymentsModule
{
    public static IServiceCollection AddPaymentsModule(this IServiceCollection services)
    {
        services.AddScoped<IPaymentService, PaymentService>();
        services.AddScoped<IPaymentReviewService, PaymentReviewService>();
        return services;
    }
}
