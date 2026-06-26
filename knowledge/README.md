# Knowledge base

This folder is the **editable brain** of the Life screen. Change any file here,
then run `./scripts/refresh.sh` (or wait for the 3am cron) and the display updates.
Everything is plain YAML — edit in any text editor.

| File | Drives | Edit this to… |
|------|--------|----------------|
| [`projects.yaml`](projects.example.yaml) | Projects screen (local provider) | list your parallel projects + top tasks (no account needed) |
| [`fitness.yaml`](fitness.yaml) | Today's movement | change gym/yoga/pickleball times per weekday |
| [`food.yaml`](food.yaml) | Next meal · tonight's dal soak | adjust the meal plan, dal rotation, or the Phase 1 `kickstart` day |
| [`house.yaml`](house.yaml) | Today's house tasks (by time of day) | re-assign chores to different days/times |
| [`travel.yaml`](travel.yaml) | Upcoming trips | add/remove trips |
| [`health.yaml`](health.yaml) | Remission phase, targets, safety, log nudges | set your phase, start date, weight/HbA1c targets, checkpoints |
| [`meal-plan.md`](meal-plan.md) | (reference) | the full plan + blood-sugar & remission protocol |

The **Projects screen** source is pluggable (set `dverse.provider` in
[`../config/config.yaml`](../config/config.yaml)): `local` reads your own
`projects.yaml` here (the default — no account); `dverse` syncs live from a dVerse
central-command portal.

## Don't want to hand-write YAML? Use the AI setup assistant
Open **`/setup`** in a browser. Paste an Anthropic API key (used only in your
browser session, never stored), and an assistant interviews you — fitness, food,
house, travel, health — and drafts the YAML for each domain. Every field stays
editable on the right; nothing is written until you click **Apply**, which saves
`knowledge/*.yaml` and refreshes the displays. (Built on the official Anthropic SDK,
`claude-opus-4-8`, tool use.)

## Rules of thumb
- Times are 24-hour `"HH:MM"` (quote them). Dates are `YYYY-MM-DD`.
- Weekday keys are lowercase: `monday … sunday`.
- A YAML list is `- item` lines or `[a, b, c]`. An empty list is `[]`.
- After editing, sanity-check with: `python -m server.sync life` (prints what it built).

## How a day is assembled
- **Fitness:** `weekly[today]`.
- **House:** `daily` (on `daily_days`) + `weekly[today]` + any `monthly` item due today, grouped by `sections`.
- **Food:** `days[today]` → the next meal by clock, tonight's `soak_tonight`. (Macros
  are computed to keep the plan balanced but are **not shown** on screen.)
- **Travel:** every trip whose `end` is today or later, soonest first.

## "Next 2 hours" — the screen only shows what's relevant now
The Life screen filters everything to the current clock so you're never looking at
afternoon chores at 6am:
- a **meal** shows when it's within ~2 hours;
- a **fitness** session shows while it's on or starting within 2 hours;
- **house** tasks show only while you're inside that group's `from`–`to` window
  (edit those times in `house.yaml` → `sections`);
- the **dal-soak** appears only in the ~2 hours before `soak_by` (evening);
- **travel** appears only when a trip is today/tomorrow/ongoing.

To change the 2-hour window, edit `WINDOW_MIN` at the top of
`web/static/js/life.js`. To change when a house group counts as "now", edit the
`from`/`to` times on each entry under `sections:` in `house.yaml`.

If nothing falls in the next 2 hours, the screen keeps the **next upcoming** item
on display (labelled "Next up · in Xh") instead of going blank.

## Google Calendar appointments (two accounts)
Appointments flow into the same "right now / next up" view, colour-tagged per
account. Configure under `google_calendar:` in `../config/config.yaml`, then
authorize each account once:

```
python scripts/gcal_auth.py "Personal"
python scripts/gcal_auth.py "Work"
```

Read-only access; tokens are stored in `config/google_tokens.json` (gitignored).
The kiosk refreshes appointments every 15 minutes. Full setup steps are in the
`google_calendar` comment block of `config.example.yaml`.

## Diabetic remission (health)
[`health.yaml`](health.yaml) drives a standing **health strip** on the Life screen
(current phase + week, weight/HbA1c progress, next checkpoint) plus **safety
reminders** during intensive phases and **glucose-log nudges** in the day's flow.

- Set `phase: 1` for the intensive kickstart (shows the `kickstart` day from
  `food.yaml`, ~1200 kcal, and a "train lighter" note). Any other phase shows the
  normal 7-day plan. ⚠️ Only run Phase 1 once your doctor has adjusted your meds.
- `kickstart_days: [saturday, sunday]` runs the low-carb kickstart only on those
  days and the ~150g plan on the rest — protects focus on creative weekdays.
- Fill in your real `targets` (weight start/target, HbA1c) and `phase_start`.

### Focus / cognition (food timing → task suggestions)
The `focus:` block in `health.yaml` ties meals to *when to do deep work*. The
**Projects screen** shows a live band — green "Prime focus" 20 min–2.5 h after a
fuel meal, "Fuel first" when fasted, red "Afternoon low" in the dip — and frames
your top priority accordingly. Edit `lag_min` / `window_min` / `fuel_meals` /
`dip_windows`. `electrolytes:` entries become 💧 reminders on the Life screen
(salt + lemon water clears most low-carb fog fast).
- **Log readings from your phone** at `http://<pi-ip>:8137/log` — fasting/post-meal
  glucose, weight, waist, HbA1c, ketones. They appear on the Life screen instantly.
  (LAN-only, no login — fine for a home network.)

> ⚠️ `food.yaml` is **not medical advice** — the macro targets are yours to set;
> confirm them with your doctor/dietitian. See the feasibility note in that file.
