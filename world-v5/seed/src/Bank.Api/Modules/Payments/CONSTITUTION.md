# Payments — constitution
**Purpose:** Money transfers between accounts, inside the bank and across currencies.
**Owner:** Payments · **Risk:** HIGH
**Rules:** A customer pays only from an account they own. Each payment carries an idempotency key: the same key never pays twice. The daily limit from BankSettings applies per customer per UTC day, in EUR equivalent. Money moves only through the Ledger.
**Forbidden:** Paying twice for one key; skipping the limit or the fraud hold; trusting an account id without an ownership check.
