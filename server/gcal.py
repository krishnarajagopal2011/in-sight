"""Google Calendar adapter — pulls today's appointments from one or more accounts.

Read-only. Uses a stored OAuth refresh token per account (minted once by
scripts/gcal_auth.py) to get a fresh access token, then calls the Calendar REST
API directly with `requests` — no Google client libraries needed.

Config (config.yaml):
  google_calendar:
    enabled: true
    client_id: "...apps.googleusercontent.com"
    client_secret: "..."
    accounts:
      - {label: "Personal", color: "#6bd0a0"}
      - {label: "Work",     color: "#6aa6ff"}

Tokens live in config/google_tokens.json (gitignored), written by the auth script:
  { "Personal": {"refresh_token": "...", "email": "..."}, "Work": {...} }

Offline-first: if a fetch fails, callers keep the last good calendar (the kiosk
never blanks). Returns [] when the feature is simply disabled / unconfigured.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Optional

import requests

from .config import CONFIG_DIR

TOKENS_PATH = CONFIG_DIR / "google_tokens.json"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/userinfo.email"
TIMEOUT = 20


class GCalError(RuntimeError):
    pass


def load_tokens() -> dict[str, Any]:
    if not TOKENS_PATH.exists():
        return {}
    with open(TOKENS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh) or {}


def _access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    r = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise GCalError(f"token refresh failed (HTTP {r.status_code}): {r.text[:200]}")
    tok = r.json().get("access_token")
    if not tok:
        raise GCalError("token refresh returned no access_token")
    return tok


def _parse_dt(value: str) -> dt.datetime:
    """Parse an RFC3339 timestamp to an aware datetime (handles trailing 'Z')."""
    v = value.replace("Z", "+00:00")
    return dt.datetime.fromisoformat(v)


def _fetch_account_events(
    client_id: str, client_secret: str, refresh_token: str,
    time_min: dt.datetime, time_max: dt.datetime,
) -> list[dict[str, Any]]:
    token = _access_token(client_id, client_secret, refresh_token)
    r = requests.get(
        EVENTS_URL,
        headers={"Authorization": f"Bearer {token}"},
        params={
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 20,
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise GCalError(f"events fetch failed (HTTP {r.status_code}): {r.text[:200]}")
    return r.json().get("items", []) or []


def _normalize(item: dict[str, Any], label: str, color: str) -> dict[str, Any]:
    start, end = item.get("start", {}), item.get("end", {})
    all_day = "date" in start
    out = {
        "account": label,
        "label": label,
        "color": color,
        "summary": item.get("summary", "(no title)"),
        "location": item.get("location", ""),
        "all_day": all_day,
        "start_hm": None,
        "end_hm": None,
    }
    if not all_day:
        try:
            out["start_hm"] = _parse_dt(start["dateTime"]).astimezone().strftime("%H:%M")
            if end.get("dateTime"):
                out["end_hm"] = _parse_dt(end["dateTime"]).astimezone().strftime("%H:%M")
        except (KeyError, ValueError):
            pass
    return out


def fetch_events(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Return today's events across all configured accounts (sorted).

    [] if disabled/unconfigured. Raises GCalError if configured accounts all fail,
    so sync.py can keep the last good calendar.
    """
    gc = cfg.get("google_calendar", {}) or {}
    if not gc.get("enabled"):
        return []
    client_id = gc.get("client_id", "")
    client_secret = gc.get("client_secret", "")
    tokens = load_tokens()
    accounts = gc.get("accounts", []) or []
    if not (client_id and client_secret and tokens and accounts):
        return []

    now = dt.datetime.now().astimezone()
    time_min = now - dt.timedelta(minutes=30)            # include a just-started meeting
    time_max = now.replace(hour=23, minute=59, second=59, microsecond=0)

    events: list[dict[str, Any]] = []
    errors: list[str] = []
    attempted = 0
    for acc in accounts:
        label = acc.get("label", "Calendar")
        color = acc.get("color", "#6aa6ff")
        entry = tokens.get(label)
        if not entry or not entry.get("refresh_token"):
            continue  # account not yet authorized — skip quietly
        attempted += 1
        try:
            items = _fetch_account_events(
                client_id, client_secret, entry["refresh_token"], time_min, time_max
            )
            events.extend(_normalize(it, label, color) for it in items)
        except (GCalError, requests.RequestException) as e:
            errors.append(f"{label}: {e}")

    if attempted and len(errors) == attempted:
        raise GCalError("; ".join(errors))  # every account failed -> keep last snapshot

    events.sort(key=lambda e: (not e["all_day"], e.get("start_hm") or "00:00"))
    return events
