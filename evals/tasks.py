"""Eval tasks for the `dblentry-record-transactions` skill.

Each task has: a natural-language prompt, optional setup FQL (run before the agent),
deterministic end-state checks against the ledger, and a reference solution used to
validate the grader. Fixtures live here only; they must never be copied into skills.
"""
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

ENTITY = "Acme"
END = "2024-12-31"

BASE = (
    "CREATE ACCOUNT @bank ASSET; CREATE ACCOUNT @equity EQUITY; "
    "CREATE JOURNAL 2024-01-01, 5000, 'Opening capital' DEBIT @bank, CREDIT @equity;"
)
SALES = "CREATE ACCOUNT @sales INCOME;"


def _num(text):
    m = re.search(r"result:\s*(-?[\d.]+)", text)
    return Decimal(m.group(1)) if m else None


def bal(c, account, date=END, dim=None):
    args = {"account": account, "date": date, "entity": ENTITY}
    if dim:
        args["dimension"] = dim
    err, text = c.call("get_balance", args)
    return None if err else _num(text)


def accounts(c):
    err, text = c.call("get_schema", {"entity": ENTITY})
    return [] if err else json.loads(text)["accounts"]


def typed_total(c, acct_type, dim=None, date=END):
    """Sum of balances for all accounts of a type (id-agnostic)."""
    vals = [bal(c, a["id"], date, dim) for a in accounts(c) if a["type"] == acct_type]
    return sum((v for v in vals if v is not None), Decimal(0))


def eq(c, account, expected, **kw):
    got = bal(c, account, **kw)
    where = f" ({kw['dim']})" if kw.get("dim") else ""
    if kw.get("date") and kw["date"] != END:
        where += f" as of {kw['date']}"
    return (f"balance of '{account}'{where} should be {expected}, got {got}",
            got is not None and got == Decimal(expected))


def eq_type(c, acct_type, expected, **kw):
    got = typed_total(c, acct_type, **kw)
    where = f" ({kw['dim']})" if kw.get("dim") else ""
    return (f"total of all {acct_type} accounts{where} should be {expected}, got {got}",
            got == Decimal(expected))


@dataclass
class Task:
    id: str
    prompt: str
    setup: str
    checks: Callable
    solution: str
    answer_contains: list = field(default_factory=list)
    skill: str = "dblentry-record-transactions"


def get_value(c, expr, alias="v", date=END):
    """Evaluate a single GET expression via execute_fql and parse its numeric result."""
    err, text = c.fql(f"GET {expr} AS {alias};", entity=ENTITY)
    m = re.search(rf"{alias}:\s*(-?[\d.]+)", text)
    return None if err or not m else Decimal(m.group(1))


def eq_get(c, label, expr, expected):
    got = get_value(c, expr)
    return (f"{label} should be {expected}, got {got}", got is not None and got == Decimal(expected))


TASKS = [
    Task(
        "invest_new_books",
        "Acme is just starting its books and has no accounts yet. On 2024-01-02 the owner invests 10,000 "
        "in cash. Set up the accounts you need and record it.",
        "",
        lambda c: [eq_type(c, "asset", 10000), eq_type(c, "equity", 10000)],
        "CREATE ACCOUNT @cash ASSET; CREATE ACCOUNT @capital EQUITY; "
        "CREATE JOURNAL 2024-01-02, 10000, 'Investment' DEBIT @cash, CREDIT @capital;",
    ),
    Task(
        "cash_sale_dimensions",
        "Record a cash sale of 750 on 2024-02-10 to the customer 'Globex' in the region 'EMEA'. "
        "Tag it with Customer and Region dimensions so it can be reported by either.",
        BASE + SALES,
        lambda c: [eq(c, "bank", 5750), eq(c, "sales", 750),
                   eq(c, "sales", 750, dim="Customer='Globex'"),
                   eq(c, "sales", 750, dim="Region='EMEA'")],
        "CREATE JOURNAL 2024-02-10, 750, 'Sale' FOR Customer='Globex', Region='EMEA' DEBIT @bank, CREDIT @sales;",
    ),
    Task(
        "pay_rent",
        "On 2024-03-01 we paid 1,200 rent from the bank account. Record it.",
        BASE + "CREATE ACCOUNT @rent EXPENSE;",
        lambda c: [eq(c, "bank", 3800), eq(c, "rent", 1200)],
        "CREATE JOURNAL 2024-03-01, 1200, 'Rent' DEBIT @rent, CREDIT @bank;",
    ),
    Task(
        "credit_sale_then_payment",
        "On 2024-03-01 we invoiced a customer 2,000 for goods (no cash yet). On 2024-03-20 they paid 1,500 of it. "
        "Record both events.",
        BASE + SALES + "CREATE ACCOUNT @receivables ASSET;",
        lambda c: [eq(c, "receivables", 500), eq(c, "bank", 6500), eq(c, "sales", 2000)],
        "CREATE JOURNAL 2024-03-01, 2000, 'Invoice' DEBIT @receivables, CREDIT @sales; "
        "CREATE JOURNAL 2024-03-20, 1500, 'Payment' DEBIT @bank, CREDIT @receivables;",
    ),
    Task(
        "fixed_amount_split",
        "On 2024-04-05 we received 1,000 into the bank: 800 is service fees (income) and 200 is sales tax we "
        "owe the tax authority. Record it as a single journal.",
        BASE + "CREATE ACCOUNT @service_fees INCOME; CREATE ACCOUNT @sales_tax_payable LIABILITY;",
        lambda c: [eq(c, "bank", 6000), eq(c, "service_fees", 800), eq(c, "sales_tax_payable", 200)],
        "CREATE JOURNAL 2024-04-05, 1000, 'Fees' DEBIT @bank, CREDIT @service_fees 800, CREDIT @sales_tax_payable 200;",
    ),
    Task(
        "percentage_split",
        "On 2024-05-02 we received 2,000 into the bank. Book 60% of it as product revenue and 40% as service "
        "revenue.",
        BASE + "CREATE ACCOUNT @product_revenue INCOME; CREATE ACCOUNT @service_revenue INCOME;",
        lambda c: [eq(c, "bank", 7000), eq(c, "product_revenue", 1200), eq(c, "service_revenue", 800)],
        "CREATE JOURNAL 2024-05-02, 2000, 'Receipt' DEBIT @bank, CREDIT @product_revenue 1200, CREDIT @service_revenue 800;",
    ),
    Task(
        "correct_wrong_customer",
        "The 500 sale on 2024-03-15 was recorded against customer 'Initech' but it should have been 'Globex'. "
        "Fix the ledger so the history is preserved and Initech has no sales left.",
        BASE + SALES + "CREATE JOURNAL 2024-03-15, 500, 'Sale' FOR Customer='Initech' DEBIT @bank, CREDIT @sales;",
        lambda c: [eq(c, "sales", 0, dim="Customer='Initech'"), eq(c, "sales", 500, dim="Customer='Globex'"),
                   eq(c, "sales", 500), eq(c, "bank", 5500)],
        "CREATE JOURNAL 2024-03-16, 500, 'Reverse' FOR Customer='Initech' DEBIT @sales, CREDIT @bank; "
        "CREATE JOURNAL 2024-03-16, 500, 'Corrected sale' FOR Customer='Globex' DEBIT @bank, CREDIT @sales;",
    ),
    Task(
        "new_expense_account",
        "On 2024-06-10 we paid a 300 electricity bill from the bank. There is no account for utilities yet; "
        "create what's needed and record it.",
        BASE,
        lambda c: [eq(c, "bank", 4700), eq_type(c, "expense", 300)],
        "CREATE ACCOUNT @utilities EXPENSE; CREATE JOURNAL 2024-06-10, 300, 'Electricity' DEBIT @utilities, CREDIT @bank;",
    ),
    Task(
        "dated_payments",
        "Record these payments from the bank: rent 1,000 on 2024-01-05, utilities 150 on 2024-01-10, and supplies "
        "75 on 2024-01-12. Use the correct dates; reports by date matter.",
        BASE + "CREATE ACCOUNT @rent EXPENSE; CREATE ACCOUNT @utilities EXPENSE; CREATE ACCOUNT @supplies EXPENSE;",
        lambda c: [eq(c, "rent", 1000), eq(c, "utilities", 150), eq(c, "supplies", 75),
                   eq(c, "bank", 3775), eq(c, "bank", 4000, date="2024-01-08"), eq(c, "bank", 3850, date="2024-01-11")],
        "CREATE JOURNAL 2024-01-05, 1000, 'Rent' DEBIT @rent, CREDIT @bank; "
        "CREATE JOURNAL 2024-01-10, 150, 'Utilities' DEBIT @utilities, CREDIT @bank; "
        "CREATE JOURNAL 2024-01-12, 75, 'Supplies' DEBIT @supplies, CREDIT @bank;",
    ),
    Task(
        "loan_and_repayment",
        "On 2024-04-01 we borrowed 5,000 from a lender, paid into the bank. On 2024-05-01 we repaid 1,000 of the "
        "principal from the bank. Record both.",
        BASE,
        lambda c: [eq(c, "bank", 9000), eq_type(c, "liability", 4000)],
        "CREATE ACCOUNT @loan LIABILITY; CREATE JOURNAL 2024-04-01, 5000, 'Loan' DEBIT @bank, CREDIT @loan; "
        "CREATE JOURNAL 2024-05-01, 1000, 'Repay' DEBIT @loan, CREDIT @bank;",
    ),
    Task(
        "hierarchy_and_answer",
        "Record two cash sales on 2024-07-01: 400 in region 'Americas/US/West' and 600 in region "
        "'Americas/Canada' (tag with a Region dimension). Then tell me the total sales for the whole 'Americas' region.",
        BASE + SALES,
        lambda c: [eq(c, "sales", 400, dim="Region='Americas/US/West'"),
                   eq(c, "sales", 600, dim="Region='Americas/Canada'"),
                   eq(c, "sales", 1000, dim="Region='Americas'")],
        "CREATE JOURNAL 2024-07-01, 400, 'Sale' FOR Region='Americas/US/West' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-07-01, 600, 'Sale' FOR Region='Americas/Canada' DEBIT @bank, CREDIT @sales;",
        answer_contains=["1000"],
    ),
    Task(
        "two_debit_legs",
        "On 2024-08-01 we made a 100 sale: the customer paid 60 in cash now and the remaining 40 is owed to us. "
        "Record it as one journal.",
        BASE + SALES + "CREATE ACCOUNT @receivables ASSET;",
        lambda c: [eq(c, "bank", 5060), eq(c, "receivables", 40), eq(c, "sales", 100)],
        "CREATE JOURNAL 2024-08-01, 100, 'Sale' DEBIT @bank 60, DEBIT @receivables 40, CREDIT @sales;",
    ),
]

ACCRUALS = "dblentry-accruals-and-schedules"
UNITS = "dblentry-multi-currency-and-units"
REPORTING = "dblentry-reporting"

STOCK = ("CREATE RATE aapl_price; CREATE ACCOUNT @stock_aapl ASSET UNITS 'aapl_price'; "
         "CREATE ACCOUNT @realized_gains INCOME;")
TWO_LOTS = (
    "SET RATE aapl_price 100 2024-01-10; "
    "CREATE JOURNAL 2024-01-10, 1000, 'Buy' DEBIT @stock_aapl 10 UNITS AT 100, CREDIT @bank; "
    "SET RATE aapl_price 120 2024-02-10; "
    "CREATE JOURNAL 2024-02-10, 1200, 'Buy' DEBIT @stock_aapl 10 UNITS AT 120, CREDIT @bank;"
)
SELL_PROMPT = ("We hold two lots of shares in the unit-tracked account 'stock_aapl' (10 bought on 2024-01-10 at 100, "
               "10 bought on 2024-02-10 at 120). On 2024-03-01 we sold 15 shares at 150 each, cash into the bank. "
               "Record the sale using {method} cost lots; book the gain in the 'realized_gains' account.")

# Harder tasks covering the other skills; used to compare agents that already ace the core set.
ADVANCED = [
    Task(
        "deferred_revenue_recognition",
        "On 2024-01-01 a customer prepaid 12,000 for a 12-month subscription covering Jan-Dec 2024. Record the "
        "receipt, then recognise the revenue evenly month by month for the whole year (the accounts "
        "'deferred_revenue' and 'subscription_revenue' exist).",
        BASE + "CREATE ACCOUNT @deferred_revenue LIABILITY; CREATE ACCOUNT @subscription_revenue INCOME;",
        lambda c: [eq(c, "bank", 17000), eq(c, "deferred_revenue", 0),
                   eq(c, "deferred_revenue", 9000, date="2024-03-31"),
                   eq(c, "subscription_revenue", 12000), eq(c, "subscription_revenue", 3000, date="2024-03-31")],
        "CREATE JOURNAL 2024-01-01, 12000, 'Prepaid' DEBIT @bank, CREDIT @deferred_revenue; "
        "DISTRIBUTE 12000 FROM 2024-01-01 TO 2024-12-31 PERIOD MONTHLY DESCRIPTION 'Recognition' "
        "DEBIT @deferred_revenue, CREDIT @subscription_revenue;",
        skill=ACCRUALS,
    ),
    Task(
        "prepaid_insurance",
        "On 2024-01-01 we paid 2,400 from the bank for a year of insurance. Record the payment as a prepaid asset "
        "and expense it evenly by month through 2024 (accounts 'prepaid_insurance' and 'insurance_expense' exist).",
        BASE + "CREATE ACCOUNT @prepaid_insurance ASSET; CREATE ACCOUNT @insurance_expense EXPENSE;",
        lambda c: [eq(c, "bank", 2600), eq(c, "prepaid_insurance", 0),
                   eq(c, "prepaid_insurance", 1800, date="2024-03-31"),
                   eq(c, "insurance_expense", 2400), eq(c, "insurance_expense", 1200, date="2024-06-30")],
        "CREATE JOURNAL 2024-01-01, 2400, 'Insurance' DEBIT @prepaid_insurance, CREDIT @bank; "
        "DISTRIBUTE 2400 FROM 2024-01-01 TO 2024-12-31 PERIOD MONTHLY DESCRIPTION 'Amortise' "
        "DEBIT @insurance_expense, CREDIT @prepaid_insurance;",
        skill=ACCRUALS,
    ),
    Task(
        "loan_interest_accrual",
        "On 2024-01-01 we lent 10,000 from the bank to customer 'Initech' (record it against the 'loans' account, "
        "tagged with the customer). Interest accrues at 6% per year. Set up the rate and accrue interest for "
        "2024-01-01 to 2024-01-31, compounded daily per customer, posting on 2024-02-01 as a debit to "
        "'interest_receivable' and a credit to 'interest_income'.",
        BASE + "CREATE ACCOUNT @loans ASSET; CREATE ACCOUNT @interest_receivable ASSET; "
        "CREATE ACCOUNT @interest_income INCOME;",
        lambda c: [eq(c, "loans", 10000), eq(c, "interest_income", "51.08"), eq(c, "interest_receivable", "51.08")],
        "CREATE JOURNAL 2024-01-01, 10000, 'Loan' FOR customer='Initech' DEBIT @loans, CREDIT @bank; "
        "CREATE RATE loan_rate; SET RATE loan_rate 0.06 2024-01-01; "
        "ACCRUE @loans FROM 2024-01-01 TO 2024-01-31 WITH RATE loan_rate COMPOUND DAILY BY customer "
        "INTO JOURNAL 2024-02-01, 'January interest' DEBIT @interest_receivable, CREDIT @interest_income;",
        skill=ACCRUALS,
    ),
    Task(
        "rate_lookup",
        "The ledger has a rate named 'base_rate'. What value is in effect on 2024-05-15, and what value on "
        "2024-08-01? Report both as decimals.",
        "CREATE RATE base_rate; SET RATE base_rate 0.04 2024-01-01; SET RATE base_rate 0.055 2024-07-01; "
        "SET RATE base_rate 0.06 2024-09-01;",
        lambda c: [],
        "",
        answer_contains=["0.04", "0.055"],
        skill=ACCRUALS,
    ),
    Task(
        "fx_invoice",
        "On 2024-03-15 we invoiced a European customer 2,000 EUR. Our books are in USD and the ledger has an FX "
        "rate named 'eur_usd' (USD per 1 EUR). Record the invoice in USD using the rate in effect on the invoice "
        "date (accounts 'receivables' and 'sales' exist).",
        BASE + SALES + "CREATE ACCOUNT @receivables ASSET; CREATE RATE eur_usd; "
        "SET RATE eur_usd 1.10 2024-01-01; SET RATE eur_usd 1.20 2024-03-01; SET RATE eur_usd 1.30 2024-04-01;",
        lambda c: [eq(c, "receivables", 2400), eq(c, "sales", 2400)],
        "CREATE JOURNAL 2024-03-15, 2400, 'EUR invoice' DEBIT @receivables, CREDIT @sales;",
        skill=UNITS,
    ),
    Task(
        "fx_convert_answer",
        "Using the ledger's 'usd_eur' rate (EUR per 1 USD), how many EUR is 5,000 USD worth on 2024-03-31?",
        "CREATE RATE usd_eur; SET RATE usd_eur 0.92 2024-01-01; SET RATE usd_eur 0.90 2024-03-01; "
        "SET RATE usd_eur 0.88 2024-05-01;",
        lambda c: [],
        "",
        answer_contains=["4500"],
        skill=UNITS,
    ),
    Task(
        "buy_shares",
        "On 2024-04-01 we bought 10 shares of AAPL at 150 each, paid from the bank. The holdings account "
        "'stock_aapl' already exists and tracks units against the 'aapl_price' rate.",
        BASE + "CREATE RATE aapl_price; CREATE ACCOUNT @stock_aapl ASSET UNITS 'aapl_price'; "
        "SET RATE aapl_price 150 2024-04-01;",
        lambda c: [eq(c, "bank", 3500), eq(c, "stock_aapl", 1500),
                   eq_get(c, "units held on 2024-04-02", "units(@stock_aapl, 2024-04-02)", 10)],
        "CREATE JOURNAL 2024-04-01, 1500, 'Buy' DEBIT @stock_aapl 10 UNITS AT 150, CREDIT @bank;",
        skill=UNITS,
    ),
    Task(
        "sell_fifo",
        SELL_PROMPT.format(method="FIFO"),
        BASE + STOCK + TWO_LOTS,
        lambda c: [eq(c, "bank", 5050), eq(c, "realized_gains", 650), eq(c, "stock_aapl", 600),
                   eq_get(c, "units left", "units(@stock_aapl, 2024-03-02)", 5)],
        "SELL 15 UNITS OF @stock_aapl AT 150 ON 2024-03-01 METHOD FIFO PROCEEDS @bank GAIN_LOSS @realized_gains "
        "DESCRIPTION 'Sale';",
        skill=UNITS,
    ),
    Task(
        "sell_lifo",
        SELL_PROMPT.format(method="LIFO (last in, first out)"),
        BASE + STOCK + TWO_LOTS,
        lambda c: [eq(c, "bank", 5050), eq(c, "realized_gains", 550), eq(c, "stock_aapl", 500),
                   eq_get(c, "units left", "units(@stock_aapl, 2024-03-02)", 5)],
        "SELL 15 UNITS OF @stock_aapl AT 150 ON 2024-03-01 METHOD LIFO PROCEEDS @bank GAIN_LOSS @realized_gains "
        "DESCRIPTION 'Sale';",
        skill=UNITS,
    ),
    Task(
        "split_and_value",
        "We hold 10 shares in 'stock_aapl' (bought 2024-01-10 at 100). On 2024-04-01 the stock split 2-for-1 and "
        "the market price is now 75 per share. Record the split and the new price, then tell me the units held "
        "and the market value on 2024-04-02.",
        BASE + STOCK + "SET RATE aapl_price 100 2024-01-10; "
        "CREATE JOURNAL 2024-01-10, 1000, 'Buy' DEBIT @stock_aapl 10 UNITS AT 100, CREDIT @bank;",
        lambda c: [eq_get(c, "units on 2024-04-02", "units(@stock_aapl, 2024-04-02)", 20),
                   eq_get(c, "market value on 2024-04-02", "market_value(@stock_aapl, 2024-04-02)", 1500)],
        "SPLIT @stock_aapl 2 FOR 1 2024-04-01; SET RATE aapl_price 75 2024-04-01;",
        answer_contains=["1500"],
        skill=UNITS,
    ),
    Task(
        "quarter_profit_and_cash",
        "What was our profit for Q2 2024 (2024-04-01 to 2024-06-30), and how much cash did we have at the end "
        "of that quarter?",
        BASE + SALES + "CREATE ACCOUNT @rent EXPENSE; "
        "CREATE JOURNAL 2024-01-15, 3000, 'Sale' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-01-20, 1000, 'Rent' DEBIT @rent, CREDIT @bank; "
        "CREATE JOURNAL 2024-04-10, 2000, 'Sale' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-05-12, 1500, 'Sale' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-06-20, 500, 'Sale' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-04-25, 800, 'Rent' DEBIT @rent, CREDIT @bank; "
        "CREATE JOURNAL 2024-06-25, 800, 'Rent' DEBIT @rent, CREDIT @bank; "
        "CREATE JOURNAL 2024-08-01, 9999, 'Late sale' DEBIT @bank, CREDIT @sales;",
        lambda c: [],
        "",
        answer_contains=["2400", "9400"],
        skill=REPORTING,
    ),
    Task(
        "customer_receivable_history",
        "How much did customer 'Globex' owe us on 2024-03-31, and how much on 2024-06-30?",
        BASE + SALES + "CREATE ACCOUNT @receivables ASSET; "
        "CREATE JOURNAL 2024-02-01, 2000, 'Invoice' FOR Customer='Globex' DEBIT @receivables, CREDIT @sales; "
        "CREATE JOURNAL 2024-02-10, 800, 'Invoice' FOR Customer='Initech' DEBIT @receivables, CREDIT @sales; "
        "CREATE JOURNAL 2024-05-01, 1200, 'Payment' FOR Customer='Globex' DEBIT @bank, CREDIT @receivables; "
        "CREATE JOURNAL 2024-06-15, 300, 'Invoice' FOR Customer='Globex' DEBIT @receivables, CREDIT @sales;",
        lambda c: [],
        "",
        answer_contains=["2000", "1100"],
        skill=REPORTING,
    ),
    Task(
        "regional_sales_hidden_key",
        "What were our total sales for the EMEA region and for the APAC region (all of 2024)?",
        BASE + SALES +
        "CREATE JOURNAL 2024-02-01, 300, 'Sale' FOR region='EMEA/UK' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-03-01, 500, 'Sale' FOR region='EMEA/DE' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-04-01, 900, 'Sale' FOR region='APAC/JP' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-05-01, 250, 'Sale' DEBIT @bank, CREDIT @sales;",
        lambda c: [],
        "",
        answer_contains=["800", "900"],
        skill=REPORTING,
    ),
    Task(
        "trial_balance_total",
        "Do the books balance as at 2024-06-30? Tell me the total debits on the trial balance.",
        BASE + SALES + "CREATE ACCOUNT @supplies EXPENSE; "
        "CREATE JOURNAL 2024-02-01, 1200, 'Sale' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-03-01, 300, 'Supplies' DEBIT @supplies, CREDIT @bank; "
        "CREATE JOURNAL 2024-09-01, 4000, 'Late sale' DEBIT @bank, CREDIT @sales;",
        lambda c: [],
        "",
        answer_contains=["6200"],
        skill=REPORTING,
    ),
    Task(
        "monthly_spend",
        "How much did we spend on utilities in each of January, February and March 2024 (separately)?",
        BASE + "CREATE ACCOUNT @utilities EXPENSE; "
        "CREATE JOURNAL 2024-01-05, 130, 'Power' DEBIT @utilities, CREDIT @bank; "
        "CREATE JOURNAL 2024-02-07, 275, 'Power' DEBIT @utilities, CREDIT @bank; "
        "CREATE JOURNAL 2024-03-03, 95, 'Power' DEBIT @utilities, CREDIT @bank; "
        "CREATE JOURNAL 2024-04-02, 500, 'Power' DEBIT @utilities, CREDIT @bank;",
        lambda c: [],
        "",
        answer_contains=["130", "275", "95"],
        skill=REPORTING,
    ),
    Task(
        "product_sales_hidden_key",
        "What were our total sales for the software product line and for the hardware product line in 2024?",
        BASE + SALES +
        "CREATE JOURNAL 2024-02-01, 600, 'Sale' FOR product='Software/Licenses' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-03-01, 350, 'Sale' FOR product='Software/Support' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-04-01, 800, 'Sale' FOR product='Hardware/Devices' DEBIT @bank, CREDIT @sales; "
        "CREATE JOURNAL 2024-05-01, 125, 'Sale' DEBIT @bank, CREDIT @sales;",
        lambda c: [],
        "",
        answer_contains=["950", "800"],
        skill=REPORTING,
    ),
    Task(
        "quarterly_amortization",
        "On 2024-01-01 we paid 6,000 from the bank for a software licence covering all of 2024. Record it as a "
        "prepaid asset and expense it evenly each quarter (accounts 'prepaid_software' and 'software_expense' "
        "exist).",
        BASE + "CREATE ACCOUNT @prepaid_software ASSET; CREATE ACCOUNT @software_expense EXPENSE;",
        lambda c: [eq(c, "bank", -1000), eq(c, "prepaid_software", 0),
                   eq(c, "prepaid_software", 3000, date="2024-06-30"),
                   eq(c, "software_expense", 6000), eq(c, "software_expense", 1500, date="2024-03-31")],
        "CREATE JOURNAL 2024-01-01, 6000, 'Licence' DEBIT @prepaid_software, CREDIT @bank; "
        "DISTRIBUTE 6000 FROM 2024-01-01 TO 2024-12-31 PERIOD QUARTERLY DESCRIPTION 'Amortise' "
        "DEBIT @software_expense, CREDIT @prepaid_software;",
        skill=ACCRUALS,
    ),
]

ALL_TASKS = TASKS + ADVANCED
BY_ID = {t.id: t for t in ALL_TASKS}
SUITES = {"core": TASKS, "advanced": ADVANCED, "all": ALL_TASKS}

