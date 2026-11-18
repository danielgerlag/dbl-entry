---
name: dblentry-accruals-and-schedules
description: Time-based accounting in DblEntry - named rates, interest accruals with ACCRUE, and spreading amounts over periods with DISTRIBUTE (revenue recognition, prepaid amortization).
---

# Accruals and schedules

## Rates

A rate is a named, time-varying value (interest rate, FX rate, price...). Each value applies from its date until the next one.

```sql
CREATE RATE prime;
SET RATE prime 0.05 2024-01-01;
SET RATE prime 0.055 2024-07-01;
```

Read one with `GET fx_rate('prime', 2024-08-01) AS r;`. Rates are stored as decimals (`0.05` is 5%).

## Interest accrual (ACCRUE)

Computes interest on a dimension-by-dimension basis and posts the journals for you.

```sql
ACCRUE @loans FROM 2024-01-01 TO 2024-01-31
  WITH RATE prime
  COMPOUND DAILY
  BY customer
  INTO JOURNAL 2024-02-01, 'January interest'
  DEBIT @interest_receivable,
  CREDIT @interest_income;
```

- `BY customer` splits the calculation per value of that dimension, so the account balance must have been posted with `FOR customer=...`.
- **Annual rates need `COMPOUND DAILY`.** That mode divides the rate by 365 per day. Without `COMPOUND`, or with `COMPOUND CONTINUOUS`, the engine applies the raw rate every day, so an annual rate produces absurdly large interest. Use those modes only when the rate is already a per-day rate.
- Create the rate and its values **before** accruing; accrue each period once, or interest will be posted twice (the ledger is append-only).
- Check the result with `get_statement` on the income account.

## Spreading an amount (DISTRIBUTE)

Generates one journal per period, dated the last day of each period.

```sql
DISTRIBUTE 12000
  FROM 2024-01-01 TO 2024-12-31
  PERIOD MONTHLY
  FOR Customer='Acme'
  DESCRIPTION 'Revenue recognition'
  DEBIT @deferred_revenue,
  CREDIT @subscription_revenue;
```

- `PERIOD` is `MONTHLY`, `QUARTERLY` or `YEARLY`.
- Default is an even split with the remainder in the last period. Use that when the user asks for an even/equal monthly amount; add `PRORATE` only when they want allocation by actual days (it gives uneven monthly amounts that differ with month length).
- Typical uses: recognise deferred revenue (debit the liability, credit income); amortise a prepaid cost (debit expense, credit the prepaid asset).
- The up-front cash movement is a separate normal journal (for example debit bank, credit `@deferred_revenue`) posted before distributing.

## Workflow

1. `get_schema` to confirm accounts and rates exist; create what is missing.
2. Post the underlying journal (loan issued, cash received).
3. Run `ACCRUE` or `DISTRIBUTE`.
4. Verify with `get_trial_balance` and `get_statement`; report the generated amounts.
5. If a statement fails, fix and resend only that statement; do not re-post journals or schedules that already succeeded (the ledger is append-only).
