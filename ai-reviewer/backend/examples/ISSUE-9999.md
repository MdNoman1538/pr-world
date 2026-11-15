# Issue 9999: StringFormatter fails on empty strings
Deserializing an empty string (length 0) should return string.Empty instead of throwing.
Acceptance: existing length limits and null checks must stay in place.
