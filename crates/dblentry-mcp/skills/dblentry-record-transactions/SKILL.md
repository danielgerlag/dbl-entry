---
name: dblentry-record-transactions
description: How to set up a chart of accounts and record journals correctly in DblEntry - debits and credits, dimensions, splits, atomic batches, and reversing mistakes.
---

# Recording transactions

## 1. Chart of accounts first

Journals can only reference accounts that exist. Check `get_schema`, then create only what is missing:

```sql
CREATE ACCOUNT @bank ASSET;
CREATE ACCOUNT @payables LIABILITY;
CREATE ACCOUNT @sales INCOME;
CREATE ACCOUNT @rent EXPENSE;
CREATE ACCOUNT @equity EQUITY;
```

Pick the account type by what the account represents; it determines how balances and reports treat it. Use short lowercase snake_case ids.

## 2. Journals

```sql
CREATE JOURNAL 2024-03-15, 500, 'Description'
  FOR Customer='Acme', Region='US'
  DEBIT @bank,
  CREDIT @sales;
```

- Arguments: effective date, total amount, description.
- Total debits must equal total credits, otherwise `unbalanced journal: total debits (X) != total credits (Y)` and nothing is written.
- A leg without an amount uses the full journal amount.
- Normal sides: assets and expenses increase with a debit; liabilities, income and equity increase with a credit.

Common patterns:

| Event | Debit | Credit |
|-------|-------|--------|
| Owner invests cash | asset (bank) | equity |
| Cash sale | asset (bank) | income |
| Sale on credit | asset (receivables) | income |
| Customer pays invoice | asset (bank) | asset (receivables) |
| Pay an expense | expense | asset (bank) |
| Borrow money | asset (bank) | liability |

### Splits

Split one side across accounts with fixed amounts (each side must still total the journal amount):

```sql
CREATE JOURNAL 2024-03-01, 200, 'Fee'
  DEBIT @bank,
  CREDIT @fee_income 120,
  CREDIT @tax_payable 80;
```

Compute any percentage split yourself and pass the resulting amounts. (`60%` percentage legs are documented in the FQL reference but currently fail to parse.)

## 3. Dimensions

`FOR key=value` tags a journal so balances can be sliced later (customer, region, product...). Rules:

- Keep dimension **keys consistent** across journals; a typo creates a new, separate slice.
- Use `/` for hierarchy (`Region='Americas/US/West'`); querying a parent value includes all its children.
- Tag the journals you will want to report on by that key.

## 4. Batches and transactions

Everything submitted in one `execute_fql` call (separated by semicolons) is atomic. Group related postings in one call. Use explicit `BEGIN; ... COMMIT;` / `ROLLBACK;` only when you need control inside a script.

## 5. Corrections

You cannot edit or delete. To fix an error, post a **reversing journal** (swap debit and credit of the original, same amount, same dimensions) and then post the correct entry:

```sql
CREATE JOURNAL 2024-03-16, 500, 'Reverse: wrong customer'
  FOR Customer='Acme'
  DEBIT @sales,
  CREDIT @bank;
```

## 6. Verify

After writing, call `get_trial_balance` (total debits should equal total credits) or `get_balance` on the touched accounts and report them.

## Common errors

- `Account not found: x` - create it first or fix the id (do not include `@` in tool arguments, do include it in FQL).
- `Account already exists: x` - it exists; skip the `CREATE ACCOUNT`.
- `unbalanced journal: ...` - recheck the amounts on each side.
- `Entity not found: x` - `CREATE ENTITY 'x'` first, and pass `entity` on the call.
