"""Entry point for the AI-powered desktop automation POC."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from config import MAX_ITERATIONS, ensure_directories, load_api_key, load_model_name
from executor import ActionExecutionError, DesktopExecutor
from planner import OpenRouterPlanner, PlannerConfigurationError, PlannerError
from screen import ScreenshotError, capture_screenshot
from test_case import goal_to_test_case, load_test_case
from utils import clean_old_session_log, describe_action, setup_logging
from runner import run_test_case


LogCallback = Callable[[str], None]


def run_agent(
    goal: str,
    stop_event: Event | None = None,
    log_callback: LogCallback | None = None,
) -> None:
    """Run the observe-plan-act loop until the planner returns DONE."""

    ensure_directories()
    clean_old_session_log()
    logger = setup_logging()

    def log(message: str = "") -> None:
        """Write a line to the session log, console, and optional GUI."""

        logger.info(message)
        if log_callback:
            log_callback(message)

    planner = OpenRouterPlanner(api_key=load_api_key(), model_name=load_model_name())
    executor = DesktopExecutor()
    history: list[str] = []

    log("Desktop Agent started")
    log(f"Goal: {goal}")

    for iteration in range(1, MAX_ITERATIONS + 1):
        if stop_event and stop_event.is_set():
            log("Stopped by user.")
            return

        log("")
        log("---")
        log(f"Iteration {iteration}")
        log(f"Goal: {goal}")

        try:
            screenshot_path = capture_screenshot()
            log(f"Observation: captured {screenshot_path.name}")
        except ScreenshotError as exc:
            log(f"Screenshot error: {exc}")
            history.append(f"Screenshot failed: {exc}")
            continue

        try:
            action = planner.plan(goal, screenshot_path, history)
            log(f"Action: {describe_action(action)}")
        except PlannerConfigurationError as exc:
            log(f"Planner configuration error: {exc}")
            log("Stopping because retrying will not fix this provider/account issue.")
            return
        except PlannerError as exc:
            log(f"Planner error: {exc}")
            history.append(f"Planner failed: {exc}")
            continue

        if stop_event and stop_event.is_set():
            log("Stopped by user before executing the next action.")
            return

        if action["action"] == "done":
            log("Completed")
            history.append("AI returned DONE")
            return

        log("Executing...")
        try:
            result = executor.execute(action, screenshot_path)
            history.append(result)
            log(result)
            log("Completed")
        except ActionExecutionError as exc:
            log(f"Execution error: {exc}")
            history.append(f"Execution failed for {describe_action(action)}: {exc}")

    log("")
    log(f"Stopped after reaching MAX_ITERATIONS={MAX_ITERATIONS}.")


def main() -> None:
    """Ask for a user goal or test file and start the QA runner."""

    print("AI QA Desktop Automation Agent")
    print("Move your mouse to the top-left corner to trigger pyautogui failsafe.")
    user_input = input("Enter a test goal or path to a JSON/YAML/TXT/MD/PDF test file: ").strip()
    if not user_input:
        print("No test provided. Exiting.")
        return

    candidate = Path(user_input)
    if candidate.exists():
        test_case = load_test_case(candidate)
    else:
        planner = OpenRouterPlanner(api_key=load_api_key(), model_name=load_model_name())
        try:
            test_case = planner.generate_test_case(user_input)
        except PlannerConfigurationError:
            raise
        except PlannerError:
            test_case = goal_to_test_case(user_input)

    result = run_test_case(test_case)
    print(f"Final status: {result.status}")
    print(f"Reason: {result.reason}")
    if result.report_path:
        print(f"Report: {result.report_path}")


if __name__ == "__main__":
    main()
