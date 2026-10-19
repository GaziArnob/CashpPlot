# CashPilot — Backend

FastAPI backend for cash flow prediction, payment recovery, explainable credit scoring,
loan readiness, a cash advisor, supplier payment plans and an AI financial agent. English and any currency (USD by default). It uses only free AI options, and it works with no API keys
at all (the agent then answers from templates).

## Run

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # macOS/Linux: .venv/bin/pip
cp .env.example .env                              # optional: add free Gemini / Groq keys
.venv/Scripts/python -m seed.seed                 # demo data (resets the database)
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Demo login: `demo@example.com` / `Demo@12345`
- Tests: `.venv/Scripts/python -m pytest -q`

The seed builds one year of data for "Evergreen Traders" relative to today, with a cash shortage a
little over a week ahead (a large supplier bill), one customer ten days overdue and another more than
30 days overdue. The demo business is on the Pro plan.

Hosting and the optional services (email, WhatsApp, SMS, Stripe, Plaid) are covered in `../docs/deploy.md`.

## PostgreSQL and row-level security

SQLite is the default. To run on PostgreSQL, create a role that is **not** a superuser (superusers skip row-level
security) and a database it owns, then set `DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname`.
Migration `0005` turns on row-level security for every table with a `business_id`: a request only sees its own
business's rows even if a query forgets the filter. Seed, background jobs and the lender view run with the bypass
flag (see `app/db.py`). `audit_log` is excluded because login events have no business.

Check it on your database: `RLS_TEST_URL=<empty test database url> pytest tests/test_rls_postgres.py` (this wipes
that database's `public` schema, so use a scratch one).

`docker compose --env-file deploy/.env up --build` (repository root) starts PostgreSQL, the backend and the frontend.
Copy `deploy/.env.example` to `deploy/.env` first.

## Layout

```
app/
  main.py          app, CORS, security headers
  config.py        settings from .env
  models.py        database tables (phones/emails encrypted at rest)
  security.py      bcrypt, JWT, field encryption
  deps.py          auth, business scoping, object-level checks, rate limits, audit
  services.py      runs the engines for one business
  engines/         forecast, recovery, credit, loan, whatif, insights (pure Python, no DB)
  ai/              free LLM providers, agent tool loop, tools, templates, OCR
  api/             routes
seed/seed.py       demo data
tests/             engine and API tests
```

## Free AI

`LLM_PROVIDERS=groq,gemini,ollama` is the fallback order. Each business picks an AI mode in Settings: `cloud`, `local` (own machine only) or `off` (templates only). A provider is used only when configured
(a key, or `OLLAMA_ENABLED=true`). If all fail or none is set, the agent uses keyword intents and
templates, so a demo never breaks. Customer and supplier names are replaced with aliases
("Customer C12") before any data reaches a provider, and restored in the answer.

Receipt scanning uses Tesseract when it is installed (set `TESSERACT_CMD` and `TESSDATA_PREFIX` if it is not on PATH),
otherwise Gemini's free vision; the result is a suggestion the owner confirms.

## Main endpoints

| Area | Endpoints |
| --- | --- |
| Auth | `POST /auth/signup`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me`, `POST /onboarding` |
| Dashboard | `GET /dashboard/summary` |
| Transactions | `GET/POST /transactions`, `DELETE /transactions/{id}`, `GET /transactions/categories`, `POST /transactions/import`, `POST /transactions/scan` |
| Cash flow | `GET /cashflow/forecast?days=30`, `/cashflow/calendar`, `/cashflow/upcoming` |
| Ledger | `GET/POST /invoices`, `PATCH /invoices/{id}/paid`, `GET /recovery/priority`, `POST /recovery/reminder/{invoice_id}`, `GET /reminders`, `POST /reminders/{id}/send`, `GET/POST /suppliers`, `GET/POST /bills`, `PATCH /bills/{id}/paid` |
| Customers | `GET/POST /customers`, `GET /customers/{id}` |
| Credit | `GET /credit-score`, `/credit-score/history` |
| Loans | `GET /loan/readiness`, `/loan/recommendations`, `POST /loan/what-if`, `GET/POST /loans`, `PATCH /repayments/{id}/paid` |
| Reports | `GET /reports/pnl?month=YYYY-MM`, `/reports/insights`, `/reports/export` (PDF), `GET/POST/PUT/DELETE /goals`, `GET /notifications`, `PATCH /notifications/{id}/read` |
| Agent | `POST /agent/chat`, `POST /agent/chat/stream` (SSE), `GET /agent/history`, `/agent/suggestions` |
| Team | `GET/POST /team`, `DELETE /team/{id}`, `POST /team/{id}/reactivate`, `POST /team/{id}/password` (owner only; staff can record transactions, customers and invoices only) |
| Plans | `GET/POST /billing/plan` (demo billing, no payments), 402 "Upgrade to Pro" on Pro-only routes; new businesses get a 14-day Pro trial |
| Referrals | `GET/POST /referrals`, `POST /referrals/{id}/status` (consented introduction requests, not loan applications) |
| Two-factor | `POST /auth/2fa/setup`, `/auth/2fa/enable`, `/auth/2fa/disable`; login then needs `code` |
| Reminders | `POST /reminders/{id}/send` delivers by Brevo email, WhatsApp or Twilio SMS when that channel has keys, otherwise only records it (`delivery: manual`); `GET /messaging/channels` |
| Pro payments | `POST /billing/checkout`, `/billing/portal`, `/billing/webhook` (Stripe, signature-checked), with `BILLING_MODE=stripe` |
| Bank | `GET /bank/status`, `POST /bank/link-token`, `/bank/exchange`, `/bank/{id}/sync`, `DELETE /bank/{id}` (Plaid, owner and Pro) |
| Settings | `GET/PUT /settings`, `GET/POST /lender-access`, `DELETE /lender-access/{id}`, `GET /lender/view` (X-Lender-Token), `GET /settings/export`, `DELETE /settings/account` |

`/auth/refresh` reads the httpOnly refresh cookie and needs the header `X-Requested-With: fetch`.

## Notes

- Owner drawings reduce cash in the forecast, but credit and loan capacity use business cash flow before drawings.
- Overdue invoices are not counted as future inflow (conservative); they show up as recovery opportunities.
- Rate limits are in memory; use Redis if you run several workers. On SQLite isolation is enforced in the app on every query; on PostgreSQL row-level security adds a second layer.
