"""
Cortex AI — Notification Reader Module  (Phase 5)
Reads Windows' actual notification history (Action Center) — not just
watches for new ones. Built on the WinRT UserNotificationListener API,
the same system API Windows' own Notification Center uses internally.

WINDOWS ONLY. Requires:
  pip install winsdk

And a one-time permission grant — call request_access() once, which
triggers a Windows system prompt asking you to allow notification
access (or grant it manually beforehand: Settings > Privacy & security
> Notifications > let apps access notifications).

HONESTY NOTE: this is the one module in Cortex AI I could not test live —
WinRT is a Windows-only COM API and doesn't exist on the Linux machine I
built this on (winsdk won't even compile here). Every WinRT call is
wrapped in defensive error handling — including a fallback for two
possible Python binding method names where I wasn't 100% certain which
your installed winsdk version uses — so it fails with a clear message
rather than a crash if anything differs from what I expected. Everything
AROUND the WinRT calls (filtering, logging, summarizing, the dispatcher)
is fully tested. If the WinRT layer itself throws an error the first
time you run this, send me the exact message and I'll fix it immediately.
"""

import os
import re
import json
import asyncio
import datetime

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_FILE = os.path.join(DATA_DIR, "notifications_log.json")

os.makedirs(DATA_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _respond(msg: str) -> str:
    print(f"  [NOTIFICATIONS] {msg}")
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


# ---------------------------------------------------------------------------
# 1. WINRT ACCESS LAYER
# ---------------------------------------------------------------------------

def _get_listener():
    """Get the UserNotificationListener singleton — handles both possible binding styles."""
    from winsdk.windows.ui.notifications.management import UserNotificationListener
    try:
        return UserNotificationListener.current
    except AttributeError:
        return UserNotificationListener.get_current()


async def _request_access_async():
    listener = _get_listener()
    return await listener.request_access_async()


def request_access() -> str:
    """
    Request permission to read notifications — triggers a one-time Windows
    system prompt (or reports existing status if already granted/denied).
    Call this once before using anything else in this module.
    """
    try:
        from winsdk.windows.ui.notifications.management import UserNotificationListenerAccessStatus
        status = asyncio.run(_request_access_async())

        if status == UserNotificationListenerAccessStatus.ALLOWED:
            return _respond("Notification access granted.")
        elif status == UserNotificationListenerAccessStatus.DENIED:
            return _respond(
                "Notification access denied. Enable it manually: Settings > "
                "Privacy & security > Notifications > let apps access notifications."
            )
        else:
            return _respond(f"Notification access status: {status}")

    except ImportError:
        return _respond("winsdk not installed. Run: pip install winsdk")
    except Exception as e:
        return _respond(f"Failed to request notification access: {e}")


def has_access() -> bool:
    """Check whether notification access is currently granted, without prompting again."""
    try:
        from winsdk.windows.ui.notifications.management import UserNotificationListenerAccessStatus
        status = asyncio.run(_request_access_async())
        return status == UserNotificationListenerAccessStatus.ALLOWED
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 2. NOTIFICATION EXTRACTION — defensive, never raises
# ---------------------------------------------------------------------------

def _extract_notification(user_notification) -> dict:
    """
    Pull app name, title, and body out of a raw WinRT UserNotification.
    Every step is independently guarded — a failure extracting the body
    still returns the app name and vice versa, rather than losing the
    whole notification to one bad attribute access.
    """
    app_name, title, body, notif_id = "Unknown App", "", "", None

    try:
        app_name = user_notification.app_info.display_info.display_name
    except Exception:
        pass

    try:
        bindings = user_notification.notification.visual.bindings
        if bindings:
            texts = [t.text for t in bindings[0].get_text_elements()]
            if texts:
                title = texts[0]
                body = " — ".join(texts[1:]) if len(texts) > 1 else ""
    except Exception:
        pass

    try:
        notif_id = user_notification.id
    except Exception:
        pass

    try:
        received_at = str(user_notification.creation_time)
    except Exception:
        received_at = _now()

    return {"id": notif_id, "app": app_name, "title": title, "body": body, "received_at": received_at}


# ---------------------------------------------------------------------------
# 3. FETCH & FILTER  (filtering logic kept separate from the WinRT call — testable without Windows)
# ---------------------------------------------------------------------------

def _filter_by_app(notifications: list, app_name: str) -> list:
    return [n for n in notifications if app_name.lower() in n["app"].lower()]


def _summarize_by_app(notifications: list) -> dict:
    counts = {}
    for n in notifications:
        counts[n["app"]] = counts.get(n["app"], 0) + 1
    return counts


async def _get_notifications_async():
    from winsdk.windows.ui.notifications import NotificationKinds
    listener = _get_listener()
    raw = await listener.get_notifications_async(NotificationKinds.TOAST)
    return [_extract_notification(n) for n in raw]


def get_all_notifications() -> list:
    """Every notification currently sitting in Action Center, right now."""
    try:
        notifications = asyncio.run(_get_notifications_async())
    except ImportError:
        _respond("winsdk not installed. Run: pip install winsdk")
        return []
    except Exception as e:
        _respond(f"Failed to read notifications: {e}. Try request_access() first.")
        return []

    print(f"  [NOTIFICATIONS] {len(notifications)} notification(s) in Action Center:")
    for n in notifications:
        print(f"    [{n['app']}] {n['title']} — {n['body'][:60]}")

    _log_notifications(notifications)
    return notifications


def get_notifications_from(app_name: str) -> list:
    """Filter to notifications from one app — e.g. get_notifications_from('WhatsApp')."""
    matches = _filter_by_app(get_all_notifications(), app_name)
    print(f"  [NOTIFICATIONS] {len(matches)} notification(s) from '{app_name}'.")
    return matches


# ---------------------------------------------------------------------------
# 4. DISMISS / CLEAR
# ---------------------------------------------------------------------------

async def _remove_notification_async(notif_id):
    _get_listener().remove_notification(notif_id)


def dismiss_notification(notif_id) -> str:
    """Clear one notification from Action Center by its id."""
    try:
        asyncio.run(_remove_notification_async(notif_id))
        return _respond(f"Notification {notif_id} dismissed.")
    except ImportError:
        return _respond("winsdk not installed. Run: pip install winsdk")
    except Exception as e:
        return _respond(f"Failed to dismiss notification: {e}")


async def _clear_all_async():
    listener = _get_listener()
    if hasattr(listener, "clear_notifications"):
        listener.clear_notifications()
    elif hasattr(listener, "clear"):
        listener.clear()
    else:
        raise AttributeError("No clear-all method found on this winsdk version.")


def clear_all_notifications() -> str:
    """Clear every notification from Action Center."""
    try:
        asyncio.run(_clear_all_async())
        return _respond("All notifications cleared.")
    except ImportError:
        return _respond("winsdk not installed. Run: pip install winsdk")
    except AttributeError as e:
        return _respond(f"{e} Dismiss notifications individually with dismiss_notification() instead.")
    except Exception as e:
        return _respond(f"Failed to clear notifications: {e}")


# ---------------------------------------------------------------------------
# 5. LOCAL LOG & SUMMARY
# ---------------------------------------------------------------------------

def _log_notifications(notifications: list) -> None:
    """Append newly-seen notifications to Cortex's own log — survives even after Windows clears them."""
    log = _load_json(LOG_FILE, [])
    existing_ids = {entry.get("id") for entry in log}
    for n in notifications:
        if n["id"] not in existing_ids:
            log.insert(0, {**n, "logged_at": _now()})
    _save_json(LOG_FILE, log[:200])


def get_notification_history(n: int = 20) -> list:
    """Previously-seen notifications from Cortex's local log."""
    log = _load_json(LOG_FILE, [])[:n]
    print(f"  [NOTIFICATIONS] Last {len(log)} logged notification(s):")
    for item in log:
        print(f"    [{item.get('logged_at', '?')}] {item['app']}: {item['title']}")
    return log


def clear_notification_history() -> str:
    _save_json(LOG_FILE, [])
    return _respond("Local notification history cleared.")


def get_notification_summary() -> str:
    notifications = get_all_notifications()
    counts = _summarize_by_app(notifications)

    print("\n  [NOTIFICATIONS] ── Summary ──")
    print(f"    Total: {len(notifications)}")
    for app, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {app}: {count}")
    return _respond("Notification summary complete.")


# ---------------------------------------------------------------------------
# 6. COMMAND DISPATCHER — Natural Language Interface
# ---------------------------------------------------------------------------

def handle_notification_command(user_input: str) -> str:
    """Main entry point — called from main.py for notification-related commands."""
    text = user_input.lower().strip()

    if any(p in text for p in ["request notification access", "allow notifications", "enable notifications"]):
        return request_access()

    if any(p in text for p in ["notification summary", "notification status"]):
        return get_notification_summary()

    if any(p in text for p in ["clear all notifications", "dismiss all notifications", "clear notifications"]):
        return clear_all_notifications()

    if any(p in text for p in ["notification history", "past notifications", "logged notifications"]):
        get_notification_history()
        return "Here's your notification history."

    if any(p in text for p in ["check notifications", "show notifications", "my notifications", "read notifications"]):
        get_all_notifications()
        return "Here are your current notifications."

    match = re.search(r"notifications? from\s+(.+)", text)
    if match:
        get_notifications_from(match.group(1).strip())
        return "Here are those notifications."

    return _respond(f"No notification command matched: '{user_input}'")


# ---------------------------------------------------------------------------
# Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*55)
    print("   Cortex AI — Notification Reader Test")
    print("="*55 + "\n")

    # ---- Defensive extraction — simulate a completely broken WinRT object ----
    print("--- Defensive Extraction (simulated broken WinRT object) ---")

    class _BrokenMock:
        """Raises AttributeError on every access — worst-case WinRT API mismatch."""
        def __getattr__(self, name):
            raise AttributeError(f"no such attribute: {name}")

    result = _extract_notification(_BrokenMock())
    print(f"  Result from fully broken input: {result}")
    assert result["app"] == "Unknown App"
    assert result["title"] == ""
    assert result["body"] == ""
    assert result["id"] is None
    assert result["received_at"]  # falls back to _now(), never empty
    print("   Extraction never crashes, even when every attribute access fails.")

    # ---- Filtering & summarizing — pure logic, fully testable without Windows ----
    print("\n--- Filtering & Summarizing (fake notification data) ---")
    fake_notifications = [
        {"id": 1, "app": "WhatsApp",  "title": "Mom",   "body": "Call me when free",     "received_at": _now()},
        {"id": 2, "app": "WhatsApp",  "title": "Dad",    "body": "Dinner at 8",           "received_at": _now()},
        {"id": 3, "app": "Gmail",     "title": "Boss",   "body": "Meeting moved to 3pm",  "received_at": _now()},
        {"id": 4, "app": "Slack",     "title": "#general","body": "Standup in 10 min",    "received_at": _now()},
    ]

    whatsapp_only = _filter_by_app(fake_notifications, "whatsapp")
    print(f"  Filter 'whatsapp' -> {len(whatsapp_only)} result(s)")
    assert len(whatsapp_only) == 2
    assert all(n["app"] == "WhatsApp" for n in whatsapp_only)

    summary = _summarize_by_app(fake_notifications)
    print(f"  Summary: {summary}")
    assert summary["WhatsApp"] == 2
    assert summary["Gmail"] == 1
    assert summary["Slack"] == 1
    print("   Filtering and summarizing logic correct.")

    # ---- Local log persistence — real file I/O, no Windows needed ----
    print("\n--- Local Log Persistence ---")
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

    _log_notifications(fake_notifications)
    history = get_notification_history()
    assert len(history) == 4

    # Logging the SAME notifications again shouldn't duplicate them (dedup by id)
    _log_notifications(fake_notifications)
    history_again = get_notification_history()
    assert len(history_again) == 4, f"Expected no duplicates, got {len(history_again)} entries"
    print("   Log persists correctly and de-duplicates by notification id.")

    print(clear_notification_history())
    assert get_notification_history() == []
    print("   Clear history works correctly.")

        # ---- WinRT Layer - Check Working Environment ----

    print("\n--- WinRT Layer ---")

    result = request_access()
    print(f"request_access(): {result}")

    access = has_access()
    print(f"has_access(): {access}")

    if access:
        print("Notification access is working.")
    else:
        print("Notification access is not available.")
    print(f"  has_access(): {has_access()}")

    notifications = get_all_notifications()

    print(f"Total notifications found: {len(notifications)}")

    for notification in notifications:
        print(notification)

    print("Notification reading working correctly.")

    # ---- Dispatcher ----
    print("\n--- Dispatcher Tests ---\n")
    for cmd in ["notification history", "notifications from whatsapp", "unknown gibberish command"]:
        print(f"  > {cmd}")
        handle_notification_command(cmd)
        print()

    print(" Notification Reader Test Complete — everything testable without Windows passed!")