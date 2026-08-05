# AI Desktop Automation Agent POC

This project is a lightweight proof of concept for an AI-powered Windows desktop automation agent. Instead of running predefined scripts, it continuously observes the screen, asks an OpenRouter vision model what to do next, executes one desktop action, and repeats until the goal is complete.

It is intentionally small and easy to understand. It is not production automation software.

## Architecture

```text
Natural Language / Guided Input / Test File
   |
   v
Standard Test Case
   |
   v
Take Screenshot with mss
   |
   v
OpenRouter Vision Planner
   |
   v
Return ONE JSON Action
   |
   v
pyautogui Executor
   |
   v
Take Next Screenshot and Repeat
```

## Features

- Vision-language planning through OpenRouter
- Screenshot capture with `mss`
- Optional OCR context with `pytesseract`
- Desktop actions with `pyautogui`
- Iterative observe-plan-act loop
- Natural language, guided, structured file, and document-based test inputs
- PASS / FAIL / BLOCKED QA results
- Per-run screenshots, logs, and Markdown reports
- JSON-only action protocol
- Action history sent back to the planner to reduce loops
- Session logging in `logs/session.log`
- Extensible target lookup interface with a Windows UI Automation first pass

## Supported Actions

```json
{"action":"click","x":123,"y":456,"target":"Add Model"}
{"action":"double_click","x":123,"y":456,"target":"File"}
{"action":"right_click","x":123,"y":456,"target":"Item"}
{"action":"type","text":"Adventure Cycle"}
{"action":"press_key","key":"enter"}
{"action":"hotkey","keys":["ctrl","l"]}
{"action":"open_url","url":"https://www.google.com"}
{"action":"assert_visible","target":"OpenRouter"}
{"action":"assert_not_visible","target":"error"}
{"action":"scroll","amount":-5}
{"action":"wait","seconds":2}
{"action":"done"}
```

Click actions work best when the model returns both `target` and `x`/`y` coordinates. When a text `target` is present, the executor first tries Windows UI Automation to find the exact visible element, then falls back to model coordinates. OpenCV template matching or OCR can be plugged into the same locator interface later.

## Installation

Use Python 3.10 or newer.

```bash
cd desktop_agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## OpenRouter API Key

1. Open OpenRouter.
2. Create an API key.
3. Copy `.env.example` to `.env`.
4. Add your key and preferred vision model:

```text
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=google/gemini-2.5-flash
```

The key is loaded from `.env` and is never hardcoded. You can change `OPENROUTER_MODEL` to any OpenRouter model that supports image inputs.

If you see `402 Payment Required`, OpenRouter is saying the account or API key
cannot pay for the selected model. Add credits, remove any key spending cap, or
choose a free vision-capable model from OpenRouter's model list.

## Running

GUI mode:

```bash
python gui.py
```

The GUI supports three input modes:

- Natural Language: describe the test and let the model generate a test case.
- Guided Builder: fill in name, start URL, objective, and expected result.
- Structured File: load `.json`, `.yaml`, `.yml`, `.txt`, `.md`, or `.pdf`.

CLI mode:

```bash
python main.py
```

You can enter a plain request:

```text
Open Google and search for OpenRouter. Verify that OpenRouter appears in the results.
```

Or pass a structured file path:

```text
tests/google_search.json
```

Enter a goal such as:

```text
Open Notepad and type a short shopping list.
```

Website example:

```text
Open google.com and search for OpenRouter vision models.
```

The agent will repeatedly:

1. Capture the screen.
2. Send the screenshot, user goal, and recent action history to OpenRouter.
3. Receive one JSON action.
4. Execute the action.
5. Continue until the planner returns `{"action":"done"}`.

## Runtime Files

- Screenshots are saved in `screenshots/`.
- Logs are written to `logs/session.log`.
- QA runs are saved in `runs/<test_name_timestamp>/`.
- Each QA run includes `screenshots/`, `session.log`, and `report.md`.
- The latest report is copied to `runs/latest_report.md`.

## Structured Test Format

```json
{
  "id": "GOOGLE_SEARCH_001",
  "name": "Google Search Smoke Test",
  "start_url": "https://www.google.com",
  "goal": "Search Google for OpenRouter and verify that relevant results appear.",
  "steps": [
    "Open https://www.google.com",
    "Search for OpenRouter",
    "Wait until the results page loads"
  ],
  "expected_results": [
    "OpenRouter"
  ]
}
```

## OCR

OCR is optional. The Python package `pytesseract` is included in
`requirements.txt`, but it also needs the Tesseract OCR application installed on
Windows. If Tesseract is missing, the agent still works from screenshots; it
just skips OCR-backed assertion evidence.

Install Tesseract on Windows with one of these:

```powershell
winget install UB-Mannheim.TesseractOCR
```

or download the Windows installer from the UB Mannheim Tesseract builds page.
After installation, close and reopen PowerShell or VS Code so PATH refreshes.

Check that OCR is available:

```powershell
tesseract --version
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

## Safety Notes

- `pyautogui.FAILSAFE` is enabled. Move the mouse to the top-left corner to abort.
- The GUI Stop button stops at the next safe checkpoint. It cannot interrupt an in-flight API request instantly.
- Start with harmless apps such as Notepad or Calculator.
- Watch the agent while it runs. This is an impressive POC, not a secure unattended operator.

## Future Improvements

- Add stronger assertion evaluation for vague expected-result sentences.
- Add OCR fallback for apps that do not expose useful UI Automation metadata.
- Add a preview mode that asks before executing risky actions.
- Add structured error feedback from the executor back into the planner prompt.
- Add multi-monitor coordinate normalization.
