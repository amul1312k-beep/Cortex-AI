"""
Cortex AI — Advanced System Control Module
Handles every aspect of OS control:
  - Volume, Brightness, Screenshot
  - Power (shutdown, restart, sleep, lock, hibernate)
  - Window Management
  - Process Manager
  - Clipboard Manager
  - File & Folder Operations
  - Wi-Fi & Network Info
  - Mouse & Keyboard Automation
  - System Health (CPU, RAM, Battery, Disk)
  - Date & Time
  - Voice-friendly response strings
"""

import os
import sys
import subprocess
import platform
import shutil
import socket
import datetime
import ctypes
import time

import psutil
import pyautogui
import pygetwindow as gw

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SYSTEM         = platform.system()          # Windows / Darwin / Linux
pyautogui.FAILSAFE = True                   # Move mouse to corner to abort
SCREENSHOT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "Cortex Screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _run(cmd: str) -> str:
    """Run a shell command silently and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _respond(msg: str) -> str:
    """Print and return a voice-friendly response string."""
    print(f"  [SYSTEM] {msg}")
    return msg


# ---------------------------------------------------------------------------
# 1. SCREENSHOT
# ---------------------------------------------------------------------------

def take_screenshot(region=None) -> str:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SCREENSHOT_DIR, f"screenshot_{timestamp}.png")
    shot = pyautogui.screenshot(region=region)
    shot.save(path)
    return _respond(f"Screenshot saved to Desktop in Cortex Screenshots folder.")


def take_region_screenshot(x: int, y: int, width: int, height: int) -> str:
    return take_screenshot(region=(x, y, width, height))


# ---------------------------------------------------------------------------
# 2. VOLUME CONTROL
# ---------------------------------------------------------------------------

def volume_up(steps: int = 5) -> str:
    for _ in range(steps):
        pyautogui.press("volumeup")
    return _respond(f"Volume increased.")


def volume_down(steps: int = 5) -> str:
    for _ in range(steps):
        pyautogui.press("volumedown")
    return _respond(f"Volume decreased.")


def volume_mute() -> str:
    pyautogui.press("volumemute")
    return _respond("Volume muted.")


def volume_unmute() -> str:
    pyautogui.press("volumemute")
    return _respond("Volume unmuted.")


# ---------------------------------------------------------------------------
# 3. BRIGHTNESS CONTROL
# ---------------------------------------------------------------------------

def brightness_up(amount: int = 10) -> str:
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness(display=0)[0]
        new_val = min(100, current + amount)
        sbc.set_brightness(new_val, display=0)
        return _respond(f"Brightness increased to {new_val} percent.")
    except ImportError:
        return _respond("Please install screen-brightness-control: pip install screen-brightness-control")


def brightness_down(amount: int = 10) -> str:
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness(display=0)[0]
        new_val = max(0, current - amount)
        sbc.set_brightness(new_val, display=0)
        return _respond(f"Brightness decreased to {new_val} percent.")
    except ImportError:
        return _respond("Please install screen-brightness-control.")


def set_brightness(level: int) -> str:
    try:
        import screen_brightness_control as sbc
        level = max(0, min(100, level))
        sbc.set_brightness(level, display=0)
        return _respond(f"Brightness set to {level} percent.")
    except ImportError:
        return _respond("Please install screen-brightness-control.")


def get_brightness() -> str:
    try:
        import screen_brightness_control as sbc
        level = sbc.get_brightness(display=0)[0]
        return _respond(f"Current brightness is {level} percent.")
    except ImportError:
        return _respond("screen-brightness-control not installed.")


# ---------------------------------------------------------------------------
# 4. POWER CONTROL
# ---------------------------------------------------------------------------

def shutdown(delay: int = 0) -> str:
    if SYSTEM == "Windows":
        os.system(f"shutdown /s /t {delay}")
    else:
        os.system("sudo shutdown now")
    return _respond(f"Shutting down in {delay} seconds.")


def restart(delay: int = 0) -> str:
    if SYSTEM == "Windows":
        os.system(f"shutdown /r /t {delay}")
    else:
        os.system("sudo reboot")
    return _respond(f"Restarting in {delay} seconds.")


def sleep() -> str:
    if SYSTEM == "Windows":
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    elif SYSTEM == "Darwin":
        os.system("pmset sleepnow")
    else:
        os.system("systemctl suspend")
    return _respond("Going to sleep.")


def hibernate() -> str:
    if SYSTEM == "Windows":
        os.system("shutdown /h")
    return _respond("Hibernating now.")


def lock() -> str:
    if SYSTEM == "Windows":
        ctypes.windll.user32.LockWorkStation()
    elif SYSTEM == "Darwin":
        os.system("/System/Library/CoreServices/Menu\ Extras/User.menu/Contents/Resources/CGSession -suspend")
    else:
        os.system("gnome-screensaver-command -l")
    return _respond("Screen locked.")


def cancel_shutdown() -> str:
    if SYSTEM == "Windows":
        os.system("shutdown /a")
    return _respond("Shutdown cancelled.")


def log_off() -> str:
    if SYSTEM == "Windows":
        os.system("shutdown /l")
    return _respond("Logging off.")


# ---------------------------------------------------------------------------
# 5. WINDOW MANAGEMENT
# ---------------------------------------------------------------------------

def minimize_window() -> str:
    try:
        w = gw.getActiveWindow()
        if w:
            w.minimize()
            return _respond(f"Minimized: {w.title}")
        return _respond("No active window found.")
    except Exception as e:
        return _respond(f"Error: {e}")


def maximize_window() -> str:
    try:
        w = gw.getActiveWindow()
        if w:
            w.maximize()
            return _respond(f"Maximized: {w.title}")
        return _respond("No active window found.")
    except Exception as e:
        return _respond(f"Error: {e}")


def close_window() -> str:
    try:
        w = gw.getActiveWindow()
        if w:
            title = w.title
            w.close()
            return _respond(f"Closed window: {title}")
        return _respond("No active window found.")
    except Exception as e:
        return _respond(f"Error: {e}")


def list_windows() -> str:
    try:
        windows = [w.title for w in gw.getAllWindows() if w.title.strip()]
        print("  [SYSTEM] Open windows:")
        for w in windows:
            print(f"    - {w}")
        return f"Found {len(windows)} open windows."
    except Exception as e:
        return _respond(f"Error: {e}")


def focus_window(title_keyword: str) -> str:
    try:
        matches = gw.getWindowsWithTitle(title_keyword)
        if matches:
            matches[0].activate()
            return _respond(f"Focused: {matches[0].title}")
        return _respond(f"No window found with: {title_keyword}")
    except Exception as e:
        return _respond(f"Error: {e}")


# ---------------------------------------------------------------------------
# 6. PROCESS MANAGER
# ---------------------------------------------------------------------------

def list_processes(top: int = 10) -> str:
    procs = sorted(
        psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']),
        key=lambda p: p.info['memory_percent'] or 0,
        reverse=True
    )
    print(f"  [SYSTEM] Top {top} processes by memory:")
    for p in procs[:top]:
        print(f"    PID {p.info['pid']:>6} | {p.info['name']:<30} | RAM: {p.info['memory_percent']:>5.1f}%")
    return f"Showing top {top} processes."


def kill_process(name: str) -> str:
    killed = []
    for proc in psutil.process_iter(['name', 'pid']):
        if name.lower() in proc.info['name'].lower():
            try:
                proc.kill()
                killed.append(proc.info['name'])
            except Exception:
                pass
    if killed:
        return _respond(f"Killed: {', '.join(killed)}")
    return _respond(f"No process found: {name}")


def kill_process_by_pid(pid: int) -> str:
    try:
        p = psutil.Process(pid)
        name = p.name()
        p.kill()
        return _respond(f"Killed {name} (PID {pid}).")
    except Exception as e:
        return _respond(f"Failed to kill PID {pid}: {e}")


def is_process_running(name: str) -> str:
    for proc in psutil.process_iter(['name']):
        if name.lower() in proc.info['name'].lower():
            return _respond(f"{name} is running.")
    return _respond(f"{name} is not running.")


# ---------------------------------------------------------------------------
# 7. CLIPBOARD MANAGER
# ---------------------------------------------------------------------------

def copy_to_clipboard(text: str) -> str:
    try:
        import pyperclip
        pyperclip.copy(text)
        return _respond("Copied to clipboard.")
    except ImportError:
        if SYSTEM == "Windows":
            subprocess.run("clip", input=text.encode(), check=True)
            return _respond("Copied to clipboard.")
        return _respond("Install pyperclip: pip install pyperclip")


def get_clipboard() -> str:
    try:
        import pyperclip
        content = pyperclip.paste()
        print(f"  [SYSTEM] Clipboard: '{content}'")
        return f"Clipboard contains: {content}"
    except ImportError:
        return _respond("Install pyperclip: pip install pyperclip")


def clear_clipboard() -> str:
    try:
        import pyperclip
        pyperclip.copy("")
        return _respond("Clipboard cleared.")
    except ImportError:
        return _respond("Install pyperclip: pip install pyperclip")


# ---------------------------------------------------------------------------
# 8. FILE & FOLDER OPERATIONS
# ---------------------------------------------------------------------------

def open_folder(path: str) -> str:
    if os.path.exists(path):
        if SYSTEM == "Windows":
            os.startfile(path)
        elif SYSTEM == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
        return _respond(f"Opened folder: {path}")
    return _respond(f"Folder not found: {path}")


def open_file(path: str) -> str:
    if os.path.exists(path):
        if SYSTEM == "Windows":
            os.startfile(path)
        elif SYSTEM == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
        return _respond(f"Opened: {path}")
    return _respond(f"File not found: {path}")


def create_folder(name: str, path: str = ".") -> str:
    full_path = os.path.join(path, name)
    os.makedirs(full_path, exist_ok=True)
    return _respond(f"Folder created: {full_path}")


def delete_file(path: str, confirm: bool = True) -> str:
    if not os.path.exists(path):
        return _respond(f"Not found: {path}")
    if confirm:
        answer = input(f"  Delete '{path}'? (yes/no): ")
        if answer.lower() != "yes":
            return _respond("Deletion cancelled.")
    try:
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        return _respond(f"Deleted: {path}")
    except Exception as e:
        return _respond(f"Failed: {e}")


def rename_file(old_path: str, new_name: str) -> str:
    try:
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        os.rename(old_path, new_path)
        return _respond(f"Renamed to: {new_name}")
    except Exception as e:
        return _respond(f"Rename failed: {e}")


def copy_file(src: str, dst: str) -> str:
    try:
        shutil.copy2(src, dst)
        return _respond(f"Copied to: {dst}")
    except Exception as e:
        return _respond(f"Copy failed: {e}")


def move_file(src: str, dst: str) -> str:
    try:
        shutil.move(src, dst)
        return _respond(f"Moved to: {dst}")
    except Exception as e:
        return _respond(f"Move failed: {e}")


def list_files(path: str = ".") -> str:
    try:
        files = os.listdir(path)
        print(f"  [SYSTEM] Files in '{path}':")
        for f in files:
            print(f"    - {f}")
        return f"Found {len(files)} items in {path}."
    except Exception as e:
        return _respond(f"Error: {e}")


def get_disk_usage(path: str = None) -> str:
    if path is None:
        path = "C:/" if SYSTEM == "Windows" else "/"
    usage = shutil.disk_usage(path)
    total = usage.total / (1024 ** 3)
    used  = usage.used  / (1024 ** 3)
    free  = usage.free  / (1024 ** 3)
    return _respond(f"Disk — Total: {total:.1f} GB, Used: {used:.1f} GB, Free: {free:.1f} GB.")


# ---------------------------------------------------------------------------
# 9. NETWORK & WI-FI
# ---------------------------------------------------------------------------

def get_ip_address() -> str:
    try:
        ip = socket.gethostbyname(socket.gethostname())
        return _respond(f"Your IP address is {ip}.")
    except Exception as e:
        return _respond(f"Could not get IP: {e}")


def get_wifi_name() -> str:
    if SYSTEM == "Windows":
        result = _run("netsh wlan show interfaces")
        for line in result.splitlines():
            if "SSID" in line and "BSSID" not in line:
                ssid = line.split(":", 1)[1].strip()
                return _respond(f"Connected to Wi-Fi: {ssid}")
        return _respond("Not connected to any Wi-Fi.")
    elif SYSTEM == "Darwin":
        result = _run("/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I")
        for line in result.splitlines():
            if " SSID" in line:
                return _respond(f"Connected to: {line.split(':')[1].strip()}")
    return _respond("Wi-Fi info not available on this OS.")


def get_network_speed() -> str:
    net1 = psutil.net_io_counters()
    time.sleep(1)
    net2 = psutil.net_io_counters()
    sent = (net2.bytes_sent - net1.bytes_sent) / 1024
    recv = (net2.bytes_recv - net1.bytes_recv) / 1024
    return _respond(f"Upload: {sent:.1f} KB/s | Download: {recv:.1f} KB/s.")


def ping(host: str = "google.com") -> str:
    param = "-n" if SYSTEM == "Windows" else "-c"
    result = _run(f"ping {param} 1 {host}")
    if "TTL" in result or "bytes from" in result:
        return _respond(f"{host} is reachable.")
    return _respond(f"{host} is not reachable.")


# ---------------------------------------------------------------------------
# 10. SYSTEM HEALTH
# ---------------------------------------------------------------------------

def get_battery() -> str:
    battery = psutil.sensors_battery()
    if battery:
        status = "charging" if battery.power_plugged else "not charging"
        return _respond(f"Battery is at {int(battery.percent)} percent and {status}.")
    return _respond("Battery information is not available.")


def get_cpu_usage() -> str:
    cpu = psutil.cpu_percent(interval=1)
    cores = psutil.cpu_count()
    return _respond(f"CPU usage is {cpu} percent across {cores} cores.")


def get_ram_usage() -> str:
    ram = psutil.virtual_memory()
    avail = ram.available / (1024 ** 3)
    return _respond(f"RAM usage is {ram.percent} percent. {avail:.1f} GB available.")


def get_full_system_health() -> str:
    print("\n  [SYSTEM] ── Full System Health Report ──")
    get_battery()
    get_cpu_usage()
    get_ram_usage()
    get_disk_usage()
    get_ip_address()
    get_wifi_name()
    return _respond("System health report complete.")


# ---------------------------------------------------------------------------
# 11. DATE & TIME
# ---------------------------------------------------------------------------

def get_time() -> str:
    return _respond(f"Current time is {datetime.datetime.now().strftime('%I:%M %p')}.")


def get_date() -> str:
    return _respond(f"Today is {datetime.datetime.now().strftime('%A, %B %d %Y')}.")


def get_datetime() -> str:
    now = datetime.datetime.now()
    return _respond(f"It is {now.strftime('%A, %B %d %Y')} at {now.strftime('%I:%M %p')}.")


# ---------------------------------------------------------------------------
# 12. MOUSE & KEYBOARD AUTOMATION
# ---------------------------------------------------------------------------

def type_text(text: str) -> str:
    pyautogui.typewrite(text, interval=0.05)
    return _respond(f"Typed: {text}")


def press_key(key: str) -> str:
    pyautogui.press(key)
    return _respond(f"Pressed: {key}")


def hotkey(*keys) -> str:
    pyautogui.hotkey(*keys)
    return _respond(f"Hotkey: {' + '.join(keys)}")


def click(x: int, y: int) -> str:
    pyautogui.click(x, y)
    return _respond(f"Clicked at ({x}, {y}).")


def double_click(x: int, y: int) -> str:
    pyautogui.doubleClick(x, y)
    return _respond(f"Double-clicked at ({x}, {y}).")


def right_click(x: int, y: int) -> str:
    pyautogui.rightClick(x, y)
    return _respond(f"Right-clicked at ({x}, {y}).")


def move_mouse(x: int, y: int) -> str:
    pyautogui.moveTo(x, y, duration=0.5)
    return _respond(f"Mouse moved to ({x}, {y}).")


def scroll(direction: str = "down", amount: int = 3) -> str:
    clicks = -amount if direction == "down" else amount
    pyautogui.scroll(clicks)
    return _respond(f"Scrolled {direction}.")


# ---------------------------------------------------------------------------
# 13. COMMAND DISPATCHER
# ---------------------------------------------------------------------------

COMMAND_MAP: dict[str, callable] = {
    # Screenshot
    "screenshot":           take_screenshot,
    "take screenshot":      take_screenshot,
    # Volume
    "volume up":            volume_up,
    "increase volume":      volume_up,
    "volume down":          volume_down,
    "decrease volume":      volume_down,
    "mute":                 volume_mute,
    "unmute":               volume_unmute,
    # Brightness
    "brightness up":        brightness_up,
    "increase brightness":  brightness_up,
    "brightness down":      brightness_down,
    "decrease brightness":  brightness_down,
    "brightness":           get_brightness,
    # Power
    "shutdown":             shutdown,
    "restart":              restart,
    "reboot":               restart,
    "sleep":                sleep,
    "hibernate":            hibernate,
    "lock":                 lock,
    "lock screen":          lock,
    "log off":              log_off,
    "cancel shutdown":      cancel_shutdown,
    # Windows
    "minimize":             minimize_window,
    "maximize":             maximize_window,
    "close window":         close_window,
    "list windows":         list_windows,
    # System Health
    "battery":              get_battery,
    "cpu":                  get_cpu_usage,
    "cpu usage":            get_cpu_usage,
    "ram":                  get_ram_usage,
    "ram usage":            get_ram_usage,
    "memory":               get_ram_usage,
    "disk":                 get_disk_usage,
    "disk usage":           get_disk_usage,
    "system health":        get_full_system_health,
    "health":               get_full_system_health,
    # Network
    "ip address":           get_ip_address,
    "ip":                   get_ip_address,
    "wifi":                 get_wifi_name,
    "wi-fi":                get_wifi_name,
    "network speed":        get_network_speed,
    "ping":                 ping,
    # Date & Time
    "time":                 get_time,
    "date":                 get_date,
    "datetime":             get_datetime,
    # Processes
    "processes":            list_processes,
    "running processes":    list_processes,
    # Clipboard
    "clipboard":            get_clipboard,
    "clear clipboard":      clear_clipboard,
    # Files
    "list files":           list_files,
}


def handle_system_command(user_input: str) -> str:
    """
    Match user input to a system command and execute it.
    Tries longest keyword match first for accuracy.
    Returns a voice-friendly response string.
    """
    normalized = user_input.lower().strip()

    # Sort by keyword length descending — prefer more specific matches
    for keyword in sorted(COMMAND_MAP.keys(), key=len, reverse=True):
        if keyword in normalized:
            try:
                return COMMAND_MAP[keyword]()
            except Exception as e:
                return _respond(f"Error running '{keyword}': {e}")

    return _respond(f"No system command matched: '{user_input}'")


# ---------------------------------------------------------------------------
# Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*50)
    print("   Cortex AI — System Control Test")
    print("="*50 + "\n")

    print(get_time())
    print(get_date())
    print(get_battery())
    print(get_cpu_usage())
    print(get_ram_usage())
    print(get_disk_usage())
    print(get_ip_address())
    print(get_wifi_name())
    take_screenshot()

    print("\n--- Dispatcher Test ---\n")
    for cmd in [
        "what time is it",
        "check battery",
        "show cpu usage",
        "take a screenshot",
        "check my wifi",
        "what is my ip",
        "full system health",
    ]:
        print(f"\n  > {cmd}")
        handle_system_command(cmd)