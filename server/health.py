"""Diabetic-remission health module.

Builds the health block shown on the Life screen:
  - current phase + week (from health.yaml `phase` / `phase_start`)
  - next checkpoint (HbA1c recheck, doctor visit …) with days-until
  - progress vs targets (weight, HbA1c) using the latest logged readings
  - safety reminders during the intensive phases
  - log nudges (fasting in the morning; 2 h after each main meal)

Readings come from the phone form (server.db.health_readings). This block is
computed at request time in app.py so newly-logged numbers show immediately.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Optional

from . import db, schedules


def _as_date(v: Any) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


def _next_checkpoint(start: Optional[dt.date], checkpoints: list[dict], today: dt.date):
    if not start:
        return None
    upcoming = []
    for c in checkpoints or []:
        wk = c.get("offset_weeks", 0)
        date = start + dt.timedelta(weeks=wk)
        if date >= today:
            upcoming.append({"label": c.get("label", "Checkpoint"),
                             "date": date.isoformat(),
                             "days_until": (date - today).days})
    upcoming.sort(key=lambda x: x["date"])
    return upcoming[0] if upcoming else None


def _num(x) -> Optional[float]:
    """Tolerant number parse — e.g. "70kg" -> 70.0, "" / None / "—" -> None."""
    try:
        return float(x)
    except (TypeError, ValueError):
        m = re.search(r"-?\d+(\.\d+)?", str(x or ""))
        return float(m.group()) if m else None


def _progress(targets: dict, latest) -> dict[str, Any]:
    out: dict[str, Any] = {}

    w = targets.get("weight_kg", {}) or {}
    cur_w = latest("weight_kg")
    start, target = _num(w.get("start")), _num(w.get("target"))
    now_w = _num(cur_w["value"]) if cur_w else None
    if now_w is not None and start is not None and target is not None:
        lost, goal = start - now_w, start - target
        out["weight"] = {
            "current": now_w, "start": start, "target": target,
            "lost": round(lost, 1), "goal": round(goal, 1),
            "pct": max(0, min(100, round(lost / goal * 100))) if goal else 0,
            "date": cur_w["date"],
        }
    elif now_w is not None:
        out["weight"] = {"current": now_w, "date": cur_w["date"]}

    h = targets.get("hba1c_pct", {}) or {}
    cur_h = latest("hba1c_pct")
    if cur_h and _num(cur_h["value"]) is not None:
        out["hba1c"] = {"current": _num(cur_h["value"]), "date": cur_h["date"],
                        "start": _num(h.get("start")), "target": _num(h.get("target"))}

    for f in ("fasting_glucose", "waist_cm"):
        r = latest(f)
        if r and _num(r["value"]) is not None:
            out[f] = {"current": _num(r["value"]), "date": r["date"]}
    return out


def build_health(cfg: dict[str, Any], today: dt.date, db_path=None) -> dict[str, Any]:
    h = cfg.get("health", {}) or {}
    if not h:
        return {}

    phase = h.get("phase", 4)
    labels = {int(k): v for k, v in (h.get("phase_labels", {}) or {}).items()}
    start = _as_date(h.get("phase_start"))
    week = ((today - start).days // 7 + 1) if start else None

    latest = (lambda f: db.latest_reading(f, db_path)) if db_path else db.latest_reading

    safety = h.get("safety", {}) or {}
    intensive = phase in (safety.get("show_in_phases", [0, 1]) or [])

    # Log nudges as timed items the Life screen can surface within its window.
    nudges = []
    lr = h.get("log_reminders", {}) or {}
    fasting = lr.get("fasting", {})
    if fasting.get("time"):
        nudges.append({"time": fasting["time"], "label": fasting.get("label", "Log fasting glucose"),
                       "kind": "fasting", "icon": "🩸", "sub": "Log on your phone → /log"})
    after = int(lr.get("post_meal_after_min", 120))
    main = set(lr.get("main_meals", []) or [])
    food = schedules.food_today(cfg, today)
    for m in food.get("meals", []):
        if m.get("name") in main:
            t = _hhmm_plus(m.get("time", ""), after)
            if t:
                nudges.append({"time": t, "label": f"Log 2 h glucose ({m['name']})",
                               "kind": "post_meal", "icon": "🩸", "sub": "Log on your phone → /log"})

    # Electrolytes clear most "low-carb fog" fast (sodium/water loss; worse on SGLT2 meds).
    for e in (h.get("focus", {}) or {}).get("electrolytes", []) or []:
        if e.get("time"):
            nudges.append({"time": e["time"], "label": e.get("label", "Electrolytes"),
                           "kind": "electrolyte", "icon": "💧", "sub": "Clears the low-carb fog"})

    return {
        "phase": phase,
        "phase_label": labels.get(phase, str(phase)),
        "week": week,
        "intensive": intensive,
        "training_note": h.get("training_note_intensive", "") if intensive else "",
        "next_checkpoint": _next_checkpoint(start, h.get("checkpoints", []), today),
        "targets": h.get("targets", {}) or {},
        "progress": _progress(h.get("targets", {}) or {}, latest),
        "safety": (safety.get("reminders", []) or []) if intensive else [],
        "nudges": nudges,
    }


def _hhmm_plus(hhmm: str, minutes: int) -> Optional[str]:
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except (ValueError, AttributeError):
        return None
    total = (h * 60 + m + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"
