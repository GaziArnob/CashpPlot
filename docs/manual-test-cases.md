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
| A4 | Onboarding step 1: leave the business name empty, press Next | Cannot continue |
| A5 | Fill all 3 steps (name, currency, opening balance, safety level), skip records | Dashboard shows your balance |
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
| K1 | Add an invoice due in 2 days, a bill due tomorrow and a bill due 3 days ago, then open the Dashboard | The bell shows an unread count; Alerts lists them. The late bill is marked urgent |
| K2 | Click the bell | A dropdown with the latest alerts, "Mark all read" and "See all notifications" |
| K3 | Click an alert | You go to the page that fixes it (Ledger, Loan Center...) and the unread count drops by one |
| K4 | Reload the Dashboard several times | No duplicate alerts appear |
| K5 | Notifications page: Unread tab, Mark read, Mark all read, X to dismiss | Each does what it says |
| K6 | Settings → Notifications: untick "Invoices coming due", Save, add another invoice due soon, open the Dashboard | No new invoice alert |
| K7 | Settings → Notifications: "Also email me urgent alerts" | Greyed out with a note until Brevo is set up; once it is, tick it and an urgent alert is emailed once |
| K8 | Sign in as a staff member | No bell and no Notifications page |
