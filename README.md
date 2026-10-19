# CashPilot

An AI financial assistant for small businesses. It warns the owner about cash shortages 7 to 30 days before they
happen, shows who to chase for payment and what to do about it, explains a 300 to 900 credit score, and estimates what
the business can safely borrow. English, any currency.

**Every number comes from testable calculations, not from an AI.** The language model only explains the results, and any
figure it adds that the engines did not produce is rejected. Nothing is paid, sent or applied for without the owner
pressing the button.

**Live demo:** https://chinese-hackathon.vercel.app (API: https://cashpilot-api-26h3.onrender.com)
**Local demo data:** `python -m seed.seed`, then sign in as `demo@example.com` / `Demo@12345`

The first request after a pause on the free hosting can take about 50 seconds.

## What it does

| Area | Features |
| --- | --- |
| Cash | Dashboard, 7-day (Free) and 30-day (Pro) forecast with the day cash runs short, what-if simulator, Cash Advisor action plan |
| Money records | Transactions (manual, CSV import, receipt scan, bank import), invoices and bills, customers, suppliers |
| Collections | Who to chase first (priority score), credit limits, reminders by WhatsApp or email after the owner approves |
| Suppliers | Payment plans, financing comparison, drafted messages (names are masked before any AI sees them) |
| Products | Margin, trend and stock-days per product: push, keep, shrink or clear |
| Credit and loans | Explainable credit score, a "how to raise it" planner, 8 loan types tied to the score, My loans, lender introductions with consent |
| Reports | Monthly profit and loss, insights, goals, export |
| AI Agent | Ask in plain language; answers use the business's own numbers |
| Notifications | 16 alert rules, unread count, preferences, optional urgent email |
| Team and security | Staff logins, 2FA, lender access links, data export, account deletion |

Free plan: transactions, customers, invoices, dashboard, 7-day forecast, notifications. Pro (14-day trial): the rest.
Billing is in demo mode (no payments).

## How it fits together

```
Browser -> Website (Next.js, Vercel) -> API (FastAPI, Render) -> Database (PostgreSQL, Neon)
                                              |-> Email (Mailjet / Brevo / SMTP)
                                              |-> WhatsApp (Meta Cloud API or Twilio)
                                              |-> AI (Groq, Gemini; optional)
                                              |-> Bank import (Plaid sandbox)
```

- `frontend/`: Next.js 16, React 19, Tailwind 4, Recharts. Screens only; all data and logic come from the API.
- `backend/`: FastAPI, SQLAlchemy 2, Alembic. `app/engines/` holds the calculations (forecast, collections, credit,
  loans, planner, payables, products, what-if), `app/api/` the endpoints, `app/messaging.py` email and WhatsApp
  delivery, `app/alert_rules.py` the alerts, `seed/` the demo data.
- PostgreSQL row-level security keeps each business's rows separate even if a query forgets the filter.

## Run it locally

Backend (port 8000):

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # macOS/Linux: .venv/bin/pip
cp .env.example .env                               # optional: add free Gemini / Groq keys
.venv/Scripts/python -m seed.seed                  # demo data (resets the local database)
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Frontend (port 3000):

```bash
cd frontend
npm install
npm run dev
```

It works with no API keys at all: the agent then answers from templates, and email or WhatsApp sends are only recorded.
Tests: `cd backend && .venv/Scripts/python -m pytest -q` (SQLite by default; PostgreSQL tests are opt-in).

## Deploy

Free tiers: Vercel (website), Render (API), Neon (database). Step by step, including the optional services, in [docs/deploy.md](docs/deploy.md).

## Documents

- [docs/CashPilot-project-overview.pdf](docs/CashPilot-project-overview.pdf): what is where and how it connects
- [docs/CashPilot-feature-guide.pdf](docs/CashPilot-feature-guide.pdf): every feature, how to use it, how it works
- [docs/manual-test-cases.md](docs/manual-test-cases.md): manual test cases
- [docs/deploy.md](docs/deploy.md): deployment
- [backend/README.md](backend/README.md): backend details

## Not included yet

Real lender integrations, live Pro payments (Stripe code exists but is off), production bank connections (Plaid
sandbox only), and a verified-domain email sender (mail from a Gmail address can land in spam).

CashPilot gives estimates from your own data. It is not financial advice, and loan figures are not an approval.
