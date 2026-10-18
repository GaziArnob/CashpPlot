# SME Finance Assistant — Backend

FastAPI backend for cash flow prediction, payment recovery, explainable credit scoring,
loan readiness and an AI financial agent. It uses only free AI options, and it works with no API keys
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

The seed builds one year of data for "Karim Traders" relative to today: a cash shortage of about
12,000 nine days ahead (a large supplier bill), Rahim Store 10 days overdue on 15,000, and
Hasan Enterprise more than 30 days overdue.

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

`LLM_PROVIDERS=gemini,groq,ollama` is the fallback order. A provider is used only when configured
(a key, or `OLLAMA_ENABLED=true`). If all fail or none is set, the agent uses keyword intents and
templates, so a demo never breaks. Customer and supplier names are replaced with aliases
("Customer C12") before any data reaches a provider, and restored in the answer.

Receipt scanning uses Tesseract when `pytesseract` and `Pillow` are installed, otherwise Gemini's
free vision; the result is a suggestion the owner confirms.

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
| Settings | `GET/PUT /settings`, `GET/POST /lender-access`, `DELETE /lender-access/{id}`, `GET /lender/view` (X-Lender-Token), `GET /settings/export`, `DELETE /settings/account` |

`/auth/refresh` reads the httpOnly refresh cookie and needs the header `X-Requested-With: fetch`.

## Notes

- Owner drawings reduce cash in the forecast, but credit and loan capacity use business cash flow before drawings.
- Overdue invoices are not counted as future inflow (conservative); they show up as recovery opportunities.
- Rate limits are in memory; use Redis if you run several workers. PostgreSQL Row-Level Security is not set up yet; isolation is enforced in the app on every query.
