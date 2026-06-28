# Deploying in_sight to Render

in_sight runs as one always-on web service (Flask via waitress) with a persistent
disk for its SQLite cache and an in-process sync (no separate cron). A password gate
turns on automatically when `INSIGHT_PASSWORD` is set.

## 0. Your personal data — two choices

Your real `config/config.yaml` and `knowledge/*.yaml` are gitignored (so they never
hit the public repo). Pick how to get them onto Render:

- **Private repo (simplest).** Create a *private* GitHub repo, push this project to it
  including your data files (`git add -f config/config.yaml knowledge/*.yaml`), and
  point Render at that repo. Data stays in a private repo; passwords/keys still go in
  env vars below, never in git.
- **Secret Files (keeps data off GitHub).** Deploy from the public repo and, in the
  Render dashboard → *Environment* → *Secret Files*, paste each of `config/config.yaml`
  and `knowledge/<domain>.yaml`. More clicks, but nothing personal is on GitHub.

> If you skip both, the app falls back to the `*.example.yaml` templates (generic demo
> data) — useful to confirm the deploy works before adding your real data.

## 1. Create the service

1. Push this repo (with `render.yaml`) to GitHub.
2. Render dashboard → **New → Blueprint** → connect the repo. Render reads
   `render.yaml` and proposes the `in-sight` web service + a 1 GB disk.
3. Click **Apply**.

## 2. Set the secrets (dashboard → the service → Environment)

| Key | Value |
|-----|-------|
| `INSIGHT_PASSWORD` | a password you choose — protects the public URL |
| `INSIGHT_DVERSE_PASSWORD` | your dVerse central-command password |
| `ANTHROPIC_API_KEY` | optional — only for the setup wizard |

`INSIGHT_DB`, `INSIGHT_BG_SYNC`, `INSIGHT_SYNC_SECONDS`, and `INSIGHT_SECRET_KEY` are
set automatically by `render.yaml`.

## 3. First load

Open the service URL (e.g. `https://in-sight.onrender.com`). You'll get the login
page → enter `INSIGHT_PASSWORD` → the Projects screen. The background sync fills the
data within a minute. Add it as an app / press fullscreen on each device.

## Notes

- **Plan:** `starter` ($7/mo) stays always-warm. `free` works but spins down when idle
  (~30s cold start on next open); the last snapshot is preserved on the disk.
- **Google Calendar** needs `config/google_tokens.json` — add it as a Secret File if
  you want calendar events on the cloud instance.
- **Fullscreen:** the PWA manifest is `display: fullscreen`; "Install app" (desktop
  Chrome) or "Add to Home screen" (OnePlus) opens it chromeless.
