"""
Cortex AI — Browser Control Module
Full browser automation and intelligence layer for Cortex AI:
  - Multi-browser launch (Chrome, Firefox, Edge) — headless or visible
  - Navigation — open URL, back, forward, refresh, new/close/switch tab
  - Smart search — Google, YouTube, Wikipedia, Amazon, Bing, DuckDuckGo,
    GitHub, or Maps
  - DOM interaction — click, type, scroll, select, submit, hover
  - Smart waits — element presence, clickability, full page load
  - Content extraction — page text, title, links, images, element text
  - Screenshot capture — full page or a single element
  - Cookie-banner auto-dismiss
  - Download folder tracking
  - Alert / popup handling
  - Cortex-side browsing history (JSON — real browser history isn't
    reachable through automation, so Cortex keeps its own)
  - Custom bookmark manager
  - Tab manager — list, switch, close by index
  - Voice-friendly responses throughout
  - Natural language command dispatcher

Requires: pip install selenium
Also requires the matching browser to be installed — Selenium 4.6+
auto-manages the matching driver via Selenium Manager.
"""

import os
import re
import json
import time
import datetime
import urllib.parse

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
DATA_DIR       = os.path.join(BASE_DIR, "..", "data")
HISTORY_FILE   = os.path.join(DATA_DIR, "browser_history.json")
BOOKMARKS_FILE = os.path.join(DATA_DIR, "bookmarks.json")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "browser_screenshots")
DOWNLOAD_DIR   = os.path.join(os.path.expanduser("~"), "Downloads", "Cortex Downloads")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# One browser session per Cortex run
_driver = None
_current_browser_type = None

SEARCH_ENGINES: dict[str, str] = {
    "google":     "https://www.google.com/search?q={}",
    "youtube":    "https://www.youtube.com/results?search_query={}",
    "wikipedia":  "https://en.wikipedia.org/wiki/Special:Search?search={}",
    "amazon":     "https://www.amazon.com/s?k={}",
    "bing":       "https://www.bing.com/search?q={}",
    "duckduckgo": "https://duckduckgo.com/?q={}",
    "github":     "https://github.com/search?q={}",
    "maps":       "https://www.google.com/maps/search/{}",
}

COOKIE_BANNER_XPATHS: list[str] = [
    "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept all')]",
    "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
    "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'i agree')]",
    "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'allow all')]",
    "//button[@id='L2AGLb']",  # Google's "I agree"
]


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _respond(msg: str) -> str:
    print(f"  [BROWSER] {msg}")
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


def _log_history(url: str, title: str = "") -> None:
    history = _load_json(HISTORY_FILE, [])
    history.insert(0, {"url": url, "title": title, "visited_at": _now()})
    _save_json(HISTORY_FILE, history[:200])


def _resolve_by(by: str):
    """Map a friendly selector name to a Selenium By strategy."""
    from selenium.webdriver.common.by import By
    mapping = {
        "id": By.ID, "name": By.NAME, "class": By.CLASS_NAME,
        "css": By.CSS_SELECTOR, "xpath": By.XPATH,
        "text": By.LINK_TEXT, "tag": By.TAG_NAME,
    }
    return mapping.get(by.lower(), By.CSS_SELECTOR)


def wait_for_element(selector: str, by: str = "css", timeout: int = 10):
    """Block until an element is present in the DOM, then return it."""
    if _driver is None:
        raise RuntimeError("No active browser session. Call launch_browser() first.")
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    by_strategy = _resolve_by(by)
    return WebDriverWait(_driver, timeout).until(EC.presence_of_element_located((by_strategy, selector)))


# ---------------------------------------------------------------------------
# 1. BROWSER LAUNCH & LIFECYCLE
# ---------------------------------------------------------------------------

def launch_browser(browser: str = "chrome", headless: bool = False) -> str:
    """
    Launch a browser session. Reuses an existing one if already running.
    Supported: 'chrome', 'firefox', 'edge'.
    """
    global _driver, _current_browser_type

    if _driver is not None:
        return _respond(f"Browser already running ({_current_browser_type}). Call close_browser() first to switch.")

    browser = browser.lower().strip()
    try:
        from selenium import webdriver

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        if browser == "chrome":
            from selenium.webdriver.chrome.options import Options
            options = Options()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--start-maximized")
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            options.add_experimental_option("prefs", {"download.default_directory": DOWNLOAD_DIR})
            _driver = webdriver.Chrome(options=options)

        elif browser == "firefox":
            from selenium.webdriver.firefox.options import Options
            options = Options()
            if headless:
                options.add_argument("--headless")
            _driver = webdriver.Firefox(options=options)

        elif browser == "edge":
            from selenium.webdriver.edge.options import Options
            options = Options()
            if headless:
                options.add_argument("--headless=new")
            _driver = webdriver.Edge(options=options)

        else:
            return _respond(f"Unsupported browser: '{browser}'. Use chrome, firefox, or edge.")

        _current_browser_type = browser
        return _respond(f"{browser.title()} launched{' (headless)' if headless else ''}.")

    except ImportError:
        return _respond("Selenium not installed. Run: pip install selenium")
    except Exception as e:
        return _respond(
            f"Failed to launch {browser}: {e}. "
            f"Make sure {browser.title()} is installed (Selenium 4.6+ auto-manages the driver)."
        )


def close_browser() -> str:
    """Close the active browser session, if any."""
    global _driver, _current_browser_type
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        _driver.quit()
    except Exception:
        pass
    _driver = None
    _current_browser_type = None
    return _respond("Browser closed.")


def is_browser_running() -> bool:
    return _driver is not None


# ---------------------------------------------------------------------------
# 2. NAVIGATION
# ---------------------------------------------------------------------------

def open_url(url: str, new_tab_flag: bool = False) -> str:
    """Navigate to a URL. Auto-launches a browser if none is running yet."""
    if not url.startswith("http"):
        url = "https://" + url

    if _driver is None:
        result = launch_browser()
        if _driver is None:
            return result

    try:
        if new_tab_flag:
            _driver.execute_script(f"window.open('{url}', '_blank');")
            _driver.switch_to.window(_driver.window_handles[-1])
        _driver.get(url)
        time.sleep(1)
        title = _driver.title
        _log_history(url, title)
        return _respond(f"Opened: {title or url}")
    except Exception as e:
        return _respond(f"Failed to open {url}: {e}")


def go_back() -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    _driver.back()
    return _respond("Went back a page.")


def go_forward() -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    _driver.forward()
    return _respond("Went forward a page.")


def refresh_page() -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    _driver.refresh()
    return _respond("Page refreshed.")


def new_tab(url: str = None) -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    _driver.execute_script("window.open('about:blank', '_blank');")
    _driver.switch_to.window(_driver.window_handles[-1])
    return open_url(url) if url else _respond("New tab opened.")


def close_tab() -> str:
    global _driver
    if _driver is None:
        return _respond("No browser session is currently open.")
    _driver.close()
    handles = _driver.window_handles
    if handles:
        _driver.switch_to.window(handles[-1])
        return _respond("Tab closed.")
    _driver = None
    return _respond("Last tab closed — browser session ended.")


def list_tabs() -> list:
    if _driver is None:
        _respond("No browser session is currently open.")
        return []
    original = _driver.current_window_handle
    tabs = []
    for i, handle in enumerate(_driver.window_handles):
        _driver.switch_to.window(handle)
        tabs.append({"index": i, "title": _driver.title, "url": _driver.current_url, "active": handle == original})
    _driver.switch_to.window(original)
    print(f"  [BROWSER] {len(tabs)} open tab(s):")
    for t in tabs:
        print(f"    {'→' if t['active'] else ' '} [{t['index']}] {t['title']}")
    return tabs


def switch_tab(index: int) -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    handles = _driver.window_handles
    if 0 <= index < len(handles):
        _driver.switch_to.window(handles[index])
        return _respond(f"Switched to tab {index}: {_driver.title}")
    return _respond(f"Tab {index} does not exist.")


# ---------------------------------------------------------------------------
# 3. SMART SEARCH
# ---------------------------------------------------------------------------

def search(query: str, engine: str = "google") -> str:
    """Search using google, youtube, wikipedia, amazon, bing, duckduckgo, github, or maps."""
    engine = engine.lower().strip()
    template = SEARCH_ENGINES.get(engine)
    if not template:
        return _respond(f"Unknown search engine '{engine}'. Options: {', '.join(SEARCH_ENGINES)}")
    return open_url(template.format(urllib.parse.quote_plus(query)))


def google_search(query: str) -> str:
    return search(query, "google")


def youtube_search(query: str) -> str:
    return search(query, "youtube")


# ---------------------------------------------------------------------------
# 4. DOM INTERACTION
# ---------------------------------------------------------------------------

def click_element(selector: str, by: str = "css", timeout: int = 10) -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        el = WebDriverWait(_driver, timeout).until(EC.element_to_be_clickable((_resolve_by(by), selector)))
        el.click()
        return _respond(f"Clicked: {selector}")
    except Exception as e:
        return _respond(f"Click failed for '{selector}': {e}")


def type_text(selector: str, text: str, by: str = "css", clear_first: bool = True, submit: bool = False, timeout: int = 10) -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        from selenium.webdriver.common.keys import Keys
        el = wait_for_element(selector, by, timeout)
        if clear_first:
            el.clear()
        el.send_keys(text)
        if submit:
            el.send_keys(Keys.RETURN)
        return _respond(f"Typed into '{selector}'.")
    except Exception as e:
        return _respond(f"Type failed for '{selector}': {e}")


def scroll_page(direction: str = "down", amount: int = 500) -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    delta = amount if direction == "down" else -amount
    _driver.execute_script(f"window.scrollBy(0, {delta});")
    return _respond(f"Scrolled {direction}.")


def scroll_to_bottom() -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    _driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    return _respond("Scrolled to bottom of page.")


def select_dropdown(selector: str, value: str, by: str = "css", by_visible_text: bool = True) -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        from selenium.webdriver.support.ui import Select
        dropdown = Select(wait_for_element(selector, by))
        if by_visible_text:
            dropdown.select_by_visible_text(value)
        else:
            dropdown.select_by_value(value)
        return _respond(f"Selected '{value}' in dropdown.")
    except Exception as e:
        return _respond(f"Dropdown selection failed: {e}")


def submit_form(selector: str, by: str = "css") -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        wait_for_element(selector, by).submit()
        return _respond("Form submitted.")
    except Exception as e:
        return _respond(f"Submit failed: {e}")


def hover_element(selector: str, by: str = "css") -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(_driver).move_to_element(wait_for_element(selector, by)).perform()
        return _respond(f"Hovering over: {selector}")
    except Exception as e:
        return _respond(f"Hover failed: {e}")


# ---------------------------------------------------------------------------
# 5. COOKIE BANNER AUTO-DISMISS
# ---------------------------------------------------------------------------

def dismiss_cookie_banner() -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    from selenium.webdriver.common.by import By
    for xpath in COOKIE_BANNER_XPATHS:
        try:
            _driver.find_element(By.XPATH, xpath).click()
            return _respond("Cookie banner dismissed.")
        except Exception:
            continue
    return _respond("No cookie banner found (or already dismissed).")


# ---------------------------------------------------------------------------
# 6. CONTENT EXTRACTION
# ---------------------------------------------------------------------------

def get_page_title() -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    return _respond(f"Page title: {_driver.title}")


def get_page_text(max_chars: int = 3000) -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        from selenium.webdriver.common.by import By
        text = _driver.find_element(By.TAG_NAME, "body").text
        truncated = text[:max_chars]
        print(f"  [BROWSER] Page text ({len(text)} chars, showing first {len(truncated)}):\n{truncated}")
        return truncated
    except Exception as e:
        return _respond(f"Failed to extract text: {e}")


def get_current_url() -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    return _respond(f"Current URL: {_driver.current_url}")


def get_all_links() -> list:
    if _driver is None:
        _respond("No browser session is currently open.")
        return []
    from selenium.webdriver.common.by import By
    links = [
        {"text": e.text.strip(), "href": e.get_attribute("href")}
        for e in _driver.find_elements(By.TAG_NAME, "a") if e.get_attribute("href")
    ]
    print(f"  [BROWSER] Found {len(links)} link(s) on the page.")
    for l in links[:15]:
        print(f"    {l['text'][:40]:<40} → {l['href']}")
    return links


def get_all_images() -> list:
    if _driver is None:
        _respond("No browser session is currently open.")
        return []
    from selenium.webdriver.common.by import By
    images = [e.get_attribute("src") for e in _driver.find_elements(By.TAG_NAME, "img") if e.get_attribute("src")]
    print(f"  [BROWSER] Found {len(images)} image(s) on the page.")
    return images


def get_element_text(selector: str, by: str = "css") -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        text = wait_for_element(selector, by).text
        return _respond(f"Element text: {text}")
    except Exception as e:
        return _respond(f"Failed to get element text: {e}")


# ---------------------------------------------------------------------------
# 7. SCREENSHOTS
# ---------------------------------------------------------------------------

def take_screenshot(filename: str = None) -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    filename = filename or f"page_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = os.path.join(SCREENSHOT_DIR, filename)
    _driver.save_screenshot(path)
    return _respond(f"Screenshot saved: {path}")


def screenshot_element(selector: str, by: str = "css", filename: str = None) -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        el = wait_for_element(selector, by)
        filename = filename or f"element_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        el.screenshot(path)
        return _respond(f"Element screenshot saved: {path}")
    except Exception as e:
        return _respond(f"Element screenshot failed: {e}")


# ---------------------------------------------------------------------------
# 8. WAIT UTILITIES
# ---------------------------------------------------------------------------

def wait_for_page_load(timeout: int = 15) -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        from selenium.webdriver.support.ui import WebDriverWait
        WebDriverWait(_driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
        return _respond("Page fully loaded.")
    except Exception as e:
        return _respond(f"Page load wait timed out: {e}")


# ---------------------------------------------------------------------------
# 9. ALERT / POPUP HANDLING
# ---------------------------------------------------------------------------

def accept_alert() -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        alert = _driver.switch_to.alert
        text = alert.text
        alert.accept()
        return _respond(f"Alert accepted: '{text}'")
    except Exception as e:
        return _respond(f"No alert present: {e}")


def dismiss_alert() -> str:
    if _driver is None:
        return _respond("No browser session is currently open.")
    try:
        _driver.switch_to.alert.dismiss()
        return _respond("Alert dismissed.")
    except Exception as e:
        return _respond(f"No alert present: {e}")


# ---------------------------------------------------------------------------
# 10. BROWSING HISTORY (Cortex-side)
# ---------------------------------------------------------------------------

def get_history(n: int = 10) -> list:
    history = _load_json(HISTORY_FILE, [])[:n]
    print(f"  [BROWSER] Last {len(history)} visited page(s):")
    for h in history:
        print(f"    [{h['visited_at']}] {h['title'] or h['url']}")
    return history


def search_history(keyword: str) -> list:
    history = _load_json(HISTORY_FILE, [])
    keyword_lower = keyword.lower()
    matches = [h for h in history if keyword_lower in h["url"].lower() or keyword_lower in h.get("title", "").lower()]
    print(f"  [BROWSER] Found {len(matches)} match(es) in history for '{keyword}':")
    for m in matches[:10]:
        print(f"    {m['title'] or m['url']}")
    return matches


def clear_history() -> str:
    _save_json(HISTORY_FILE, [])
    return _respond("Browsing history cleared.")


# ---------------------------------------------------------------------------
# 11. BOOKMARK MANAGER
# ---------------------------------------------------------------------------

def add_bookmark(url: str, name: str = None, tag: str = "general") -> str:
    if not url.startswith("http"):
        url = "https://" + url
    bookmarks = _load_json(BOOKMARKS_FILE, [])
    bookmarks.append({
        "id":       (bookmarks[-1]["id"] + 1) if bookmarks else 1,
        "name":     name or url,
        "url":      url,
        "tag":      tag,
        "saved_at": _now(),
    })
    _save_json(BOOKMARKS_FILE, bookmarks)
    return _respond(f"Bookmarked: {name or url}")


def get_bookmarks(tag: str = None) -> list:
    bookmarks = _load_json(BOOKMARKS_FILE, [])
    if tag:
        bookmarks = [b for b in bookmarks if b.get("tag") == tag]
    print(f"  [BROWSER] {len(bookmarks)} bookmark(s):")
    for b in bookmarks:
        print(f"    [{b['id']}] {b['name']} — {b['url']}")
    return bookmarks


def open_bookmark(name_or_id) -> str:
    bookmarks = _load_json(BOOKMARKS_FILE, [])
    for b in bookmarks:
        if str(b["id"]) == str(name_or_id) or str(name_or_id).lower() in b["name"].lower():
            return open_url(b["url"])
    return _respond(f"Bookmark '{name_or_id}' not found.")


def delete_bookmark(bookmark_id: int) -> str:
    bookmarks = _load_json(BOOKMARKS_FILE, [])
    before = len(bookmarks)
    bookmarks = [b for b in bookmarks if b["id"] != bookmark_id]
    _save_json(BOOKMARKS_FILE, bookmarks)
    return _respond(f"Bookmark {bookmark_id} deleted.") if len(bookmarks) < before else _respond("Bookmark not found.")


# ---------------------------------------------------------------------------
# 12. DOWNLOADS
# ---------------------------------------------------------------------------

def get_recent_downloads(n: int = 10) -> list:
    if not os.path.exists(DOWNLOAD_DIR):
        _respond("No downloads yet.")
        return []
    files = sorted(
        (os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR)),
        key=os.path.getmtime, reverse=True
    )[:n]
    print(f"  [BROWSER] {len(files)} recent download(s):")
    for f in files:
        print(f"    - {f}")
    return files


# ---------------------------------------------------------------------------
# 13. STATUS REPORT
# ---------------------------------------------------------------------------

def get_browser_status() -> str:
    print("\n  [BROWSER] ── Browser Status ──")
    if _driver is None:
        print("    Session: Not running")
    else:
        print(f"    Session: Running ({_current_browser_type})")
        print(f"    Current URL: {_driver.current_url}")
        print(f"    Open tabs: {len(_driver.window_handles)}")
    print(f"    History entries: {len(_load_json(HISTORY_FILE, []))}")
    print(f"    Bookmarks saved: {len(_load_json(BOOKMARKS_FILE, []))}")
    return _respond("Browser status complete.")


# ---------------------------------------------------------------------------
# 14. COMMAND DISPATCHER — Natural Language Interface
# ---------------------------------------------------------------------------

def handle_browser_command(user_input: str) -> str:
    """Main entry point — called from main.py for browser-related commands."""
    text = user_input.lower().strip()

    exact_triggers = {
        "close browser":     close_browser,
        "quit browser":      close_browser,
        "go back":            go_back,
        "go forward":         go_forward,
        "refresh":            refresh_page,
        "reload":             refresh_page,
        "new tab":            new_tab,
        "close tab":          close_tab,
        "scroll to bottom":   scroll_to_bottom,
        "scroll down":        lambda: scroll_page("down"),
        "scroll up":          lambda: scroll_page("up"),
        "current url":        get_current_url,
        "what page am i on":  get_current_url,
        "page title":         get_page_title,
        "take a screenshot":  take_screenshot,
        "screenshot":         take_screenshot,
        "browser status":     get_browser_status,
    }
    for phrase in sorted(exact_triggers, key=len, reverse=True):
        if phrase in text:
            return exact_triggers[phrase]()

    if any(p in text for p in ["list tabs", "show tabs"]):
        list_tabs()
        return "Here are your open tabs."

    if any(p in text for p in ["show history", "browsing history"]):
        get_history()
        return "Here's your browsing history."

    if any(p in text for p in ["show bookmarks", "my bookmarks"]):
        get_bookmarks()
        return "Here are your bookmarks."

    if any(p in text for p in ["show downloads", "recent downloads"]):
        get_recent_downloads()
        return "Here are your recent downloads."

    match = re.search(r"search (?:for\s+)?(.+?)\s+on\s+(\w+)", text)
    if match:
        return search(match.group(1).strip(), match.group(2).strip())

    match = re.search(r"(?:search|google)\s+(.+)", text)
    if match:
        return search(match.group(1).strip(), "google")

    match = re.search(r"(?:open|go to|visit)\s+(.+)", text)
    if match:
        return open_url(match.group(1).strip())

    match = re.search(r"bookmark this(?:\s+as\s+(.+))?", text)
    if match and _driver:
        return add_bookmark(_driver.current_url, match.group(1))

    return _respond(f"No browser command matched: '{user_input}'")


# ---------------------------------------------------------------------------
# Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*55)
    print("   Cortex AI — Browser Control Test")
    print("="*55 + "\n")

    # ---- History Tracker ----
    print("--- History Tracker ---")
    _log_history("https://github.com/anthropics", "Anthropic on GitHub")
    _log_history("https://www.python.org", "Welcome to Python.org")
    _log_history("https://docs.python.org/3/", "Python Documentation")
    get_history()
    search_history("python")

    # ---- Bookmark Manager ----
    print("\n--- Bookmark Manager ---")
    print(add_bookmark("github.com/anthropics", name="Anthropic GitHub", tag="work"))
    print(add_bookmark("python.org", name="Python Home", tag="dev"))
    get_bookmarks()
    get_bookmarks(tag="dev")
    print(delete_bookmark(1))
    get_bookmarks()

    # ---- Selector Resolution ----
    print("\n--- Selector Resolution ---")
    for strategy in ["id", "css", "xpath", "class", "unknown"]:
        print(f"  {strategy:<10} → {_resolve_by(strategy)}")

    # ---- Status (no driver yet) ----
    print("\n--- Status (before launch) ---")
    get_browser_status()

    # ---- Attempt real browser launch ----
    print("\n--- Live Browser Attempt ---")
    result = launch_browser("chrome", headless=True)
    print(f"  Result: {result}")

    if is_browser_running():
        print("\n  ✅ Real browser session active — running live navigation test.")
        print(open_url("https://github.com"))
        print(get_page_title())
        get_current_url()
        get_all_links()
        print(take_screenshot("test_github.png"))
        print(add_bookmark(_driver.current_url if _driver else "github.com", "Live Test Bookmark"))
        print(close_browser())
    else:
        print("  ℹ️  No real browser available in this environment — "
              "confirmed the module fails gracefully instead of crashing.")

    # ---- Dispatcher Tests (driver-independent commands) ----
    print("\n--- Dispatcher Tests ---\n")
    for cmd in ["show history", "show bookmarks", "browser status", "unknown gibberish command"]:
        print(f"  > {cmd}")
        handle_browser_command(cmd)
        print()

    print("\n✅ Browser Control Test Complete!")
