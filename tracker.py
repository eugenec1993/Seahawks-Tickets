#!/usr/bin/env python3
"""Find Seahawks ticket prices and email only newly-low deals.

Uses official partner APIs when their credentials are supplied, plus any number
of marketplace event pages you add to config.json.  Page adapters extract only
structured (JSON-LD) offer prices; they do not bypass logins or bot controls.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from html import unescape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
STATE_PATH = ROOT / "data" / "state.json"
USER_AGENT = "SeahawksTicketTracker/1.0 (+https://github.com/eugenec1993/Seahawks-Tickets)"


@dataclass(frozen=True)
class EventPrice:
    opponent: str
    source: str
    price: float
    url: str
    event_name: str = "Seattle Seahawks"
    observed_at: str = ""

    @property
    def key(self) -> str:
        return f"{self.opponent}|{self.source}"


def get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_json_ld_prices(html: str) -> list[float]:
    """Return structured offer lowPrice/price values embedded in an event page."""
    blocks = re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.I | re.S)
    prices: list[float] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("lowPrice", "price"):
                raw = value.get(key)
                if isinstance(raw, (int, float)) or (isinstance(raw, str) and re.fullmatch(r"\d+(?:\.\d+)?", raw.strip())):
                    prices.append(float(raw))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for block in blocks:
        try:
            visit(json.loads(unescape(block).strip()))
        except json.JSONDecodeError:
            continue
    return [price for price in prices if price > 0]


def ticketmaster_prices(opponent: str, api_key: str) -> list[EventPrice]:
    query = urllib.parse.urlencode({"apikey": api_key, "keyword": f"Seattle Seahawks {opponent}", "classificationName": "football", "size": 20})
    payload = get_json(f"https://app.ticketmaster.com/discovery/v2/events.json?{query}")
    result: list[EventPrice] = []
    for event in payload.get("_embedded", {}).get("events", []):
        ranges = event.get("priceRanges") or []
        if not ranges:
            continue
        low = min(float(item["min"]) for item in ranges if item.get("min") is not None)
        result.append(EventPrice(opponent, "Ticketmaster", low, event.get("url", "https://www.ticketmaster.com"), event.get("name", "Seattle Seahawks")))
    return result


def seatgeek_prices(opponent: str, client_id: str) -> list[EventPrice]:
    query = urllib.parse.urlencode({"client_id": client_id, "q": f"Seattle Seahawks {opponent}", "per_page": 20})
    payload = get_json(f"https://api.seatgeek.com/2/events?{query}")
    result: list[EventPrice] = []
    for event in payload.get("events", []):
        stats = event.get("stats") or {}
        if stats.get("lowest_price") is not None:
            result.append(EventPrice(opponent, "SeatGeek", float(stats["lowest_price"]), event.get("url", "https://seatgeek.com"), event.get("title", "Seattle Seahawks")))
    return result


def page_prices(opponent: str, source: str, url: str) -> list[EventPrice]:
    prices = extract_json_ld_prices(get_text(url))
    return [EventPrice(opponent, source, min(prices), url)] if prices else []


def load_state() -> dict[str, Any]:
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}


def alerts_to_send(prices: list[EventPrice], state: dict[str, Any], maximum: float) -> list[EventPrice]:
    alerts = []
    for price in prices:
        last = state.get(price.key, {}).get("last_alerted_price")
        if price.price <= maximum and (last is None or price.price < float(last)):
            alerts.append(price)
    return alerts


def save_state(state: dict[str, Any], prices: list[EventPrice], alerted: list[EventPrice]) -> None:
    alerted_keys = {item.key for item in alerted}
    timestamp = datetime.now(timezone.utc).isoformat()
    for item in prices:
        record = state.setdefault(item.key, {})
        record.update({"last_seen_price": item.price, "last_seen_at": timestamp, "url": item.url})
        if item.key in alerted_keys:
            record["last_alerted_price"] = item.price
            record["last_alerted_at"] = timestamp
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def send_email(alerts: list[EventPrice], maximum: float) -> None:
    host, user, password, recipient = (os.getenv(key) for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_TO"))
    if not all((host, user, password, recipient)):
        raise RuntimeError("Deals found but Gmail secrets are incomplete: SMTP_HOST, SMTP_USER, SMTP_PASSWORD, ALERT_TO")
    lines = [f"{item.opponent}: ${item.price:.2f}/ticket at {item.source} — {item.url}" for item in alerts]
    message = EmailMessage()
    message["Subject"] = f"Seahawks ticket deal: {len(alerts)} price(s) at or below ${maximum:.2f}"
    message["From"] = user
    message["To"] = recipient
    message.set_content("New Seahawks ticket deals:\n\n" + "\n".join(lines))
    with smtplib.SMTP_SSL(host, 465, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--max-price", type=float, default=os.getenv("ALERT_MAX_PRICE"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    maximum = args.max_price if args.max_price is not None else config.get("max_price_per_ticket")
    if maximum is None:
        raise ValueError("Set max_price_per_ticket in config.json or ALERT_MAX_PRICE in GitHub Secrets.")
    prices: list[EventPrice] = []
    for opponent in config["opponents"]:
        if os.getenv("TICKETMASTER_API_KEY"):
            prices.extend(ticketmaster_prices(opponent, os.environ["TICKETMASTER_API_KEY"]))
        if os.getenv("SEATGEEK_CLIENT_ID"):
            prices.extend(seatgeek_prices(opponent, os.environ["SEATGEEK_CLIENT_ID"]))
        for page in config.get("custom_event_pages", {}).get(opponent, []):
            prices.extend(page_prices(opponent, page["source"], page["url"]))
    timestamp = datetime.now(timezone.utc).isoformat()
    prices = [EventPrice(**{**asdict(item), "observed_at": timestamp}) for item in prices]
    state = load_state()
    alerts = alerts_to_send(prices, state, float(maximum))
    if alerts and not args.dry_run:
        send_email(alerts, float(maximum))
    save_state(state, prices, alerts)
    print(json.dumps({"checked": len(prices), "alerts": [asdict(item) for item in alerts]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"tracker error: {error}", file=sys.stderr)
        raise SystemExit(1)
