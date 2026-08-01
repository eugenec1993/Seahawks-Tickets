# Seahawks ticket deal alerts

This GitHub Actions project checks Seahawks tickets for Patriots, Chargers, 49ers, Chiefs, Bears, Cowboys, and Rams, then emails only when a source reaches a new low at or below your configured per-ticket, all-in limit.

It includes official API adapters for Ticketmaster and SeatGeek, plus unlimited structured event-page adapters. Add direct event URLs for TickPick, Gametime, StubHub, Vivid Seats, TicketCity, or any other marketplace whose event page publishes a JSON-LD offer price. This avoids bypassing logins, CAPTCHAs, or marketplace access controls.

## Your alert limits

The included `config.json` is already configured for two adjacent seats with these all-in, per-ticket maximums:

| Seat category | Maximum |
| --- | ---: |
| Charter / club | $300 |
| Sideline | $250 |
| Everything else | $150 |

The official Ticketmaster and SeatGeek API results are event-wide low prices, so they are checked as `everything_else`. For Charter/Club or sideline alerts, add a filtered, exact-game marketplace URL to `custom_event_pages` and set its `category` to `charter_club` or `sideline`. The URL must show only the desired seat category.

## One-time setup

1. In GitHub, open **Settings → Secrets and variables → Actions**, then add these repository secrets:

   | Secret | Value |
   | --- | --- |
   | `GMAIL_ADDRESS` | Gmail address that sends the alert |
   | `GMAIL_APP_PASSWORD` | A [Google App Password](https://myaccount.google.com/apppasswords), not your regular Gmail password |
   | `ALERT_TO` | Email address that receives alerts |
   | `TICKETMASTER_API_KEY` | Optional Ticketmaster Discovery API key |
   | `SEATGEEK_CLIENT_ID` | Optional SeatGeek Platform API client ID |

   `ALERT_MAX_PRICE` is no longer used; remove it or leave it blank so it does not override the category rules.

2. Edit `config.json` to add exact-game, category-filtered marketplace URLs. Use `config.example.json` as the schema reference.
3. Go to **Actions → Seahawks ticket alerts → Run workflow** to test it. Scheduled checks run every six hours; GitHub Actions may delay scheduled jobs during heavy platform load.

## Source coverage

| Source | Setup | Alert category |
| --- | --- | --- |
| Ticketmaster | `TICKETMASTER_API_KEY` | Everything else (event-wide listed minimum) |
| SeatGeek | `SEATGEEK_CLIENT_ID` | Everything else (event-wide lowest listing) |
| TickPick, Gametime, StubHub, Vivid Seats, TicketCity, etc. | Add an exact filtered event page under `custom_event_pages` | The `category` you assign to that URL |

Marketplace fees vary. Prefer pages that show all-in pricing. The state file is committed after each run, so the same category/listing price does not repeatedly email you; a newly lower price will.

## Local test

```sh
python -m unittest discover -s tests
python tracker.py --dry-run
```
