# Seahawks ticket price-drop alerts

The tracker checks the official Ticketmaster and SeatGeek APIs, plus any number
of public marketplace event pages that expose JSON-LD offer prices. It emails a
deal only after it is below its category cap and has fallen by the configured
percentage from the prior 14-day high.

## Supported sources

Official adapters: Ticketmaster and SeatGeek.

Public structured-page adapters: StubHub, Vivid Seats, TickPick, Gametime,
TicketCity, TicketNetwork, TicketSmarter, SeatPick, AXS, Viagogo, and any other
marketplace event page that actually returns JSON-LD prices without a login.
Add its exact Seahawks game URL under `custom_event_pages`. Use a page filtered
for the required two adjacent seats and seating category. The tracker does not
bypass logins, CAPTCHAs, anti-bot controls, or marketplace terms.

## Rules and frequency

Configure `alert_rules` with a price cap and `drop_percent` per category.
`repeat_drop_percent` prevents repeat emails until a newly lower price is seen,
and `cooldown_hours` is an additional guard.

Add each kickoff (UTC) under `games`. The GitHub Action wakes every 15 minutes,
but the tracker only makes source requests at the top of each hour until a
configured kickoff is seven days away. It then requests prices every 15 minutes.

## Setup

1. Copy `config.example.json` to `config.json`, replace the example URLs, and
   add all Seahawks kickoff times.
2. Add `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `ALERT_TO`,
   `TICKETMASTER_API_KEY`, and `SEATGEEK_CLIENT_ID` in GitHub Actions secrets.
3. Run `python -m unittest discover -s tests`, then trigger the workflow
   manually once to validate source access and email delivery.
