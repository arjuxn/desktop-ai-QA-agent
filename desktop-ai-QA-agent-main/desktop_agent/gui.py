"""Tkinter GUI for the AI desktop automation POC."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from config import load_api_key, load_model_name
from planner import OpenRouterPlanner, PlannerConfigurationError, PlannerError
from runner import run_test_case
from test_case import TestCase, guided_to_test_case, goal_to_test_case, load_test_case


class DesktopAgentGui:
    """Small GUI wrapper around the agent loop."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AI Desktop Automation Agent")
        self.root.geometry("820x560")
        self.root.minsize(700, 460)

        self._messages: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None

        self._build_ui()
        self._poll_messages()

    def _build_ui(self) -> None:
        """Create the GUI controls."""

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(4, weight=1)

        header = ttk.Frame(self.root, padding=(14, 12, 14, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(
            header,
            text="AI Desktop Automation Agent",
            font=("Segoe UI", 15, "bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(
            header,
            text="Create a QA test from natural language, guided fields, or a structured file.",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        mode_frame = ttk.Frame(self.root, padding=(14, 4, 14, 4))
        mode_frame.grid(row=1, column=0, sticky="ew")
        mode_frame.columnconfigure(1, weight=1)

        ttk.Label(mode_frame, text="Input mode").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.input_mode = tk.StringVar(value="Natural Language")
        self.mode_combo = ttk.Combobox(
            mode_frame,
            textvariable=self.input_mode,
            values=["Natural Language", "Guided Builder", "Structured File"],
            state="readonly",
            width=22,
        )
        self.mode_combo.grid(row=0, column=1, sticky="w")
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_input_mode())

        self.goal_var = tk.StringVar()
        self.name_var = tk.StringVar(value="Google Search Smoke Test")
        self.url_var = tk.StringVar(value="https://www.google.com")
        self.expected_var = tk.StringVar(value="Search results are visible")
        self.file_var = tk.StringVar()

        self.input_container = ttk.Frame(self.root, padding=(14, 4, 14, 10))
        self.input_container.grid(row=2, column=0, sticky="ew")
        self.input_container.columnconfigure(1, weight=1)

        button_bar = ttk.Frame(self.root, padding=(14, 0, 14, 10))
        button_bar.grid(row=3, column=0, sticky="ew")
        button_bar.columnconfigure(0, weight=1)

        self.start_button = ttk.Button(button_bar, text="Start", command=self.start_agent)
        self.start_button.grid(row=0, column=1, padx=(0, 8))

        self.stop_button = ttk.Button(
            button_bar,
            text="Stop",
            command=self.stop_agent,
            state=tk.DISABLED,
        )
        self.stop_button.grid(row=0, column=2)

        log_frame = ttk.Frame(self.root, padding=(14, 0, 14, 8))
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            height=18,
            font=("Consolas", 10),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state=tk.DISABLED)

        footer = ttk.Frame(self.root, padding=(14, 0, 14, 12))
        footer.grid(row=5, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(footer, textvariable=self.status_var)
        status.grid(row=0, column=0, sticky="w")

        safety = ttk.Label(
            footer,
            text="Failsafe: move the mouse to the top-left corner to abort pyautogui.",
        )
        safety.grid(row=0, column=1, sticky="e")

        self._update_input_mode()

    def start_agent(self) -> None:
        """Start the agent worker thread."""

        if self._worker and self._worker.is_alive():
            return

        try:
            test_case = self._build_test_case()
        except Exception as exc:
            messagebox.showwarning("Invalid test input", str(exc))
            return

        self._clear_log()
        self._stop_event.clear()
        self._set_running(True)
        self._append_log("Starting agent...")

        self._worker = threading.Thread(
            target=self._run_worker,
            args=(test_case,),
            daemon=True,
        )
        self._worker.start()

    def stop_agent(self) -> None:
        """Ask the running worker to stop at the next safe checkpoint."""

        self._stop_event.set()
        self.status_var.set("Stopping after the current step...")
        self.stop_button.configure(state=tk.DISABLED)

    def _run_worker(self, test_case: TestCase) -> None:
        """Run the agent and report completion back to the GUI thread."""

        try:
            run_test_case(test_case, stop_event=self._stop_event, log_callback=self._messages.put)
        except Exception as exc:
            self._messages.put(f"Fatal error: {exc}")
        finally:
            self._messages.put("__AGENT_FINISHED__")

    def _poll_messages(self) -> None:
        """Move worker-thread log lines into the Tkinter text widget."""

        while True:
            try:
                message = self._messages.get_nowait()
            except queue.Empty:
                break

            if message == "__AGENT_FINISHED__":
                self._set_running(False)
            else:
                self._append_log(message)

        self.root.after(100, self._poll_messages)

    def _append_log(self, message: str) -> None:
        """Append a line to the log viewer."""

        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        """Clear the visible log."""

        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_running(self, running: bool) -> None:
        """Update controls for running or idle state."""

        self.start_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_button.configure(state=tk.NORMAL if running else tk.DISABLED)
        self.mode_combo.configure(state=tk.DISABLED if running else "readonly")
        self.status_var.set("Running" if running else "Ready")

    def _update_input_mode(self) -> None:
        """Swap visible input controls for the selected mode."""

        for child in self.input_container.winfo_children():
            child.destroy()

        mode = self.input_mode.get()
        if mode == "Natural Language":
            ttk.Label(self.input_container, text="Test request").grid(row=0, column=0, sticky="nw", padx=(0, 8))
            self.goal_entry = ttk.Entry(self.input_container, textvariable=self.goal_var)
            self.goal_entry.grid(row=0, column=1, sticky="ew")
            self.goal_entry.bind("<Return>", lambda _event: self.start_agent())
            self.goal_entry.focus_set()
            return

        if mode == "Guided Builder":
            fields = [
                ("Name", self.name_var),
                ("Website / start URL", self.url_var),
                ("What to test", self.goal_var),
                ("Expected result", self.expected_var),
            ]
            for row, (label, variable) in enumerate(fields):
                ttk.Label(self.input_container, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
                ttk.Entry(self.input_container, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=2)
            return

        ttk.Label(self.input_container, text="Test file").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(self.input_container, textvariable=self.file_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(self.input_container, text="Browse", command=self._browse_file).grid(row=0, column=2, padx=(8, 0))

    def _browse_file(self) -> None:
        """Pick a structured or document-based test input file."""

        path = filedialog.askopenfilename(
            title="Select test input",
            filetypes=[
                ("Test inputs", "*.json *.yaml *.yml *.txt *.md *.pdf"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.file_var.set(path)

    def _build_test_case(self) -> TestCase:
        """Create a TestCase from the selected GUI input mode."""

        mode = self.input_mode.get()
        if mode == "Natural Language":
            request = self.goal_var.get().strip()
            if not request:
                raise ValueError("Enter a natural-language test request.")
            planner = OpenRouterPlanner(api_key=load_api_key(), model_name=load_model_name())
            try:
                return planner.generate_test_case(request)
            except PlannerConfigurationError:
                raise
            except PlannerError:
                return goal_to_test_case(request)

        if mode == "Guided Builder":
            return guided_to_test_case(
                self.name_var.get(),
                self.url_var.get(),
                self.goal_var.get(),
                self.expected_var.get(),
            )

        file_path = self.file_var.get().strip()
        if not file_path:
            raise ValueError("Choose a test input file.")
        return load_test_case(Path(file_path))


def main() -> None:
    """Start the Tkinter app."""

    root = tk.Tk()
    DesktopAgentGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
