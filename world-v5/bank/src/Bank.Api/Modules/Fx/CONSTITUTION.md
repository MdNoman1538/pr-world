# Fx — constitution
**Purpose:** Currency exchange rates and conversion.
**Owner:** Treasury · **Risk:** HIGH
**Rules:** Rates come from the bank's rate table. Converted amounts are rounded to cents, half away from zero. Cross-currency money moves through the FxClearing accounts of both currencies.
**Forbidden:** Hard-coded rates in other modules; converting without rounding.
