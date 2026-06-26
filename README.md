# in sight

An ADHD-friendly, clutter-free **life + work dashboard** — a wall kiosk (built for a
Raspberry Pi 5) *and* an installable phone app, always in sync.

> Built to defeat *out of sight, out of mind*. The screens never go blank, never
> need a click, and only ever show what's relevant **right now**.

Two fullscreen views:

| Screen | Route | Shows |
|--------|-------|-------|
| **Projects** | `/projects` | Your parallel projects + top tasks, with a live "focus window" hint tied to food timing. Source is pluggable: your own list (default) or a dVerse central-command portal. |
| **Life** | `/life` | A calm "next 2 hours": the next meal, today's movement, house tasks, travel, and health/remission progress — only what's relevant to the clock. |

## Quickstart

Runs on any machine (Mac/Linux/Pi). No accounts needed to try it.

```bash
git clone https://github.com/krishnarajagopal2011/in-sight.git
cd in-sight
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m server.sync        # build the first snapshot (uses the bundled examples)
python -m server.app         # serve on http://localhost:8137
```

Open **http://localhost:8137/projects** and **/life** — they work immediately on the
bundled example data.

**Make it yours (two options):**
1. **AI setup assistant** — open **`/settings`**, paste your **Anthropic (Claude) API
   key** (stored only on your device), then open **`/setup`**: an assistant interviews
   you and fills your config (projects, fitness, food, house, travel, health). Review
   each as a friendly form, then **Apply**.
2. **Edit files** — copy any `knowledge/<name>.example.yaml` to `knowledge/<name>.yaml`
   and edit. Run `python -m server.sync` to refresh.

Log health readings from your phone at **`/log`**. Install the phone app via your
browser's **Add to Home screen** (full-screen PWA). For the Pi kiosk + autostart, see
[Quick start (on the Pi)](#quick-start-on-the-pi) below.

## How it works

```
                 cron 03:00 ──► sync.py ──► SQLite snapshot
                                   │              │
        dVerse central command ────┘              │  (offline-first cache)
        (ClickUp adapter)                         ▼
                                            Flask + waitress  ──►  Chromium kiosk
        config/config.yaml ─────────────► (schedules engine)       (one view, fullscreen)
        (fitness/meals/travel/house)
```

- **`sync.py`** runs at 3am (and on boot). It pulls projects/tasks from dVerse
  central command and computes today's life plan from `config/config.yaml`,
  then writes two JSON **snapshots** into SQLite.
- **`app.py`** (Flask, served by waitress) serves the two HTML views and a small
  JSON API that just reads the latest snapshot. If sync fails, the last good
  snapshot stays on screen and a small "stale" dot appears.
- The browser **auto-refreshes** the data every 30s and recomputes time-sensitive
  items (next meal, tablets) every minute — no interaction ever needed.

## Quick start (on the Pi)

```bash
git clone <this repo> /opt/in_sight   # or copy the folder there
cd /opt/in_sight
cp config/config.example.yaml config/config.yaml
nano config/config.yaml               # add your ClickUp token + your schedules
sudo ./scripts/install.sh             # installs deps, services, kiosk autostart, 3am cron
```

After install:
- Screen 1 (HDMI-1) boots into `/projects`
- Screen 2 (HDMI-2) boots into `/life`
- Data refreshes automatically every morning at 03:00

## Run it on your laptop first (recommended)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/config.example.yaml config/config.yaml
python -m server.sync          # build the first snapshot
python -m server.app           # serve on http://localhost:8137
# open http://localhost:8137/projects  and  http://localhost:8137/life
```

## Phone widget (PWA) — the kiosk in your pocket

in_sight is an installable **PWA**, so you can add it to your Android home screen as
a **full-screen app** that shows the *same* views as the kiosk. They stay in sync
automatically — the phone loads the same `/life` and `/projects` pages and polls the
same `/api` snapshot every 30s, so it always shows exactly what the kiosk shows.
On the phone a small bottom nav (Right now / Projects) appears; on the wide kiosk it
doesn't. A service worker caches the shell so it opens instantly and survives a
dropped connection (last view stays up, with the "stale" dot).

### Reaching it from anywhere + HTTPS (Tailscale)
The server is LAN-only, and Android needs **HTTPS** to install a full-screen PWA.
[Tailscale](https://tailscale.com) solves both, free:

1. Install Tailscale on the Pi and your phone, signed into the same account.
2. On the Pi, expose the kiosk over HTTPS on your tailnet:
   ```bash
   sudo tailscale serve --bg 8137      # → https://<pi-name>.<tailnet>.ts.net
   ```
3. On the phone, open that `https://…ts.net` URL in Chrome → **⋮ → Add to Home
   screen / Install app**. It installs as a full-screen "in sight" icon, reachable
   anywhere you're on the tailnet — no need to be home.

(On plain `http://<lan-ip>:8137` you can still "Add to Home screen", but Android may
keep the address bar and won't enable offline caching — HTTPS via Tailscale gives the
true full-screen app.)

`start_url` is `/life`; change it in `web/manifest.webmanifest` to default to
`/projects` instead. Long-pressing the icon offers both as shortcuts.

## Secrets — set them once at `/settings`

Open **`/settings`** to store your **Anthropic API key** and **dVerse password**.
They're written to a gitignored, owner-only `config/.env` (the local equivalent of
a Vercel/Supabase env-var store), loaded at startup, and applied live — set once and
they persist across restarts, are never typed into the chat, and aren't sent on every
request. systemd reads the same file via `EnvironmentFile=`. Over a network, use HTTPS
(`tailscale serve`) so values aren't sent in the clear. You can also set them the
classic way: `export ANTHROPIC_API_KEY=…` / put `INSIGHT_DVERSE_PASSWORD=…` in
`config/.env` by hand — real process env vars take precedence over the file.

## Connecting dVerse central command

Central command (https://dverse-central-command.vercel.app) is a Next.js app with
no public read API — its "What's Today" page is server-rendered. `server/dverse.py`
authenticates (`POST /api/auth/login` → 30-day session cookie), fetches `/tasks`,
and parses the embedded React Server Components payload, which carries the full
**Goals → Milestones → Tasks** tree.

In `config/config.yaml` under `dverse:` set `provider: dverse`, your `email`, and
the password (better: export `INSIGHT_DVERSE_PASSWORD` instead of writing it to
the file). Then:
- each **Goal** becomes a parallel-project card with its current milestone + next action,
- your **top priorities** (`myTasks`) become the immediate-tasks rail,
- the highest-priority task is promoted to the big "Do this next" focus card.

> If central command changes its page structure, the RSC parser may need a tweak —
> the anchor is the `myEmployeeId` key in `server/dverse.py`.

No account / offline? Set `provider: local` and define projects under
`projects_fallback:` / `immediate_fallback:` — everything still runs.

## Files

```
in_sight/
├── server/
│   ├── app.py            # Flask server (views + JSON API)
│   ├── sync.py           # 3am job: pull dVerse + compute life plan → snapshots
│   ├── db.py             # SQLite snapshot cache (offline-first)
│   ├── schedules.py      # fitness/meals/tablets/travel/house engine
│   ├── dverse.py         # adapter: ClickUp client + local fallback
│   └── config.py         # config loader
├── web/
│   ├── projects.html     # Screen 1
│   ├── life.html         # Screen 2
│   └── static/{css,js}   # ADHD-friendly kiosk styling + vanilla JS
├── scripts/              # install + kiosk launchers + refresh
├── systemd/              # server + two kiosk services
└── config/config.example.yaml
```
