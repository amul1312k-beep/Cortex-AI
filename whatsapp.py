"""
Cortex AI — WhatsApp Module
Automates your own personal WhatsApp account through WhatsApp Web — no
Business API, no Meta approval process, no Twilio, completely free.
Scan the QR code once; a persistent Chrome profile keeps you logged in
on every future run.

Capabilities:
  - Launch & persistent login (QR scan only needed the first time)
  - Send messages to any phone number directly, saved contact or not
  - Send messages to a saved contact or group by name
  - Send files, images, and documents as attachments
  - Bulk send to a list of numbers with rate-limit-friendly delay
  - Read recent chats and unread message counts
  - Local sent-message log
  - Debug helper for when WhatsApp updates their page layout
  - Natural language command dispatcher

Requires: pip install selenium  (same as browser_control.py)
Also requires Chrome installed and your phone nearby to scan the QR
code the first time you run this.

HONESTY NOTE: this automates the real WhatsApp Web page, not an
official API — WhatsApp can change their HTML at any time. Every
interaction here tries several known-good selectors in sequence and
fails with a clear message rather than a cryptic crash. If WhatsApp
ships a redesign and something stops working, call debug_dump_page()
to save the current page's HTML and find the new selector to swap in.
"""

import os
import re
import time
import json
import datetime
import urllib.parse

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "data")
PROFILE_DIR = os.path.join(DATA_DIR, "whatsapp_chrome_profile")
SENT_LOG    = os.path.join(DATA_DIR, "sent_whatsapp_log.json")
DEBUG_DIR   = os.path.join(DATA_DIR, "whatsapp_debug")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PROFILE_DIR, exist_ok=True)

_driver = None

# Multiple fallback selectors per UI element, tried in order — hedges
# against WhatsApp Web's HTML changing between versions.
SELECTORS: dict[str, list[tuple]] = {
    "logged_in_marker": [
        ("css", "#side"),
        ("css", "div[aria-label='Chat list']"),
        ("css", "div[data-testid='chat-list']"),
    ],
    "message_box": [
        ("css", "div[aria-label='Type a message']"),
        ("css", "div[title='Type a message']"),
        ("xpath", "//footer//div[@contenteditable='true']"),
    ],
    "send_button": [
        ("css", "button[aria-label='Send']"),
        ("xpath", "//button[@aria-label='Send']"),
        ("css", "span[data-icon='send']"),
    ],
    "search_box": [
        ("css", "div[aria-label='Search input textbox']"),
        ("css", "div[title='Search input textbox']"),
        ("xpath", "//div[@contenteditable='true'][@data-tab='3']"),
    ],
    "chat_list_item": [
        ("css", "div[aria-label='Chat list'] div[role='listitem']"),
        ("css", "#pane-side div[role='listitem']"),
    ],
    "unread_badge": [
        ("css", "span[aria-label*='unread message']"),
    ],
    "attach_button": [
        ("css", "span[data-icon='attach-menu-plus']"),
        ("css", "span[data-icon='clip']"),
        ("xpath", "//div[@title='Attach']"),
    ],
    "file_input": [
        ("css", "input[type='file'][accept*='image']"),
        ("css", "input[type='file']"),
    ],
}


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _respond(msg: str) -> str:
    print(f"  [WHATSAPP] {msg}")
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


def _log_sent(to: str, message: str) -> None:
    log = _load_json(SENT_LOG, [])
    log.insert(0, {"to": to, "message": message[:200], "sent_at": _now()})
    _save_json(SENT_LOG, log[:100])


def _normalize_phone(phone: str) -> str:
    """'+91 98765-43210' -> '919876543210' — WhatsApp's URL scheme wants digits only."""
    return re.sub(r"[^\d]", "", phone)


def _find_first(selector_key: str, timeout: int = 10):
    """Try every known selector for this element until one is found. Raises if none work."""
    if _driver is None:
        raise RuntimeError("No active WhatsApp session. Call launch_whatsapp() first.")

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    by_map = {"css": By.CSS_SELECTOR, "xpath": By.XPATH}
    options = SELECTORS[selector_key]
    per_attempt_timeout = max(1, timeout // len(options))

    for strategy, selector in options:
        try:
            return WebDriverWait(_driver, per_attempt_timeout).until(
                EC.presence_of_element_located((by_map[strategy], selector))
            )
        except Exception:
            continue

    raise RuntimeError(
        f"Could not find '{selector_key}' on the page — WhatsApp Web's layout may have "
        f"changed. Call debug_dump_page() to inspect and update the selector."
    )


# ---------------------------------------------------------------------------
# 1. LAUNCH, LOGIN & LIFECYCLE
# ---------------------------------------------------------------------------

def launch_whatsapp(headless: bool = False) -> str:
    """Open WhatsApp Web with a persistent profile so you only scan the QR code once, ever."""
    global _driver
    if _driver is not None:
        return _respond("WhatsApp session already running.")

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        options = Options()
        options.add_argument(f"--user-data-dir={PROFILE_DIR}")
        options.add_argument("--profile-directory=Default")
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])

        _driver = webdriver.Chrome(options=options)
        _driver.get("https://web.whatsapp.com")
        return _respond("WhatsApp Web opened.")

    except ImportError:
        return _respond("Selenium not installed. Run: pip install selenium")
    except Exception as e:
        return _respond(f"Failed to launch WhatsApp: {e}")


def is_logged_in() -> bool:
    if _driver is None:
        return False
    from selenium.webdriver.common.by import By
    by_map = {"css": "css selector", "xpath": "xpath"}
    for strategy, selector in SELECTORS["logged_in_marker"]:
        try:
            by = By.CSS_SELECTOR if strategy == "css" else By.XPATH
            if _driver.find_elements(by, selector):
                return True
        except Exception:
            continue
    return False


def wait_for_login(timeout: int = 60) -> str:
    """Blocks until you scan the QR code (first run only) or confirms you're already in."""
    if _driver is None:
        return _respond("No WhatsApp session running. Call launch_whatsapp() first.")

    if is_logged_in():
        return _respond("Already logged in.")

    _respond(f"Scan the QR code with your phone now — waiting up to {timeout} seconds...")
    start = time.time()
    while time.time() - start < timeout:
        if is_logged_in():
            return _respond("Logged in! This session stays linked for future runs — no need to scan again.")
        time.sleep(2)

    return _respond("Timed out waiting for login. Call wait_for_login() again if you need more time.")


def close_whatsapp() -> str:
    global _driver
    if _driver is None:
        return _respond("No WhatsApp session is currently open.")
    try:
        _driver.quit()
    except Exception:
        pass
    _driver = None
    return _respond("WhatsApp session closed.")


def _ensure_ready() -> bool:
    """Auto-launch and wait for login if no session is active yet. Returns True if ready to use."""
    if _driver is None:
        launch_whatsapp()
        if _driver is None:
            return False
    if not is_logged_in():
        wait_for_login()
    return is_logged_in()


# ---------------------------------------------------------------------------
# 2. SEND MESSAGES
# ---------------------------------------------------------------------------

def send_message(phone: str, message: str, wait_for_load: int = 15) -> str:
    """
    Send a message to any phone number — saved contact or not.
    phone: include country code, e.g. '+91 98765 43210' or '919876543210'.
    """
    if not _ensure_ready():
        return _respond("Could not establish a logged-in WhatsApp session.")

    try:
        digits = _normalize_phone(phone)
        if not digits:
            return _respond(f"'{phone}' doesn't look like a valid phone number.")

        encoded_msg = urllib.parse.quote(message)
        _driver.get(f"https://web.whatsapp.com/send?phone={digits}&text={encoded_msg}")

        _find_first("message_box", timeout=wait_for_load)
        send_btn = _find_first("send_button", timeout=5)
        send_btn.click()
        time.sleep(1)

        _log_sent(phone, message)
        return _respond(f"Message sent to {phone}.")

    except RuntimeError as e:
        return _respond(
            f"{e} This can also mean that number isn't on WhatsApp, or the chat "
            f"didn't load in time — try increasing wait_for_load."
        )
    except Exception as e:
        return _respond(f"Failed to send message: {e}")


def send_to_contact(name: str, message: str) -> str:
    """Send to a saved contact or group by its display name (partial match works)."""
    if not _ensure_ready():
        return _respond("Could not establish a logged-in WhatsApp session.")

    try:
        search_box = _find_first("search_box", timeout=10)
        search_box.click()
        search_box.send_keys(name)
        time.sleep(1.5)  # let search results render

        from selenium.webdriver.common.by import By
        results = _driver.find_elements(By.CSS_SELECTOR, "#pane-side div[role='listitem']")
        if not results:
            return _respond(f"No chat found matching '{name}'.")

        results[0].click()
        time.sleep(1)

        message_box = _find_first("message_box", timeout=10)
        message_box.click()
        message_box.send_keys(message)

        send_btn = _find_first("send_button", timeout=5)
        send_btn.click()

        _log_sent(name, message)
        return _respond(f"Message sent to '{name}'.")

    except Exception as e:
        return _respond(f"Failed to send to '{name}': {e}")


def send_bulk(recipients: list, message: str, delay_between: int = 3) -> str:
    """Send the same message to multiple numbers, with a delay between each."""
    sent, failed = [], []
    for phone in recipients:
        result = send_message(phone, message)
        (sent if "sent to" in result.lower() else failed).append(phone)
        time.sleep(delay_between)

    print(f"  [WHATSAPP] Bulk send complete: {len(sent)} sent, {len(failed)} failed.")
    if failed:
        print(f"    Failed: {', '.join(failed)}")
    return _respond(f"Bulk send: {len(sent)}/{len(recipients)} delivered successfully.")


# ---------------------------------------------------------------------------
# 3. SEND FILES / ATTACHMENTS
# ---------------------------------------------------------------------------

def send_file(phone_or_name: str, file_path: str, caption: str = "", by_number: bool = True) -> str:
    """Send a file/image/document. Set by_number=False to target a saved contact/group name."""
    if not os.path.exists(file_path):
        return _respond(f"File not found: {file_path}")

    if not _ensure_ready():
        return _respond("Could not establish a logged-in WhatsApp session.")

    try:
        if by_number:
            digits = _normalize_phone(phone_or_name)
            _driver.get(f"https://web.whatsapp.com/send?phone={digits}")
            _find_first("message_box", timeout=15)
        else:
            search_box = _find_first("search_box", timeout=10)
            search_box.click()
            search_box.send_keys(phone_or_name)
            time.sleep(1.5)
            from selenium.webdriver.common.by import By
            results = _driver.find_elements(By.CSS_SELECTOR, "#pane-side div[role='listitem']")
            if not results:
                return _respond(f"No chat found matching '{phone_or_name}'.")
            results[0].click()
            time.sleep(1)

        attach_btn = _find_first("attach_button", timeout=10)
        attach_btn.click()
        time.sleep(0.5)

        file_input = _find_first("file_input", timeout=5)
        file_input.send_keys(os.path.abspath(file_path))
        time.sleep(2)  # let the preview render

        if caption:
            caption_box = _find_first("message_box", timeout=5)
            caption_box.send_keys(caption)

        send_btn = _find_first("send_button", timeout=10)
        send_btn.click()

        _log_sent(phone_or_name, f"[file] {os.path.basename(file_path)}")
        return _respond(f"File sent to {phone_or_name}: {os.path.basename(file_path)}")

    except Exception as e:
        return _respond(f"Failed to send file: {e}")


# ---------------------------------------------------------------------------
# 4. READ CHATS
# ---------------------------------------------------------------------------

def get_recent_chats(n: int = 10) -> list:
    if _driver is None or not is_logged_in():
        _respond("No active, logged-in WhatsApp session.")
        return []
    try:
        from selenium.webdriver.common.by import By
        chats = _driver.find_elements(By.CSS_SELECTOR, "#pane-side div[role='listitem']")[:n]
        results = []
        for chat in chats:
            try:
                name = chat.find_element(By.CSS_SELECTOR, "span[title]").get_attribute("title")
            except Exception:
                name = "(unknown)"
            results.append({"name": name})

        print(f"  [WHATSAPP] {len(results)} recent chat(s):")
        for r in results:
            print(f"    - {r['name']}")
        return results
    except Exception as e:
        _respond(f"Failed to list chats: {e}")
        return []


def get_unread_chats() -> list:
    if _driver is None or not is_logged_in():
        _respond("No active, logged-in WhatsApp session.")
        return []
    try:
        from selenium.webdriver.common.by import By
        chats = _driver.find_elements(By.CSS_SELECTOR, "#pane-side div[role='listitem']")
        unread = []
        for chat in chats:
            badges = chat.find_elements(By.CSS_SELECTOR, "span[aria-label*='unread message']")
            if badges:
                try:
                    name = chat.find_element(By.CSS_SELECTOR, "span[title]").get_attribute("title")
                except Exception:
                    name = "(unknown)"
                unread.append({"name": name, "unread_count": badges[0].text or "1+"})

        print(f"  [WHATSAPP] {len(unread)} unread chat(s):")
        for u in unread:
            print(f"    {u['name']} — {u['unread_count']} unread")
        return unread
    except Exception as e:
        _respond(f"Failed to check unread chats: {e}")
        return []


# ---------------------------------------------------------------------------
# 5. SENT LOG
# ---------------------------------------------------------------------------

def get_sent_log(n: int = 10) -> list:
    log = _load_json(SENT_LOG, [])[:n]
    print(f"  [WHATSAPP] Last {len(log)} sent message(s):")
    for item in log:
        print(f"    [{item['sent_at']}] To: {item['to']} — {item['message']}")
    return log


# ---------------------------------------------------------------------------
# 6. DEBUG HELPER
# ---------------------------------------------------------------------------

def debug_dump_page(filename: str = None) -> str:
    """Save the current page's HTML — use this to find updated selectors if WhatsApp's UI changes."""
    if _driver is None:
        return _respond("No WhatsApp session running.")
    os.makedirs(DEBUG_DIR, exist_ok=True)
    filename = filename or f"page_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    path = os.path.join(DEBUG_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_driver.page_source)
    return _respond(f"Page source saved to: {path}")


# ---------------------------------------------------------------------------
# 7. COMMAND DISPATCHER — Natural Language Interface
# ---------------------------------------------------------------------------

def handle_whatsapp_command(user_input: str) -> str:
    """Main entry point — called from main.py for WhatsApp-related commands."""
    text = user_input.lower().strip()

    if any(p in text for p in ["open whatsapp", "launch whatsapp", "start whatsapp"]):
        result = launch_whatsapp()
        wait_for_login()
        return result

    if any(p in text for p in ["close whatsapp", "quit whatsapp"]):
        return close_whatsapp()

    if any(p in text for p in ["unread whatsapp", "whatsapp unread", "check whatsapp"]):
        get_unread_chats()
        return "Here are your unread WhatsApp chats."

    if any(p in text for p in ["recent whatsapp", "recent chats", "show whatsapp chats"]):
        get_recent_chats()
        return "Here are your recent WhatsApp chats."

    if any(p in text for p in ["sent whatsapp", "whatsapp history", "messages i sent",
                                "sent messages", "show sent", "sent log"]):
        get_sent_log()
        return "Here are your recently sent WhatsApp messages."

    match = re.search(r"(?:send|message)\s+(\+?\d[\d\s-]{6,})\s+(?:on whatsapp\s+)?(?:saying|that says|:)\s+(.+)", text)
    if match:
        return send_message(match.group(1).strip(), match.group(2).strip())

    match = re.search(r"whatsapp\s+(.+?)\s+(?:saying|that says|:)\s+(.+)", text)
    if match:
        return send_to_contact(match.group(1).strip(), match.group(2).strip())

    return _respond(f"No WhatsApp command matched: '{user_input}'")


# ---------------------------------------------------------------------------
# Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*55)
    print("   Cortex AI — WhatsApp Module Test")
    print("="*55 + "\n")

    print("--- Phone Number Normalization ---")
    test_cases = [
        ("+91 98765 43210", "919876543210"),
        ("(555) 123-4567", "5551234567"),
        ("91-9876-543-210", "919876543210"),
    ]
    for raw, expected in test_cases:
        result = _normalize_phone(raw)
        status = "" if result == expected else "❌"
        print(f"  {status} '{raw}' -> '{result}' (expected '{expected}')")
        assert result == expected, f"Normalization failed for {raw}"

    print("\n--- URL / Message Encoding ---")
    msg = "Hey! Are we still on for 3pm? "
    encoded = urllib.parse.quote(msg)
    decoded_back = urllib.parse.unquote(encoded)
    print(f"  Original: {msg}")
    print(f"  Encoded:  {encoded}")
    assert decoded_back == msg, "Encode/decode round-trip failed"
    print("   Round-trip encoding correct.")

    print("\n--- Sent Log Persistence ---")
    _log_sent("+919876543210", "Test message 1")
    _log_sent("Mom", "Test message 2")
    log = get_sent_log()
    assert len(log) == 2
    assert log[0]["to"] == "Mom"  # most recent first
    print("   Sent log persistence correct.")

    print("\n--- Session State (no driver yet) ---")
    print(f"  is_logged_in(): {is_logged_in()}")
    assert is_logged_in() == False

    print("\n--- Live Launch Attempt ---")
    result = launch_whatsapp()
    print(f"  Result: {result}")
    if _driver is None:
        print("   No real browser available in this environment — "
              "confirmed the module fails gracefully instead of crashing.")

    print("\n--- Dispatcher Tests (session-independent) ---\n")
    for cmd in ["show sent messages", "unknown gibberish command"]:
        print(f"  > {cmd}")
        result = handle_whatsapp_command(cmd)
        print()
        if cmd == "show sent messages":
            assert "No WhatsApp command matched" not in result, f"Dispatcher gap: '{cmd}' should have matched!"
    print("   Dispatcher correctly handles natural phrasing.")

    print("\n--- Dispatcher Regex Matching (pattern only, no send) ---")
    dispatcher_tests = [
        ("send 919876543210 saying hello there", "phone-based send pattern"),
        ("whatsapp Mom saying I'll be late", "contact-name send pattern"),
    ]
    for cmd, desc in dispatcher_tests:
        text = cmd.lower()
        m1 = re.search(r"(?:send|message)\s+(\+?\d[\d\s-]{6,})\s+(?:on whatsapp\s+)?(?:saying|that says|:)\s+(.+)", text)
        m2 = re.search(r"whatsapp\s+(.+?)\s+(?:saying|that says|:)\s+(.+)", text)
        match = m1 or m2
        if match:
            print(f"   '{cmd}' -> matched: {match.groups()}  ({desc})")
        else:
            print(f"   '{cmd}' -> no match  ({desc})")

    print("\n WhatsApp Module Test Complete!")
