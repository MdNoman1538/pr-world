namespace Bank.Shared.Time;

/// <summary>The bank's clock. Always use this instead of DateTimeOffset.UtcNow so tests can control time.</summary>
public interface IClock
{
    DateTimeOffset UtcNow { get; }
}

public sealed class SystemClock : IClock
{
    public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;
}
