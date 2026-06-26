#!/usr/bin/env python3
"""One-time Google Calendar authorization for the in_sight kiosk.

Run this ONCE PER ACCOUNT on a machine with a browser (e.g. your Mac). It opens
Google's consent screen; you log in + approve read-only Calendar access; it
captures the result on a loopback port and saves a long-lived refresh token to
config/google_tokens.json. The kiosk then refreshes appointments on its own.

Prereqs (do these yourself in the Google Cloud console — Claude can't):
  1. Create / pick a project, enable the "Google Calendar API".
  2. Configure the OAuth consent screen (External, add yourself as a test user
     for each of your two Google accounts).
  3. Create an OAuth client of type "Desktop app". Copy its Client ID + Secret
     into config.yaml under google_calendar.client_id / client_secret.

Usage:
  python scripts/gcal_auth.py "Personal"
  python scripts/gcal_auth.py "Work"
(The label must match an entry under google_calendar.accounts in config.yaml.)
"""
from __future__ import annotations

import http.server
import json
import socket
import sys
import urllib.parse
import webbrowser

import requests

# Make `server` importable when run as a script.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from server.config import load_config              # noqa: E402
from server.gcal import TOKENS_PATH, SCOPE         # noqa: E402

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Handler(http.server.BaseHTTPRequestHandler):
    code = None
    def do_GET(self):  # noqa: N802
        q = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(q)
        _Handler.code = (params.get("code") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        ok = "✅ Authorized. You can close this tab and return to the terminal."
        err = "⚠️ No code received. Check the terminal."
        self.wfile.write(f"<html><body style='font-family:sans-serif;padding:3rem'>{ok if _Handler.code else err}</body></html>".encode())
    def log_message(self, *_):  # silence
        pass


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: python scripts/gcal_auth.py \"<AccountLabel>\"")
        return 2
    label = argv[0]

    cfg = load_config()
    gc = cfg.get("google_calendar", {}) or {}
    client_id, client_secret = gc.get("client_id", ""), gc.get("client_secret", "")
    if not client_id or not client_secret:
        print("✗ Set google_calendar.client_id and client_secret in config.yaml first.")
        return 1
    labels = [a.get("label") for a in gc.get("accounts", []) or []]
    if label not in labels:
        print(f"✗ '{label}' is not in google_calendar.accounts ({labels}). Add it first.")
        return 1

    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",        # force a refresh_token every time
        "include_granted_scopes": "true",
    })

    print(f"\nAuthorizing account '{label}'.")
    print("A browser window will open. Sign in with the Google account you want")
    print(f"to map to '{label}', then approve read-only Calendar access.\n")
    print(f"If it doesn't open, paste this URL:\n{auth_url}\n")
    webbrowser.open(auth_url)

    httpd = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    httpd.handle_request()  # serve exactly one request (the redirect)
    code = _Handler.code
    if not code:
        print("✗ Did not receive an authorization code.")
        return 1

    tok = requests.post(TOKEN_URL, data={
        "client_id": client_id, "client_secret": client_secret,
        "code": code, "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }, timeout=20).json()
    refresh_token = tok.get("refresh_token")
    access_token = tok.get("access_token")
    if not refresh_token:
        print(f"✗ No refresh_token returned: {tok}")
        print("  Tip: revoke prior access at myaccount.google.com → Security → Third-party,")
        print("  then re-run (prompt=consent is already set).")
        return 1

    email = ""
    try:
        email = requests.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"},
                             timeout=20).json().get("email", "")
    except requests.RequestException:
        pass

    tokens = {}
    if TOKENS_PATH.exists():
        tokens = json.loads(TOKENS_PATH.read_text())
    tokens[label] = {"refresh_token": refresh_token, "email": email}
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))
    try:
        TOKENS_PATH.chmod(0o600)
    except OSError:
        pass

    print(f"\n✓ Saved '{label}'{f' ({email})' if email else ''} → {TOKENS_PATH}")
    print("  Re-run for your other account with a different label, then:")
    print("  ./scripts/refresh.sh life   &&   open the Life screen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
