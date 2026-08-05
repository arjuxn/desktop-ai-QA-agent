"""QA test runner, assertions, run folders, and report generation."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any

from config import MAX_ITERATIONS, RUNS_DIR, ensure_directories, load_api_key, load_model_name
from executor import ActionExecutionError, DesktopExecutor
from ocr import extract_screen_text
from planner import OpenRouterPlanner, PlannerConfigurationError, PlannerError
from screen import ScreenshotError, capture_screenshot
from test_case import TestCase
from utils import describe_action, setup_logging, timestamp


LogCallback = Callable[[str], None]


@dataclass
class TestRunResult:
    """Final result for one QA execution."""

    status: str = "BLOCKED"
    reason: str = ""
    actions: list[str] = field(default_factory=list)
    screenshots: list[Path] = field(default_factory=list)
    report_path: Path | None = None


def run_test_case(
    test_case: TestCase,
    stop_event: Event | None = None,
    log_callback: LogCallback | None = None,
) -> TestRunResult:
    """Run a structured QA test case with the visual desktop agent."""

    ensure_directories()
    run_dir = RUNS_DIR / f"{test_case.safe_name}_{timestamp()}"
    screenshot_dir = run_dir / "screenshots"
    run_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(run_dir / "session.log")
    result = TestRunResult()

    def log(message: str = "") -> None:
        logger.info(message)
        if log_callback:
            log_callback(message)

    planner = OpenRouterPlanner(api_key=load_api_key(), model_name=load_model_name())
    executor = DesktopExecutor()
    history: list[str] = []
    current_step_index = 0
    started_at = time.time()

    log("AI QA Test Runner started")
    log(f"Test: {test_case.name}")
    log(f"Source: {test_case.source}")
    log(f"Goal: {test_case.goal}")

    for iteration in range(1, MAX_ITERATIONS + 1):
        if stop_event and stop_event.is_set():
            result.status = "BLOCKED"
            result.reason = "Stopped by user."
            break

        log("")
        log("---")
        log(f"Iteration {iteration}")
        log(f"Step {min(current_step_index + 1, len(test_case.steps) or 1)}")

        try:
            screenshot_path = capture_screenshot(screenshot_dir)
            result.screenshots.append(screenshot_path)
            log(f"Observation: captured {screenshot_path.name}")
        except ScreenshotError as exc:
            history.append(f"Screenshot failed: {exc}")
            log(f"Screenshot error: {exc}")
            continue

        ocr_text, ocr_status = extract_screen_text(screenshot_path)
        log(ocr_status)

        planner_goal = test_case.to_prompt(current_step_index)
        try:
            action = planner.plan(
                planner_goal,
                screenshot_path,
                history,
                ocr_text=ocr_text,
            )
            log(f"Action: {describe_action(action)}")
        except PlannerConfigurationError as exc:
            result.status = "BLOCKED"
            result.reason = str(exc)
            log(f"Planner configuration error: {exc}")
            break
        except PlannerError as exc:
            history.append(f"Planner failed: {exc}")
            log(f"Planner error: {exc}")
            continue

        if action["action"] in {"assert_visible", "assert_not_visible"}:
            assertion_status, assertion_message = evaluate_assertion(action, ocr_text)
            history.append(assertion_message)
            result.actions.append(assertion_message)
            log(assertion_message)
            if assertion_status == "PASS":
                current_step_index += 1
                if _all_steps_done(test_case, current_step_index):
                    result.status = "PASS"
                    result.reason = "All expected results were verified."
                    break
                continue
            result.status = "FAIL"
            result.reason = assertion_message
            break

        if action["action"] == "done":
            final_status, final_reason = evaluate_expected_results(test_case, ocr_text)
            result.status = final_status
            result.reason = final_reason
            log(f"Final status: {result.status}")
            log(f"Reason: {result.reason}")
            break

        if stop_event and stop_event.is_set():
            result.status = "BLOCKED"
            result.reason = "Stopped by user before executing the next action."
            break

        log("Executing...")
        try:
            action_result = executor.execute(action, screenshot_path)
            history.append(action_result)
            result.actions.append(action_result)
            log(action_result)
            if _step_appears_complete(test_case, current_step_index, action_result):
                current_step_index += 1
        except ActionExecutionError as exc:
            failure = f"Execution failed for {describe_action(action)}: {exc}"
            history.append(failure)
            result.actions.append(failure)
            log(failure)

    else:
        result.status = "BLOCKED"
        result.reason = f"Reached MAX_ITERATIONS={MAX_ITERATIONS}."

    if not result.reason:
        result.reason = "Test ended without a detailed reason."

    result.report_path = write_report(test_case, result, run_dir, time.time() - started_at)
    log("")
    log(f"Report: {result.report_path}")
    copy_latest_report(result.report_path)
    return result


def evaluate_assertion(action: dict[str, Any], ocr_text: str) -> tuple[str, str]:
    """Evaluate simple OCR-backed visibility assertions."""

    target = str(action.get("target", "")).strip()
    visible = target.lower() in ocr_text.lower()
    if action["action"] == "assert_visible":
        if visible:
            return "PASS", f"Assertion passed: {target!r} is visible."
        return "FAIL", f"Assertion failed: {target!r} was not found in OCR text."

    if not visible:
        return "PASS", f"Assertion passed: {target!r} is not visible."
    return "FAIL", f"Assertion failed: {target!r} is visible."


def evaluate_expected_results(test_case: TestCase, ocr_text: str) -> tuple[str, str]:
    """Evaluate final expected results using OCR text when possible."""

    if not test_case.expected_results:
        return "PASS", "Planner completed the test and no explicit assertions were provided."

    missing = [
        expected
        for expected in test_case.expected_results
        if _assertion_text(expected) not in ocr_text.lower()
    ]
    if not missing:
        return "PASS", "All expected result keywords were visible in OCR text."
    return (
        "BLOCKED",
        "Planner returned done, but OCR could not verify: " + "; ".join(missing),
    )


def write_report(
    test_case: TestCase,
    result: TestRunResult,
    run_dir: Path,
    duration_seconds: float,
) -> Path:
    """Write a Markdown QA execution report."""

    report_path = run_dir / "report.md"
    lines = [
        f"# {test_case.name}",
        "",
        f"Status: **{result.status}**",
        f"Duration: {duration_seconds:.1f} seconds",
        f"Source: {test_case.source}",
        "",
        "## Goal",
        test_case.goal,
        "",
        "## Steps",
    ]

    lines.extend(f"- {step}" for step in test_case.steps)
    lines.extend(["", "## Expected Results"])
    lines.extend(f"- {item}" for item in test_case.expected_results or ["Not specified"])
    lines.extend(["", "## Result Reason", result.reason, "", "## Actions"])
    lines.extend(f"- {action}" for action in result.actions or ["No actions executed"])
    lines.extend(["", "## Evidence"])
    lines.extend(
        f"- screenshots/{path.name}" for path in result.screenshots
    )
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def copy_latest_report(report_path: Path) -> None:
    """Keep a convenient pointer to the latest report."""

    latest = RUNS_DIR / "latest_report.md"
    try:
        shutil.copyfile(report_path, latest)
    except OSError:
        pass


def _all_steps_done(test_case: TestCase, current_step_index: int) -> bool:
    return current_step_index >= max(1, len(test_case.steps))


def _step_appears_complete(
    test_case: TestCase,
    current_step_index: int,
    action_result: str,
) -> bool:
    """Advance simple open-url steps after URL execution."""

    if current_step_index >= len(test_case.steps):
        return False
    current_step = test_case.steps[current_step_index].lower()
    normalized_result = action_result.lower()

    if current_step.startswith("open ") and normalized_result.startswith("opened url"):
        return True

    if "search" in current_step and "pressed enter" in normalized_result:
        return True

    if "click" in current_step and normalized_result.startswith("clicked"):
        return True

    if any(word in current_step for word in ["type", "enter", "fill"]):
        return normalized_result.startswith("typed") or "pressed enter" in normalized_result

    return False


def _assertion_text(expected: str) -> str:
    """Extract a rough keyword phrase from an expected-result sentence."""

    text = expected.lower()
    for prefix in ["visible", "appears", "contains", "shows", "is visible"]:
        text = text.replace(prefix, "")
    return " ".join(text.split()).strip()
