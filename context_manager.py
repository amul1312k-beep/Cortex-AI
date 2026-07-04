"""
Cortex AI — Context Manager
Handles all conversation history:
  - Store and retrieve full conversation logs
  - Sliding window context for AI (last N messages)
  - Session management (start, end, summarize)
  - Search through past conversations
  - Token-aware context trimming
  - Auto-save after every message
"""

import os
import json
import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "..", "data")
LOG_FILE    = os.path.join(DATA_DIR, "conversation_log.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_CONTEXT_MESSAGES = 20      # Max messages sent to AI in one request
MAX_SESSIONS_STORED  = 100     # Max sessions kept in log file
MAX_CHARS_PER_MSG    = 4000    # Truncate very long messages


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

def _new_session() -> dict:
    return {
        "session_id":  _session_id(),
        "started_at":  _now(),
        "ended_at":    None,
        "summary":     None,
        "messages":    [],
    }


def _session_id() -> str:
    return datetime.datetime.now().strftime("session_%Y%m%d_%H%M%S")


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def _load_log() -> dict:
    """Load the full conversation log from disk."""
    if not os.path.exists(LOG_FILE):
        empty = {"sessions": [], "current_session": _new_session()}
        _save_log(empty)
        return empty
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print("  [CONTEXT] Warning: log file corrupt — resetting.")
        empty = {"sessions": [], "current_session": _new_session()}
        _save_log(empty)
        return empty


def _save_log(data: dict) -> None:
    """Save conversation log atomically."""
    tmp = LOG_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, LOG_FILE)
    except IOError as e:
        print(f"  [CONTEXT] Save failed: {e}")


# ---------------------------------------------------------------------------
# 1. SESSION MANAGEMENT
# ---------------------------------------------------------------------------

def start_session() -> str:
    """Start a new conversation session."""
    log = _load_log()
    # Archive the previous session if it has messages
    prev = log.get("current_session", {})
    if prev.get("messages"):
        prev["ended_at"] = _now()
        log["sessions"].append(prev)
        # Keep only last N sessions
        log["sessions"] = log["sessions"][-MAX_SESSIONS_STORED:]
    log["current_session"] = _new_session()
    _save_log(log)
    return f"New session started: {log['current_session']['session_id']}"


def end_session(summary: str = None) -> str:
    """End current session, optionally save a summary."""
    log = _load_log()
    session = log.get("current_session", {})
    session["ended_at"] = _now()
    if summary:
        session["summary"] = summary
    if session.get("messages"):
        log["sessions"].append(session)
        log["sessions"] = log["sessions"][-MAX_SESSIONS_STORED:]
    log["current_session"] = _new_session()
    _save_log(log)
    return "Session ended and saved."


def get_current_session_id() -> str:
    return _load_log().get("current_session", {}).get("session_id", "unknown")


# ---------------------------------------------------------------------------
# 2. ADD MESSAGES
# ---------------------------------------------------------------------------

def add_message(role: str, content: str, metadata: dict = None) -> None:
    """
    Add a message to the current session.

    Args:
        role:     'user' | 'assistant' | 'system'
        content:  The message text
        metadata: Optional dict (e.g. {'intent': 'AI', 'tool': 'cortex_engine'})
    """
    log = _load_log()
    if "current_session" not in log:
        log["current_session"] = _new_session()

    # Truncate very long messages
    if len(content) > MAX_CHARS_PER_MSG:
        content = content[:MAX_CHARS_PER_MSG] + "... [truncated]"

    message = {
        "role":       role,
        "content":    content,
        "timestamp":  _now(),
    }
    if metadata:
        message["metadata"] = metadata

    log["current_session"]["messages"].append(message)
    _save_log(log)


def add_user_message(content: str, intent: str = None) -> None:
    """Shortcut: add a user message."""
    meta = {"intent": intent} if intent else None
    add_message("user", content, meta)


def add_assistant_message(content: str, engine: str = None) -> None:
    """Shortcut: add an assistant (Cortex) message."""
    meta = {"engine": engine} if engine else None
    add_message("assistant", content, meta)


def add_system_message(content: str) -> None:
    """Shortcut: add a system message."""
    add_message("system", content)


# ---------------------------------------------------------------------------
# 3. RETRIEVE CONTEXT FOR AI
# ---------------------------------------------------------------------------

def get_context(n: int = MAX_CONTEXT_MESSAGES) -> list[dict]:
    """
    Get the last N messages from the current session formatted for AI input.
    Returns list of {'role': ..., 'content': ...} dicts.
    """
    log = _load_log()
    messages = log.get("current_session", {}).get("messages", [])
    # Get last N, only role+content for AI
    context = [
        {"role": m["role"], "content": m["content"]}
        for m in messages[-n:]
    ]
    return context


def get_context_with_system_prompt(system_prompt: str, n: int = MAX_CONTEXT_MESSAGES) -> list[dict]:
    """
    Get context with a system prompt prepended.
    Ready to pass directly to an AI API.
    """
    context = get_context(n)
    # Remove any existing system messages to avoid duplicates
    context = [m for m in context if m["role"] != "system"]
    return [{"role": "system", "content": system_prompt}] + context


def get_last_n_messages(n: int = 5) -> list:
    """Get raw last N messages from current session."""
    messages = _load_log().get("current_session", {}).get("messages", [])
    return messages[-n:]


def get_last_user_message() -> Optional[str]:
    """Get the most recent user message content."""
    messages = _load_log().get("current_session", {}).get("messages", [])
    for m in reversed(messages):
        if m["role"] == "user":
            return m["content"]
    return None


def get_last_assistant_message() -> Optional[str]:
    """Get the most recent assistant message content."""
    messages = _load_log().get("current_session", {}).get("messages", [])
    for m in reversed(messages):
        if m["role"] == "assistant":
            return m["content"]
    return None


# ---------------------------------------------------------------------------
# 4. SESSION HISTORY & SEARCH
# ---------------------------------------------------------------------------

def get_all_sessions() -> list:
    """Return all archived sessions."""
    return _load_log().get("sessions", [])


def get_recent_sessions(n: int = 5) -> list:
    """Return the N most recent archived sessions."""
    sessions = _load_log().get("sessions", [])
    recent = sessions[-n:]
    print(f"  [CONTEXT] Last {len(recent)} sessions:")
    for s in recent:
        msg_count = len(s.get("messages", []))
        print(f"    {s['session_id']} | {msg_count} messages | {s.get('started_at', '')}")
    return recent


def search_history(keyword: str) -> list:
    """Search all sessions and current session for a keyword."""
    log     = _load_log()
    results = []
    all_sessions = log.get("sessions", []) + [log.get("current_session", {})]

    for session in all_sessions:
        for msg in session.get("messages", []):
            if keyword.lower() in msg.get("content", "").lower():
                results.append({
                    "session_id": session.get("session_id"),
                    "role":       msg["role"],
                    "content":    msg["content"],
                    "timestamp":  msg.get("timestamp"),
                })

    print(f"  [CONTEXT] Found {len(results)} messages containing '{keyword}':")
    for r in results[:10]:  # Show max 10
        print(f"    [{r['session_id']}] {r['role']}: {r['content'][:80]}...")
    return results


def get_conversation_stats() -> dict:
    """Return stats about the full conversation history."""
    log      = _load_log()
    sessions = log.get("sessions", [])
    current  = log.get("current_session", {})
    all_msgs = sum(len(s.get("messages", [])) for s in sessions)
    all_msgs += len(current.get("messages", []))

    stats = {
        "total_sessions":          len(sessions) + 1,
        "total_messages":          all_msgs,
        "current_session_messages":len(current.get("messages", [])),
        "current_session_id":      current.get("session_id"),
    }
    print("  [CONTEXT] Conversation Stats:")
    for k, v in stats.items():
        print(f"    {k}: {v}")
    return stats


# ---------------------------------------------------------------------------
# 5. CONTEXT WINDOW MANAGEMENT
# ---------------------------------------------------------------------------

def trim_context(max_chars: int = 8000) -> list:
    """
    Return context trimmed to fit within a character budget.
    Keeps most recent messages. Useful for models with small context windows.
    """
    messages = _load_log().get("current_session", {}).get("messages", [])
    trimmed  = []
    total    = 0

    for msg in reversed(messages):
        length = len(msg.get("content", ""))
        if total + length > max_chars:
            break
        trimmed.insert(0, {"role": msg["role"], "content": msg["content"]})
        total += length

    return trimmed


def count_tokens_approx(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def get_context_token_count() -> int:
    """Estimate total tokens in current context."""
    messages = _load_log().get("current_session", {}).get("messages", [])
    total_chars = sum(len(m.get("content", "")) for m in messages)
    tokens = count_tokens_approx(total_chars * " ")
    print(f"  [CONTEXT] Estimated tokens in context: ~{tokens}")
    return tokens


# ---------------------------------------------------------------------------
# 6. CLEAR & RESET
# ---------------------------------------------------------------------------

def clear_current_session() -> str:
    """Clear messages in the current session without archiving."""
    log = _load_log()
    log["current_session"]["messages"] = []
    _save_log(log)
    return "Current session cleared."


def clear_all_history(confirm: bool = False) -> str:
    """Wipe the entire conversation log."""
    if not confirm:
        return "To clear all history call clear_all_history(confirm=True). This cannot be undone."
    empty = {"sessions": [], "current_session": _new_session()}
    _save_log(empty)
    return "All conversation history cleared."


def export_history(export_path: str = None) -> str:
    if not export_path:
        export_path = os.path.join(
            DATA_DIR,
            f"conversation_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
    log = _load_log()
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    return f"Conversation history exported to: {export_path}"


# ---------------------------------------------------------------------------
# Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*50)
    print("   Cortex AI — Context Manager Test")
    print("="*50 + "\n")

    # Start session
    print(start_session())

    # Simulate a conversation
    add_user_message("Hey Cortex, what can you do?", intent="AI")
    add_assistant_message("I'm Cortex AI — I can control your computer, answer questions, manage files, and more!", engine="cortex_engine")

    add_user_message("Open Chrome for me", intent="SYSTEM")
    add_assistant_message("Opening Chrome now.", engine="cortex_engine")

    add_user_message("Remember my favourite editor is VS Code", intent="MEMORY")
    add_assistant_message("Got it! I'll remember your favourite editor is VS Code.", engine="cortex_engine")

    add_user_message("What is machine learning?", intent="AI")
    add_assistant_message("Machine learning is a branch of AI where systems learn from data to improve over time.", engine="cortex_engine")

    # Get context for AI
    print("\n--- Context for AI (last 4 messages) ---")
    context = get_context(n=4)
    for msg in context:
        print(f"  {msg['role']}: {msg['content']}")

    # Stats
    print()
    get_conversation_stats()

    # Search
    print()
    search_history("Chrome")

    # Last messages
    print(f"\n  Last user message: {get_last_user_message()}")
    print(f"  Last assistant message: {get_last_assistant_message()}")

    # Token estimate
    get_context_token_count()

    # Export
    print(export_history())

    # End session
    print(end_session(summary="User tested memory and context manager modules."))

    print("\n✅ Context Manager Test Complete!")
