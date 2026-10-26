# AGENTS.md

## Scope
- All code lives in `desktop_agent/`. Run every command from there, not repo root.
- Windows-only POC: `pyautogui` + `pywinauto (uia)` + Tkinter GUI + `mss` screenshots. No CI, no lint, no test suite.

## Setup
```bash
cd desktop_agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
- `.env` needs `OPENROUTER_API_KEY` and vision-capable `OPENROUTER_MODEL` (default `google/gemini-2.5-flash` in `config.py`).
- Never commit `.env`, `runs/`, `screenshots/`, `logs/`.
- OCR is optional: `pip` package alone is not enough, needs Tesseract app on PATH or agent runs screenshot-only. Check with `tesseract --version`.

## Entrypoints
- `python gui.py` — Tkinter app, 3 modes: Natural Language / Guided Builder / Structured File (`.json/.yaml/.yml/.txt/.md/.pdf`).
- `python main.py` — CLI: enter goal text or path like `tests/google_search.json`, goes through `run_test_case()`.
- Real flow is `test_case.py -> screen.py -> planner.py -> executor.py -> runner.py`. `main.run_agent()` is a legacy simple loop; `runner.run_test_case()` is the QA path both GUI and CLI use.

## Loop & config (`config.py`)
- `MAX_ITERATIONS=30`, `PLANNER_MAX_RETRIES=3`, `SCREENSHOT_MONITOR_INDEX=1` (clamped, not multi-monitor normalized).
- Runtime outputs: `runs/<safe_name_timestamp>/` with `screenshots/`, `session.log`, `report.md`, plus `runs/latest_report.md` copy. Legacy `screenshots/` and `logs/session.log` (wiped each `run_agent` run).

## Planner / executor quirks
- Planner speaks OpenRouter vision, JSON-only single action. `SUPPORTED_ACTIONS` in `planner.py`: `click, double_click, right_click, type, press_key, hotkey, open_url, assert_visible, assert_not_visible, scroll, wait, done`.
- `PlannerConfigurationError` (HTTP 401/402/403/404: bad key, no credits, no permission, bad model) means stop — retrying won't help. Other `PlannerError`s retry.
- Click resolution order in `executor.HybridTargetLocator`: OCR exact text match on screenshot -> `pywinauto` UIA fallback -> model `x/y`. Targets containing `icon/avatar/glyph/profile icon/search icon` skip text lookup and use `x/y` directly. Always send both `target` + `x/y` for text buttons.
- Timing baked in: clicks sleep 1.0s, `open_url` sleeps 2.0s, `pyautogui.PAUSE=0.2`, `FAILSAFE=True`.

## Assertions are weak
- `runner.evaluate_assertion()` is substring match of `target` in OCR text. Final `evaluate_expected_results()` skips generic phrases (`completed`, `as expected`) and returns `PASS` ("Planner completed all test steps") even when keywords are missing. Write concrete, literal on-screen strings in `expected_results`.

## Safety
- Do NOT run `gui.py` / `main.py` / `run_test_case()` autonomously — it takes over mouse/keyboard. Prefer reading code and test files (`tests/google_search.json` is the minimal example).
- GUI Stop only stops at the next checkpoint, not mid-API-request. Mouse to top-left corner triggers pyautogui failsafe.
