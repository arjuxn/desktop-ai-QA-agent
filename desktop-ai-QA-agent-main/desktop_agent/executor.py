"""Action execution layer backed by pyautogui."""

from __future__ import annotations

import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pyautogui

from config import DEFAULT_WAIT_SECONDS


class ActionExecutionError(RuntimeError):
    """Raised when an action cannot be executed."""


@dataclass(frozen=True)
class Point:
    """Screen coordinate."""

    x: int
    y: int


class TargetLocator(Protocol):
    """Interface for pluggable target location strategies."""

    def find_target(self, target: str, screenshot_path: Path | None = None) -> Point | None:
        """Return the center point for a visible target, if found."""


class WindowsUiAutomationLocator:
    """Locate visible controls by name with Windows UI Automation."""

    def find_target(self, target: str, screenshot_path: Path | None = None) -> Point | None:
        try:
            from pywinauto import Desktop
        except ImportError:
            return None

        normalized_target = target.strip().lower()
        if not normalized_target or _is_icon_target(normalized_target):
            return None

        try:
            desktop = Desktop(backend="uia")
            candidates = desktop.descendants(title=target)
            if not candidates:
                candidates = [
                    element
                    for element in desktop.descendants()
                    if normalized_target in str(element.window_text()).strip().lower()
                ]

            for element in candidates:
                rectangle = element.rectangle()
                if rectangle.width() <= 0 or rectangle.height() <= 0:
                    continue
                return Point(
                    x=int((rectangle.left + rectangle.right) / 2),
                    y=int((rectangle.top + rectangle.bottom) / 2),
                )
        except Exception:
            return None

        return None


def _is_icon_target(target: str) -> bool:
    """Check if the target label describes a visual icon rather than literal text."""
    lowered = target.lower()
    return any(keyword in lowered for keyword in ["icon", "avatar", "glyph", "profile icon", "search icon"])


class DesktopExecutor:
    """Execute planner actions on the Windows desktop."""

    def __init__(self, locator: TargetLocator | None = None, pause: float = 0.2) -> None:
        self._locator = locator or WindowsUiAutomationLocator()
        pyautogui.PAUSE = pause
        pyautogui.FAILSAFE = True

    def execute(self, action: dict[str, Any], screenshot_path: Path | None = None) -> str:
        """Execute one normalized action and return a history description."""

        kind = str(action["action"]).lower()

        if kind == "done":
            return "Completed goal"

        if kind in ("click", "double_click", "right_click"):
            point = self._resolve_point(action, screenshot_path)
            if kind == "click":
                pyautogui.click(point.x, point.y)
                past_tense = "Clicked"
            elif kind == "double_click":
                pyautogui.doubleClick(point.x, point.y)
                past_tense = "Double-clicked"
            else:
                pyautogui.rightClick(point.x, point.y)
                past_tense = "Right-clicked"

            time.sleep(1.0)  # Allow dropdown menus / overlays time to animate & open
            return self._describe_pointer_action(past_tense, action, point)

        if kind == "type":
            text = str(action.get("text", ""))
            pyautogui.write(text, interval=0.01)
            return f"Typed {text!r}"

        if kind == "press_key":
            key = str(action.get("key", "")).lower()
            pyautogui.press(key)
            return f"Pressed {key}"

        if kind == "wait":
            seconds = float(action.get("seconds", DEFAULT_WAIT_SECONDS))
            time.sleep(max(0.0, seconds))
            return f"Waited {seconds:g} seconds"

        if kind == "scroll":
            amount = int(action.get("amount", -5))
            pyautogui.scroll(amount)
            return f"Scrolled {amount}"

        if kind == "hotkey":
            keys = [str(key).lower() for key in action.get("keys", [])]
            if not keys:
                raise ActionExecutionError("hotkey requires a non-empty keys list.")
            pyautogui.hotkey(*keys)
            return f"Pressed hotkey {'+'.join(keys)}"

        if kind == "open_url":
            url = str(action.get("url", "")).strip()
            if not url:
                raise ActionExecutionError("open_url requires a url field.")
            webbrowser.open(url)
            time.sleep(2.0)  # Allow page time to load in browser
            return f"Opened URL {url}"

        raise ActionExecutionError(f"Unsupported action: {kind}")

    def _resolve_point(self, action: dict[str, Any], screenshot_path: Path | None) -> Point:
        """Resolve target using text locator first (for text labels), falling back to visual coordinates."""

        target = str(action.get("target", "")).strip()

        # 1. If text target (not an icon label), try locator first
        if target and not _is_icon_target(target):
            point = self._locator.find_target(target, screenshot_path)
            if point:
                return point

        # 2. Fall back to VLM visual coordinates (x, y)
        if "x" in action and "y" in action:
            return Point(int(action["x"]), int(action["y"]))

        # 3. Last resort attempt for any text target if x,y wasn't passed
        if target:
            point = self._locator.find_target(target, screenshot_path)
            if point:
                return point

        raise ActionExecutionError(
            f"Click action for {target!r} could not be resolved (no valid coordinates or text match found)."
        )

    @staticmethod
    def _describe_pointer_action(prefix: str, action: dict[str, Any], point: Point) -> str:
        target = action.get("target")
        if target:
            return f"{prefix} {target!r} at ({point.x}, {point.y})"
        return f"{prefix} at ({point.x}, {point.y})"
