using Bank.Data;
using Bank.Modules.Accounts;
using Bank.Modules.Audit;
using Bank.Modules.Auth;
using Bank.Modules.Cards;
using Bank.Modules.Customers;
using Bank.Modules.Deposits;
using Bank.Modules.Fees;
using Bank.Modules.Fx;
using Bank.Modules.Ledger;
using Bank.Modules.Loans;
using Bank.Modules.Notifications;
using Bank.Modules.Payments;
using Bank.Modules.Statements;
using Bank.Shared;
using Bank.Shared.Events;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddDbContext<BankDbContext>(o =>
    o.UseSqlite(builder.Configuration.GetConnectionString("Bank") ?? "Data Source=bank.db"));
builder.Services.AddControllers();
builder.Services.AddShared();
builder.Services.AddEventBus();
builder.Services.AddAuthModule();
builder.Services.AddAccountsModule();
builder.Services.AddLedgerModule();
builder.Services.AddAuditModule();
builder.Services.AddNotificationsModule();
builder.Services.AddCustomersModule();
builder.Services.AddPaymentsModule();
builder.Services.AddFxModule();
builder.Services.AddFeesModule();
builder.Services.AddCardsModule();
builder.Services.AddDepositsModule();
builder.Services.AddLoansModule();
builder.Services.AddStatementsModule();
// MODULES: register new modules above this line

var app = builder.Build();
using (var scope = app.Services.CreateScope())
{
    scope.ServiceProvider.GetRequiredService<BankDbContext>().Database.EnsureCreated();
}
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();
app.Run();

public partial class Program { }
