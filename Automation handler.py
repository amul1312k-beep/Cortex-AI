"""
Cortex AI — Automation Handler
The workflow engine for Cortex AI.
Handles multi-step routines, scheduled tasks, and smart automation:
  - Pre-built power workflows (work, focus, study, gaming, night, morning)
  - Custom workflow builder — create, save, run, delete your own
  - Workflow scheduler — run at specific times or intervals
  - Step executor — integrates system_control, app_control, memory
  - Condition-based triggers — "when battery < 20%, notify me"
  - Voice-friendly responses throughout
"""

import os
import sys
import json
import time
import datetime
import threading
import subprocess
import platform
from typing import Callable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
DATA_DIR       = os.path.join(BASE_DIR, "..", "data")
WORKFLOWS_FILE = os.path.join(DATA_DIR, "custom_workflows.json")
SCHEDULE_FILE  = os.path.join(DATA_DIR, "scheduled_tasks.json")

os.makedirs(DATA_DIR, exist_ok=True)

SYSTEM = platform.system()

# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _respond(msg: str) -> str:
    """Print and return a voice-friendly response."""
    print(f"  [AUTO] {msg}")
    return msg


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: str, default) -> any:
    if not os.path.exists(path):
        _save_json(path, default)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def _save_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Step Executor
# ---------------------------------------------------------------------------

def _open_app(app: str) -> str:
    """Open an application by name."""
    apps = {
        "chrome":      {"Windows": "start chrome",          "Darwin": "open -a 'Google Chrome'"},
        "firefox":     {"Windows": "start firefox",         "Darwin": "open -a Firefox"},
        "vscode":      {"Windows": "code",                  "Darwin": "open -a 'Visual Studio Code'"},
        "notepad":     {"Windows": "notepad",               "Darwin": "open -a TextEdit"},
        "calculator":  {"Windows": "calc",                  "Darwin": "open -a Calculator"},
        "terminal":    {"Windows": "start cmd",             "Darwin": "open -a Terminal"},
        "spotify":     {"Windows": "start spotify:",        "Darwin": "open -a Spotify"},
        "discord":     {"Windows": "start discord:",        "Darwin": "open -a Discord"},
        "slack":       {"Windows": "start slack:",          "Darwin": "open -a Slack"},
        "notion":      {"Windows": "start notion:",         "Darwin": "open -a Notion"},
        "zoom":        {"Windows": "start zoom:",           "Darwin": "open -a zoom.us"},
        "whatsapp":    {"Windows": "start whatsapp:",       "Darwin": "open -a WhatsApp"},
        "excel":       {"Windows": "start excel",           "Darwin": "open -a 'Microsoft Excel'"},
        "word":        {"Windows": "start winword",         "Darwin": "open -a 'Microsoft Word'"},
        "powerpoint":  {"Windows": "start powerpnt",        "Darwin": "open -a 'Microsoft PowerPoint'"},
        "obs":         {"Windows": "start obs64",           "Darwin": "open -a OBS"},
        "task manager":{"Windows": "taskmgr",               "Darwin": "open -a 'Activity Monitor'"},
        "file explorer":{"Windows": "explorer",             "Darwin": "open ~"},
    }
    key = app.lower().strip()
    cmd = apps.get(key, {}).get(SYSTEM)
    if cmd:
        os.system(cmd)
        return f"Opened {app}."
    return f"App '{app}' not found in app list."


def _open_website(url: str) -> str:
    """Open a website in the default browser."""
    if not url.startswith("http"):
        url = "https://" + url
    if SYSTEM == "Windows":
        os.system(f"start {url}")
    elif SYSTEM == "Darwin":
        os.system(f"open {url}")
    else:
        os.system(f"xdg-open {url}")
    return f"Opened {url}."


def _close_app(name: str) -> str:
    """Kill an application by process name."""
    try:
        import psutil
        killed = []
        for proc in psutil.process_iter(['name', 'pid']):
            if name.lower() in proc.info['name'].lower():
                proc.kill()
                killed.append(proc.info['name'])
        return f"Closed {', '.join(killed)}." if killed else f"{name} was not running."
    except ImportError:
        if SYSTEM == "Windows":
            os.system(f"taskkill /f /im {name}.exe >nul 2>&1")
        return f"Attempted to close {name}."


def _wait(seconds: int) -> str:
    """Wait for a given number of seconds."""
    time.sleep(seconds)
    return f"Waited {seconds} seconds."


def _notify(message: str) -> str:
    """Show a desktop notification."""
    try:
        if SYSTEM == "Windows":
            # Use PowerShell toast notification
            ps = (
                f"Add-Type -AssemblyName System.Windows.Forms; "
                f"$n = New-Object System.Windows.Forms.NotifyIcon; "
                f"$n.Icon = [System.Drawing.SystemIcons]::Information; "
                f"$n.Visible = $true; "
                f"$n.ShowBalloonTip(3000, 'Cortex AI', '{message}', "
                f"[System.Windows.Forms.ToolTipIcon]::Info); "
                f"Start-Sleep -s 4; $n.Dispose()"
            )
            subprocess.Popen(["powershell", "-Command", ps],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif SYSTEM == "Darwin":
            os.system(f'osascript -e \'display notification "{message}" with title "Cortex AI"\'')
        else:
            os.system(f'notify-send "Cortex AI" "{message}"')
        return f"Notification sent: {message}"
    except Exception as e:
        return f"Notification failed: {e}"


def _set_volume(level: int) -> str:
    """Set system volume."""
    try:
        import pyautogui
        # Press mute first to reset, then set
        pyautogui.press("volumemute")
        time.sleep(0.1)
        pyautogui.press("volumemute")
        steps = int(level / 2)  # Each key press ~ 2%
        for _ in range(steps):
            pyautogui.press("volumeup")
        return f"Volume set to approximately {level}%."
    except ImportError:
        return "pyautogui not installed — volume not changed."


def _take_screenshot() -> str:
    """Take a screenshot."""
    try:
        import pyautogui
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(os.path.expanduser("~"), "Desktop", f"cortex_{ts}.png")
        pyautogui.screenshot(path)
        return f"Screenshot saved: {path}"
    except ImportError:
        return "pyautogui not installed — screenshot skipped."


def _run_command(cmd: str) -> str:
    """Run a raw shell command."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return f"Command ran: {cmd}"
    except Exception as e:
        return f"Command failed: {e}"


def _print_message(msg: str) -> str:
    """Print a message to the user."""
    print(f"\n  💬 {msg}\n")
    return msg


# ---------------------------------------------------------------------------
# Step Registry — maps step type → executor function
# ---------------------------------------------------------------------------

STEP_REGISTRY: dict[str, Callable] = {
    "open_app":      lambda p: _open_app(p),
    "open_website":  lambda p: _open_website(p),
    "close_app":     lambda p: _close_app(p),
    "wait":          lambda p: _wait(int(p)),
    "notify":        lambda p: _notify(p),
    "set_volume":    lambda p: _set_volume(int(p)),
    "screenshot":    lambda p: _take_screenshot(),
    "run_command":   lambda p: _run_command(p),
    "message":       lambda p: _print_message(p),
}


def execute_step(step: dict) -> str:
    """
    Execute a single workflow step.
    Step format: {"type": "open_app", "param": "chrome"}
    """
    step_type = step.get("type", "").lower()
    param     = step.get("param", "")
    delay     = step.get("delay", 0)

    if delay:
        time.sleep(delay)

    executor = STEP_REGISTRY.get(step_type)
    if executor:
        try:
            result = executor(param)
            print(f"     {step_type}({param}) → {result}")
            return result
        except Exception as e:
            msg = f"Step failed [{step_type}]: {e}"
            print(f"     {msg}")
            return msg
    else:
        return f"Unknown step type: {step_type}"


def execute_workflow(steps: list[dict], name: str = "Workflow") -> str:
    """Execute a full list of steps sequentially."""
    print(f"\n  [AUTO] ── Running: {name} ({len(steps)} steps) ──\n")
    results = []
    for i, step in enumerate(steps, 1):
        print(f"  Step {i}/{len(steps)}: {step.get('type')} → {step.get('param', '')}")
        result = execute_step(step)
        results.append(result)
    print(f"\n  [AUTO] ── {name} Complete ──\n")
    return f"{name} finished. {len(steps)} steps executed."


# ---------------------------------------------------------------------------
# Pre-Built Power Workflows
# ---------------------------------------------------------------------------

BUILTIN_WORKFLOWS: dict[str, dict] = {

    "work mode": {
        "description": "Sets up your full work environment",
        "steps": [
            {"type": "message",      "param": "Starting Work Mode — get ready! 🚀"},
            {"type": "notify",       "param": "Work Mode Activated!"},
            {"type": "set_volume",   "param": "30"},
            {"type": "open_app",     "param": "vscode"},
            {"type": "wait",         "param": "2"},
            {"type": "open_app",     "param": "chrome"},
            {"type": "wait",         "param": "2"},
            {"type": "open_website", "param": "https://github.com"},
            {"type": "wait",         "param": "1"},
            {"type": "open_website", "param": "https://notion.so"},
            {"type": "message",      "param": "Work Mode ready. Time to grind! "},
        ]
    },

    "focus mode": {
        "description": "Closes distractions, sets up deep focus environment",
        "steps": [
            {"type": "message",      "param": "Entering Focus Mode — closing distractions "},
            {"type": "close_app",    "param": "discord"},
            {"type": "close_app",    "param": "spotify"},
            {"type": "close_app",    "param": "whatsapp"},
            {"type": "set_volume",   "param": "10"},
            {"type": "notify",       "param": "Focus Mode ON — No distractions!"},
            {"type": "open_app",     "param": "vscode"},
            {"type": "message",      "param": "Focus Mode active. You got this! "},
        ]
    },

    "study mode": {
        "description": "Sets up a productive study environment",
        "steps": [
            {"type": "message",      "param": "Study Mode starting "},
            {"type": "close_app",    "param": "discord"},
            {"type": "close_app",    "param": "spotify"},
            {"type": "set_volume",   "param": "20"},
            {"type": "open_website", "param": "https://notion.so"},
            {"type": "wait",         "param": "1"},
            {"type": "open_website", "param": "https://www.youtube.com/results?search_query=lofi+study"},
            {"type": "notify",       "param": "Study Mode ON — Focus and learn!"},
            {"type": "message",      "param": "Study Mode active. Stay focused! "},
        ]
    },

    "morning routine": {
        "description": "Start your morning — news, weather, calendar",
        "steps": [
            {"type": "message",      "param": "Good Morning! Starting your morning routine "},
            {"type": "notify",       "param": "Good Morning! Cortex AI is ready."},
            {"type": "set_volume",   "param": "50"},
            {"type": "open_website", "param": "https://news.google.com"},
            {"type": "wait",         "param": "2"},
            {"type": "open_website", "param": "https://calendar.google.com"},
            {"type": "wait",         "param": "1"},
            {"type": "open_website", "param": "https://mail.google.com"},
            {"type": "message",      "param": "Morning routine complete. Have a great day! "},
        ]
    },

    "night mode": {
        "description": "Wind down — close everything and prepare for rest",
        "steps": [
            {"type": "message",      "param": "Night Mode starting — winding down "},
            {"type": "set_volume",   "param": "20"},
            {"type": "close_app",    "param": "chrome"},
            {"type": "close_app",    "param": "discord"},
            {"type": "close_app",    "param": "spotify"},
            {"type": "close_app",    "param": "vscode"},
            {"type": "screenshot",   "param": ""},
            {"type": "notify",       "param": "Night Mode ON — Rest well!"},
            {"type": "message",      "param": "Good night! Sleep well "},
        ]
    },

    "gaming mode": {
        "description": "Optimise system for gaming — max performance",
        "steps": [
            {"type": "message",      "param": "Gaming Mode starting "},
            {"type": "close_app",    "param": "chrome"},
            {"type": "close_app",    "param": "slack"},
            {"type": "close_app",    "param": "discord"},
            {"type": "set_volume",   "param": "80"},
            {"type": "notify",       "param": "Gaming Mode ON — Let's go!"},
            {"type": "open_app",     "param": "discord"},
            {"type": "wait",         "param": "2"},
            {"type": "open_app",     "param": "spotify"},
            {"type": "message",      "param": "Gaming Mode ready. Let's play! "},
        ]
    },

    "presentation mode": {
        "description": "Set up screen for a presentation or meeting",
        "steps": [
            {"type": "message",      "param": "Presentation Mode starting "},
            {"type": "close_app",    "param": "slack"},
            {"type": "close_app",    "param": "discord"},
            {"type": "close_app",    "param": "whatsapp"},
            {"type": "set_volume",   "param": "60"},
            {"type": "notify",       "param": "Presentation Mode ON — Good luck!"},
            {"type": "open_app",     "param": "powerpoint"},
            {"type": "message",      "param": "All set! You're going to crush it "},
        ]
    },

    "break mode": {
        "description": "Take a proper break — 5 minute rest",
        "steps": [
            {"type": "message",      "param": "Break time! Step away from the screen "},
            {"type": "notify",       "param": "Break time — 5 minutes!"},
            {"type": "set_volume",   "param": "40"},
            {"type": "open_website", "param": "https://www.youtube.com/results?search_query=5+minute+meditation"},
            {"type": "wait",         "param": "300"},
            {"type": "notify",       "param": "Break over — back to work!"},
            {"type": "message",      "param": "Break over. Back to it! "},
        ]
    },

    "shutdown routine": {
        "description": "Safe shutdown — save work and power off",
        "steps": [
            {"type": "message",      "param": "Shutdown routine starting — saving and closing "},
            {"type": "screenshot",   "param": ""},
            {"type": "close_app",    "param": "chrome"},
            {"type": "close_app",    "param": "discord"},
            {"type": "close_app",    "param": "spotify"},
            {"type": "notify",       "param": "Shutting down in 30 seconds..."},
            {"type": "wait",         "param": "30"},
            {"type": "run_command",  "param": "shutdown /s /t 0"},
        ]
    },

    "meeting mode": {
        "description": "Prepare for an online meeting — mute apps, open meeting tools",
        "steps": [
            {"type": "message",      "param": "Meeting Mode starting "},
            {"type": "close_app",    "param": "spotify"},
            {"type": "close_app",    "param": "discord"},
            {"type": "set_volume",   "param": "60"},
            {"type": "notify",       "param": "Meeting Mode — You're live!"},
            {"type": "open_app",     "param": "zoom"},
            {"type": "wait",         "param": "2"},
            {"type": "open_website", "param": "https://calendar.google.com"},
            {"type": "message",      "param": "Meeting Mode ready. You're on! "},
        ]
    },
}


# ---------------------------------------------------------------------------
# Run Built-in Workflow
# ---------------------------------------------------------------------------

def run_builtin(name: str) -> str:
    """Run a pre-built workflow by name."""
    key = name.lower().strip()

    # Fuzzy match — allow partial names
    match = None
    for wf_name in BUILTIN_WORKFLOWS:
        if key in wf_name or wf_name in key:
            match = wf_name
            break

    if not match:
        available = ", ".join(BUILTIN_WORKFLOWS.keys())
        return _respond(f"No workflow found for '{name}'. Available: {available}")

    workflow = BUILTIN_WORKFLOWS[match]
    return execute_workflow(workflow["steps"], name=match.title())


def list_builtin_workflows() -> str:
    """List all available pre-built workflows."""
    print("\n  [AUTO] ── Built-in Workflows ──")
    for name, data in BUILTIN_WORKFLOWS.items():
        steps_count = len(data["steps"])
        print(f"    • {name:<20} — {data['description']} ({steps_count} steps)")
    return f"Found {len(BUILTIN_WORKFLOWS)} built-in workflows."


# ---------------------------------------------------------------------------
# Custom Workflow Builder
# ---------------------------------------------------------------------------

def create_custom_workflow(name: str, steps: list[dict], description: str = "") -> str:
    """
    Save a custom workflow.

    Example:
        create_custom_workflow("dev setup", [
            {"type": "open_app",     "param": "vscode"},
            {"type": "open_website", "param": "github.com"},
        ])
    """
    workflows = _load_json(WORKFLOWS_FILE, {})
    workflows[name.lower()] = {
        "name":        name,
        "description": description,
        "steps":       steps,
        "created_at":  _now(),
        "run_count":   0,
    }
    _save_json(WORKFLOWS_FILE, workflows)
    return _respond(f"Custom workflow '{name}' saved with {len(steps)} steps.")


def run_custom_workflow(name: str) -> str:
    """Run a saved custom workflow by name."""
    workflows = _load_json(WORKFLOWS_FILE, {})
    key = name.lower().strip()

    # Fuzzy match
    match = None
    for wf_name in workflows:
        if key in wf_name or wf_name in key:
            match = wf_name
            break

    if not match:
        return _respond(f"Custom workflow '{name}' not found. Use list_custom_workflows() to see all.")

    wf = workflows[match]
    workflows[match]["run_count"] += 1
    workflows[match]["last_run"] = _now()
    _save_json(WORKFLOWS_FILE, workflows)
    return execute_workflow(wf["steps"], name=wf["name"])


def list_custom_workflows() -> str:
    """List all saved custom workflows."""
    workflows = _load_json(WORKFLOWS_FILE, {})
    if not workflows:
        return _respond("No custom workflows saved yet. Use create_custom_workflow() to make one.")
    print("\n  [AUTO] ── Custom Workflows ──")
    for key, wf in workflows.items():
        print(f"    • {wf['name']:<20} — {wf.get('description', '')} (runs: {wf.get('run_count', 0)})")
    return f"Found {len(workflows)} custom workflows."


def delete_custom_workflow(name: str) -> str:
    """Delete a saved custom workflow."""
    workflows = _load_json(WORKFLOWS_FILE, {})
    key = name.lower().strip()
    if key in workflows:
        del workflows[key]
        _save_json(WORKFLOWS_FILE, workflows)
        return _respond(f"Workflow '{name}' deleted.")
    return _respond(f"Workflow '{name}' not found.")


def update_custom_workflow(name: str, new_steps: list[dict]) -> str:
    """Update steps in an existing custom workflow."""
    workflows = _load_json(WORKFLOWS_FILE, {})
    key = name.lower().strip()
    if key in workflows:
        workflows[key]["steps"] = new_steps
        workflows[key]["updated_at"] = _now()
        _save_json(WORKFLOWS_FILE, workflows)
        return _respond(f"Workflow '{name}' updated with {len(new_steps)} steps.")
    return _respond(f"Workflow '{name}' not found.")


# ---------------------------------------------------------------------------
# Workflow Scheduler
# ---------------------------------------------------------------------------

_scheduler_thread: threading.Thread = None
_scheduler_running: bool = False


def _load_schedule() -> list:
    return _load_json(SCHEDULE_FILE, [])


def _save_schedule(tasks: list) -> None:
    _save_json(SCHEDULE_FILE, tasks)


def schedule_workflow(workflow_name: str, run_at: str, repeat: str = None) -> str:
    """
    Schedule a workflow to run at a specific time.

    Args:
        workflow_name: Name of built-in or custom workflow
        run_at:        Time string — "08:30" (daily) or "2026-07-05 08:30"
        repeat:        "daily" | "weekdays" | "weekly" | None (one-time)

    Example:
        schedule_workflow("morning routine", "08:00", repeat="weekdays")
    """
    tasks = _load_schedule()
    task = {
        "id":            len(tasks) + 1,
        "workflow":      workflow_name,
        "run_at":        run_at,
        "repeat":        repeat,
        "active":        True,
        "created_at":    _now(),
        "last_triggered":None,
    }
    tasks.append(task)
    _save_schedule(tasks)
    repeat_str = f" (repeats {repeat})" if repeat else " (one-time)"
    return _respond(f"Scheduled '{workflow_name}' at {run_at}{repeat_str}.")


def list_scheduled_tasks() -> str:
    """List all scheduled tasks."""
    tasks = _load_schedule()
    active = [t for t in tasks if t.get("active")]
    if not active:
        return _respond("No scheduled tasks. Use schedule_workflow() to add one.")
    print("\n  [AUTO] ── Scheduled Tasks ──")
    for t in active:
        print(f"    [{t['id']}] {t['workflow']:<20} at {t['run_at']} — {t.get('repeat', 'one-time')}")
    return f"Found {len(active)} active scheduled tasks."


def cancel_scheduled_task(task_id: int) -> str:
    """Cancel a scheduled task by ID."""
    tasks = _load_schedule()
    for task in tasks:
        if task["id"] == task_id:
            task["active"] = False
            _save_schedule(tasks)
            return _respond(f"Task {task_id} cancelled.")
    return _respond(f"Task {task_id} not found.")


def _scheduler_loop():
    """Background thread that checks and triggers scheduled tasks."""
    global _scheduler_running
    _scheduler_running = True
    print("  [AUTO] Scheduler started in background.")

    while _scheduler_running:
        now = datetime.datetime.now()
        current_time  = now.strftime("%H:%M")
        current_day   = now.strftime("%A").lower()        # monday, tuesday...
        weekdays      = ["monday", "tuesday", "wednesday", "thursday", "friday"]

        tasks = _load_schedule()
        updated = False

        for task in tasks:
            if not task.get("active"):
                continue

            run_at   = task.get("run_at", "")
            repeat   = task.get("repeat")
            last_run = task.get("last_triggered")

            # Check time match
            time_match = current_time in run_at

            # Check repeat logic
            should_run = False
            if time_match:
                if last_run and last_run.startswith(now.strftime("%Y-%m-%d")):
                    should_run = False  # Already ran today
                elif repeat == "daily":
                    should_run = True
                elif repeat == "weekdays" and current_day in weekdays:
                    should_run = True
                elif repeat == "weekly":
                    should_run = True
                elif repeat is None:
                    should_run = True  # One-time

            if should_run:
                task["last_triggered"] = _now()
                if repeat is None:
                    task["active"] = False  # One-time — disable after run
                updated = True
                print(f"\n  [AUTO]  Triggering scheduled workflow: {task['workflow']}")
                # Run in separate thread to avoid blocking scheduler
                threading.Thread(
                    target=handle_automation,
                    args=(task["workflow"],),
                    daemon=True
                ).start()

        if updated:
            _save_schedule(tasks)

        time.sleep(30)  # Check every 30 seconds


def start_scheduler() -> str:
    """Start the background scheduler thread."""
    global _scheduler_thread, _scheduler_running
    if _scheduler_thread and _scheduler_thread.is_alive():
        return _respond("Scheduler is already running.")
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()
    return _respond("Scheduler started. Tasks will trigger automatically.")


def stop_scheduler() -> str:
    """Stop the background scheduler thread."""
    global _scheduler_running
    _scheduler_running = False
    return _respond("Scheduler stopped.")


# ---------------------------------------------------------------------------
# Condition-Based Triggers
# ---------------------------------------------------------------------------

def check_battery_trigger(threshold: int = 20, workflow: str = "notify") -> str:
    """
    Run a workflow when battery drops below threshold.
    Call this periodically or hook into main loop.
    """
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery and battery.percent <= threshold and not battery.power_plugged:
            msg = f"Battery at {int(battery.percent)}%! Please plug in your charger."
            _notify(msg)
            return _respond(msg)
        return _respond(f"Battery OK at {int(battery.percent) if battery else 'N/A'}%.")
    except ImportError:
        return _respond("psutil not installed — battery check skipped.")


def check_cpu_trigger(threshold: int = 90, workflow: str = "notify") -> str:
    """Notify when CPU usage exceeds threshold."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        if cpu >= threshold:
            msg = f"Warning! CPU at {cpu}% — system under heavy load."
            _notify(msg)
            return _respond(msg)
        return _respond(f"CPU OK at {cpu}%.")
    except ImportError:
        return _respond("psutil not installed.")


# ---------------------------------------------------------------------------
# Main Dispatcher — called from main.py
# ---------------------------------------------------------------------------

# Keyword map for routing automation commands
AUTOMATION_KEYWORDS: dict[str, str] = {
    "work mode":          "work mode",
    "start work":         "work mode",
    "focus mode":         "focus mode",
    "deep focus":         "focus mode",
    "study mode":         "study mode",
    "morning routine":    "morning routine",
    "good morning":       "morning routine",
    "night mode":         "night mode",
    "sleep mode":         "night mode",
    "gaming mode":        "gaming mode",
    "game mode":          "gaming mode",
    "presentation mode":  "presentation mode",
    "meeting mode":       "meeting mode",
    "break mode":         "break mode",
    "take a break":       "break mode",
    "shutdown routine":   "shutdown routine",
    "safe shutdown":      "shutdown routine",
    "list workflows":     "__list__",
    "show workflows":     "__list__",
    "what workflows":     "__list__",
}


def handle_automation(user_input: str) -> str:
    """
    Main entry point — called from main.py for AUTOMATION-routed commands.
    Matches user input to a workflow and executes it.
    Returns a voice-friendly response string.
    """
    normalized = user_input.lower().strip()

    # Check for list command
    if any(k in normalized for k in ["list workflows", "show workflows", "what workflows"]):
        list_builtin_workflows()
        list_custom_workflows()
        return "Here are all available workflows."

    # Match built-in workflows (longest keyword first)
    for keyword in sorted(AUTOMATION_KEYWORDS.keys(), key=len, reverse=True):
        if keyword in normalized:
            workflow_name = AUTOMATION_KEYWORDS[keyword]
            if workflow_name == "__list__":
                continue
            return run_builtin(workflow_name)

    # Try custom workflows
    custom = _load_json(WORKFLOWS_FILE, {})
    for key in custom:
        if key in normalized or normalized in key:
            return run_custom_workflow(key)

    return _respond(
        f"No automation workflow matched '{user_input}'. "
        f"Say 'list workflows' to see all options."
    )


# ---------------------------------------------------------------------------
# Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*55)
    print("   Cortex AI — Automation Handler Test")
    print("="*55 + "\n")

    # List all built-in
    list_builtin_workflows()
    print()

    # Create a custom workflow
    create_custom_workflow(
        name="dev setup",
        description="My personal dev environment",
        steps=[
            {"type": "open_app",     "param": "vscode"},
            {"type": "wait",         "param": "2"},
            {"type": "open_website", "param": "github.com"},
            {"type": "notify",       "param": "Dev environment ready!"},
            {"type": "message",      "param": "Dev setup complete! Let's build 🚀"},
        ]
    )

    # List custom workflows
    list_custom_workflows()
    print()

    # Test dispatcher
    print("\n--- Dispatcher Tests ---\n")
    test_inputs = [
        "start work mode",
        "activate focus mode",
        "list workflows",
        "dev setup",
        "unknown command",
    ]

    for cmd in test_inputs:
        print(f"  > {cmd}")
        # Only run non-destructive ones in test
        if "list" in cmd or "unknown" in cmd:
            result = handle_automation(cmd)
            print(f"  → {result}\n")
        else:
            print(f"  → Would run: {cmd} (skipped in test mode)\n")

    # Test scheduler
    print("\n--- Scheduler Test ---\n")
    schedule_workflow("morning routine", "08:00", repeat="weekdays")
    schedule_workflow("night mode", "23:00", repeat="daily")
    list_scheduled_tasks()

    # Battery trigger test
    print("\n--- Trigger Test ---\n")
    check_battery_trigger(threshold=100)  # Always triggers in test
    check_cpu_trigger(threshold=0)        # Always triggers in test

    print("\n Automation Handler Test Complete!")
