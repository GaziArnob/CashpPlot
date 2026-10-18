# CashPilot — Frontend

Next.js 16 (App Router), React 19, Tailwind 4, Recharts. English only; money is formatted for the business's own currency.

## Run

The backend must be running on port 8000 (see `../backend/README.md`).

```bash
npm install
npm run dev        # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL` in `.env.local` if the API is not at `http://localhost:8000`.

Demo login: `demo@example.com` / `Demo@12345` (created by `python -m seed.seed` in the backend).

## Pages

| Area | Routes |
| --- | --- |
| Public | `/` landing, `/signup`, `/login` (asks for a code when two-factor is on), `/onboarding`, `/lender` (lender pastes an access token) |
| Overview | `/dashboard`, `/advisor` |
| Money | `/transactions` (CSV import, receipt scan), `/cashflow`, `/ledger`, `/customers`, `/payables`, `/products` |
| Finance | `/credit-score`, `/loan` (including introduction requests), `/reports` |
| Assistant | `/agent` |
| Account | `/settings` (profile, AI privacy, plan, team, lender access, two-factor, export and delete) |

Staff accounts only see Transactions, Ledger and Customers. Pro-only pages show an "Upgrade to Pro" notice on a free plan.

## Checks

```bash
npx tsc --noEmit
npx eslint .
```
