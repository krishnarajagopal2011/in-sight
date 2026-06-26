"""Focus engine — connects food timing + circadian rhythm to *when* to do deep work.

A personalised energy pattern (configurable; not the generic post-meal model):
  • Energy peaks right after waking and declines through the day.
  • A HIGH-PROTEIN breakfast carries that morning peak through to early afternoon.
  • A CARB-HEAVY lunch causes a post-lunch slump; a light/low-carb lunch doesn't —
    so on kickstart (low-carb) days the afternoon stays sharp.

State machine for the current clock:
  rest      → before wake
  prime     → in the morning peak (extended by a high-protein breakfast)
  dip       → post-lunch slump (only if lunch carbs are high) or a fixed dip window
  winddown  → after the peak: energy lower, do admin/planning, hardest work tomorrow AM

Computed at request time in app.py, so it tracks the day without a re-sync.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from . import schedules


def _to_min(hhmm: str) -> Optional[int]:
    try:
        h, m = (int(x) for x in str(hhmm).split(":"))
        return h * 60 + m
    except (ValueError, AttributeError):
        return None


def _find_meal(meals: list[dict], name: str) -> Optional[dict]:
    name = name.lower()
    for m in meals:
        if name in str(m.get("name", "")).lower():
            return m
    return None


def build_focus(cfg: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    fcfg = (cfg.get("health", {}) or {}).get("focus", {}) or {}
    meals = schedules.food_today(cfg, now.date()).get("meals", [])
    now_min = now.hour * 60 + now.minute

    wake = _to_min(fcfg.get("wake_time", "05:00")) or 300
    peak_end = wake + int(fcfg.get("morning_peak_hours", 5)) * 60

    # A high-protein breakfast extends the peak toward early afternoon.
    breakfast = _find_meal(meals, "breakfast")
    extended = False
    if breakfast and (breakfast.get("protein_g", 0) or 0) >= int(fcfg.get("breakfast_protein_threshold_g", 35)):
        ext = _to_min(fcfg.get("breakfast_extends_to", "14:00"))
        if ext and ext > peak_end:
            peak_end, extended = ext, True

    # A carb-heavy lunch opens a post-lunch slump.
    lunch = _find_meal(meals, "lunch")
    dip_start = dip_end = None
    carb_heavy = False
    if lunch and lunch.get("time"):
        lt = _to_min(lunch["time"])
        if lt is not None and (lunch.get("carbs_g", 0) or 0) >= int(fcfg.get("lunch_carb_dip_threshold_g", 45)):
            carb_heavy = True
            dip_start = lt + int(fcfg.get("post_lunch_dip_after_min", 30))
            dip_end = dip_start + int(fcfg.get("post_lunch_dip_dur_min", 90))

    def out(state, label, message, **extra):
        d = {"state": state, "label": label, "message": message}
        d.update(extra)
        return d

    if now_min < wake:
        return out("steady", "Rest", "Before your wake time — recharge.")

    # Post-lunch carb slump overrides everything while it's active.
    if dip_start is not None and dip_start <= now_min <= dip_end:
        return out("dip", "Post-lunch dip",
                   "Carb-heavier lunch — energy's low. Walk it off; do light tasks, not deep work.",
                   minutes_left=dip_end - now_min)

    # Fixed dip windows (optional).
    for d in fcfg.get("dip_windows", []) or []:
        a, b = _to_min(d.get("from", "")), _to_min(d.get("to", ""))
        if a is not None and b is not None and a <= now_min <= b:
            return out("dip", d.get("label", "Energy dip"),
                       "Running low — quick wins or admin, not hard thinking.")

    if now_min <= peak_end:
        msg = "Morning peak — your sharpest window. Take the hardest thing now."
        if extended and breakfast:
            msg = "Still peaking — your high-protein breakfast is carrying focus into the afternoon."
        return out("prime", "Peak focus", msg, minutes_left=peak_end - now_min,
                   extended=extended)

    # After the peak.
    tail = ("A low-carb lunch kept the crash away, but energy naturally tapers now — "
            if (lunch and not carb_heavy) else "")
    return out("winddown", "Winding down",
               tail + "Do admin, planning or recharge. Save the hardest work for tomorrow morning.")
