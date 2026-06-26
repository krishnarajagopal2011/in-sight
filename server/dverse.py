"""Adapter for dVerse central command (https://dverse-central-command.vercel.app).

Central command is a Next.js App-Router app. There is no public JSON read API:
the "What's Today" page (/tasks) is server-rendered and embeds its data as a
React Server Components (RSC) payload inside <script>self.__next_f.push(...)</script>
chunks. We authenticate, fetch that page, reassemble the RSC buffer, and pull out
the well-formed JSON object that holds goals, milestones and tasks.

Data model:  Goals -> Milestones -> Tasks
  goalSummaries[]  : {id, title, ownerName, status, pct, done, total, targetDate}
  teamSummaries[]  : {leadId, leadName, milestones:[{id,title,status,goalTitle,dueDate,done,total,pct}]}
  myTasks[]        : {id, title, status, priority, dueDate, milestoneId, milestoneTitle, goalId, goalTitle}
  pendingDrafts    : approvals waiting on the CEO

If login or fetch fails, callers keep showing the last good snapshot (offline-first).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import requests

DEFAULT_BASE_URL = "https://dverse-central-command.vercel.app"
LOGIN_PATH = "/api/auth/login"
TASKS_PATH = "/tasks"
TIMEOUT = 20

_RSC_RE = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)', re.S)

PRIORITY_LABELS = {1: "High", 2: "Normal", 3: "Low"}


class DverseError(RuntimeError):
    pass


def _reassemble_rsc(html: str) -> str:
    """Concatenate the decoded string args of every self.__next_f.push([1, "..."])."""
    parts = []
    for raw in _RSC_RE.findall(html):
        try:
            parts.append(json.loads(raw))  # raw includes its own surrounding quotes
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def _extract_object_containing(buf: str, anchor: str) -> Optional[str]:
    """Return the smallest brace-balanced JSON object in `buf` that contains `anchor`."""
    i = buf.find(anchor)
    if i < 0:
        return None
    start = buf.rfind("{", 0, i)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(buf)):
        ch = buf[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return buf[start : j + 1]
    return None


def fetch_central_data(
    base_url: str, email: str, password: str
) -> dict[str, Any]:
    """Log in and return the parsed 'What's Today' data object.

    Raises DverseError on any failure so sync.py can fall back to cache.
    """
    base_url = base_url.rstrip("/")
    session = requests.Session()
    session.headers.update({"User-Agent": "in-sight-kiosk/1.0"})

    try:
        r = session.post(
            base_url + LOGIN_PATH,
            json={"email": email, "password": password},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise DverseError(f"login request failed: {e}") from e

    if r.status_code != 200:
        raise DverseError(f"login returned HTTP {r.status_code}")
    if "dverse_session" not in session.cookies.get_dict():
        raise DverseError("login did not set a session cookie (bad credentials?)")

    try:
        r = session.get(base_url + TASKS_PATH, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise DverseError(f"tasks request failed: {e}") from e
    if r.status_code != 200:
        raise DverseError(f"/tasks returned HTTP {r.status_code}")

    buf = _reassemble_rsc(r.text)
    obj = _extract_object_containing(buf, '"myEmployeeId"')
    if not obj:
        raise DverseError("could not locate data payload in /tasks RSC")
    try:
        return json.loads(obj)
    except json.JSONDecodeError as e:
        raise DverseError(f"data payload was not valid JSON: {e}") from e


def build_projects_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Shape central-command data into the projects-screen snapshot.

    Each company goal becomes a "parallel project" card carrying its current
    milestone, progress, and single most-immediate next action.
    """
    goals = data.get("goalSummaries", []) or []
    my_tasks = data.get("myTasks", []) or []
    me = data.get("myEmployeeId")

    # Flatten every lead's milestones; index the current milestone per goal title.
    milestone_by_goal: dict[str, dict[str, Any]] = {}
    for team in data.get("teamSummaries", []) or []:
        for m in team.get("milestones", []) or []:
            gt = m.get("goalTitle")
            if gt and gt not in milestone_by_goal:
                milestone_by_goal[gt] = m

    # The signed-in user's milestones from Team Progress.
    my_milestones = []
    teams = data.get("teamSummaries", []) or []
    mine = [t for t in teams if t.get("leadId") == me] or teams
    person = next((t.get("leadName") for t in mine if t.get("leadName")), None)
    for team in mine:
        for m in team.get("milestones", []) or []:
            my_milestones.append(
                {
                    "goal": m.get("goalTitle"),
                    "title": m.get("title"),
                    "status": m.get("status"),
                    "done": m.get("done", 0),
                    "total": m.get("total", 0),
                    "pct": m.get("pct", 0),
                    "due": m.get("dueDate"),
                }
            )

    # Immediate next task per goal (lowest priority number = most urgent).
    next_task_by_goal: dict[str, dict[str, Any]] = {}
    for t in sorted(my_tasks, key=lambda x: (x.get("priority") or 99)):
        gt = t.get("goalTitle")
        if gt and gt not in next_task_by_goal:
            next_task_by_goal[gt] = t

    projects = []
    for g in goals:
        title = g.get("title", "Untitled")
        ms = milestone_by_goal.get(title, {})
        nt = next_task_by_goal.get(title)
        projects.append(
            {
                "title": title,
                "owner": g.get("ownerName"),
                "status": g.get("status"),
                "pct": g.get("pct", 0),
                "done": g.get("done", 0),
                "total": g.get("total", 0),
                "milestone": ms.get("title"),
                "milestone_status": ms.get("status"),
                "milestone_done": ms.get("done", 0),
                "milestone_total": ms.get("total", 0),
                # The one thing to actually do next on this project.
                "next_action": (nt or {}).get("title") or ms.get("title"),
                "next_action_priority": _priority_label((nt or {}).get("priority")),
            }
        )

    immediate = [
        {
            "title": t.get("title", ""),
            "priority": t.get("priority"),
            "priority_label": _priority_label(t.get("priority")),
            "goal": t.get("goalTitle"),
            "milestone": t.get("milestoneTitle"),
            "due": t.get("dueDate"),
            "status": t.get("status"),
        }
        for t in sorted(my_tasks, key=lambda x: (x.get("priority") or 99))
    ]

    # "Waiting on you" — drafts/approvals pending the CEO's sign-off.
    drafts = data.get("pendingDrafts") or []
    waiting = {
        "count": len(drafts) if isinstance(drafts, list) else int(drafts or 0),
        "items": [
            {
                "title": d.get("title") or d.get("name") or "Draft to approve",
                "goal": d.get("goalTitle") or d.get("goal"),
            }
            for d in (drafts if isinstance(drafts, list) else [])
        ],
    }

    return {
        "source": "dverse",
        "person": person,
        "projects": projects,
        "immediate": immediate,        # top priorities (myTasks)
        "milestones": my_milestones,   # the user's milestones (team progress)
        "waiting": waiting,            # waiting on you (drafts/approvals)
    }


def _priority_label(p: Any) -> Optional[str]:
    if p is None:
        return None
    return PRIORITY_LABELS.get(int(p), "Normal")
