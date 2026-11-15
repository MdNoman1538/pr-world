namespace Bank.Shared;

/// <summary>Marks personal data. It must never be logged, sent in events, written to the audit trail
/// or returned to anyone other than its owner.</summary>
[AttributeUsage(AttributeTargets.Property)]
public sealed class PiiAttribute : Attribute
{
}
