"""
Cortex AI — Memory System
Handles all persistent user memory:
  - User profile (name, preferences, habits)
  - Favourite apps and commands
  - Notes and reminders
  - Session summaries
  - Full CRUD operations on memory
  - ChromaDB vector memory for semantic recall (optional)
"""

import os
import json
import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "..", "data")
MEMORY_FILE = os.path.join(DATA_DIR, "user_memory.json")

os.makedirs(DATA_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Default Memory Schema
# ---------------------------------------------------------------------------

DEFAULT_MEMORY: dict = {
    "profile": {
        "name":       None,
        "age":        None,
        "location":   None,
        "occupation": None,
        "created_at": None,
        "last_seen":  None,
    },
    "preferences": {
        "language":       "English",
        "voice_enabled":  True,
        "theme":          "dark",
        "response_style": "concise",
        "wake_word":      "hey cortex",
    },
    "favourite_apps":    [],
    "favourite_websites":[],
    "habits":            {},
    "notes":             [],
    "reminders":         [],
    "custom_commands":   {},
    "session_summaries": [],
    "facts":             {},
    "tags":              {},
}


# ---------------------------------------------------------------------------
# Core Load / Save
# ---------------------------------------------------------------------------

def _load() -> dict:
    """Load memory from disk. Returns default schema if file missing or corrupt."""
    if not os.path.exists(MEMORY_FILE):
        _save(DEFAULT_MEMORY.copy())
        return DEFAULT_MEMORY.copy()
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge with defaults so new keys are never missing
        return _deep_merge(DEFAULT_MEMORY.copy(), data)
    except (json.JSONDecodeError, IOError):
        print("  [MEMORY] Warning: memory file corrupt — resetting to default.")
        _save(DEFAULT_MEMORY.copy())
        return DEFAULT_MEMORY.copy()


def _save(data: dict) -> None:
    """Save memory to disk atomically."""
    tmp = MEMORY_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, MEMORY_FILE)
    except IOError as e:
        print(f"  [MEMORY] Save failed: {e}")


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base without losing base keys."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 1. USER PROFILE
# ---------------------------------------------------------------------------

def set_name(name: str) -> str:
    mem = _load()
    mem["profile"]["name"] = name
    if not mem["profile"]["created_at"]:
        mem["profile"]["created_at"] = _now()
    _save(mem)
    return f"Got it! I'll remember your name is {name}."


def get_name() -> str:
    name = _load()["profile"].get("name")
    return f"Your name is {name}." if name else "I don't know your name yet."


def set_profile(key: str, value: Any) -> str:
    mem = _load()
    mem["profile"][key] = value
    _save(mem)
    return f"Profile updated: {key} = {value}."


def get_profile() -> dict:
    profile = _load()["profile"]
    print("  [MEMORY] Your Profile:")
    for k, v in profile.items():
        if v:
            print(f"    {k}: {v}")
    return profile


def update_last_seen() -> None:
    mem = _load()
    mem["profile"]["last_seen"] = _now()
    _save(mem)


# ---------------------------------------------------------------------------
# 2. PREFERENCES
# ---------------------------------------------------------------------------

def set_preference(key: str, value: Any) -> str:
    mem = _load()
    mem["preferences"][key] = value
    _save(mem)
    return f"Preference saved: {key} = {value}."


def get_preference(key: str) -> Any:
    prefs = _load()["preferences"]
    value = prefs.get(key)
    if value is not None:
        print(f"  [MEMORY] {key} = {value}")
    else:
        print(f"  [MEMORY] No preference found for: {key}")
    return value


def get_all_preferences() -> dict:
    prefs = _load()["preferences"]
    print("  [MEMORY] All Preferences:")
    for k, v in prefs.items():
        print(f"    {k}: {v}")
    return prefs


# ---------------------------------------------------------------------------
# 3. FAVOURITE APPS & WEBSITES
# ---------------------------------------------------------------------------

def add_favourite_app(app: str) -> str:
    mem = _load()
    if app.lower() not in [a.lower() for a in mem["favourite_apps"]]:
        mem["favourite_apps"].append(app)
        _save(mem)
        return f"Added {app} to your favourite apps."
    return f"{app} is already in your favourites."


def remove_favourite_app(app: str) -> str:
    mem = _load()
    before = len(mem["favourite_apps"])
    mem["favourite_apps"] = [a for a in mem["favourite_apps"] if a.lower() != app.lower()]
    _save(mem)
    return f"Removed {app} from favourites." if len(mem["favourite_apps"]) < before else f"{app} not found in favourites."


def get_favourite_apps() -> list:
    apps = _load()["favourite_apps"]
    print(f"  [MEMORY] Favourite apps: {', '.join(apps) if apps else 'None saved yet.'}")
    return apps


def add_favourite_website(url: str) -> str:
    mem = _load()
    if url.lower() not in [w.lower() for w in mem["favourite_websites"]]:
        mem["favourite_websites"].append(url)
        _save(mem)
        return f"Saved {url} as a favourite website."
    return f"{url} is already saved."


def get_favourite_websites() -> list:
    sites = _load()["favourite_websites"]
    print(f"  [MEMORY] Favourite websites: {', '.join(sites) if sites else 'None saved yet.'}")
    return sites


# ---------------------------------------------------------------------------
# 4. HABITS & PATTERNS
# ---------------------------------------------------------------------------

def log_habit(action: str) -> None:
    """Track how often a user does something."""
    mem = _load()
    mem["habits"][action] = mem["habits"].get(action, 0) + 1
    _save(mem)


def get_habits() -> dict:
    habits = _load()["habits"]
    if habits:
        sorted_habits = sorted(habits.items(), key=lambda x: x[1], reverse=True)
        print("  [MEMORY] Your Habits (most frequent first):")
        for action, count in sorted_habits:
            print(f"    {action}: {count} times")
    else:
        print("  [MEMORY] No habits tracked yet.")
    return habits


def get_top_habits(n: int = 5) -> list:
    habits = _load()["habits"]
    top = sorted(habits.items(), key=lambda x: x[1], reverse=True)[:n]
    return top


# ---------------------------------------------------------------------------
# 5. NOTES
# ---------------------------------------------------------------------------

def add_note(content: str, tag: str = "general") -> str:
    mem = _load()
    note = {
        "id":         len(mem["notes"]) + 1,
        "content":    content,
        "tag":        tag,
        "created_at": _now(),
    }
    mem["notes"].append(note)
    _save(mem)
    return f"Note saved: '{content}'"


def get_notes(tag: str = None) -> list:
    notes = _load()["notes"]
    if tag:
        notes = [n for n in notes if n.get("tag") == tag]
    if notes:
        print(f"  [MEMORY] Notes{f' (tag: {tag})' if tag else ''}:")
        for n in notes:
            print(f"    [{n['id']}] {n['content']}  —  {n['created_at']}")
    else:
        print("  [MEMORY] No notes found.")
    return notes


def delete_note(note_id: int) -> str:
    mem = _load()
    before = len(mem["notes"])
    mem["notes"] = [n for n in mem["notes"] if n["id"] != note_id]
    _save(mem)
    return f"Note {note_id} deleted." if len(mem["notes"]) < before else f"Note {note_id} not found."


def search_notes(keyword: str) -> list:
    notes = _load()["notes"]
    matches = [n for n in notes if keyword.lower() in n["content"].lower()]
    print(f"  [MEMORY] Notes matching '{keyword}':")
    for n in matches:
        print(f"    [{n['id']}] {n['content']}")
    return matches


# ---------------------------------------------------------------------------
# 6. REMINDERS
# ---------------------------------------------------------------------------

def add_reminder(content: str, remind_at: str = None) -> str:
    mem = _load()
    reminder = {
        "id":          len(mem["reminders"]) + 1,
        "content":     content,
        "remind_at":   remind_at,
        "created_at":  _now(),
        "done":        False,
    }
    mem["reminders"].append(reminder)
    _save(mem)
    return f"Reminder set: '{content}'" + (f" at {remind_at}" if remind_at else ".")


def get_reminders(include_done: bool = False) -> list:
    reminders = _load()["reminders"]
    if not include_done:
        reminders = [r for r in reminders if not r["done"]]
    if reminders:
        print("  [MEMORY] Reminders:")
        for r in reminders:
            status = "✅" if r["done"] else "⏰"
            print(f"    {status} [{r['id']}] {r['content']}")
    else:
        print("  [MEMORY] No pending reminders.")
    return reminders


def mark_reminder_done(reminder_id: int) -> str:
    mem = _load()
    for r in mem["reminders"]:
        if r["id"] == reminder_id:
            r["done"] = True
            _save(mem)
            return f"Reminder {reminder_id} marked as done."
    return f"Reminder {reminder_id} not found."


def delete_reminder(reminder_id: int) -> str:
    mem = _load()
    before = len(mem["reminders"])
    mem["reminders"] = [r for r in mem["reminders"] if r["id"] != reminder_id]
    _save(mem)
    return f"Reminder {reminder_id} deleted." if len(mem["reminders"]) < before else "Reminder not found."


# ---------------------------------------------------------------------------
# 7. FACTS (Key-Value Memory)
# ---------------------------------------------------------------------------

def remember_fact(key: str, value: str) -> str:
    """Store an arbitrary fact about the user. e.g. remember_fact('favourite color', 'blue')"""
    mem = _load()
    mem["facts"][key.lower()] = {
        "value":      value,
        "saved_at":   _now(),
    }
    _save(mem)
    return f"Got it, I'll remember that your {key} is {value}."


def recall_fact(key: str) -> str:
    """Recall a stored fact by key."""
    facts = _load()["facts"]
    entry = facts.get(key.lower())
    if entry:
        return f"Your {key} is {entry['value']}."
    return f"I don't have anything saved for '{key}'."


def forget_fact(key: str) -> str:
    """Delete a stored fact."""
    mem = _load()
    if key.lower() in mem["facts"]:
        del mem["facts"][key.lower()]
        _save(mem)
        return f"I've forgotten your {key}."
    return f"I don't have anything saved for '{key}'."


def get_all_facts() -> dict:
    facts = _load()["facts"]
    if facts:
        print("  [MEMORY] Everything I know about you:")
        for k, v in facts.items():
            print(f"    {k}: {v['value']}")
    else:
        print("  [MEMORY] No facts stored yet.")
    return facts


# ---------------------------------------------------------------------------
# 8. CUSTOM COMMANDS
# ---------------------------------------------------------------------------

def save_custom_command(trigger: str, action: str) -> str:
    """Save a custom shortcut. e.g. 'work mode' → sequence of commands."""
    mem = _load()
    mem["custom_commands"][trigger.lower()] = {
        "action":     action,
        "created_at": _now(),
    }
    _save(mem)
    return f"Custom command saved: '{trigger}' → '{action}'"


def get_custom_command(trigger: str) -> str:
    commands = _load()["custom_commands"]
    entry = commands.get(trigger.lower())
    if entry:
        return entry["action"]
    return None


def list_custom_commands() -> dict:
    commands = _load()["custom_commands"]
    if commands:
        print("  [MEMORY] Custom Commands:")
        for trigger, data in commands.items():
            print(f"    '{trigger}' → '{data['action']}'")
    else:
        print("  [MEMORY] No custom commands saved.")
    return commands


def delete_custom_command(trigger: str) -> str:
    mem = _load()
    if trigger.lower() in mem["custom_commands"]:
        del mem["custom_commands"][trigger.lower()]
        _save(mem)
        return f"Deleted custom command: '{trigger}'"
    return f"Command '{trigger}' not found."


# ---------------------------------------------------------------------------
# 9. SESSION SUMMARIES
# ---------------------------------------------------------------------------

def save_session_summary(summary: str) -> str:
    mem = _load()
    entry = {
        "id":         len(mem["session_summaries"]) + 1,
        "summary":    summary,
        "saved_at":   _now(),
    }
    mem["session_summaries"].append(entry)
    # Keep only last 50 summaries
    mem["session_summaries"] = mem["session_summaries"][-50:]
    _save(mem)
    return "Session summary saved."


def get_recent_summaries(n: int = 5) -> list:
    summaries = _load()["session_summaries"][-n:]
    if summaries:
        print(f"  [MEMORY] Last {n} session summaries:")
        for s in summaries:
            print(f"    [{s['saved_at']}] {s['summary']}")
    else:
        print("  [MEMORY] No session summaries yet.")
    return summaries


# ---------------------------------------------------------------------------
# 10. SMART RECALL — Natural Language Interface
# ---------------------------------------------------------------------------

def smart_remember(user_input: str) -> str:
    """
    Parse natural language memory commands.
    e.g. 'remember my name is Alex' → set_name('Alex')
         'my favourite color is blue' → remember_fact('favourite color', 'blue')
         'remember I have a meeting on Monday' → add_note(...)
    """
    text = user_input.lower().strip()

    # Name patterns
    for pattern in ["my name is ", "i am ", "call me "]:
        if pattern in text:
            name = text.split(pattern)[-1].strip().title()
            return set_name(name)

    # Fact patterns — "my X is Y"
    if text.startswith("my ") and " is " in text:
        parts = text[3:].split(" is ", 1)
        if len(parts) == 2:
            key, value = parts[0].strip(), parts[1].strip()
            return remember_fact(key, value)

    # "i like / i love / i prefer"
    for pattern in ["i like ", "i love ", "i prefer ", "i enjoy "]:
        if text.startswith(pattern):
            thing = text[len(pattern):].strip()
            return remember_fact(f"likes {thing}", "yes")

    # "i hate / i don't like"
    for pattern in ["i hate ", "i don't like ", "i dislike "]:
        if text.startswith(pattern):
            thing = text[len(pattern):].strip()
            return remember_fact(f"dislikes {thing}", "yes")

    # Note patterns
    for pattern in ["note that ", "remember that ", "keep in mind ", "don't forget "]:
        if pattern in text:
            content = text.split(pattern)[-1].strip()
            return add_note(content)

    # Reminder patterns
    if "remind me" in text:
        content = text.replace("remind me to ", "").replace("remind me ", "").strip()
        return add_reminder(content)

    # Default — save as general note
    return add_note(user_input)


def smart_recall(user_input: str) -> str:
    """
    Parse natural language recall commands.
    e.g. 'what is my name?' → get_name()
         'what do you know about me?' → get_all_facts()
         'show my notes' → get_notes()
    """
    text = user_input.lower().strip()

    if any(p in text for p in ["what is my name", "who am i", "do you know my name"]):
        return get_name()

    if any(p in text for p in ["what do you know about me", "tell me about me", "my profile", "show profile"]):
        get_profile()
        get_all_facts()
        return "Here's everything I know about you."

    if any(p in text for p in ["my notes", "show notes", "what are my notes"]):
        get_notes()
        return "Here are your notes."

    if any(p in text for p in ["my reminders", "show reminders", "what do i need to do"]):
        get_reminders()
        return "Here are your reminders."

    if any(p in text for p in ["my preferences", "my settings"]):
        get_all_preferences()
        return "Here are your preferences."

    if any(p in text for p in ["my favourite apps", "my apps"]):
        get_favourite_apps()
        return "Here are your favourite apps."

    if any(p in text for p in ["my habits", "what do i usually do"]):
        get_habits()
        return "Here are your habits."

    if any(p in text for p in ["custom commands", "my commands", "shortcuts"]):
        list_custom_commands()
        return "Here are your custom commands."

    # Try to recall a specific fact — "what is my X"
    if "what is my " in text:
        key = text.split("what is my ")[-1].strip().rstrip("?")
        return recall_fact(key)

    if "do you remember my " in text:
        key = text.split("do you remember my ")[-1].strip().rstrip("?")
        return recall_fact(key)

    return "I'm not sure what you want me to recall. Try: 'what is my name' or 'show my notes'."


# ---------------------------------------------------------------------------
# 11. FULL MEMORY RESET
# ---------------------------------------------------------------------------

def reset_memory(confirm: bool = False) -> str:
    if not confirm:
        return "To reset all memory, call reset_memory(confirm=True). This cannot be undone."
    _save(DEFAULT_MEMORY.copy())
    return "All memory has been cleared."


def export_memory(export_path: str = None) -> str:
    if not export_path:
        export_path = os.path.join(DATA_DIR, f"memory_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    mem = _load()
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2, ensure_ascii=False)
    return f"Memory exported to: {export_path}"


# ---------------------------------------------------------------------------
# 12. CHROMADB VECTOR MEMORY (Semantic Search — Optional)
# ---------------------------------------------------------------------------

def vector_remember(text: str, metadata: dict = None) -> str:
    """Store a memory in ChromaDB for semantic search."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=os.path.join(DATA_DIR, "chroma"))
        collection = client.get_or_create_collection("cortex_memory")
        doc_id = f"mem_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        collection.add(
            documents=[text],
            metadatas=[metadata or {"saved_at": _now()}],
            ids=[doc_id]
        )
        return f"Stored in semantic memory: '{text}'"
    except ImportError:
        return "ChromaDB not installed. Run: pip install chromadb"
    except Exception as e:
        return f"Vector memory error: {e}"


def vector_recall(query: str, n_results: int = 3) -> list:
    """Search semantic memory using ChromaDB."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=os.path.join(DATA_DIR, "chroma"))
        collection = client.get_or_create_collection("cortex_memory")
        results = collection.query(query_texts=[query], n_results=n_results)
        docs = results.get("documents", [[]])[0]
        if docs:
            print(f"  [MEMORY] Semantic recall for '{query}':")
            for i, doc in enumerate(docs):
                print(f"    {i+1}. {doc}")
        else:
            print(f"  [MEMORY] No semantic matches found for: '{query}'")
        return docs
    except ImportError:
        print("  [MEMORY] ChromaDB not installed.")
        return []
    except Exception as e:
        print(f"  [MEMORY] Vector recall error: {e}")
        return []


# ---------------------------------------------------------------------------
# Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*50)
    print("   Cortex AI — Memory System Test")
    print("="*50 + "\n")

    # Profile
    print(set_name("Amul"))
    print(set_profile("occupation", "AI Developer"))
    print(get_name())

    # Facts
    print(remember_fact("favourite color", "black"))
    print(remember_fact("favourite language", "Python"))
    print(recall_fact("favourite color"))

    # Notes
    print(add_note("Build Cortex Phase 2 this week", tag="goals"))
    print(add_note("Install Ollama and test Llama 3", tag="tasks"))
    get_notes()

    # Reminders
    print(add_reminder("Push code to GitHub", "tonight"))
    get_reminders()

    # Preferences
    print(set_preference("response_style", "detailed"))
    print(get_preference("response_style"))

    # Custom commands
    print(save_custom_command("work mode", "open vscode, open chrome, open notion"))
    list_custom_commands()

    # Smart recall
    print("\n--- Smart Remember/Recall ---\n")
    print(smart_remember("my birthday is July 4"))
    print(smart_remember("I love dark themes"))
    print(smart_remember("note that I need to finish memory module today"))
    print(smart_recall("what is my name"))
    print(smart_recall("what is my birthday"))
    print(smart_recall("show my notes"))

    # Export
    print(export_memory())
    print("\n✅ Memory System Test Complete!")
