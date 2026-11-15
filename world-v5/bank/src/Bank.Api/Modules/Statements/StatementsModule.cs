using Bank.Modules.Statements.Application;

namespace Bank.Modules.Statements;

public static class StatementsModule
{
    public static IServiceCollection AddStatementsModule(this IServiceCollection services)
    {
        services.AddScoped<IStatementService, StatementService>();
        return services;
    }
}
