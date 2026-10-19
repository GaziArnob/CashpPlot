# Deploying CashPilot (free tiers)

Website on Vercel, API on Render, database on Neon. None of this has been deployed from this repository yet; the steps
below are what the files in it are set up for. Free-tier limits change, so check each pricing page first.

## 1. Database (Neon)

1. Create a project at https://neon.com and note the connection string.
2. Row-level security is skipped by superusers and by roles with `BYPASSRLS`. Neon's default owner role may be one of
   them. In Neon's SQL editor create a plain role and give it the database:

   ```sql
   CREATE ROLE cashpilot LOGIN PASSWORD 'choose-a-long-password';
   GRANT ALL ON DATABASE <your database> TO cashpilot;
   GRANT ALL ON SCHEMA public TO cashpilot;
   SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'cashpilot';   -- both must be false
   ```

3. `DATABASE_URL` = `postgresql+psycopg://cashpilot:PASSWORD@HOST/DBNAME?sslmode=require`
4. The API logs a warning at start-up if its role would skip row-level security.

## 2. API (Render)

1. https://render.com → New → Blueprint → pick this repository (it reads `render.yaml`).
2. Fill in the secrets Render asks for: `DATABASE_URL`, `FIELD_ENCRYPTION_KEY`, `CORS_ORIGINS`, `APP_URL`, and the AI keys.
   Generate the encryption key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   and keep a copy: without it, stored contact details cannot be read.
3. The free service sleeps when idle, so the first request after a pause is slow.
4. The tables are created by the migrations when the API starts.

## 3. Website (Vercel)

1. https://vercel.com → Add New Project → this repository, **Root Directory: `frontend`**.
2. Environment variable `NEXT_PUBLIC_API_URL` = the Render address (e.g. `https://cashpilot-api.onrender.com`).
3. Put the Vercel address into Render's `CORS_ORIGINS` and `APP_URL`.
4. The Vercel Hobby plan is for personal, non-commercial use.

## 4. Turning on the optional services

Each one is off until its keys are set in Render, and none of them acts without the owner pressing a button.

| Service | Set these | What it enables |
| --- | --- | --- |
| Email reminders, https://www.brevo.com | `BREVO_API_KEY`, `BREVO_SENDER_EMAIL` (a sender verified in Brevo) | The reminder dialog's Email channel delivers the message |
| WhatsApp, https://developers.facebook.com/docs/whatsapp/cloud-api | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and for real customers `WHATSAPP_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANG` | WhatsApp channel. Without a template, free-form text only reaches people who messaged the business in the last 24 hours, plus test numbers. See "WhatsApp template" below |
| SMS, https://www.twilio.com | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` | SMS channel. Customer phone numbers must be in international format, e.g. `+14155550123` |
| Pro payments, https://stripe.com | `BILLING_MODE=stripe`, `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET` | Settings → Upgrade to Pro opens Stripe Checkout |
| Bank import, https://plaid.com | `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV=sandbox` | Transactions → Connect a bank. Sandbox uses sample banks only |

### WhatsApp template

To reach a customer who has not messaged you, WhatsApp requires an approved template. In Meta's WhatsApp Manager create
a **Utility** template (for example named `payment_reminder`, language English) with exactly four variables:

> Hi {{1}}, a reminder from {{2}}: {{3}} was due on {{4}}. Please pay when you can, and reply here if you have a question.

Once Meta approves it, set `WHATSAPP_TEMPLATE_NAME=payment_reminder` and `WHATSAPP_TEMPLATE_LANG=en` (match the
language you chose, e.g. `en_US`). CashPilot then fills {{1}} customer name, {{2}} your business, {{3}} the amount
and {{4}} the due date. The wording sent is the template's: an edit you make in the reminder box is not used for
WhatsApp. Meta charges per conversation outside its free allowance, so check its pricing page.

### Stripe

1. Use **test mode** keys (`sk_test_...`) until Stripe has verified the business.
2. Create a product "CashPilot Pro" with a recurring price and copy its price id (`price_...`) into `STRIPE_PRICE_ID`.
3. Add a webhook endpoint `https://<your API>/billing/webhook` for the events `checkout.session.completed`,
   `customer.subscription.updated` and `customer.subscription.deleted`, and copy its signing secret into
   `STRIPE_WEBHOOK_SECRET`.
4. A plan only changes when Stripe's signed webhook says the payment happened, never from the browser. Test card:
   `4242 4242 4242 4242`, any future date and any CVC.
5. Deleting an account cancels its subscription first; if Stripe cannot be reached the account is kept.

### Plaid

1. Create a Plaid account, copy the sandbox `client_id` and `secret`.
2. In the sandbox the sample login is `user_good` / `pass_good`. Production needs Plaid's approval and is currently
   limited to US-style banks in this code (`country_codes` is `["US"]` in `app/banking.py`).
3. The bank's access token is stored encrypted and never sent to the browser. Pending transactions and transactions in
   another currency than the business's are skipped.

## Not included

Lemon Squeezy (https://www.lemonsqueezy.com) is an alternative to Stripe for selling the Pro plan; it is not wired up.
