"""
Cortex AI — Reminder Module  (Phase 5)
Voice-activated reminders and scheduling. Understands natural language
time expressions directly — no external date-parsing library required.

Capabilities:
  - Natural language time parsing — relative ("in 20 minutes"), absolute
    ("at 5pm", "tomorrow at 9am"), and repeating ("every day at 8am",
    "every monday at 10am", "every weekday at 9am")
  - Smart ambiguous-hour resolution — "remind me at 5" picks whichever
    of 5am/5pm is soonest, the way Siri/Google Assistant do
  - Full CRUD — add, list, mark done, delete, snooze
  - Background scheduler — fires reminders automatically, no polling needed
  - Desktop notifications when a reminder fires
  - Pluggable actions — other modules (whatsapp.py, gmail.py) can register
    a callback so a reminder can DO something, not just notify
  - Natural language command dispatcher

Zero external pip installs — pure standard library.
"""

import os
import re
import json
import time
import threading
import subprocess
import platform
import datetime

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
DATA_DIR       = os.path.join(BASE_DIR, "data")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")

os.makedirs(DATA_DIR, exist_ok=True)

SYSTEM = platform.system()
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_scheduler_thread = None
_scheduler_running = False

# Other modules can plug an action into a reminder — see register_action().
_action_handlers: dict = {}


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _respond(msg: str) -> str:
    print(f"  [REMINDER] {msg}")
    return msg


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: str, default):
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


def _notify_desktop(message: str) -> None:
    """Best-effort desktop notification — never allowed to crash the caller."""
    try:
        if SYSTEM == "Windows":
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                "$n.Visible = $true; "
                f"$n.ShowBalloonTip(5000, 'Cortex AI Reminder', '{message}', "
                "[System.Windows.Forms.ToolTipIcon]::Info); "
                "Start-Sleep -s 6; $n.Dispose()"
            )
            subprocess.Popen(["powershell", "-Command", ps],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif SYSTEM == "Darwin":
            os.system(f'osascript -e \'display notification "{message}" with title "Cortex AI Reminder"\'')
        else:
            os.system(f'notify-send "Cortex AI Reminder" "{message}" 2>/dev/null')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. NATURAL LANGUAGE TIME PARSING
# ---------------------------------------------------------------------------

def _parse_clock_time(text: str):
    """Extract (hour_24, minute, had_meridiem) from a snippet like '5pm', '9:30am', '14:00'."""
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    meridiem = m.group(3)

    if not (0 <= minute <= 59):
        return None

    if meridiem == "pm":
        if not (1 <= hour <= 12):
            return None
        return (hour if hour == 12 else hour + 12), minute, True
    elif meridiem == "am":
        if not (1 <= hour <= 12):
            return None
        return (0 if hour == 12 else hour), minute, True
    else:
        if not (0 <= hour <= 23):
            return None
        return hour, minute, False


def _next_occurrence(hour: int, minute: int, had_meridiem: bool, now: datetime.datetime) -> datetime.datetime:
    """
    Resolve (hour, minute) to the next future datetime today or tomorrow.
    If am/pm wasn't specified and the hour is ambiguous (1-12), picks
    whichever interpretation (am or pm) is soonest — same convention
    Siri and Google Assistant use.
    """
    if not had_meridiem and 1 <= hour <= 12:
        am_hour = 0 if hour == 12 else hour
        pm_hour = 12 if hour == 12 else hour + 12
        candidates = []
        for h in (am_hour, pm_hour):
            t = now.replace(hour=h, minute=minute, second=0, microsecond=0)
            if t <= now:
                t += datetime.timedelta(days=1)
            candidates.append(t)
        return min(candidates)

    t = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t <= now:
        t += datetime.timedelta(days=1)
    return t


def parse_time_expression(text: str, now: datetime.datetime = None) -> dict:
    """
    Parse a natural-language time expression into a concrete datetime plus
    an optional repeat rule.

    Returns {"remind_at": datetime, "repeat": None|"daily"|"weekly"|"weekdays",
             "repeat_day": None|weekday_name} or None if nothing recognizable found.
    """
    now = now or datetime.datetime.now()
    text = text.lower().strip()
    clock_pattern = r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"

    # "in N minute(s)/hour(s)/day(s)/week(s)" — relative time
    m = re.search(r"\bin\s+(\d+)\s*(minute|min|hour|hr|day|week)s?\b", text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        delta = {
            "minute": datetime.timedelta(minutes=amount), "min": datetime.timedelta(minutes=amount),
            "hour": datetime.timedelta(hours=amount), "hr": datetime.timedelta(hours=amount),
            "day": datetime.timedelta(days=amount),
            "week": datetime.timedelta(weeks=amount),
        }[unit]
        return {"remind_at": now + delta, "repeat": None, "repeat_day": None}

    # "every weekday at H" — repeats Mon-Fri
    if "every weekday" in text:
        m2 = re.search(clock_pattern, text)
        clock = _parse_clock_time(m2.group(1)) if m2 else (9, 0, True)
        hour, minute, had_meridiem = clock
        target = _next_occurrence(hour, minute, had_meridiem, now)
        while target.weekday() >= 5:  # skip Sat/Sun for the first occurrence
            target += datetime.timedelta(days=1)
        return {"remind_at": target, "repeat": "weekdays", "repeat_day": None}

    # "every <weekday> at H" — weekly repeat
    for day in WEEKDAYS:
        if f"every {day}" in text:
            m2 = re.search(clock_pattern, text)
            clock = _parse_clock_time(m2.group(1)) if m2 else (9, 0, True)
            hour, minute, had_meridiem = clock
            days_ahead = (WEEKDAYS.index(day) - now.weekday()) % 7
            base = now + datetime.timedelta(days=days_ahead)
            target = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += datetime.timedelta(days=7)
            return {"remind_at": target, "repeat": "weekly", "repeat_day": day}

    # "every day at H" / "daily at H" — daily repeat
    if "every day" in text or "daily" in text:
        m2 = re.search(clock_pattern, text)
        clock = _parse_clock_time(m2.group(1)) if m2 else (9, 0, True)
        hour, minute, had_meridiem = clock
        target = _next_occurrence(hour, minute, had_meridiem, now)
        return {"remind_at": target, "repeat": "daily", "repeat_day": None}

    # "on <weekday> at H" — one-time, next occurrence of that weekday
    for day in WEEKDAYS:
        if f"on {day}" in text:
            m2 = re.search(clock_pattern, text)
            clock = _parse_clock_time(m2.group(1)) if m2 else (9, 0, True)
            hour, minute, had_meridiem = clock
            days_ahead = (WEEKDAYS.index(day) - now.weekday()) % 7
            base = now + datetime.timedelta(days=days_ahead)
            target = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += datetime.timedelta(days=7)
            return {"remind_at": target, "repeat": None, "repeat_day": None}

    # "tomorrow at H" (defaults to 9am if no time given)
    if "tomorrow" in text:
        m2 = re.search(clock_pattern, text)
        clock = _parse_clock_time(m2.group(1)) if m2 else (9, 0, True)
        hour, minute, had_meridiem = clock
        target = (now + datetime.timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return {"remind_at": target, "repeat": None, "repeat_day": None}

    # "at H" / "tonight at H" / bare "H am/pm" — today, rolling to tomorrow if passed
    m = re.search(r"(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text)
    if m:
        clock = _parse_clock_time(m.group(1))
        if clock:
            hour, minute, had_meridiem = clock
            target = _next_occurrence(hour, minute, had_meridiem, now)
            return {"remind_at": target, "repeat": None, "repeat_day": None}

    return None


def smart_add_reminder(user_input: str) -> str:
    """
    Parse a full natural-language request and create the reminder in one step.
    e.g. 'remind me to call mom at 5pm'
         'remind me every day at 8am to take medicine'
         'remind me in 20 minutes to check the oven'
    """
    text = user_input.strip()
    lower = text.lower()

    for lead in ["remind me to ", "remind me that ", "remind me "]:
        if lower.startswith(lead):
            text = text[len(lead):]
            break

    time_info = parse_time_expression(text)
    if not time_info:
        return _respond(
            f"I couldn't find a time in that — try something like "
            f"'remind me to {text} at 5pm' or 'in 20 minutes'."
        )

    content = text
    for pattern in [
        r"\bin\s+\d+\s*(minute|min|hour|hr|day|week)s?\b",
        r"\bevery\s+weekday\b", r"\bevery\s+\w+day\b", r"\bevery day\b", r"\bdaily\b",
        r"\bon\s+\w+day\b", r"\btomorrow\b", r"\btonight\b",
        r"\bat\s+\d{1,2}(:\d{2})?\s*(am|pm)?\b",
        r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b",
    ]:
        content = re.sub(pattern, "", content, flags=re.IGNORECASE)
    content = re.sub(r"\s+", " ", content).strip()
    content = content.strip(" ,.")
    if content.lower().startswith("to "):
        content = content[3:].strip()
    content = content.strip(" ,.")
    content = content or "Reminder"

    return add_reminder(content, time_info["remind_at"], repeat=time_info["repeat"], repeat_day=time_info["repeat_day"])


# ---------------------------------------------------------------------------
# 2. CORE CRUD
# ---------------------------------------------------------------------------

def add_reminder(content: str, remind_at: datetime.datetime, repeat: str = None,
                  repeat_day: str = None, action_type: str = None, action_params: dict = None) -> str:
    reminders = _load_json(REMINDERS_FILE, [])
    reminder = {
        "id":             (reminders[-1]["id"] + 1) if reminders else 1,
        "content":        content,
        "remind_at":      remind_at.strftime("%Y-%m-%d %H:%M:%S"),
        "repeat":         repeat,
        "repeat_day":     repeat_day,
        "action_type":    action_type,
        "action_params":  action_params or {},
        "created_at":     _now(),
        "done":           False,
        "last_triggered": None,
    }
    reminders.append(reminder)
    _save_json(REMINDERS_FILE, reminders)

    when_str = remind_at.strftime("%A, %B %d at %I:%M %p")
    repeat_str = f" (repeats {repeat})" if repeat else ""
    return _respond(f"Reminder set: '{content}' — {when_str}{repeat_str}")


def get_reminders(include_done: bool = False) -> list:
    reminders = _load_json(REMINDERS_FILE, [])
    if not include_done:
        reminders = [r for r in reminders if not r["done"]]

    print(f"  [REMINDER] {len(reminders)} reminder(s):")
    for r in sorted(reminders, key=lambda x: x["remind_at"]):
        when = datetime.datetime.strptime(r["remind_at"], "%Y-%m-%d %H:%M:%S").strftime("%a %b %d, %I:%M %p")
        repeat_tag = f" [{r['repeat']}]" if r["repeat"] else ""
        status = "done" if r["done"] else "pending"
        print(f"    [{r['id']}] {r['content']} — {when}{repeat_tag} ({status})")
    return reminders


def get_upcoming_reminders(hours: int = 24) -> list:
    """Reminders due within the next N hours."""
    now = datetime.datetime.now()
    cutoff = now + datetime.timedelta(hours=hours)
    reminders = _load_json(REMINDERS_FILE, [])
    upcoming = []
    for r in reminders:
        if r["done"]:
            continue
        remind_at = datetime.datetime.strptime(r["remind_at"], "%Y-%m-%d %H:%M:%S")
        if now <= remind_at <= cutoff:
            upcoming.append(r)

    print(f"  [REMINDER] {len(upcoming)} reminder(s) in the next {hours} hours:")
    for r in sorted(upcoming, key=lambda x: x["remind_at"]):
        when = datetime.datetime.strptime(r["remind_at"], "%Y-%m-%d %H:%M:%S").strftime("%a %I:%M %p")
        print(f"    [{r['id']}] {r['content']} — {when}")
    return upcoming


def mark_done(reminder_id: int) -> str:
    reminders = _load_json(REMINDERS_FILE, [])
    for r in reminders:
        if r["id"] == reminder_id:
            r["done"] = True
            _save_json(REMINDERS_FILE, reminders)
            return _respond(f"Reminder {reminder_id} marked as done.")
    return _respond(f"Reminder {reminder_id} not found.")


def delete_reminder(reminder_id: int) -> str:
    reminders = _load_json(REMINDERS_FILE, [])
    before = len(reminders)
    reminders = [r for r in reminders if r["id"] != reminder_id]
    _save_json(REMINDERS_FILE, reminders)
    return _respond(f"Reminder {reminder_id} deleted.") if len(reminders) < before else _respond(f"Reminder {reminder_id} not found.")


def snooze_reminder(reminder_id: int, minutes: int) -> str:
    reminders = _load_json(REMINDERS_FILE, [])
    for r in reminders:
        if r["id"] == reminder_id:
            new_time = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
            r["remind_at"] = new_time.strftime("%Y-%m-%d %H:%M:%S")
            r["done"] = False
            _save_json(REMINDERS_FILE, reminders)
            return _respond(f"Reminder {reminder_id} snoozed for {minutes} minutes.")
    return _respond(f"Reminder {reminder_id} not found.")


def update_reminder(reminder_id: int, content: str = None, remind_at: datetime.datetime = None) -> str:
    reminders = _load_json(REMINDERS_FILE, [])
    for r in reminders:
        if r["id"] == reminder_id:
            if content:
                r["content"] = content
            if remind_at:
                r["remind_at"] = remind_at.strftime("%Y-%m-%d %H:%M:%S")
            _save_json(REMINDERS_FILE, reminders)
            return _respond(f"Reminder {reminder_id} updated.")
    return _respond(f"Reminder {reminder_id} not found.")


def clear_completed() -> str:
    reminders = _load_json(REMINDERS_FILE, [])
    before = len(reminders)
    reminders = [r for r in reminders if not r["done"]]
    _save_json(REMINDERS_FILE, reminders)
    return _respond(f"Cleared {before - len(reminders)} completed reminder(s).")


# ---------------------------------------------------------------------------
# 3. PLUGGABLE ACTIONS
# ---------------------------------------------------------------------------

def register_action(action_type: str, handler) -> None:
    """
    Let another module plug a callback into reminders, so a reminder can DO
    something when it fires, not just notify.

    Example, from whatsapp.py:
        import reminder
        reminder.register_action(
            "whatsapp_message",
            lambda params: whatsapp.send_message(params["to"], params["message"])
        )
        reminder.add_reminder(
            "Good morning text", tomorrow_8am,
            action_type="whatsapp_message",
            action_params={"to": "+919876543210", "message": "Good morning!"}
        )
    """
    _action_handlers[action_type] = handler
    print(f"  [REMINDER] Action registered: {action_type}")


def get_registered_actions() -> list:
    return list(_action_handlers.keys())


# ---------------------------------------------------------------------------
# 4. BACKGROUND SCHEDULER
# ---------------------------------------------------------------------------

def _trigger_reminder(reminder: dict) -> None:
    content = reminder["content"]
    _notify_desktop(content)
    print(f"\n  🔔 REMINDER: {content}\n")

    action_type = reminder.get("action_type")
    if action_type:
        handler = _action_handlers.get(action_type)
        if handler:
            try:
                handler(reminder.get("action_params", {}))
            except Exception as e:
                print(f"  [REMINDER] Action handler for '{action_type}' failed: {e}")
        else:
            print(f"  [REMINDER] No handler registered for action '{action_type}' — call register_action() first.")


def _advance_repeat(reminder: dict, fired_at: datetime.datetime) -> None:
    """Move a repeating reminder's remind_at to its next occurrence, or mark one-time reminders done."""
    repeat = reminder["repeat"]
    if repeat == "daily":
        next_time = fired_at + datetime.timedelta(days=1)
    elif repeat == "weekly":
        next_time = fired_at + datetime.timedelta(days=7)
    elif repeat == "weekdays":
        next_time = fired_at + datetime.timedelta(days=1)
        while next_time.weekday() >= 5:
            next_time += datetime.timedelta(days=1)
    else:
        reminder["done"] = True
        return
    reminder["remind_at"] = next_time.strftime("%Y-%m-%d %H:%M:%S")


def _scheduler_loop(check_interval: int) -> None:
    global _scheduler_running
    _scheduler_running = True
    print("  [REMINDER] Scheduler started in background.")

    while _scheduler_running:
        now = datetime.datetime.now()
        reminders = _load_json(REMINDERS_FILE, [])
        changed = False

        for r in reminders:
            if r["done"]:
                continue

            remind_at = datetime.datetime.strptime(r["remind_at"], "%Y-%m-%d %H:%M:%S")
            if now < remind_at:
                continue

            last = r.get("last_triggered")
            already_fired_this_minute = last == remind_at.strftime("%Y-%m-%d %H:%M:%S") + "|fired"
            if already_fired_this_minute:
                continue

            _trigger_reminder(r)
            r["last_triggered"] = remind_at.strftime("%Y-%m-%d %H:%M:%S") + "|fired"
            _advance_repeat(r, remind_at)
            changed = True

        if changed:
            _save_json(REMINDERS_FILE, reminders)

        time.sleep(check_interval)


def start_scheduler(check_interval: int = 20) -> str:
    """Start the background thread that fires reminders automatically. Call once at startup."""
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return _respond("Scheduler is already running.")
    _scheduler_thread = threading.Thread(target=_scheduler_loop, args=(check_interval,), daemon=True)
    _scheduler_thread.start()
    return _respond(f"Scheduler started — checking every {check_interval} seconds.")


def stop_scheduler() -> str:
    global _scheduler_running
    _scheduler_running = False
    return _respond("Scheduler stopped.")


def is_scheduler_running() -> bool:
    return _scheduler_thread is not None and _scheduler_thread.is_alive()


# ---------------------------------------------------------------------------
# 5. SUMMARY
# ---------------------------------------------------------------------------

def get_reminder_summary() -> str:
    reminders = _load_json(REMINDERS_FILE, [])
    pending = [r for r in reminders if not r["done"]]
    repeating = [r for r in pending if r["repeat"]]

    print("\n  [REMINDER] ── Summary ──")
    print(f"    Total reminders:  {len(reminders)}")
    print(f"    Pending:          {len(pending)}")
    print(f"    Repeating:        {len(repeating)}")
    print(f"    Scheduler active: {is_scheduler_running()}")
    get_upcoming_reminders(24)
    return _respond("Reminder summary complete.")


# ---------------------------------------------------------------------------
# 6. COMMAND DISPATCHER — Natural Language Interface
# ---------------------------------------------------------------------------

def handle_reminder_command(user_input: str) -> str:
    """Main entry point — called from main.py for reminder-related commands."""
    text = user_input.lower().strip()

    if any(p in text for p in ["show reminders", "my reminders", "what reminders", "list reminders"]):
        get_reminders()
        return "Here are your reminders."

    if any(p in text for p in ["upcoming reminders", "what's coming up", "reminders today"]):
        get_upcoming_reminders()
        return "Here's what's coming up."

    if any(p in text for p in ["reminder summary", "reminder status"]):
        return get_reminder_summary()

    match = re.search(r"(?:delete|remove|cancel)\s+reminder\s+(\d+)", text)
    if match:
        return delete_reminder(int(match.group(1)))

    match = re.search(r"(?:mark|complete)\s+reminder\s+(\d+)", text)
    if match:
        return mark_done(int(match.group(1)))

    match = re.search(r"snooze\s+reminder\s+(\d+)\s+(?:for\s+)?(\d+)\s*(?:minute|min)s?", text)
    if match:
        return snooze_reminder(int(match.group(1)), int(match.group(2)))

    if "remind me" in text:
        return smart_add_reminder(user_input)

    return _respond(f"No reminder command matched: '{user_input}'")


# ---------------------------------------------------------------------------
# Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*55)
    print("   Cortex AI — Reminder Module Test")
    print("="*55 + "\n")

    FIXED_NOW = datetime.datetime(2026, 9, 19, 14, 30, 0)  # Saturday, 2:30 PM
    print(f"  Fixed 'now' for testing: {FIXED_NOW.strftime('%A, %B %d %Y, %I:%M %p')}\n")

    print("--- Time Expression Parsing ---")
    cases = [
        ("in 20 minutes",              FIXED_NOW + datetime.timedelta(minutes=20), None),
        ("in 2 hours",                 FIXED_NOW + datetime.timedelta(hours=2),    None),
        ("in 3 days",                  FIXED_NOW + datetime.timedelta(days=3),     None),
        ("at 5pm",                     FIXED_NOW.replace(hour=17, minute=0),       None),         # later today
        ("at 9am",                     FIXED_NOW.replace(hour=9, minute=0) + datetime.timedelta(days=1), None),  # already passed -> tomorrow
        ("tomorrow at 9am",            (FIXED_NOW + datetime.timedelta(days=1)).replace(hour=9, minute=0), None),
        ("tomorrow",                   (FIXED_NOW + datetime.timedelta(days=1)).replace(hour=9, minute=0), None),  # default 9am
        ("every day at 8am",           (FIXED_NOW + datetime.timedelta(days=1)).replace(hour=8, minute=0), "daily"),
        ("every monday at 10am",       None, "weekly"),   # checked separately below (date varies)
        ("every weekday at 9am",       None, "weekdays"),
        ("on friday at 3pm",           None, None),
    ]

    passed = 0
    for text, expected_dt, expected_repeat in cases:
        result = parse_time_expression(text, now=FIXED_NOW)
        ok = result is not None
        if ok and expected_dt is not None:
            ok = result["remind_at"] == expected_dt
        if ok and expected_repeat is not None:
            ok = result["repeat"] == expected_repeat
        status = "right" if ok else "wrong"
        got = result["remind_at"].strftime("%a %b %d %I:%M %p") if result else "None"
        got_repeat = result["repeat"] if result else "-"
        print(f"  {status} '{text}'  ->  {got}  [{got_repeat}]")
        if ok:
            passed += 1
        else:
            print(f"      Expected: {expected_dt}, repeat={expected_repeat}")

    print(f"\n  {passed}/{len(cases)} time-parsing cases passed.")
    assert passed == len(cases), "Time parsing has a bug — see failures above."

    # Ambiguous-hour resolution check (no am/pm given)
    print("\n--- Ambiguous Hour Resolution ('at 5' with no am/pm) ---")
    result = parse_time_expression("at 5", now=FIXED_NOW)
    print(f"  'at 5' at 2:30 PM ->  {result['remind_at'].strftime('%I:%M %p')}  (should be 5:00 PM — soonest future option)")
    assert result["remind_at"].hour == 17
    print("   Correctly picked 5 PM over 5 AM (which would already be in the past).")

    # Weekday-name repeat: verify it lands on the RIGHT weekday
    print("\n--- Weekly Repeat — Correct Weekday ---")
    result = parse_time_expression("every monday at 10am", now=FIXED_NOW)
    print(f"  'every monday at 10am' ->  {result['remind_at'].strftime('%A, %b %d, %I:%M %p')}")
    assert result["remind_at"].strftime("%A").lower() == "monday"
    assert result["remind_at"] > FIXED_NOW
    print("   Lands on a Monday, in the future.")

    print("\n--- Weekdays Repeat — Skips Weekend ---")
    result = parse_time_expression("every weekday at 9am", now=FIXED_NOW)
    print(f"  'every weekday at 9am' ->  {result['remind_at'].strftime('%A, %b %d, %I:%M %p')}")
    assert result["remind_at"].weekday() < 5
    print("   First occurrence falls on a weekday.")

    # ---- Smart full-sentence parsing ----
    print("\n--- Smart Full-Sentence Reminder Creation ---")
    import unittest.mock
    with unittest.mock.patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = FIXED_NOW
        mock_dt.strptime = datetime.datetime.strptime
        # (patching datetime.datetime globally is messy for this module's internal calls,
        #  so instead we test smart_add_reminder's content-stripping logic directly)

    test_sentences = [
        ("remind me to call mom at 5pm", "call mom"),
        ("remind me every day at 8am to take medicine", "take medicine"),
        ("remind me in 20 minutes to check the oven", "check the oven"),
        ("remind me to submit the report tomorrow at 9am", "submit the report"),
    ]
    for sentence, expected_content in test_sentences:
        result = smart_add_reminder(sentence)
        print(f"  '{sentence}'\n    -> {result}")
        assert f"'{expected_content}'" in result, (
            f"Content extraction bug! Expected '{expected_content}' in result, got: {result}"
        )
    print("   All reminder content correctly extracted — no missing letters.")
    print()

    # ---- CRUD ----
    print("--- CRUD Operations ---")
    if os.path.exists(REMINDERS_FILE):
        os.remove(REMINDERS_FILE)

    print(add_reminder("Test CRUD reminder", datetime.datetime.now() + datetime.timedelta(hours=1)))
    reminders = get_reminders()
    assert len(reminders) >= 1
    first_id = reminders[0]["id"]

    print(snooze_reminder(first_id, 5))
    print(mark_done(first_id))
    done_list = get_reminders(include_done=True)
    assert any(r["id"] == first_id and r["done"] for r in done_list)
    print("   Snooze and mark-done work correctly.")

    print(delete_reminder(first_id))
    remaining = get_reminders(include_done=True)
    assert not any(r["id"] == first_id for r in remaining)
    print("   Delete works correctly.")

    # ---- Pluggable actions + live scheduler test ----
    print("\n--- Pluggable Action + Live Scheduler ---")
    fired_log = []

    def _test_handler(params):
        fired_log.append(params)

    register_action("test_action", _test_handler)
    assert "test_action" in get_registered_actions()

    # Reminder due almost immediately, with an attached action
    due_soon = datetime.datetime.now() + datetime.timedelta(seconds=2)
    add_reminder("Scheduler live-fire test", due_soon,
                 action_type="test_action", action_params={"hello": "world"})

    start_scheduler(check_interval=1)
    print("  Waiting for the scheduler to fire the due reminder...")
    time.sleep(5)
    stop_scheduler()

    assert len(fired_log) == 1, f"Expected the action to fire exactly once, fired {len(fired_log)} times."
    assert fired_log[0] == {"hello": "world"}
    print(f"   Scheduler fired the reminder for real and called the registered action with: {fired_log[0]}")

    all_reminders = get_reminders(include_done=True)
    fired_reminder = next(r for r in all_reminders if r["content"] == "Scheduler live-fire test")
    assert fired_reminder["done"] is True, "One-time reminder should be marked done after firing."
    print("   One-time reminder correctly marked done after firing.")

    # ---- Repeat advancement check ----
    print("\n--- Repeat Advancement After Firing ---")
    past_daily = datetime.datetime.now() - datetime.timedelta(minutes=1)
    add_reminder("Daily repeat test", past_daily, repeat="daily")
    reminders = _load_json(REMINDERS_FILE, [])
    target = next(r for r in reminders if r["content"] == "Daily repeat test")
    fire_time = datetime.datetime.strptime(target["remind_at"], "%Y-%m-%d %H:%M:%S")
    _advance_repeat(target, fire_time)
    new_time = datetime.datetime.strptime(target["remind_at"], "%Y-%m-%d %H:%M:%S")
    assert (new_time - fire_time).days == 1
    assert target["done"] is False
    print(f"   Daily reminder correctly advanced by 1 day ({fire_time.date()} -> {new_time.date()}), still pending.")

    # ---- Cleanup ----
    if os.path.exists(REMINDERS_FILE):
        os.remove(REMINDERS_FILE)

    # ---- Dispatcher ----
    print("\n--- Dispatcher Tests ---\n")
    for cmd in ["show reminders", "reminder summary", "unknown gibberish command"]:
        print(f"  > {cmd}")
        handle_reminder_command(cmd)
        print()

    print(" Reminder Module Test Complete — every assertion passed!")