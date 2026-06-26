"""Configuration loading.

Reads config/config.yaml. Secrets (the dVerse password) may be supplied via the
INSIGHT_DVERSE_PASSWORD environment variable instead of living in the file.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# Project layout: <root>/server/config.py  ->  root is two levels up.
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
KNOWLEDGE_DIR = ROOT / "knowledge"
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"

# knowledge/<name>.yaml is merged into config under the top-level key <name>.
KNOWLEDGE_FILES = ["projects", "fitness", "food", "house", "travel", "health"]

# Secrets store — a gitignored .env on the device (the local equivalent of a
# Vercel/Supabase env-var store). Loaded into the environment at startup, so a key
# set once here persists across restarts and is never typed in the browser again.
ENV_PATH = CONFIG_DIR / ".env"


def _load_env_file() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        # Real process env vars win over the file (e.g. systemd Environment=).
        os.environ.setdefault(key.strip(), val.strip())


_load_env_file()  # before anything reads os.environ below

CONFIG_PATH = Path(os.environ.get("INSIGHT_CONFIG", CONFIG_DIR / "config.yaml"))
DB_PATH = Path(os.environ.get("INSIGHT_DB", DATA_DIR / "insight.db"))


def load_config() -> dict[str, Any]:
    """Load config.yaml, applying env overrides for secrets.

    Falls back to config.example.yaml so a fresh checkout still runs.
    """
    path = CONFIG_PATH
    if not path.exists():
        example = CONFIG_DIR / "config.example.yaml"
        if example.exists():
            path = example
        else:
            raise FileNotFoundError(
                f"No config at {CONFIG_PATH} and no example to fall back to."
            )

    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    # The Life-screen domain lives in the editable knowledge base. Each
    # knowledge/<name>.yaml overrides cfg[<name>], so config.yaml stays focused
    # on server + dVerse, and the user edits human-friendly files in knowledge/.
    # A fresh checkout has no personal *.yaml (gitignored) — fall back to the
    # committed *.example.yaml so it runs out of the box.
    for name in KNOWLEDGE_FILES:
        kpath = KNOWLEDGE_DIR / f"{name}.yaml"
        if not kpath.exists():
            kpath = KNOWLEDGE_DIR / f"{name}.example.yaml"
        if kpath.exists():
            with open(kpath, "r", encoding="utf-8") as fh:
                cfg[name] = yaml.safe_load(fh) or {}

    cfg.setdefault("dverse", {})
    cfg.setdefault("projects", {})
    cfg.setdefault("fitness", {})
    cfg.setdefault("food", {})
    cfg.setdefault("travel", {})
    cfg.setdefault("house", {})
    cfg.setdefault("health", {})
    cfg.setdefault("server", {})

    # Secret precedence: env var > config file.
    env_pw = os.environ.get("INSIGHT_DVERSE_PASSWORD")
    if env_pw:
        cfg["dverse"]["password"] = env_pw

    return cfg


def set_env_secret(key: str, value: str) -> None:
    """Persist a secret to the gitignored config/.env (chmod 600) and apply it live.

    Upserts the KEY=value line, preserving other entries, then updates the running
    process's environment so the change takes effect without a restart.
    """
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    out, found = [], False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped \
                and stripped.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        ENV_PATH.chmod(0o600)
    except OSError:
        pass
    os.environ[key] = value


def server_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    s = cfg.get("server", {})
    return {
        "host": s.get("host", "0.0.0.0"),
        "port": int(s.get("port", 8080)),
        # How often the browser re-polls the JSON API (seconds).
        "refresh_seconds": int(s.get("refresh_seconds", 30)),
        # Seconds after which a snapshot is considered stale (shows the dot).
        "stale_after_seconds": int(s.get("stale_after_seconds", 26 * 3600)),
    }
