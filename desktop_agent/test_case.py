"""Standard QA test case representation and input loaders."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TestCase:
    """A normalized test case consumed by the Digital Human runner."""

    name: str
    goal: str
    steps: list[str] = field(default_factory=list)
    expected_results: list[str] = field(default_factory=list)
    start_url: str | None = None
    source: str = "manual"

    @property
    def safe_name(self) -> str:
        """Return a filesystem-safe test name."""

        slug = re.sub(r"[^a-zA-Z0-9]+", "_", self.name.strip()).strip("_").lower()
        return slug or "qa_test"

    def to_prompt(self, current_step_index: int) -> str:
        """Render the current test state for the planner."""

        steps = "\n".join(
            f"{index + 1}. {step}" for index, step in enumerate(self.steps)
        ) or "No explicit steps. Work toward the goal."
        expected = "\n".join(f"- {item}" for item in self.expected_results) or "- Goal is complete"
        current_step = (
            self.steps[current_step_index]
            if current_step_index < len(self.steps)
            else "Verify the expected result and finish the test."
        )
        start_url = self.start_url or "Not specified"

        return (
            f"Test name: {self.name}\n"
            f"Start URL: {start_url}\n"
            f"Goal: {self.goal}\n\n"
            f"Steps:\n{steps}\n\n"
            f"Current step: {current_step_index + 1}. {current_step}\n\n"
            f"Expected results:\n{expected}"
        )


def goal_to_test_case(goal: str) -> TestCase:
    """Wrap a plain natural-language goal as a minimal test case."""

    return TestCase(
        name="Natural Language Test",
        goal=goal,
        steps=[goal],
        expected_results=["The requested goal is visibly completed."],
        source="natural_language",
    )


def guided_to_test_case(
    name: str,
    start_url: str,
    objective: str,
    expected_result: str,
) -> TestCase:
    """Build a test case from simple guided form fields."""

    steps: list[str] = []
    if start_url.strip():
        steps.append(f"Open {start_url.strip()}")
    if objective.strip():
        steps.append(objective.strip())

    return TestCase(
        name=name.strip() or "Guided QA Test",
        goal=objective.strip() or expected_result.strip() or "Run the guided QA test.",
        steps=steps,
        expected_results=[expected_result.strip()] if expected_result.strip() else [],
        start_url=start_url.strip() or None,
        source="guided_builder",
    )


def load_test_case(path: Path) -> TestCase:
    """Load a structured test case from JSON, YAML, text, markdown, or PDF."""

    suffix = path.suffix.lower()
    if suffix == ".json":
        return test_case_from_mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    if suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("YAML test case must contain a mapping/object.")
        return test_case_from_mapping(data, str(path))
    if suffix in {".txt", ".md"}:
        return goal_to_test_case(path.read_text(encoding="utf-8").strip())
    if suffix == ".pdf":
        text = extract_pdf_text(path)
        return goal_to_test_case(text)
    raise ValueError(f"Unsupported test input file type: {suffix}")


def test_case_from_mapping(data: dict[str, Any], source: str = "structured") -> TestCase:
    """Create a test case from a dict-like structure."""

    name = str(data.get("name") or data.get("id") or "Structured QA Test")
    goal = str(data.get("goal") or data.get("objective") or name)
    steps = _string_list(data.get("steps", []))
    expected = _string_list(
        data.get("expected_results", data.get("expected_result", data.get("assertions", [])))
    )
    start_url = data.get("start_url") or data.get("url")

    if start_url and not any("open" in step.lower() for step in steps):
        steps.insert(0, f"Open {start_url}")

    return TestCase(
        name=name,
        goal=goal,
        steps=steps or [goal],
        expected_results=expected,
        start_url=str(start_url) if start_url else None,
        source=source,
    )


def extract_pdf_text(path: Path) -> str:
    """Extract text from a PDF for document-driven test generation."""

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Install pypdf to load PDF test descriptions.") from exc

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _string_list(value: Any) -> list[str]:
    """Normalize scalar/list values into a list of strings."""

    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
