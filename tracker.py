#!/usr/bin/env python3
"""Monitor Seahawks ticket prices using official APIs and public structured event pages.

Only public pages that expose JSON-LD are read; this project never bypasses a
login, CAPTCHA, paywall, rate limit, or marketplace access control.
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
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import unescape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
STATE_PATH = ROOT / "data" / "state.json"
USER_AGENT = "SeahawksTicketTracker/2.0 (+https://github.com/eugenec1993/Seahawks-Tickets)"
CATEGORIES = ("charter_club", "sideline", "everything_else")
HISTORY_DAYS = 14


@dataclass(frozen=True)
class EventPrice:
    opponent: str
    source: str
    price: float
    url: str
    category: str = "everything_else"
    event_name: str = "Seattle Seahawks"
    observed_at: str = ""

    @property
    def key(self) -> str:
        return f"{self.opponent}|{self.category}|{self.source}"


def get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_json_ld_prices(html: str) -> list[float]:
    """Return public JSON-LD offer prices. Pages without valid structured offers are skipped."""
    blocks = re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.I | re.S)
    prices: list[float] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            # Prefer offer values; a page may contain both a lowPrice and an individual price.
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


def event_matches(event_name: str, opponent: str) -> bool:
    normalized = event_name.casefold()
    return "seattle seahawks" in normalized and opponent.casefold() in normalized


def ticketmaster_prices(opponent: str, api_key: str) -> list[EventPrice]:
    query = urllib.parse.urlencode({"apikey": api_key, "keyword": f"Seattle Seahawks {opponent}", "classificationName": "football", "size": 20})
    payload = get_json(f"https://app.ticketmaster.com/discovery/v2/events.json?{query}")
    result: list[EventPrice] = []
    for event in payload.get("_embedded", {}).get("events", []):
        name = event.get("name", "")
        ranges = event.get("priceRanges") or []
        if not event_matches(name, opponent) or not ranges:
            continue
        lows = [float(item["min"]) for item in ranges if item.get("min") is not None]
        if lows:
            result.append(EventPrice(opponent, "Ticketmaster", min(lows), event.get("url", "https://www.ticketmaster.com"), event_name=name))
    return result


def seatgeek_prices(opponent: str, client_id: str) -> list[EventPrice]:
    query = urllib.parse.urlencode({"client_id": client_id, "q": f"Seattle Seahawks {opponent}", "per_page": 20})
    payload = get_json(f"https://api.seatgeek.com/2/events?{query}")
    result: list[EventPrice] = []
    for event in payload.get("events", []):
        name, stats = event.get("title", ""), event.get("stats") or {}
        if event_matches(name, opponent) and stats.get("lowest_price") is not None:
            result.append(EventPrice(opponent, "SeatGeek", float(stats["lowest_price"]), event.get("url", "https://seatgeek.com"), event_name=name))
    return result


def page_prices(opponent: str, page: dict[str, Any]) -> list[EventPrice]:
    category = page.get("category", "everything_else")
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category {category!r}; use one of: {', '.join(CATEGORIES)}")
    prices = extract_json_ld_prices(get_text(page["url"]))
    return [EventPrice(opponent, page["source"], min(prices), page["url"], category=category)] if prices else []


def rules_for(config: dict[str, Any], category: str) -> dict[str, float]:
    # Backward compatible with the original price_limits config.
    raw = (config.get("alert_rules") or {}).get(category)
    if raw is None:
        limit = (config.get("price_limits") or config.get("max_price_per_ticket") or {}).get(category)
        if limit is None:
            raise ValueError(f"Missing alert rule for category {category!r}")
        raw = {"max_price": limit}
    if isinstance(raw, (int, float)):
        raw = {"max_price": raw}
    return {
        "max_price": float(raw["max_price"]),
        "drop_percent": float(raw.get("drop_percent", 0)),
        "repeat_drop_percent": float(raw.get("repeat_drop_percent", 5)),
        "cooldown_hours": float(raw.get("cooldown_hours", 6)),
    }


def history_baseline(record: dict[str, Any]) -> float | None:
    values = [float(item["price"]) for item in record.get("history", []) if item.get("price") is not None]
    return max(values) if values else None


def alert_reason(price: EventPrice, record: dict[str, Any], config: dict[str, Any], now: datetime) -> str | None:
    rule = rules_for(config, price.category)
    if price.price > rule["max_price"]:
        return None
    baseline = history_baseline(record)
    if baseline is None:
        return "first price under cap" if config.get("alert_on_first_match", True) else None
    drop = (baseline - price.price) / baseline * 100
    if drop < rule["drop_percent"]:
        return None
    previous = record.get("last_alerted_price")
    if previous is not None and price.price >= float(previous) * (1 - rule["repeat_drop_percent"] / 100):
        return None
    last_at = record.get("last_alerted_at")
    if last_at:
        elapsed = now - datetime.fromisoformat(last_at)
        if elapsed < timedelta(hours=rule["cooldown_hours"]):
            return None
    return f"{drop:.1f}% below the {HISTORY_DAYS}-day high (${baseline:.2f})"


def alerts_to_send(prices: list[EventPrice], state: dict[str, Any], config: dict[str, Any], now: datetime | None = None) -> list[tuple[EventPrice, str]]:
    now = now or datetime.now(timezone.utc)
    return [(price, reason) for price in prices if (reason := alert_reason(price, state.get(price.key, {}), config, now))]


def save_state(state: dict[str, Any], prices: list[EventPrice], alerted: list[tuple[EventPrice, str]], now: datetime) -> None:
    alerted_by_key = {item.key: reason for item, reason in alerted}
    cutoff = now - timedelta(days=HISTORY_DAYS)
    timestamp = now.isoformat()
    for item in prices:
        record = state.setdefault(item.key, {})
        history = [entry for entry in record.get("history", []) if datetime.fromisoformat(entry["observed_at"]) >= cutoff]
        history.append({"price": item.price, "observed_at": timestamp})
        record.update({"last_seen_price": item.price, "last_seen_at": timestamp, "url": item.url, "category": item.category, "history": history})
        if item.key in alerted_by_key:
            record.update({"last_alerted_price": item.price, "last_alerted_at": timestamp, "last_alert_reason": alerted_by_key[item.key]})
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def game_within_week(config: dict[str, Any], now: datetime) -> bool:
    for game in config.get("games", []):
        try:
            kickoff = datetime.fromisoformat(game["kickoff"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if now <= kickoff <= now + timedelta(days=7):
            return True
    return False


def should_check_now(config: dict[str, Any], now: datetime) -> bool:
    return game_within_week(config, now) or now.minute == 0


def send_email(alerts: list[tuple[EventPrice, str]], config: dict[str, Any]) -> None:
    host, user, password, recipient = (os.getenv(key) for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_TO"))
    if not all((host, user, password, recipient)):
        raise RuntimeError("Deals found but Gmail secrets are incomplete: SMTP_HOST, SMTP_USER, SMTP_PASSWORD, ALERT_TO")
    lines = []
    for item, reason in alerts:
        rule = rules_for(config, item.category)
        lines.append(f"{item.opponent} — {item.category.replace('_', '/')} — ${item.price:.2f}/ticket (cap ${rule['max_price']:.2f}; {reason}) at {item.source}: {item.url}")
    message = EmailMessage()
    message["Subject"] = f"Seahawks ticket drop: {len(alerts)} matching listing(s)"
    message["From"], message["To"] = user, recipient
    message.set_content("New Seahawks ticket price drops:\n\n" + "\n".join(lines))
    with smtplib.SMTP_SSL(host, 465, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scheduled", action="store_true", help="Skip off-hour runs unless a game is within seven days.")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    now = datetime.now(timezone.utc)
    if args.scheduled and not should_check_now(config, now):
        print(json.dumps({"checked": 0, "skipped": "next game is more than seven days away"}))
        return 0
    prices: list[EventPrice] = []
    for opponent in config["opponents"]:
        if os.getenv("TICKETMASTER_API_KEY"):
            prices.extend(ticketmaster_prices(opponent, os.environ["TICKETMASTER_API_KEY"]))
        if os.getenv("SEATGEEK_CLIENT_ID"):
            prices.extend(seatgeek_prices(opponent, os.environ["SEATGEEK_CLIENT_ID"]))
        for page in config.get("custom_event_pages", {}).get(opponent, []):
            prices.extend(page_prices(opponent, page))
    prices = [EventPrice(**{**asdict(item), "observed_at": now.isoformat()}) for item in prices]
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    alerts = alerts_to_send(prices, state, config, now)
    if alerts and not args.dry_run:
        send_email(alerts, config)
    save_state(state, prices, alerts, now)
    print(json.dumps({"checked": len(prices), "alerts": [{**asdict(item), "reason": reason} for item, reason in alerts]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"tracker error: {error}", file=sys.stderr)
        raise SystemExit(1)
