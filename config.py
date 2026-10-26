"""Configuration for the desktop automation POC."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
LOGS_DIR = BASE_DIR / "logs"
RUNS_DIR = BASE_DIR / "runs"
SESSION_LOG_PATH = LOGS_DIR / "session.log"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL_NAME = "google/gemini-2.5-flash"
MAX_ITERATIONS = 30
PLANNER_MAX_RETRIES = 3
PLANNER_RETRY_DELAY_SECONDS = 2.0
DEFAULT_WAIT_SECONDS = 1.0
SCREENSHOT_MONITOR_INDEX = 1


def ensure_directories() -> None:
    """Create runtime directories used by the agent."""

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def load_api_key() -> str:
    """Load the OpenRouter API key from .env or the process environment."""

    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is missing. Create desktop_agent/.env from .env.example."
        )
    return api_key


def load_model_name() -> str:
    """Load the OpenRouter model slug, falling back to a vision-capable default."""

    load_dotenv(BASE_DIR / ".env")
    return os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME
