# Pitch deck: corrections (global, English)

Apply these to the current deck. Wording below states only what the product does today.

## Remove or fix
- **"Enterprise-grade security implemented"** — replace with the list in "Security (built)" below. Do not claim certifications, penetration tests or PostgreSQL row-level security (not set up yet).
- **Blank slide 4** — fill with "How it works" (below) or delete.
- **Placeholders** (team, traction, margin) — fill only with real numbers, or delete the slide. Nothing here is invented for you.
- **Any country-specific wording, currency symbol or local payment brand** — the product is English-only and works in any currency.

## Add slides
1. **Problem** — small businesses are over 90% of firms and about 70% of employment, yet 40% of formal MSMEs in emerging economies are credit-constrained, a $5.7 trillion gap (IFC / World Bank, March 2025; see `project-need-chart.png` and `project-need-sources.md`).
2. **Cash Advisor** — dated forecast split into confirmed and estimated cash; finds the shortage day and recommends actions (chase invoices, move a bill, split a payment) with the simulated effect of each.
3. **Supplier payment plans** — proposes instalments or a financing comparison, drafts a message to the supplier (names masked before any AI sees them). Nothing is sent or paid without the owner's approval. Financing offers are demo data.
4. **Products** — margin and sales trend per product (a quadrant view).
5. **Explainable credit score and loan readiness** — every point traced to a factor; consent-based lender sharing and introduction requests.
6. **Teams and plans** — staff logins with limited access; Free and Pro tiers (demo billing, no payments yet).

## Security (built)
Password hashing (bcrypt), short-lived access tokens with rotating refresh cookies, optional authenticator-app two-factor sign-in, encrypted contact fields, per-business data isolation checked on every query, audit log, rate limits, expiring revocable lender access, data export and full account deletion.

## AI (built)
Numbers always come from deterministic engines; the language model only explains them, and any figure it adds that the engines did not produce is rejected. Customer and supplier names are replaced by codes before reaching a hosted model. Owners can choose cloud, local-only or no AI. Free-tier providers only.

## Roadmap (not built — label as such)
Bank and payment-wallet connections, real lender integrations, real WhatsApp sending, live payments for the Pro plan, PostgreSQL row-level security, hosted deployment, on-device receipt OCR install.

## Still needed from you
Team details, real traction (users, pilots), and the pricing/margin basis. These cannot be filled in by the tool.
