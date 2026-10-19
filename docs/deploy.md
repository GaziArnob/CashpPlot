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

### Demo account on the live site

Set `SEED_DEMO_ON_START=true` in Render (Environment), then Manual Deploy. At start-up the API creates
`demo@example.com` / `Demo@12345` (Evergreen Traders, one year of sample data) **only if it does not exist**. It never
wipes or edits other accounts. Set it back to `false` afterwards if you like; the data stays. To rebuild the demo from
scratch, delete that account in the app (Settings, Delete account) and deploy again with the flag on.

## 4. Turning on the optional services

Each one is off until its keys are set in Render, and none of them acts without the owner pressing a button.

| Service | Set these | What it enables |
| --- | --- | --- |
| Email reminders through Mailjet (HTTPS, free plan 200 a day), https://www.mailjet.com | `MAILJET_API_KEY`, `MAILJET_SECRET_KEY`, `MAILJET_SENDER_EMAIL` (an address you verified in Mailjet under Senders & Domains) | The Email channel delivers over HTTPS, so it works on Render's free plan |
| Email reminders by SMTP, free with any mailbox (e.g. Gmail). **Does not work on Render's free plan, which blocks SMTP ports 25, 465 and 587**; fine on your own computer or a paid plan | `SMTP_HOST`, `SMTP_PORT` (587, or 465 for SSL), `SMTP_USER`, `SMTP_PASSWORD`, optional `SMTP_FROM` | The reminder dialog's Email channel delivers the message. For Gmail: turn on 2-step verification, then Google Account → Security → App passwords, and use that 16-character password as `SMTP_PASSWORD` (host `smtp.gmail.com`). Gmail allows about 500 messages a day |
| Email reminders through Brevo instead, https://www.brevo.com (used first when set; it also has a free plan, check its pricing page) | `BREVO_API_KEY`, `BREVO_SENDER_EMAIL` (a sender verified in Brevo) | The reminder dialog's Email channel delivers the message |
| WhatsApp, https://developers.facebook.com/docs/whatsapp/cloud-api | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and for real customers `WHATSAPP_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANG` | WhatsApp channel. Without a template, free-form text only reaches people who messaged the business in the last 24 hours, plus test numbers. See "WhatsApp template" below |
| WhatsApp through Twilio (no Meta setup), https://www.twilio.com | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` (`whatsapp:+14155238886` for the sandbox) | WhatsApp channel. See "WhatsApp through Twilio" below |
| Pro payments, https://stripe.com | `BILLING_MODE=stripe`, `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET` | Settings → Upgrade to Pro opens Stripe Checkout |
| Bank import, https://plaid.com | `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV=sandbox` | Transactions → Connect a bank. Sandbox uses sample banks only |

### WhatsApp through Twilio (no Meta setup)

Set `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886` (Twilio's sandbox number; see Console → Messaging → Try it out → Send a
WhatsApp message, where the exact number and your join phrase are shown). With your `TWILIO_ACCOUNT_SID` and
`TWILIO_AUTH_TOKEN`, the WhatsApp channel works. Each recipient must first send the join phrase
(`join something-something`) from their WhatsApp to the sandbox number; after that, free text reaches them for 24 hours
from their last message. If the Meta variables are also set, Meta's WhatsApp is used instead, unless you set `WHATSAPP_PROVIDER=twilio` (or `meta`) to choose.

### Twilio trial notes

- A trial account has free credit (about 100 WhatsApp messages). Messages start with a "Sent from your Twilio trial account"
  style prefix. Upgrading removes the sandbox limits.
- Customer phone numbers must be in international format, e.g. `+8801XXXXXXXXX` or `+14155550123`.
- If Twilio refuses a message, the reminder dialog shows Twilio's own reason (for example "has not joined the sandbox").

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
