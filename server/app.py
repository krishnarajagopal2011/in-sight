"""Flask server: serves the kiosk views, a tiny JSON API, and the phone log form.

The display API only ever reads snapshots from SQLite — it never calls dVerse on
the request path, so the kiosk is always instant. sync.py touches the network on a
schedule. The health block is the one exception: it's computed per-request so a
reading you just logged on your phone shows on the Life screen immediately.

Dev:   python -m server.app           (Flask dev server)
Prod:  served by waitress via scripts/refresh + systemd (see systemd/).
"""
from __future__ import annotations

import copy
import datetime as dt
import os
import time

from flask import Flask, jsonify, redirect, request, send_from_directory

from . import assistant, config, db, focus, health, schedules, sync
from .config import DB_PATH, KNOWLEDGE_DIR, KNOWLEDGE_FILES, WEB_DIR, load_config, server_settings

# Secrets the Settings page can store (whitelist — never echo values back).
ALLOWED_SECRETS = {
    "ANTHROPIC_API_KEY": "Anthropic API key (for the setup assistant)",
    "INSIGHT_DVERSE_PASSWORD": "dVerse central command password",
}

app = Flask(__name__, static_folder=None)

_CFG = load_config()
_SETTINGS = server_settings(_CFG)


def _snapshot_body(name: str):
    snap = db.get_snapshot(name)
    if snap is None:
        return {
            "ok": False, "stale": True,
            "error": "no snapshot yet — run `python -m server.sync`",
            "settings": {"refresh_seconds": _SETTINGS["refresh_seconds"]},
        }, 503
    age = time.time() - snap["updated_at"]
    return {
        "ok": True,
        "stale": age > _SETTINGS["stale_after_seconds"],
        "age_seconds": round(age),
        "updated_at": snap["updated_at"],
        "settings": {"refresh_seconds": _SETTINGS["refresh_seconds"]},
        "data": snap["payload"],
    }, 200


@app.get("/api/health")           # kiosk liveness probe (used by the launchers)
def healthcheck():
    return jsonify({"ok": True, "ts": int(time.time() * 1000)})


@app.get("/api/projects")
def api_projects():
    body, status = _snapshot_body("projects")
    if body.get("ok"):
        # Live focus state (food timing → suggest deep vs. light tasks).
        body["data"]["focus"] = focus.build_focus(load_config(), dt.datetime.now())
    return jsonify(body), status


@app.get("/api/life")
def api_life():
    body, status = _snapshot_body("life")
    if body.get("ok"):
        # Live health block (reads latest phone-logged readings + current phase).
        cfg = load_config()
        body["data"]["health"] = health.build_health(cfg, dt.date.today(), DB_PATH)
    return jsonify(body), status


# ── Health logging (phone form) ──────────────────────────────────────────────
@app.post("/api/log")
def api_log():
    payload = request.get_json(silent=True) or request.form.to_dict()
    data = {"date": payload.get("date") or dt.date.today().isoformat()}
    for f in ("weight_kg", "waist_cm", "fasting_glucose", "post_meal_glucose",
              "hba1c_pct", "ketones"):
        v = payload.get(f)
        data[f] = float(v) if v not in (None, "", "null") else None
    data["post_meal_label"] = payload.get("post_meal_label") or None
    data["notes"] = payload.get("notes") or None
    rid = db.add_reading(data)
    return jsonify({"ok": True, "id": rid})


@app.get("/api/readings")
def api_readings():
    return jsonify({"ok": True, "readings": db.recent_readings(20)})


# ── AI setup assistant + admin ───────────────────────────────────────────────
@app.post("/api/assistant")
def api_assistant():
    body = request.get_json(silent=True) or {}
    messages = body.get("messages") or []
    api_key = body.get("api_key")  # bring-your-own; used per-request, never stored
    try:
        result = assistant.run_turn(messages, api_key=api_key)
        return jsonify({"ok": True, **result})
    except assistant.AssistantError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


def _expand_food_week(data: dict) -> dict:
    """Fill every weekday's meals by cycling the days that have them, so all 7 days
    are written out explicitly (and independently editable)."""
    days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(days, dict):
        return data
    filled = [d for d in schedules.WEEKDAYS if (days.get(d) or {}).get("meals")]
    if not filled:
        return data
    for i, d in enumerate(schedules.WEEKDAYS):
        if not (days.get(d) or {}).get("meals"):
            days[d] = copy.deepcopy(days[filled[i % len(filled)]])
    data["days"] = {d: days[d] for d in schedules.WEEKDAYS if d in days}  # Mon→Sun order
    return data


@app.post("/api/assistant/apply")
def api_assistant_apply():
    """Write reviewed proposals into the knowledge base, then rebuild the snapshot."""
    body = request.get_json(silent=True) or {}
    written, errors = [], []
    import yaml
    for p in body.get("proposals") or []:
        domain = p.get("domain")
        if domain not in KNOWLEDGE_FILES:          # whitelist → no path traversal
            errors.append(f"unknown domain '{domain}'")
            continue
        try:
            if p.get("data") is not None:          # edited via the friendly form
                if domain == "food":
                    _expand_food_week(p["data"])   # write out all 7 days
                text = yaml.safe_dump(p["data"], sort_keys=False, allow_unicode=True)
            else:                                   # raw-YAML fallback
                text = p.get("yaml", "")
                yaml.safe_load(text)                # validate before writing
            (KNOWLEDGE_DIR / f"{domain}.yaml").write_text(text, encoding="utf-8")
            written.append(domain)
        except Exception as e:                      # noqa: BLE001 — surface to UI
            errors.append(f"{domain}: {e}")
    if written:
        try:
            sync.sync_life(load_config())           # reflect changes immediately
        except Exception:                           # noqa: BLE001
            pass
    return jsonify({"ok": not errors, "written": written, "errors": errors})


@app.get("/api/secrets")
def api_secrets_status():
    # Report only whether each secret is set — never the value.
    return jsonify({
        "ok": True,
        "secrets": {k: {"label": v, "set": bool(os.environ.get(k))}
                    for k, v in ALLOWED_SECRETS.items()},
    })


@app.post("/api/secrets")
def api_secrets_set():
    """Save secrets to the gitignored config/.env (chmod 600), applied live."""
    body = request.get_json(silent=True) or {}
    saved = []
    for key in ALLOWED_SECRETS:               # whitelist — ignore anything else
        val = (body.get(key) or "").strip()
        if val:
            config.set_env_secret(key, val)
            saved.append(key)
    return jsonify({"ok": bool(saved), "saved": saved})


@app.get("/settings")
def settings_view():
    return send_from_directory(WEB_DIR, "settings.html")


@app.get("/setup")
def setup_view():
    return send_from_directory(WEB_DIR, "setup.html")


@app.get("/")
def index():
    return redirect("/projects")


@app.get("/projects")
def projects_view():
    return send_from_directory(WEB_DIR, "projects.html")


@app.get("/life")
def life_view():
    return send_from_directory(WEB_DIR, "life.html")


@app.get("/log")                  # phone-friendly logging form
def log_view():
    return send_from_directory(WEB_DIR, "log.html")


@app.get("/static/<path:path>")
def static_files(path: str):
    return send_from_directory(WEB_DIR / "static", path)


# ── PWA (installable full-screen phone app) ──────────────────────────────────
@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(WEB_DIR, "manifest.webmanifest",
                               mimetype="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    # Served from root so its scope covers /life and /projects.
    resp = send_from_directory(WEB_DIR, "sw.js", mimetype="text/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


def run():
    db.init()
    app.run(host=_SETTINGS["host"], port=_SETTINGS["port"], debug=False)


if __name__ == "__main__":
    run()
