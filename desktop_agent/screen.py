"""Screenshot capture utilities."""

from __future__ import annotations

from pathlib import Path

import mss
from PIL import Image

from config import SCREENSHOT_MONITOR_INDEX, SCREENSHOTS_DIR
from utils import timestamp


class ScreenshotError(RuntimeError):
    """Raised when the screen cannot be captured."""


def capture_screenshot(output_dir: Path = SCREENSHOTS_DIR) -> Path:
    """Capture the current desktop screen and save it as a PNG file."""

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with mss.mss() as sct:
            monitor_index = min(SCREENSHOT_MONITOR_INDEX, len(sct.monitors) - 1)
            monitor = sct.monitors[monitor_index]
            raw = sct.grab(monitor)
            image = Image.frombytes("RGB", raw.size, raw.rgb)

        path = output_dir / f"screenshot_{timestamp()}.png"
        image.save(path)
        return path
    except Exception as exc:
        raise ScreenshotError(f"Failed to capture screenshot: {exc}") from exc
