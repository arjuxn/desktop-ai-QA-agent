"""Shared utilities for logging, timestamps, and JSON handling."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from config import SESSION_LOG_PATH


LOGGER_NAME = "desktop_agent"


def timestamp() -> str:
    """Return a filesystem-friendly timestamp."""

    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def setup_logging(log_path: Path = SESSION_LOG_PATH) -> logging.Logger:
    """Configure console and file logging for a single agent session."""

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def parse_json_object(raw_text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating accidental markdown fences."""

    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("The planner returned JSON, but it was not an object.")
    return parsed


def format_history(history: list[str], limit: int = 12) -> str:
    """Render recent action history for the planner prompt."""

    if not history:
        return "No previous actions."
    recent = history[-limit:]
    return "\n".join(f"{index + 1}. {item}" for index, item in enumerate(recent))


def describe_action(action: dict[str, Any]) -> str:
    """Create a human-readable one-line description of an action."""

    kind = str(action.get("action", "")).upper()
    if kind in {"CLICK", "DOUBLE_CLICK", "RIGHT_CLICK"}:
        target = action.get("target") or f"({action.get('x')}, {action.get('y')})"
        return f"{kind} {target}"
    if kind == "TYPE":
        return f"TYPE {action.get('text', '')!r}"
    if kind == "PRESS_KEY":
        return f"PRESS_KEY {action.get('key', '')}"
    if kind == "WAIT":
        return f"WAIT {action.get('seconds', '')}s"
    if kind == "SCROLL":
        return f"SCROLL {action.get('amount', '')}"
    if kind == "HOTKEY":
        return f"HOTKEY {'+'.join(action.get('keys', []))}"
    if kind == "OPEN_URL":
        return f"OPEN_URL {action.get('url', '')}"
    if kind in {"ASSERT_VISIBLE", "ASSERT_NOT_VISIBLE"}:
        return f"{kind} {action.get('target', '')}"
    return kind


def clean_old_session_log(path: Path = SESSION_LOG_PATH) -> None:
    """Start each run with a fresh session log."""

    if path.exists():
        path.unlink()
