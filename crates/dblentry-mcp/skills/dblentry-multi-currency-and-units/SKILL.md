---
name: dblentry-multi-currency-and-units
description: Foreign-currency conversion and unit-tracked holdings (shares, lots) in DblEntry - convert/fx_rate, buying with UNITS, SELL with FIFO/LIFO/AVERAGE, SPLIT, market value and unrealized gain.
---

# Multi-currency and unit-tracked holdings

## Currency conversion

FX rates are ordinary rates (see `dblentry-accruals-and-schedules`), looked up as of a date using the closest prior value.

```sql
CREATE RATE usd_eur;
SET RATE usd_eur 0.92 2024-01-01;
GET convert(1000, 'usd_eur', 2024-03-31) AS eur,
    fx_rate('usd_eur', 2024-03-31) AS rate;
```

Pass the rate name as quoted text. Convert amounts explicitly before posting a journal in another currency; every journal still has to balance in a single amount.

**Always look the rate up for the transaction date** with `convert(...)` or `fx_rate(...)` (run it with `execute_fql`). Never assume or reuse a rate from memory or the prompt: a rate series usually has several values, and the one in effect on the transaction date is the one to use. Post the amount the engine returns.

## Unit-tracked accounts

Link an asset account to a price rate to track quantity, cost lots and market value:

```sql
CREATE RATE aapl_price;
CREATE ACCOUNT @stock_aapl ASSET UNITS 'aapl_price';
```

Buy by stating the units and cost per unit on the debit leg (journal amount = units x price):

```sql
SET RATE aapl_price 150 2024-04-01;
CREATE JOURNAL 2024-04-01, 1500, 'Buy'
  FOR Sector='Technology/Software'
  DEBIT @stock_aapl 10 UNITS AT 150,
  CREDIT @bank;
```

Each purchase is a separate lot. Update the price with `SET RATE` whenever you want market value to move.

## Selling

```sql
SELL 5 UNITS OF @stock_aapl AT 175 ON 2024-06-15
  METHOD FIFO
  PROCEEDS @bank
  GAIN_LOSS @realized_gains
  DESCRIPTION 'Sell shares';
```

- `METHOD` is `FIFO` (default), `LIFO` or `AVERAGE`.
- `FOR dim=value` limits which lots can be depleted (hierarchical values match children).
- The engine records proceeds and the realized gain or loss; you need `PROCEEDS` and `GAIN_LOSS` accounts to exist first.
- Check available units with `units(...)` before selling.

## Splits

```sql
SPLIT @stock_aapl 2 FOR 1 2024-08-01;
```

Adjusts open lots (units up, cost per unit down). Also update the price rate to the post-split price.

## Position queries

```sql
GET units(@stock_aapl, 2024-08-01) AS held,
    market_value(@stock_aapl, 2024-08-01) AS mv,
    cost_basis(@stock_aapl, 2024-08-01) AS avg_cost,
    unrealized_gain(@stock_aapl, 2024-08-01) AS unrealized,
    lots(@stock_aapl, 2024-08-01) AS open_lots;
```

All accept an optional dimension filter, e.g. `units(@stock_aapl, 2024-08-01, Sector='Technology')`.

## Workflow

1. `get_schema` to see unit accounts (`is_unit_account`) and their rate.
2. Make sure the price rate has a value on or before the date you value at.
3. Post buys, sells and splits in date order.
4. Report units, market value and gains from the position queries rather than computing them yourself.
5. If a statement fails, fix and resend only that statement; do not re-post journals or schedules that already succeeded (the ledger is append-only).
