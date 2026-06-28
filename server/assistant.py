"""AI setup assistant ("Zen Mate" style) — interviews the user and proposes config.

Bring-your-own Anthropic key (per-request, never persisted). The assistant asks
short, ADHD-friendly questions one domain at a time and, when it has enough for a
domain, calls the `save_domain` tool with well-formed YAML. The backend surfaces
those as *editable proposals* — nothing is written to the knowledge base until the
user reviews and clicks Apply (see app.py /api/assistant/apply).

Uses the official Anthropic SDK + tool use (claude-api skill reference).
"""
from __future__ import annotations

import os
from typing import Any, Optional

import anthropic
import yaml

MODEL = "claude-opus-4-8"
MAX_TOKENS = 4096
DOMAINS = ["projects", "fitness", "food", "house", "travel", "health", "schedule"]

SYSTEM = """\
You are the in sight setup assistant — a warm, concise onboarding guide (think
"Zen Mate"). in sight is an ADHD-friendly dashboard that shows someone only what's
relevant right now: their projects, the next meal, today's movement, house tasks,
travel, and health.

in sight is a strictly **100% VEGAN** platform. This is non-negotiable: every food
suggestion, example, question, and the food config must be entirely plant-based.
NEVER mention or suggest meat, fish, seafood, eggs, dairy (milk, cheese, paneer,
curd, yogurt, whey, ghee, butter), honey, or gelatin — not even as an example. If
the user names a non-vegan food, gently suggest a vegan swap (e.g. tofu/tempeh/soy,
legumes, nuts/seeds, plant milks). Lean on plant proteins, dals/legumes, non-starchy
veg, nuts and seeds; for omega-3 use flax/chia/walnuts/algae oil (never fish).

Your job: interview the user and fill their configuration. Rules:
- ADHD-friendly: ask ONE small thing at a time, 1–2 sentences. Never a wall of questions.
- Go domain by domain in this order: projects, fitness, food, house, travel, health, schedule.
  Skip any the user says don't apply.
- The moment you have enough for a domain, call the `save_domain` tool with valid
  YAML for that domain (schemas below), then move to the next domain with a short
  transition. Don't wait until the end.
- Propose sensible defaults from what they tell you; they'll review and edit everything.
- For FOOD specifically: fill all seven days (monday..sunday) with meals based on their
  inputs — vary them across the week for interest while keeping each day near the macro
  targets. Never leave days empty.
- Times are "HH:MM" (24h). Weekday keys are lowercase monday..sunday.
- Never give medical advice. For the health domain, capture what they tell you and
  add a brief note to confirm targets with their doctor.

YAML schemas (match these shapes):

projects:               # parallel projects + top tasks (the Projects screen)
  projects:
    - {title: "Project name", next_action: "the next concrete step", status: ACTIVE, pct: 0}
  tasks:                # top priorities right now (the #1 becomes "Do this next")
    - {title: "a task to do", priority: High, goal: "Project name"}

fitness:
  weekly:
    monday: [{name: Gym, start: "06:00", end: "07:30", detail: "Strength"}]
    tuesday: []   # rest day

food:
  targets: {protein_g: 180, carbs_g: 150, fat_g: 70, calories: 2000}
  soak_by: "19:00"
  daily_supplements: [{name: "Creatine 5 g", when: "any time"}]
  guidance: ["short reminder strings"]
  days:                 # FILL ALL SEVEN DAYS (monday..sunday) — never just one.
    monday:             # Vary meals across days for interest, keeping each day near targets.
      soak_tonight: "what to soak tonight for tomorrow (or empty)"
      meals:
        - {name: Breakfast, time: "08:00", items: ["item one", "item two"],
           protein_g: 40, carbs_g: 30, fat_g: 12, note: "optional cue e.g. ACV first"}
    # … tuesday, wednesday, thursday, friday, saturday, sunday — all populated.

house:
  sections:
    - {key: early_morning, label: "Early morning", from: "05:00", to: "11:00"}
    - {key: afternoon_evening, label: "Afternoon – evening", from: "12:00", to: "19:00"}
    - {key: night, label: "Night", from: "19:00", to: "23:59"}
  daily_days: [monday, tuesday, wednesday, thursday, friday]
  daily: {early_morning: ["task"], night: ["task"]}
  weekly: {tuesday: {afternoon_evening: ["task"]}}
  monthly: [{when: first-monday, section: early_morning, task: "Rent payment"}]

travel:
  trips: [{destination: "City", start: "2026-07-02", end: "2026-07-04", purpose: "why", note: "flight etc"}]

health:
  phase: 4            # 1=intensive kickstart, 4=maintenance
  phase_start: "2026-06-25"
  targets:
    weight_kg: {start: null, target: null}
    hba1c_pct: {start: null, target: null}
  focus:
    wake_time: "06:00"
    morning_peak_hours: 5
    electrolytes: [{time: "10:30", label: "Salt + lemon water"}]
  log_reminders: {fasting: {time: "06:30", label: "Log fasting glucose"}}

schedule:               # practical daily time blocks; each shows 2 options to pick
  buffer_min: 15        # task-switch buffer between blocks (ADHD)
  parents_call: {every_days: 2, since: "2026-06-28", label: "Call parents"}
  blocks:
    - {name: "Focus block", start: "05:00", end: "06:00", kind: focus,
       options: ["Grant writing", "Concept detailing"]}
    - {name: "Recharge", start: "14:00", end: "18:00", kind: danger, community: true,
       options: ["Outdoor walk in the light", "Movement / sport", "Protein snack, not junk"]}
  events:               # recurring community events, surfaced in the matching block
    - {name: "Event", days: [friday], start: "20:00", end: "22:00", place: "Venue"}

Begin by briefly introducing yourself in one line, then ask what projects or goals
they're juggling right now.
"""

SAVE_TOOL = {
    "name": "save_domain",
    "description": (
        "Propose configuration for one domain. Call this when you have enough info "
        "for that domain. The user reviews and edits before it's applied."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "enum": DOMAINS},
            "yaml_content": {
                "type": "string",
                "description": "Valid YAML for the domain, matching its schema.",
            },
            "summary": {
                "type": "string",
                "description": "One short sentence describing what you set.",
            },
        },
        "required": ["domain", "yaml_content"],
    },
}


class AssistantError(RuntimeError):
    pass


def _client(api_key: Optional[str]) -> anthropic.Anthropic:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise AssistantError("No Anthropic API key. Paste your key to start.")
    return anthropic.Anthropic(api_key=key)


def run_turn(messages: list[dict[str, Any]], api_key: Optional[str] = None) -> dict[str, Any]:
    """Run one assistant turn. Returns {reply, proposals, messages}.

    `messages` is the running history (plain dicts, round-tripped via the client).
    Proposals are surfaced for review; tool_results are appended so the chat stays
    coherent on the next turn.
    """
    client = _client(api_key)
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM,
            tools=[SAVE_TOOL], messages=messages,
        )
    except anthropic.AuthenticationError:
        raise AssistantError("That API key was rejected. Check it and try again.")
    except anthropic.APIStatusError as e:
        raise AssistantError(f"Anthropic API error ({e.status_code}). Try again shortly.")
    except anthropic.APIConnectionError:
        raise AssistantError("Couldn't reach Anthropic. Check the connection.")

    reply_parts, proposals, tool_results = [], [], []
    for block in resp.content:
        if block.type == "text":
            reply_parts.append(block.text)
        elif block.type == "tool_use" and block.name == "save_domain":
            inp = block.input or {}
            domain = inp.get("domain")
            ycontent = inp.get("yaml_content", "")
            ok, err = _validate_yaml(domain, ycontent)
            # Send the parsed object too, so the UI can render a friendly form
            # (no YAML library needed in the browser).
            data = yaml.safe_load(ycontent) if ok else None
            proposals.append({
                "domain": domain, "yaml": ycontent, "data": data,
                "summary": inp.get("summary", ""), "valid": ok, "error": err,
            })
            tool_results.append({
                "type": "tool_result", "tool_use_id": block.id,
                "content": "Captured for the user to review and edit."
                if ok else f"Captured, but the YAML had an issue: {err}",
            })

    # Keep the conversation coherent: append assistant turn + any tool results.
    new_messages = list(messages)
    new_messages.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
    if tool_results:
        new_messages.append({"role": "user", "content": tool_results})

    return {
        "reply": "\n\n".join(reply_parts).strip(),
        "proposals": proposals,
        "messages": new_messages,
        "done": resp.stop_reason != "tool_use",
    }


def _validate_yaml(domain: Optional[str], content: str) -> tuple[bool, str]:
    if domain not in DOMAINS:
        return False, f"unknown domain '{domain}'"
    try:
        yaml.safe_load(content)
        return True, ""
    except yaml.YAMLError as e:
        return False, str(e)[:200]
