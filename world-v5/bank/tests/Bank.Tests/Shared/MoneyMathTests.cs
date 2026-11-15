using Bank.Shared.Money;
using Xunit;

namespace Bank.Tests.Shared;

public sealed class MoneyMathTests
{
    public static IEnumerable<object[]> PositiveMidpointCases()
    {
        yield return new object[] { 2.345m, 2.35m };
        yield return new object[] { 2.355m, 2.36m };
        yield return new object[] { 0.005m, 0.01m };
        yield return new object[] { 0.015m, 0.02m };
        yield return new object[] { 1.005m, 1.01m };
        yield return new object[] { 999999999.995m, 1000000000.00m };
    }

    public static IEnumerable<object[]> NegativeMidpointCases()
    {
        yield return new object[] { -2.345m, -2.35m };
        yield return new object[] { -2.355m, -2.36m };
        yield return new object[] { -0.005m, -0.01m };
        yield return new object[] { -0.015m, -0.02m };
        yield return new object[] { -1.005m, -1.01m };
        yield return new object[] { -999999999.995m, -1000000000.00m };
    }

    public static IEnumerable<object[]> ExactCentAndShorterCases()
    {
        yield return new object[] { 12.34m, 12.34m };
        yield return new object[] { -12.34m, -12.34m };
        yield return new object[] { 0.01m, 0.01m };
        yield return new object[] { -0.01m, -0.01m };
        yield return new object[] { 5.5m, 5.50m };
        yield return new object[] { -5.5m, -5.50m };
        yield return new object[] { 100m, 100.00m };
        yield return new object[] { -100m, -100.00m };
        yield return new object[] { 12.3400m, 12.34m };
    }

    [Theory]
    [MemberData(nameof(PositiveMidpointCases))]
    public void ToCents_rounds_positive_midpoints_away_from_zero(decimal input, decimal expected)
    {
        Assert.Equal(expected, MoneyMath.ToCents(input));
    }

    [Theory]
    [MemberData(nameof(NegativeMidpointCases))]
    public void ToCents_rounds_negative_midpoints_away_from_zero(decimal input, decimal expected)
    {
        Assert.Equal(expected, MoneyMath.ToCents(input));
    }

    [Theory]
    [MemberData(nameof(ExactCentAndShorterCases))]
    public void ToCents_leaves_exact_cent_and_fewer_decimal_amounts_unchanged(decimal input, decimal expected)
    {
        Assert.Equal(expected, MoneyMath.ToCents(input));
    }

    [Fact]
    public void ToCents_returns_zero_for_zero_and_sub_half_cent_values()
    {
        Assert.Equal(0.00m, MoneyMath.ToCents(0m));
        Assert.Equal(0.00m, MoneyMath.ToCents(-0m));
        Assert.Equal(0.00m, MoneyMath.ToCents(0.000m));
        Assert.Equal(0.00m, MoneyMath.ToCents(0.004m));
        Assert.Equal(0.00m, MoneyMath.ToCents(-0.004m));
        Assert.Equal(0.00m, MoneyMath.ToCents(0.0049999m));
        Assert.Equal(0.00m, MoneyMath.ToCents(-0.0049999m));
    }

    [Fact]
    public void ToCents_rounds_values_below_and_above_midpoint_to_nearest_cent()
    {
        Assert.Equal(2.34m, MoneyMath.ToCents(2.344m));
        Assert.Equal(2.34m, MoneyMath.ToCents(2.3449999m));
        Assert.Equal(2.35m, MoneyMath.ToCents(2.3450001m));
        Assert.Equal(2.35m, MoneyMath.ToCents(2.346m));

        Assert.Equal(-2.34m, MoneyMath.ToCents(-2.344m));
        Assert.Equal(-2.34m, MoneyMath.ToCents(-2.3449999m));
        Assert.Equal(-2.35m, MoneyMath.ToCents(-2.3450001m));
        Assert.Equal(-2.35m, MoneyMath.ToCents(-2.346m));
    }

    [Fact]
    public void ToCents_is_symmetric_for_opposite_signed_amounts()
    {
        var samples = new[] { 0m, 0.004m, 0.005m, 0.015m, 2.344m, 2.345m, 2.355m, 12.34m, 1234567890.125m };

        foreach (var amount in samples)
        {
            Assert.Equal(-MoneyMath.ToCents(amount), MoneyMath.ToCents(-amount));
        }
    }
}
