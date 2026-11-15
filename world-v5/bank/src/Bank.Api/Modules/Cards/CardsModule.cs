using Bank.Modules.Cards.Application;

namespace Bank.Modules.Cards;

public static class CardsModule
{
    public static IServiceCollection AddCardsModule(this IServiceCollection services)
    {
        services.AddScoped<ICardService, CardService>();
        return services;
    }
}
