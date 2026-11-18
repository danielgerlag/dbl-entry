---
name: dblentry-reporting
description: How to answer questions about a DblEntry ledger - balances, statements, trial balance, income statement, dimension slicing and combined queries.
---

# Reporting and answering questions

Reads never change the ledger, so run as many as you need. Always state the date or period you used in your answer.

## Pick the query

| Question | Query |
|----------|-------|
| "How much is in X on date D?" | `get_balance` (account, date) |
| "What moved in X between A and B?" | `get_statement` (account, from, to) |
| "Do the books balance / overall position?" | `get_trial_balance` (date) |
| "Profit or loss for a period?" | `get_income_statement` (from, to) |
| "Balance for one customer / region?" | `get_balance` with `dimension` `Key='Value'` |
| Several figures at once | `execute_fql` with a multi-alias `GET` |

## Balances at a date

Balances are as of the given date. For month-end or year-end, pass the last day (`2024-12-31`). To compare periods, call it for each date.

## Dimension slicing

```sql
GET balance(@receivables, 2024-12-31, Client='Initial') AS initial;
GET balance(@revenue, 2024-12-31, Branch='North') AS north;
```

- A parent value (`North`) includes children (`North/East`, `North/West`).
- Dimension keys and values are **case-sensitive** and must match how journals were tagged exactly (e.g. `Branch` and `branch` are different keys). `get_statement` does not show dimensions, and there is no query that lists them.
- If a slice returns 0 but the account total is non-zero, the key or value probably does not match. Systematically retry the same query with the key lowercase, Capitalised and UPPER, and with singular/plural forms, before concluding there is no data. Compare slices against the untagged total to see what is tagged.
- Once one slice works, the key spelling is settled: **re-run every other slice with that same key** instead of reporting 0 for them. Sanity-check that the slices add up to the total you expect.
- Do not report "no data for that region" unless every plausible key spelling returned 0; say which spellings you tried.

## Combined report in one call

```sql
GET balance(@bank, 2024-12-31) AS cash,
    balance(@receivables, 2024-12-31) AS owed_to_us,
    trial_balance(2024-12-31) AS tb;
```

Useful helpers inside `GET`: `round(x, 2)`, `abs(x)`, `min(a, b)`, `max(a, b)`, arithmetic with `+ - * /`.

## Reconciling

- Trial balance: total debits must equal total credits. If not, report it as a data problem rather than adjusting figures.
- To explain a balance, call `get_statement` for the account; it lists date, description, amount and running balance.

## Presenting results

- Show the figures the engine returned; do not recompute or round them silently.
- Name the entity, date or period, and any dimension filter used.
- For empty results, say the account has no activity in that range rather than guessing.
