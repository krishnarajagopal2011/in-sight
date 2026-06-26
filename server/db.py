"""Offline-first snapshot cache (SQLite).

The whole point: the display reads the *last good snapshot*, so a failed sync or a
dead network never blanks the screen — it just goes stale. sync.py writes
snapshots; app.py reads them.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    name        TEXT PRIMARY KEY,   -- 'projects' | 'life'
    payload     TEXT NOT NULL,      -- JSON blob the API serves verbatim
    updated_at  REAL NOT NULL       -- epoch seconds of last successful build
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS health_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,          -- YYYY-MM-DD the reading is for
    weight_kg          REAL,
    waist_cm           REAL,
    fasting_glucose    REAL,            -- mg/dL
    post_meal_glucose  REAL,            -- mg/dL
    post_meal_label    TEXT,            -- which meal (e.g. "Lunch")
    hba1c_pct          REAL,
    ketones            REAL,
    notes              TEXT,
    created_at  REAL NOT NULL
);
"""

_READING_FIELDS = [
    "weight_kg", "waist_cm", "fasting_glucose", "post_meal_glucose",
    "post_meal_label", "hba1c_pct", "ketones", "notes",
]


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init(db_path: Path = DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)


def set_snapshot(name: str, payload: dict[str, Any], db_path: Path = DB_PATH) -> None:
    init(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO snapshots (name, payload, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET payload=excluded.payload, "
            "updated_at=excluded.updated_at",
            (name, json.dumps(payload), time.time()),
        )
        conn.commit()


def get_snapshot(name: str, db_path: Path = DB_PATH) -> Optional[dict[str, Any]]:
    """Return {'payload': ..., 'updated_at': float} or None if never built."""
    init(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT payload, updated_at FROM snapshots WHERE name = ?", (name,)
        ).fetchone()
    if row is None:
        return None
    return {"payload": json.loads(row["payload"]), "updated_at": row["updated_at"]}


def set_meta(key: str, value: str, db_path: Path = DB_PATH) -> None:
    init(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()


def get_meta(key: str, default: Optional[str] = None, db_path: Path = DB_PATH) -> Optional[str]:
    init(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


# ── Health readings (logged from the phone form) ─────────────────────────────
def add_reading(data: dict[str, Any], db_path: Path = DB_PATH) -> int:
    """Insert one health reading. `data` may include date + any of _READING_FIELDS."""
    init(db_path)
    date = str(data.get("date") or "")[:10]
    vals = [data.get(f) for f in _READING_FIELDS]
    with _connect(db_path) as conn:
        cur = conn.execute(
            f"INSERT INTO health_readings (date, {', '.join(_READING_FIELDS)}, created_at) "
            f"VALUES (?, {', '.join(['?'] * len(_READING_FIELDS))}, ?)",
            (date, *vals, time.time()),
        )
        conn.commit()
        return cur.lastrowid


def recent_readings(limit: int = 30, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    init(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM health_readings ORDER BY date DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def latest_reading(field: str, db_path: Path = DB_PATH) -> Optional[dict[str, Any]]:
    """Most recent non-null value for one field, with its date."""
    if field not in _READING_FIELDS:
        return None
    init(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            f"SELECT {field} AS value, date FROM health_readings "
            f"WHERE {field} IS NOT NULL ORDER BY date DESC, id DESC LIMIT 1"
        ).fetchone()
    return {"value": row["value"], "date": row["date"]} if row else None
