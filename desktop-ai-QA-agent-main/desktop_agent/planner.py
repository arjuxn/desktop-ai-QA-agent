"""OpenRouter-powered planning layer for the desktop automation loop."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import requests

from config import OPENROUTER_BASE_URL, PLANNER_MAX_RETRIES, PLANNER_RETRY_DELAY_SECONDS
from prompts import SYSTEM_PROMPT, TEST_CASE_GENERATION_PROMPT, USER_PROMPT_TEMPLATE
from test_case import TestCase, test_case_from_mapping
from utils import format_history, parse_json_object


SUPPORTED_ACTIONS = {
    "click",
    "type",
    "press_key",
    "wait",
    "double_click",
    "right_click",
    "scroll",
    "hotkey",
    "open_url",
    "assert_visible",
    "assert_not_visible",
    "done",
}


class PlannerError(RuntimeError):
    """Raised when the planner cannot produce a usable action."""


class PlannerConfigurationError(PlannerError):
    """Raised when credentials, billing, or permissions prevent planning."""


class OpenRouterPlanner:
    """Ask an OpenRouter vision model to choose the next desktop action."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self._api_key = api_key
        self._model_name = model_name

    def plan(
        self,
        goal: str,
        screenshot_path: Path,
        history: list[str],
        ocr_text: str = "",
    ) -> dict[str, Any]:
        """Return one validated action dictionary."""

        prompt = USER_PROMPT_TEMPLATE.format(
            goal=goal,
            history=format_history(history),
            ocr_text=ocr_text or "No OCR text available.",
        )
        image_data_url = _image_to_data_url(screenshot_path)

        last_error: Exception | None = None
        for attempt in range(1, PLANNER_MAX_RETRIES + 1):
            response: requests.Response | None = None
            try:
                response = requests.post(
                    OPENROUTER_BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "X-OpenRouter-Title": "AI Desktop Automation Agent POC",
                    },
                    json={
                        "model": self._model_name,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": image_data_url},
                                    },
                                ],
                            },
                        ],
                        "temperature": 0.1,
                    },
                    timeout=90,
                )
                _raise_for_non_retryable_http_error(response)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return validate_action(parse_json_object(content or ""))
            except PlannerConfigurationError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < PLANNER_MAX_RETRIES:
                    time.sleep(_retry_delay(response))

        raise PlannerError(f"OpenRouter did not return a valid action: {last_error}") from last_error

    def generate_test_case(self, request_text: str) -> TestCase:
        """Convert a natural-language QA request into a structured test case."""

        last_error: Exception | None = None
        for attempt in range(1, PLANNER_MAX_RETRIES + 1):
            response: requests.Response | None = None
            try:
                response = requests.post(
                    OPENROUTER_BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "X-OpenRouter-Title": "AI QA Test Case Generator",
                    },
                    json={
                        "model": self._model_name,
                        "messages": [
                            {"role": "system", "content": TEST_CASE_GENERATION_PROMPT},
                            {"role": "user", "content": request_text},
                        ],
                        "temperature": 0.2,
                    },
                    timeout=60,
                )
                _raise_for_non_retryable_http_error(response)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                generated = parse_json_object(content or "")
                return test_case_from_mapping(generated, "generated_from_natural_language")
            except PlannerConfigurationError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < PLANNER_MAX_RETRIES:
                    time.sleep(_retry_delay(response))

        raise PlannerError(f"OpenRouter did not generate a valid test case: {last_error}") from last_error


def _image_to_data_url(path: Path) -> str:
    """Convert a screenshot to a base64 data URL for OpenRouter vision input."""

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _retry_delay(response: requests.Response | None) -> float:
    """Use Retry-After when present, otherwise fall back to a small fixed delay."""

    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), PLANNER_RETRY_DELAY_SECONDS)
            except ValueError:
                pass
    return PLANNER_RETRY_DELAY_SECONDS


def _raise_for_non_retryable_http_error(response: requests.Response) -> None:
    """Fail fast for OpenRouter errors that retries will not fix."""

    if response.status_code not in {401, 402, 403, 404}:
        return

    message = _extract_error_message(response)
    if response.status_code == 401:
        hint = "Check that OPENROUTER_API_KEY is correct in desktop_agent/.env."
    elif response.status_code == 402:
        hint = (
            "OpenRouter says this account or API key has insufficient credits. "
            "Add credits, remove the key spending cap, or switch OPENROUTER_MODEL "
            "to a free vision-capable model available to your account."
        )
    elif response.status_code == 403:
        hint = "The API key does not have permission for this request or model."
    else:
        hint = "The configured OPENROUTER_MODEL was not found or is unavailable."

    raise PlannerConfigurationError(
        f"OpenRouter HTTP {response.status_code}: {message} {hint}"
    )


def _extract_error_message(response: requests.Response) -> str:
    """Return OpenRouter's error message without exposing credentials."""

    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()

    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message", "")).strip()
    return str(payload).strip()


def validate_action(action: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a planner action."""

    raw_name = str(action.get("action", "")).strip().lower()
    if raw_name not in SUPPORTED_ACTIONS:
        raise ValueError(f"Unsupported action: {raw_name!r}")

    normalized = dict(action)
    normalized["action"] = raw_name

    if raw_name in {"click", "double_click", "right_click"}:
        has_coordinates = "x" in normalized and "y" in normalized
        has_target = bool(normalized.get("target"))
        if not has_coordinates and not has_target:
            raise ValueError(f"{raw_name} requires x/y coordinates or a target.")
        if has_coordinates:
            normalized["x"] = int(normalized["x"])
            normalized["y"] = int(normalized["y"])

    if raw_name == "type" and "text" not in normalized:
        raise ValueError("type requires a text field.")

    if raw_name == "press_key" and "key" not in normalized:
        raise ValueError("press_key requires a key field.")

    if raw_name == "wait":
        normalized["seconds"] = float(normalized.get("seconds", 1))

    if raw_name == "scroll":
        normalized["amount"] = int(normalized.get("amount", -5))

    if raw_name == "hotkey":
        keys = normalized.get("keys")
        if not isinstance(keys, list) or not keys:
            raise ValueError("hotkey requires a non-empty keys list.")
        normalized["keys"] = [str(key).strip().lower() for key in keys]

    if raw_name == "open_url":
        url = str(normalized.get("url", "")).strip()
        if not url:
            raise ValueError("open_url requires a url field.")
        normalized["url"] = url

    if raw_name in {"assert_visible", "assert_not_visible"}:
        target = str(normalized.get("target", "")).strip()
        if not target:
            raise ValueError(f"{raw_name} requires a target field.")
        normalized["target"] = target

    return normalized
