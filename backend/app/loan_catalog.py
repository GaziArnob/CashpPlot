"""The loan types every business sees in the Loan Center.

Eight sample products, from small and pricey (low credit score) to large and cheap (high credit score). Which ones a
business can take depends on its credit score and on how much it can safely repay each month (engines/loan.py).
They are SAMPLE products until real lenders are connected: the Loan Center says so, and the lender names are generic.
Amounts are in the business's own currency; the scale suits small businesses.
"""

# name, lender, kind, min_amount, max_amount, annual_rate_pct, tenure_months, min_credit_score
LOAN_TYPES = [
    ("Micro Enterprise Loan", "Sample Microfinance", "microfinance", 500, 15_000, 24.0, 12, 500),
    ("Seasonal Stock Loan", "Sample Microfinance", "microfinance", 1_000, 25_000, 21.0, 6, 520),
    ("Quick Trade Credit", "Sample Trade Finance", "working_capital", 1_000, 30_000, 18.0, 9, 550),
    ("Shop Expansion Loan", "Sample Trade Finance", "sme_term", 5_000, 100_000, 16.0, 24, 580),
    ("Small Business Booster", "Sample SME Bank", "working_capital", 3_000, 60_000, 14.0, 18, 600),
    ("Retail Growth Loan", "Sample SME Bank", "sme_term", 5_000, 150_000, 12.5, 24, 620),
    ("SME Working Capital Line", "Sample SME Bank", "working_capital", 10_000, 250_000, 11.0, 12, 650),
    ("SME Term Loan", "Sample SME Bank", "sme_term", 20_000, 500_000, 9.5, 36, 700),
]
