# Seahawks ticket deal alerts

This GitHub Actions project checks Seahawks tickets for Patriots, Chargers, 49ers, Chiefs, Bears, Cowboys, and Rams, then emails only when a source reaches a new low at or below your target price.

It includes official API adapters for Ticketmaster and SeatGeek, plus unlimited structured event-page adapters. Add direct event URLs for TickPick, Gametime, StubHub, Vivid Seats, TicketCity, or any other marketplace whose event page publishes a JSON-LD offer price. This avoids bypassing logins, CAPTCHAs, or marketplace access controls.

## One-time setup

1. In GitHub, open **Settings → Secrets and variables → Actions**, then add these repository secrets:

   | Secret | Value |
   | --- | --- |
   | `ALERT_MAX_PRICE` | Maximum **per-ticket, all-in** price, for example `180` |
   | `GMAIL_ADDRESS` | Gmail address that sends the alert |
   | `GMAIL_APP_PASSWORD` | A [Google App Password](https://myaccount.google.com/apppasswords), not your regular Gmail password |
   | `ALERT_TO` | Email address that receives alerts |
   | `TICKETMASTER_API_KEY` | Optional Ticketmaster Discovery API key |
   | `SEATGEEK_CLIENT_ID` | Optional SeatGeek Platform API client ID |

2. Edit the included `config.json` (or use `config.example.json` as a reference) to set a target price if you prefer it stored in the file, and add a direct URL for each marketplace/game you want to watch. Commit the result. Keep only URLs that clearly show the desired game's tickets.
3. Go to **Actions → Seahawks ticket alerts → Run workflow** to test it. Scheduled checks run every six hours; GitHub Actions may delay scheduled jobs during heavy platform load.

## Source coverage

| Source | Setup | Price type |
| --- | --- | --- |
| Ticketmaster | `TICKETMASTER_API_KEY` | Primary-market listed minimum |
| SeatGeek | `SEATGEEK_CLIENT_ID` | Marketplace lowest listed price |
| TickPick, Gametime, StubHub, Vivid Seats, TicketCity, etc. | Add direct event page under `custom_event_pages` | Structured page offer price, if exposed |

Marketplace fees vary. Set your limit with fees in mind and prefer pages that show all-in pricing. The state file is committed after each run, so the same price will not repeatedly email you; a newly lower price will.

## Local test

```sh
python -m unittest discover -s tests
ALERT_MAX_PRICE=180 python tracker.py --dry-run
```
