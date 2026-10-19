# CashPilot: manual test cases

Run these on the live site (https://chinese-hackathon.vercel.app) or locally (http://localhost:3000, demo login
`demo@example.com` / `Demo@12345`).

- A **new account on the live site is empty**, so charts and the forecast stay thin. Import the sample CSV in section B first.
- The first request after a pause on the live site can take about 50 seconds (free hosting sleeps). That is not a bug.
- Mark each row Pass or Fail. For a Fail, note the page, what you did and the exact message shown.

## Sample CSV (save as `sample.csv`)

```
date,amount,type,category,description
2026-08-03,1800,income,Sales,Weekly sales
2026-08-10,2100,income,Sales,Weekly sales
2026-08-17,1950,income,Sales,Weekly sales
2026-08-24,2300,income,Sales,Weekly sales
2026-08-31,2000,income,Sales,Weekly sales
2026-09-07,2200,income,Sales,Weekly sales
2026-09-14,2400,income,Sales,Weekly sales
2026-09-21,2100,income,Sales,Weekly sales
2026-09-28,2500,income,Sales,Weekly sales
2026-10-05,2300,income,Sales,Weekly sales
2026-08-05,900,expense,Supplies,Beans
2026-09-05,950,expense,Supplies,Beans
2026-10-05,1000,expense,Supplies,Beans
2026-08-01,1200,expense,Rent,Shop rent
2026-09-01,1200,expense,Rent,Shop rent
2026-10-01,1200,expense,Rent,Shop rent
```

## A. Account

| # | Do this | Expect |
|---|---|---|
| A1 | Open `/signup`, enter a name, new email, password under 8 characters | "Use at least 8 characters" and nothing is created |
| A2 | Same, but the two passwords differ | "The two passwords don't match" |
| A3 | Valid details | Lands on the 3-step onboarding |
| A4 | Onboarding step 1: leave the business name empty | Next is disabled |
| A5 | Step 1: name, pick a business type card, currency chip and how long it has run. Step 2: cash today and a safety level (try the preset chips). Step 3: skip, or drop a CSV on the box | Dashboard shows your balance; the progress bar fills as you go |
| A6 | Sign out, sign in with a wrong password | "Wrong email or password", no raw JSON |
| A7 | Sign in correctly | Dashboard |
| A8 | Reload any page while signed in | Stays signed in |
| A9 | Open `/dashboard` in a private window | Sent to the sign-in page |

## B. Transactions

| # | Do this | Expect |
|---|---|---|
| B1 | Transactions → Add: income 500, category Sales | Appears at the top of the list, balance rises |
| B2 | Add an expense of 200 | Balance falls by 200 |
| B3 | Add with an empty amount or a negative amount | Refused with a clear message |
| B4 | Import CSV: upload `sample.csv` | "Imported 16", rows appear |
| B5 | Import the same file again | Rows are added again (CSV has no duplicate check); delete extras if you want a clean list |
| B6 | Import a text file renamed to `.csv` with no date/amount columns | "CSV needs 'date' and 'amount' columns" |
| B7 | Filter by Money in / Money out, by category, by date range, and search "Beans" | List narrows each time |
| B8 | Delete a transaction | Asks to confirm, then disappears |
| B9 | Scan receipt: upload a clear photo of a receipt with a total | A pre-filled form opens; nothing is saved until you press Save |
| B10 | Scan receipt: upload a non-image file | "Upload a JPEG, PNG or WebP image" |

## C. Customers and payments owed

| # | Do this | Expect |
|---|---|---|
| C1 | Customers → add a customer with name, email, phone `+14155550123` | Saved |
| C2 | Ledger → add an invoice for that customer, due 10 days ago | Shows overdue |
| C3 | Ledger or Cash Flow → recovery list | The customer ranks with the amount overdue |
| C4 | Draft a reminder | A message with the customer's name, amount and tone appears; it is a draft |
| C5 | Edit the text, choose Email, press Send | Says **"Recorded as sent. CashPilot did not deliver it"** and offers Copy (email is not connected). After you add Brevo keys it says "Reminder sent by EMAIL" |
| C6 | Mark the invoice paid | Leaves the overdue list |
| C7 | Customers → pencil icon on a row (or open a customer → Edit details), change the phone to `+8801XXXXXXXXX` and the email, Save | The change shows when you reopen the customer; sending a WhatsApp or email reminder now uses it |
| C8 | Edit a customer and empty the phone, Save | The phone is cleared; the name cannot be left empty |

## D. Forecast and advisor

| # | Do this | Expect |
|---|---|---|
| D1 | Dashboard | Balance, this month's in/out, overdue, credit score, 14-day chart, a summary sentence |
| D2 | Cash Flow: switch to 30 days | Chart and a shortage date, or "no shortage expected" |
| D3 | Add a large bill (Ledger → bills) due next week, larger than your balance | A shortage appears with a date and a gap amount |
| D4 | Cash Advisor | Steps to close the gap, each showing the cash it brings and when |
| D5 | Approve a step | It moves to approved; nothing is sent or paid |

## E. Suppliers

| # | Do this | Expect |
|---|---|---|
| E1 | Supplier Plans → pick the large bill → create a plan (instalments) | A schedule appears as a draft |
| E2 | Create a draft message to the supplier | Editable text; the supplier's real name appears only in your view, never as a code |
| E3 | Approve the plan, then accept | Status changes; no message is sent automatically |
| E4 | Financing comparison | Offers listed, labelled as demo data |

## F. Credit and loans

| # | Do this | Expect |
|---|---|---|
| F1 | Credit Score | A 300–900 score with reasons that add up |
| F2 | Loan Center | Readiness, safe monthly installment, matching offers |
| F3 | What-if simulator: change sales and run | The chart shows base vs scenario |
| F4 | Request intro on an offer, leave consent unticked | Save is disabled |
| F5 | Tick consent, Save | "Your introduction requests" lists it as `submitted`; nothing was sent to a lender |
| F6 | Request the same offer again | Refused: an open request already exists |
| F7 | Mark it "Lender contacted me", then "Funded" | Status follows; you cannot go backwards |

## G. Reports and AI agent

| # | Do this | Expect |
|---|---|---|
| G1 | Reports: pick a month | Profit and loss, a note on insights |
| G2 | Download the PDF | A PDF opens with the same figures |
| G3 | AI Agent: "Will I run short on cash next week?" | An answer that uses your own numbers |
| G4 | Ask something outside finance | A polite refusal or a short answer, no invented figures |

## H. Settings

| # | Do this | Expect |
|---|---|---|
| H1 | Change the business name, currency to EUR, save | Amounts show € everywhere |
| H2 | AI privacy: choose Off, then ask the agent a question | Template-style answer, no AI wording |
| H3 | Plan: choose Free | Pro pages (Advisor, Credit Score, Loans, Reports, Agent) show "Upgrade to Pro" |
| H4 | Plan: choose Pro again | Pages work again |
| H5 | Team: add a staff member (name, email, 8+ character password) | Appears in the list |
| H6 | Sign in as the staff member (private window) | Only Transactions, Ledger, Customers are shown |
| H7 | As staff, type `/credit-score` in the address bar | Sent back to Transactions |
| H8 | As the owner, remove the staff member | The staff login stops working at once |
| H9 | Lender access: add a lender, tick items, consent, Grant | A token is shown **once** |
| H10 | Open `/lender`, paste the token | Shows only the items you ticked |
| H11 | Revoke the access, reload `/lender` | "Access token invalid, expired or revoked" |
| H12 | Two-factor: Set up, enter the key in an authenticator app, enter the code | Turns on |
| H13 | Sign out and in | Asks for a 6-digit code; a wrong code is refused |
| H14 | Download my data | A JSON file with your records |
| H15 | Delete account (type DELETE) | Signs you out; signing in again fails |

## I. Safety and edge cases

| # | Do this | Expect |
|---|---|---|
| I1 | Sign in as two different accounts in two browsers | Neither sees the other's customers or transactions |
| I2 | Try 11 wrong sign-ins in a minute | "Too many auth requests, slow down" |
| I3 | Stop the backend (local) and reload | A clear "Can't reach the backend" message |
| I4 | Very long business name (300 characters) | Refused or trimmed, no crash |
| I5 | Mobile width (browser devtools, 375 px) | Navigation scrolls horizontally; no cut-off buttons |

## J. Optional services (only after their keys are set)

| # | Service | Do this | Expect |
|---|---|---|---|
| J1 | Brevo | C5 with Email, customer email set | The email arrives in the customer's inbox; a bad key gives "Nothing was sent" and the reminder stays a draft |
| J2 | Stripe test | Settings → Upgrade to Pro, card `4242 4242 4242 4242`, any future date and CVC | Returns to Settings, plan shows Pro; the webhook (not the browser) changed it |
| J3 | Stripe test | Card `4000 0000 0000 0002` | Declined, plan stays Free |
| J4 | Stripe | Manage billing → cancel | Plan returns to Free |
| J5 | Plaid sandbox | Transactions → Connect a bank, login `user_good` / `pass_good` | Connected; Sync imports sample transactions once; Sync again adds none |
| J6 | Plaid | Disconnect | Connection removed; imported transactions stay |

## K. Notifications

| # | Do this | Expect |
|---|---|---|
| K1 | Add an invoice due in 2 days, a bill due tomorrow and a bill due 3 days ago, then open the Dashboard | A red unread count appears beside Notifications in the left menu; the Dashboard's Alerts card lists them. The late bill is marked urgent |
| K2 | Open Notifications in the left menu | The full list, with Unread / All tabs, Mark all read and an X on each row |
| K3 | Click Open on an alert | You go to the page that fixes it (Ledger, Loan Center...) and the unread count drops by one |
| K4 | Reload the Dashboard several times | No duplicate alerts appear |
| K5 | Notifications page: Unread tab, Mark read, Mark all read, X to dismiss | Each does what it says |
| K6 | Settings → Notifications: untick "Invoices coming due", Save, add another invoice due soon, open the Dashboard | No new invoice alert |
| K7 | Settings → Notifications: "Also email me urgent alerts" | Greyed out with a note until Brevo is set up; once it is, tick it and an urgent alert is emailed once |
| K8 | Sign in as a staff member | No bell and no Notifications page |
| K9 | Look at the top right of any page | No bell: notifications live in the left menu, with the unread count beside the link |
| K10 | Create a product with 100 in stock and record two sales of 45 in the last 3 weeks | A "will run out in about N days" alert (Products running low) |
| K11 | Add an invoice due 10 days ago | "Invoice #N from X is 10 days late" (separate from the 30+ day customer alert) |
| K12 | Add a bill due 3 days ago | An urgent "was due" alert |
| K13 | Add a loan with the first installment due in 2 days (Loan Center → Add a loan) | "Loan installment ... is due" |
| K14 | Set a goal (Reports) due within 14 days and not yet reached | A goal-deadline alert |
| K15 | Turn off one type in Settings → Notifications | That type is never created again |

## L. Credit score with little data

| # | Do this | Expect |
|---|---|---|
| L1 | Open Credit Score on a brand-new account | A yellow box: "only a starting point", listing exactly what to add (income, 3 months of records, loans/bills). The score is low (about 377) and says nothing is recorded, not that you did something wrong |
| L2 | Import `sample.csv` (see the top of this file) and reload | The box becomes blue or disappears as records grow; the score rises; "Average monthly income" shows points near zero or positive, not a large minus |
| L3 | Add a loan with its installments marked paid (Loan Center → Add a loan) and a bill, mark the bill paid on time | The "On-time repayment rate" factor improves and the "no repayment history" note goes away |
| L4 | Score history card | Shows "No history yet" on day one, then a line as days pass (never an endless loading spinner) |

## M. How to raise your score

| # | Do this | Expect |
|---|---|---|
| M1 | Import `sample.csv`, add an invoice due 20 days ago for 4,000, open Credit Score | A card "How to raise your score": points to the next band, points to the next loan type, and steps such as "Collect the overdue invoices from X: +N points" |
| M2 | Mark that invoice paid in the Ledger and reload the Credit Score page | The score rose by about the N the card promised, and that step is gone |
| M3 | Add a loan or bill and pay it on time | The "Pay your next 3 bills on time" step shrinks or goes away as your repayment record builds |
| M4 | A business already in the Excellent band | "You are in the top band" and no next band |
| M5 | A brand-new account | The card lists what data to add; no invented gains |
