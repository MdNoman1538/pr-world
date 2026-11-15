using Bank.Modules.Accounts.Application;
using Bank.Modules.Audit.Application;
using Bank.Modules.Auth;
using Bank.Modules.Customers.Application;
using Bank.Modules.Customers.Domain;
using Bank.Shared.Events;
using Xunit;

namespace Bank.Tests.Customers;

public sealed class CustomerTests
{
    [Fact]
    public void Customer_starts_with_pending_status()
    {
        var customer = new Customer();

        Assert.Equal(KycStatus.Pending, customer.Status);
        Assert.Null(customer.DecidedBy);
    }

    [Fact]
    public void Customer_verify_transitions_pending_to_verified_and_sets_decided_by()
    {
        var customer = new Customer
        {
            Id = "alice",
            FullName = "Alice Smith",
            Email = "alice@example.com",
            NationalId = "FI-123456",
            DateOfBirth = new DateOnly(1990, 5, 1)
        };

        customer.Verify("officer-1");

        Assert.Equal(KycStatus.Verified, customer.Status);
        Assert.Equal("officer-1", customer.DecidedBy);
    }

    [Fact]
    public void Customer_reject_transitions_pending_to_rejected_and_sets_decided_by()
    {
        var customer = new Customer
        {
            Id = "alice",
            FullName = "Alice Smith",
            Email = "alice@example.com",
            NationalId = "FI-123456",
            DateOfBirth = new DateOnly(1990, 5, 1)
        };

        customer.Reject("officer-2");

        Assert.Equal(KycStatus.Rejected, customer.Status);
        Assert.Equal("officer-2", customer.DecidedBy);
    }

    [Theory]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public void Customer_verify_or_reject_when_not_pending_throws_invalid_operation(bool firstVerify, bool secondVerify)
    {
        var customer = new Customer
        {
            Id = "alice",
            FullName = "Alice Smith",
            Email = "alice@example.com",
            NationalId = "FI-123456",
            DateOfBirth = new DateOnly(1990, 5, 1)
        };

        if (firstVerify)
            customer.Verify("officer-1");
        else
            customer.Reject("officer-1");

        if (secondVerify)
            Assert.Throws<InvalidOperationException>(() => customer.Verify("officer-2"));
        else
            Assert.Throws<InvalidOperationException>(() => customer.Reject("officer-2"));
    }

    [Fact]
    public async Task Register_creates_pending_customer_for_current_user_and_publishes_event()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        ICustomerService service = new CustomerService(db, user, clock, bus);

        var request = new RegisterCustomerRequest("Alice Smith", "alice@example.com", "FI-123456", new DateOnly(1990, 5, 1));
        var created = await service.RegisterAsync(request);

        Assert.Equal("alice", created.Id);
        Assert.Equal(KycStatus.Pending, created.Status);
        Assert.Equal(clock.UtcNow, created.RegisteredAt);
        Assert.Null(created.DecidedBy);

        db.ChangeTracker.Clear();
        var persisted = db.Customers.Single(c => c.Id == "alice");
        Assert.Equal("Alice Smith", persisted.FullName);
        Assert.Equal("alice@example.com", persisted.Email);
        Assert.Equal("FI-123456", persisted.NationalId);
        Assert.Equal(new DateOnly(1990, 5, 1), persisted.DateOfBirth);
        Assert.Equal(KycStatus.Pending, persisted.Status);
        Assert.Null(persisted.DecidedBy);
        Assert.Equal(clock.UtcNow, persisted.RegisteredAt);

        var ev = Assert.IsType<CustomerRegistered>(Assert.Single(bus.Events));
        Assert.Equal("alice", ev.CustomerId);
        Assert.Equal(clock.UtcNow, ev.OccurredAt);
    }

    [Fact]
    public async Task Register_accepts_applicant_turning_18_on_clock_date()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock { UtcNow = new DateTimeOffset(2026, 3, 15, 10, 0, 0, TimeSpan.Zero) };
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var service = new CustomerService(db, user, clock, bus);

        var created = await service.RegisterAsync(new RegisterCustomerRequest(
            "Alice Smith",
            "alice@example.com",
            "FI-123456",
            new DateOnly(2008, 3, 15)));

        Assert.Equal("alice", created.Id);
        Assert.Equal(KycStatus.Pending, created.Status);
    }

    [Fact]
    public async Task Register_rejects_applicant_one_day_under_18_on_clock_date()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock { UtcNow = new DateTimeOffset(2026, 3, 15, 10, 0, 0, TimeSpan.Zero) };
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var service = new CustomerService(db, user, clock, bus);

        await Assert.ThrowsAsync<ArgumentException>(() => service.RegisterAsync(new RegisterCustomerRequest(
            "Alice Smith",
            "alice@example.com",
            "FI-123456",
            new DateOnly(2008, 3, 16))));

        Assert.Empty(db.Customers);
        Assert.Empty(bus.Events);
    }

    [Fact]
    public async Task Register_uses_clock_rather_than_system_time_for_age_check()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock { UtcNow = new DateTimeOffset(2000, 6, 1, 12, 0, 0, TimeSpan.Zero) };
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var service = new CustomerService(db, user, clock, bus);
        var request = new RegisterCustomerRequest("Alice Smith", "alice@example.com", "FI-123456", new DateOnly(1982, 6, 2));

        await Assert.ThrowsAsync<ArgumentException>(() => service.RegisterAsync(request));

        clock.Advance(TimeSpan.FromDays(1));
        var created = await service.RegisterAsync(request);

        Assert.Equal(clock.UtcNow, created.RegisteredAt);
        Assert.Equal(KycStatus.Pending, created.Status);
    }

    [Fact]
    public async Task Register_rejects_underage_applicant_even_when_days_exceed_365_times_18()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock { UtcNow = new DateTimeOffset(2026, 3, 15, 10, 0, 0, TimeSpan.Zero) };
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var service = new CustomerService(db, user, clock, bus);

        await Assert.ThrowsAsync<ArgumentException>(() => service.RegisterAsync(new RegisterCustomerRequest(
            "Alice Smith",
            "alice@example.com",
            "FI-123456",
            new DateOnly(2008, 3, 19))));
    }

    [Theory]
    [InlineData("", "alice@example.com", "FI-123456")]
    [InlineData("   ", "alice@example.com", "FI-123456")]
    [InlineData(null, "alice@example.com", "FI-123456")]
    [InlineData("Alice Smith", "", "FI-123456")]
    [InlineData("Alice Smith", "   ", "FI-123456")]
    [InlineData("Alice Smith", null, "FI-123456")]
    [InlineData("Alice Smith", "alice@example.com", "")]
    [InlineData("Alice Smith", "alice@example.com", "   ")]
    [InlineData("Alice Smith", "alice@example.com", null)]
    public async Task Register_rejects_null_empty_or_whitespace_fields(string? fullName, string? email, string? nationalId)
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var service = new CustomerService(db, user, clock, bus);

        await Assert.ThrowsAnyAsync<ArgumentException>(() => service.RegisterAsync(new RegisterCustomerRequest(
            fullName!,
            email!,
            nationalId!,
            new DateOnly(1990, 5, 1))));

        Assert.Empty(db.Customers);
        Assert.Empty(bus.Events);
    }

    [Fact]
    public async Task Register_when_customer_already_exists_throws_invalid_operation()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var service = new CustomerService(db, user, clock, bus);
        var request = new RegisterCustomerRequest("Alice Smith", "alice@example.com", "FI-123456", new DateOnly(1990, 5, 1));

        await service.RegisterAsync(request);

        await Assert.ThrowsAsync<InvalidOperationException>(() => service.RegisterAsync(request));
        Assert.Single(db.Customers);
        Assert.Single(bus.Events);
    }

    [Fact]
    public async Task Verify_by_compliance_officer_updates_status_persists_and_publishes_event()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var customerUser = new FakeUser("alice", Roles.Customer);
        await new CustomerService(db, customerUser, clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Alice Smith", "alice@example.com", "FI-123456", new DateOnly(1990, 5, 1)));

        clock.Advance(TimeSpan.FromHours(2));
        var officerUser = new FakeUser("officer-1", Roles.ComplianceOfficer);
        var verified = await new CustomerService(db, officerUser, clock, bus).VerifyAsync("alice");

        Assert.Equal(KycStatus.Verified, verified.Status);
        Assert.Equal("officer-1", verified.DecidedBy);

        db.ChangeTracker.Clear();
        var persisted = db.Customers.Single(c => c.Id == "alice");
        Assert.Equal(KycStatus.Verified, persisted.Status);
        Assert.Equal("officer-1", persisted.DecidedBy);

        var ev = Assert.IsType<CustomerVerified>(bus.Events.Last());
        Assert.Equal("alice", ev.CustomerId);
        Assert.Equal("officer-1", ev.VerifiedBy);
        Assert.Equal(clock.UtcNow, ev.OccurredAt);
    }

    [Fact]
    public async Task Reject_by_compliance_officer_updates_status_persists_and_publishes_event()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var customerUser = new FakeUser("alice", Roles.Customer);
        await new CustomerService(db, customerUser, clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Alice Smith", "alice@example.com", "FI-123456", new DateOnly(1990, 5, 1)));

        clock.Advance(TimeSpan.FromHours(3));
        var officerUser = new FakeUser("officer-2", Roles.ComplianceOfficer);
        var rejected = await new CustomerService(db, officerUser, clock, bus).RejectAsync("alice");

        Assert.Equal(KycStatus.Rejected, rejected.Status);
        Assert.Equal("officer-2", rejected.DecidedBy);

        db.ChangeTracker.Clear();
        var persisted = db.Customers.Single(c => c.Id == "alice");
        Assert.Equal(KycStatus.Rejected, persisted.Status);
        Assert.Equal("officer-2", persisted.DecidedBy);

        var ev = Assert.IsType<CustomerRejected>(bus.Events.Last());
        Assert.Equal("alice", ev.CustomerId);
        Assert.Equal("officer-2", ev.RejectedBy);
        Assert.Equal(clock.UtcNow, ev.OccurredAt);
    }

    [Theory]
    [InlineData(Roles.Customer)]
    [InlineData(Roles.Teller)]
    [InlineData(Roles.LoanOfficer)]
    [InlineData(Roles.Admin)]
    [InlineData(null)]
    public async Task Verify_and_reject_by_non_compliance_role_throw_unauthorized(string? role)
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        await new CustomerService(db, new FakeUser("alice", Roles.Customer), clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Alice Smith", "alice@example.com", "FI-123456", new DateOnly(1990, 5, 1)));

        var actor = role is null ? new FakeUser("bob") : new FakeUser("bob", role);
        var officerService = new CustomerService(db, actor, clock, bus);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => officerService.VerifyAsync("alice"));
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => officerService.RejectAsync("alice"));

        db.ChangeTracker.Clear();
        var persisted = db.Customers.Single(c => c.Id == "alice");
        Assert.Equal(KycStatus.Pending, persisted.Status);
        Assert.Null(persisted.DecidedBy);
        Assert.Single(bus.Events);
    }

    [Fact]
    public async Task Compliance_officer_cannot_self_verify_or_self_reject()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var self = new FakeUser("officer-1", Roles.Customer, Roles.ComplianceOfficer);
        var service = new CustomerService(db, self, clock, bus);
        await service.RegisterAsync(new RegisterCustomerRequest("Officer One", "officer@example.com", "FI-999999", new DateOnly(1985, 1, 10)));

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.VerifyAsync("officer-1"));
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.RejectAsync("officer-1"));

        db.ChangeTracker.Clear();
        var persisted = db.Customers.Single(c => c.Id == "officer-1");
        Assert.Equal(KycStatus.Pending, persisted.Status);
        Assert.Null(persisted.DecidedBy);
        Assert.Single(bus.Events);
    }

    [Fact]
    public async Task Verify_and_reject_unknown_customer_throw_key_not_found()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var officer = new FakeUser("officer-1", Roles.ComplianceOfficer);
        var service = new CustomerService(db, officer, clock, bus);

        await Assert.ThrowsAsync<KeyNotFoundException>(() => service.VerifyAsync("missing-id"));
        await Assert.ThrowsAsync<KeyNotFoundException>(() => service.RejectAsync("missing-id"));
        Assert.Empty(bus.Events);
    }

    [Fact]
    public async Task Verify_and_reject_already_decided_customer_throw_invalid_operation()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var officerService = new CustomerService(db, new FakeUser("officer-1", Roles.ComplianceOfficer), clock, bus);

        await new CustomerService(db, new FakeUser("alice", Roles.Customer), clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Alice Smith", "alice@example.com", "FI-111111", new DateOnly(1990, 5, 1)));
        await officerService.VerifyAsync("alice");

        await Assert.ThrowsAsync<InvalidOperationException>(() => officerService.VerifyAsync("alice"));
        await Assert.ThrowsAsync<InvalidOperationException>(() => officerService.RejectAsync("alice"));

        await new CustomerService(db, new FakeUser("bob", Roles.Customer), clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Bob Jones", "bob@example.com", "FI-222222", new DateOnly(1991, 6, 2)));
        await officerService.RejectAsync("bob");

        await Assert.ThrowsAsync<InvalidOperationException>(() => officerService.VerifyAsync("bob"));
        await Assert.ThrowsAsync<InvalidOperationException>(() => officerService.RejectAsync("bob"));
    }

    [Fact]
    public async Task Get_returns_customer_when_exists_and_null_when_missing()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var service = new CustomerService(db, new FakeUser("alice", Roles.Customer), clock, bus);

        Assert.Null(await service.GetAsync("alice"));

        await service.RegisterAsync(new RegisterCustomerRequest("Alice Smith", "alice@example.com", "FI-123456", new DateOnly(1990, 5, 1)));

        var found = await service.GetAsync("alice");
        Assert.NotNull(found);
        Assert.Equal("alice", found.Id);
        Assert.Equal("Alice Smith", found.FullName);
        Assert.Null(await service.GetAsync("unknown"));
    }

    [Fact]
    public async Task Kyc_rule_blocks_unknown_pending_and_rejected_customers()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        IAccountOpeningRule rule = new KycAccountOpeningRule(db);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => rule.EnsureMayOpenAsync("unknown"));

        await new CustomerService(db, new FakeUser("pending-user", Roles.Customer), clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Pending User", "pending@example.com", "FI-111111", new DateOnly(1990, 1, 1)));
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => rule.EnsureMayOpenAsync("pending-user"));

        await new CustomerService(db, new FakeUser("rejected-user", Roles.Customer), clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Rejected User", "rejected@example.com", "FI-222222", new DateOnly(1990, 1, 1)));
        await new CustomerService(db, new FakeUser("officer-1", Roles.ComplianceOfficer), clock, bus).RejectAsync("rejected-user");
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => rule.EnsureMayOpenAsync("rejected-user"));
    }

    [Fact]
    public async Task Kyc_rule_allows_verified_customer()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        await new CustomerService(db, new FakeUser("alice", Roles.Customer), clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Alice Smith", "alice@example.com", "FI-123456", new DateOnly(1990, 5, 1)));
        await new CustomerService(db, new FakeUser("officer-1", Roles.ComplianceOfficer), clock, bus).VerifyAsync("alice");

        IAccountOpeningRule rule = new KycAccountOpeningRule(db);
        await rule.EnsureMayOpenAsync("alice");
    }

    [Fact]
    public async Task Account_service_with_kyc_rule_enforces_verified_kyc_before_opening()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var accountService = new AccountService(
            db,
            user,
            TestKit.Settings(),
            clock,
            bus,
            new IAccountOpeningRule[] { new KycAccountOpeningRule(db) });

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => accountService.OpenAsync("EUR"));

        await new CustomerService(db, user, clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Alice Smith", "alice@example.com", "FI-123456", new DateOnly(1990, 5, 1)));
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => accountService.OpenAsync("EUR"));

        await new CustomerService(db, new FakeUser("officer-1", Roles.ComplianceOfficer), clock, bus).VerifyAsync("alice");
        var opened = await accountService.OpenAsync("EUR");
        Assert.Equal("alice", opened.OwnerId);
        Assert.Equal("EUR", opened.Currency);

        user.UserId = "bob";
        await new CustomerService(db, user, clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Bob Jones", "bob@example.com", "FI-654321", new DateOnly(1991, 6, 2)));
        await new CustomerService(db, new FakeUser("officer-1", Roles.ComplianceOfficer), clock, bus).RejectAsync("bob");
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => accountService.OpenAsync("EUR"));
    }

    [Fact]
    public async Task Events_audit_logs_and_exceptions_do_not_expose_pii()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        const string secretNationalId = "NAT-987654-XY";
        var dob = new DateOnly(1992, 11, 23);

        await new CustomerService(db, new FakeUser("alice", Roles.Customer), clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Alice Smith", "alice@example.com", secretNationalId, dob));
        await new CustomerService(db, new FakeUser("officer-1", Roles.ComplianceOfficer), clock, bus).VerifyAsync("alice");

        await new CustomerService(db, new FakeUser("bob", Roles.Customer), clock, bus).RegisterAsync(
            new RegisterCustomerRequest("Bob Jones", "bob@example.com", secretNationalId, dob));
        await new CustomerService(db, new FakeUser("officer-1", Roles.ComplianceOfficer), clock, bus).RejectAsync("bob");

        foreach (IDomainEvent ev in bus.Events)
        {
            var redacted = AuditLog.Redact(ev);
            var text = ev.ToString() ?? string.Empty;
            Assert.DoesNotContain(secretNationalId, redacted);
            Assert.DoesNotContain("1992-11-23", redacted);
            Assert.DoesNotContain("1992", redacted);
            Assert.DoesNotContain(secretNationalId, text);
            Assert.DoesNotContain("1992-11-23", text);
            Assert.DoesNotContain("1992", text);
        }

        const string minorNationalId = "NAT-UNDERAGE-01";
        var minorService = new CustomerService(db, new FakeUser("minor", Roles.Customer), clock, bus);
        var ex = await Assert.ThrowsAsync<ArgumentException>(() => minorService.RegisterAsync(
            new RegisterCustomerRequest("Minor User", "minor@example.com", minorNationalId, new DateOnly(2012, 4, 5))));
        Assert.DoesNotContain(minorNationalId, ex.Message);
        Assert.DoesNotContain("2012-04-05", ex.Message);
        Assert.DoesNotContain("2012", ex.Message);
    }
}
