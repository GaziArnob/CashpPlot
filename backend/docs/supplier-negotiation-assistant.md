# AI Early-Payment & Supplier Negotiation Assistant

Spots payment clashes before they happen, proposes new payment schedules to suppliers, drafts the
request (English or Bangla), compares financing costs, and recommends the cheapest safe mix.

**Safety rules (enforced in code, covered by tests)**

- The app never pays a supplier, never sends a message and never applies for financing.
- Every plan is a draft until the owner approves it. It affects the cash forecast only after the owner
  records that the supplier **accepted** it.
- Editing an approved plan sends it back to draft, so an approval always matches what was approved.
- Messages are editable drafts. "I sent it" only records that the owner sent it themselves.
- "I paid this" only records a payment the owner made. No money moves.
- Financing offers are **demo data** and are labelled so everywhere. They are never presented as real offers or approvals.

## Where it lives

| Area | File |
| --- | --- |
| Dated cash flow, conflicts, bill options, financing costs | `app/engines/payables.py` |
| Recommendation (simulates each step) | `app/engines/payables_recommend.py` |
| Supplier messages (English, template + guarded AI rewrite) | `app/ai/negotiation.py` |
| API | `app/api/payables.py` |
| Service glue | `app/services.py` (`payables_analysis`, `supplier_profiles`, `financing_offers`) |
| Tables | `app/models.py`, migration `migrations/versions/0003_supplier_negotiation_assistant.py` |
| Page | `frontend/app/(app)/payables/page.tsx`, `frontend/components/payables/*` |
| Tests | `tests/test_payables.py` (44 tests) |

## Database (migration 0003)

New tables: `payment_plans`, `payment_plan_installments`, `negotiation_drafts`, `financing_offers`,
`payables_recommendations`. New columns: `suppliers.payment_terms_days`, `early_pay_discount_pct`,
`early_pay_within_days`, `late_fee_pct_month`; `bills.amount_paid`.

| Table | Purpose |
| --- | --- |
| `payment_plans` | One proposed schedule for one bill. `status`: draft, approved, accepted, rejected, cancelled, completed. Keeps who approved and when. |
| `payment_plan_installments` | The dated parts of a plan: `due_date`, `amount`, `status` (scheduled/paid). |
| `negotiation_drafts` | Editable message per bill/plan, with `lang` (always `en`), `generated_by`, `status` (draft/marked_sent). |
| `financing_offers` | Catalogue used for comparisons. Seeded rows have `is_demo = true`. |
| `payables_recommendations` | History: one row per saved recommendation, with the full payload for later review. |

Every table that belongs to a business carries `business_id`, and every query filters on the business of the
logged-in user. Reading or changing another business's record returns 404.

## How the numbers are produced

**Dated 30-day cash flow.** Each amount is counted exactly once and tagged.

- *Confirmed*: supplier bills (or the installments of an **accepted** plan instead of the bill's due date),
  loan installments, recurring payables (rent, salaries).
- *Estimated*: day-to-day sales and running costs (the existing forecast), and customer payments.
- Customer payments are placed on each invoice's **expected date** = due date + that customer's usual delay.
  Partly paid invoices count only the remainder. An invoice already later than the customer's habit is **at risk**:
  counted at 60% a week from now. A customer with no record is assumed a week late and counted at 80%.
- Daily balance = previous balance + estimated in + receivables - estimated out - confirmed out.

**Conflicts.** A run of days below the safety level, with the payments that cause it and any money that arrives too late.

**Bill options.** *Pay on time*, *extension* (smallest of 7/14/21/30 days that keeps cash safe, else the best one), and
*partial* (a rounded first part the cash can carry, the rest on the first date that is affordable). Estimated fee =
the supplier's late-fee % a month x days late. Each option reports the lowest balance it leads to.

**Financing cost** (all demo rates): principal, fees, interest, repayment dates, total repayment, total cost, cost per 100
and effective annual rate.

- Invoice advance: advance % of an eligible invoice (not at risk, big enough, paid later than the funds arrive);
  fee % of the invoice; interest on the advance until the customer's expected payment date; repaid from that payment.
- Overdraft: fee + interest for the days needed, one repayment.
- Term loan: equal monthly installments (EMI), fee up front.

**Recommendation.** Each candidate step (a supplier plan or an offer) is judged by **applying its dated cash movements
to the forecast**. The engine repeatedly picks the step that lifts the lowest balance at the lowest cost per taka of
relief (supplier changes before debt, then lower risk), sizes loans to the gap that is still left, and stops once the
lowest balance is above the safety level. A loan repaid before the tightest day therefore earns no credit. Options not
chosen are listed with the reason.

## API

All endpoints need `Authorization: Bearer <token>`.

| Method and path | What it does |
| --- | --- |
| `GET /payables/analysis` | Cash flow, conflicts, upcoming bills, per-bill options, financing comparison, recommendation, at-risk invoices |
| `POST /payables/recommendations` | Run and save a recommendation to history |
| `GET /payables/recommendations` / `/{id}` | History list / one saved recommendation |
| `GET /financing/compare?amount=&needed_by_days=&duration_days=` | Compare demo offers for an amount you choose |
| `GET /payment-plans`, `GET /payment-plans/{id}` | List / read plans |
| `POST /payment-plans` | Create a draft. Installments must add up to what is still owed, dates not in the past, one per day |
| `PUT /payment-plans/{id}` | Edit a draft or approved plan (approved goes back to draft) |
| `POST /payment-plans/{id}/approve` | Body `{"confirm": true}`. Owner approves proposing it |
| `POST /payment-plans/{id}/supplier-response` | Body `{"accepted": bool, "note": str?, "confirm": true}`. Needs approved. One accepted plan per bill |
| `POST /payment-plans/{id}/cancel` | Cancel a plan |
| `POST /payment-plans/installments/{id}/paid` | Body `{"confirm": true, "paid_date"?}`. Records a payment the owner made; updates the bill |
| `POST /negotiation-drafts` | `{"bill_id", "plan_id"?, "polish": true}` creates an editable draft |
| `GET/PUT/DELETE /negotiation-drafts[/{id}]` | List, edit, delete |
| `POST /negotiation-drafts/{id}/mark-sent` | Body `{"confirm": true}`. Records that the owner sent it |
| `GET /suppliers/{id}/terms` | Terms and the owner's payment record with that supplier |

Errors: 401 not logged in, 404 not found or not yours, 409 wrong state (for example approving a plan that is not a
draft), 422 invalid input (installments do not add up, past dates, missing `confirm`).

## Set up and run

```powershell
cd "E:\Project\China Hackathon\backend"
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m seed.seed          # rebuilds the demo database (applies all migrations)
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

```powershell
cd "E:\Project\China Hackathon\frontend"; npm run dev      # then open http://localhost:3000/payables
```

An existing database is upgraded automatically at startup. To apply by hand: `.\.venv\Scripts\alembic upgrade head`.
Demo login: `demo@example.com` / `Demo@12345`. Free AI keys (Groq, Gemini) are optional; without them messages come from templates.

## Sample data (from `seed/seed.py`)

Four suppliers with terms (for example Northwind Distributors: 30 days, 2% discount if paid within 10 days, 1.5% a month
late fee), unpaid bills with dates close to today, overdue and partly paid customer invoices, a new customer with no
record, and four **demo** financing offers (invoice advance, short-term loan, overdraft, quick trade loan).
The demo shows a predicted clash of about 73,000 around Nov 5.

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q          # 142 tests, all passing
```

`tests/test_payables.py` covers: balance reconciliation, confirmed versus estimated, no double counting (receivables,
accepted plans, partly paid bills), late and at-risk receipts, new customers, overdue bills, conflicts, plan scheduling
(totals, order, rounding, late fees), financing costs by hand-worked examples, the "repaid before the dip" rule,
loan sizing, honest reporting of an unfixable gap, message figures and the AI-rewrite guard, and the API's
approval flow, validation, isolation and "nothing is sent" behaviour.

## Not built, and needed for real use

- Real **financing partners**: licensed lenders or invoice-finance providers and their APIs. The offers here are demo data.
- Real **delivery** of messages (WhatsApp Business API, SMS or email). Today the owner copies a draft and sends it.
- **Payment execution** (bank or payment-provider APIs). The app only records payments the owner made.
- A way to import **supplier terms** automatically; they are entered by hand or seeded.
- Row-Level Security in PostgreSQL and a multi-worker rate limiter (the app enforces isolation in code).
