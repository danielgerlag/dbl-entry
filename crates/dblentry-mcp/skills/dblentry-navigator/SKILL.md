---
name: dblentry-navigator
description: Start here. How to orient yourself in a DblEntry ledger over MCP - which tool to call first, how entities work, and which other skill to load for the task at hand.
---

# DblEntry navigator

DblEntry is a double-entry bookkeeping engine driven by FQL (Finance Query Language). Every accounting operation is an FQL statement; the engine enforces the invariants (balanced journals, append-only ledger, atomic batches).

## Orient before you write

1. `get_fql_spec` - load the grammar once per session. Do not guess syntax.
2. `list_entities` - see which sets of books exist. An empty list or only `default` means a fresh ledger.
3. `get_schema` with an `entity` - see existing accounts (id, type, unit-tracking) and rates. **Reuse existing accounts; never recreate them** (`Account already exists` is an error).
4. `get_trial_balance` at today's date - see the current state of the books before changing them.

## Entities

- An entity is an isolated set of books (own accounts, journals, rates).
- Each MCP tool call starts a fresh context. **Pass the `entity` argument on every call** rather than relying on `USE ENTITY` in an earlier call. Omitting it targets `default`.
- Create one with `execute_fql`: `CREATE ENTITY 'name'`. Entity names are quoted text in FQL; the tools take the same name unquoted.

## Choose the right tool

| Goal | Tool |
|------|------|
| Create accounts, record journals, accruals, rates, sales | `execute_fql` |
| One balance at a date | `get_balance` |
| Ledger lines for one account | `get_statement` |
| All balances | `get_trial_balance` |
| Revenue and expenses for a period | `get_income_statement` |
| Anything else (units, market value, conversions, multiple results) | `execute_fql` with `GET ...` |

The `get_*` tools are shortcuts that build a `GET` statement for you and validate their inputs. Dimension filters are passed as `Key=Value`, e.g. `Region='Americas'` (quote text values).

## Ground rules

- Account references use `@name`; account types are `ASSET`, `LIABILITY`, `INCOME`, `EXPENSE`, `EQUITY`.
- Dates are `YYYY-MM-DD` literals, text is single-quoted, amounts are exact decimals.
- A batch of statements is atomic: if one fails, the whole batch rolls back, so a failed call leaves the ledger unchanged.
- The ledger is **append-only**. There is no update or delete. Correct a mistake with a reversing journal (see `dblentry-record-transactions`).
- After any write, verify with a read (`get_trial_balance` or `get_balance`) and report the numbers to the user.

## Which skill next

- Setting up books or posting transactions -> `dblentry-record-transactions`
- Answering "how much / what happened" questions -> `dblentry-reporting`
- Interest, subscriptions, prepaid costs, rates -> `dblentry-accruals-and-schedules`
- Foreign currency, shares, lots, gains -> `dblentry-multi-currency-and-units`

Load a skill with the `get_skill` tool (or the `dblentry://skills/<name>` resource / prompt of the same name).
