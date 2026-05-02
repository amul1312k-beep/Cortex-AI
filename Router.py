"""
Cortex AI — Router Module
Central decision engine for classifying user commands.
"""

from typing import Optional

# ---------------------------------------------------------------------------
# Keyword Maps
# ---------------------------------------------------------------------------

KEYWORD_MAP: dict[str, list[str]] = {
    "SYSTEM": [
        "open", "launch", "start", "run", "close", "quit", "exit",
        "kill", "show", "hide", "minimize", "maximize", "switch",
        "browse", "go to", "navigate to", "volume", "brightness",
        "screenshot", "reboot", "shutdown", "sleep", "lock",
    ],
    "AUTOMATION": [
        "work mode", "focus mode", "morning routine", "night mode",
        "do not disturb", "workflow", "automate", "schedule",
        "every day", "set up", "configure", "batch", "sequence",
        "when i", "whenever", "trigger", "pipeline",
    ],
    "MEMORY": [
        "remember", "recall", "forget", "store", "save", "retrieve",
        "what did i", "have i told", "my preference", "my name is",
        "i like", "i hate", "i prefer", "update my", "note that",
        "keep in mind", "log this", "track",
    ],
    "AI": [
        "what is", "who is", "why is", "how does", "explain",
        "summarize", "write", "generate", "create", "tell me",
        "help me", "can you", "could you", "translate", "compare",
        "define", "describe", "suggest", "recommend", "draft",
        "analyse", "analyze",
    ],
}

# Ordered priority: specific categories before the generic AI fallback
PRIORITY_ORDER: list[str] = ["SYSTEM", "AUTOMATION", "MEMORY", "AI"]


# ---------------------------------------------------------------------------
# Input Normalisation
# ---------------------------------------------------------------------------

def _normalize(user_input: str) -> str:
    """Lowercase and strip whitespace from raw user input."""
    return user_input.lower().strip()


# ---------------------------------------------------------------------------
# Rule-Based Classification
# ---------------------------------------------------------------------------

def _keyword_match(normalized_input: str) -> Optional[str]:
    """
    Return the first matching category based on keyword detection.

    Strategy: multi-word phrases are checked before single-word keywords
    across all categories to prevent short tokens (e.g. "start") from
    shadowing longer, more specific phrases (e.g. "start work mode").
    Returns None if no keyword matches.
    """
    # Split keywords into two tiers: phrases (2+ words) and tokens (1 word)
    phrase_hits: list[tuple[int, str]] = []  # (priority_index, category)
    token_hits:  list[tuple[int, str]] = []

    for idx, category in enumerate(PRIORITY_ORDER):
        for kw in KEYWORD_MAP[category]:
            if kw in normalized_input:
                bucket = phrase_hits if " " in kw else token_hits
                bucket.append((idx, category))

    # Prefer the highest-priority phrase match; fall back to highest-priority token
    for hits in (phrase_hits, token_hits):
        if hits:
            return min(hits, key=lambda x: x[0])[1]

    return None


# ---------------------------------------------------------------------------
# AI Fallback Classification
# ---------------------------------------------------------------------------

def _build_classification_prompt(user_input: str) -> str:
    """Build a strict, deterministic prompt for AI-based intent classification."""
    return (
        "You are an intent classifier for an AI assistant system called Cortex AI.\n"
        "Classify the following user input into exactly ONE of these categories:\n\n"
        "  SYSTEM     — commands to control the OS, apps, or hardware\n"
        "  AUTOMATION — multi-step workflows, routines, or scheduled tasks\n"
        "  MEMORY     — storing, recalling, or managing user-specific data\n"
        "  AI         — general questions, conversation, or content generation\n\n"
        "Rules:\n"
        "- Respond with ONE word only: SYSTEM, AUTOMATION, MEMORY, or AI\n"
        "- No punctuation, no explanation, no other text whatsoever\n\n"
        f'User input: "{user_input}"'
    )


def _ai_fallback(user_input: str) -> str:
    """
    Use the AI model to classify intent when keyword matching fails.
    Calls the externally defined `classify_intent(prompt: str) -> str`.
    """
    prompt = _build_classification_prompt(user_input)

    try:
        # classify_intent is assumed to be imported / available at runtime
        raw_result: str = classify_intent(prompt)  # noqa: F821
        category = raw_result.strip().upper()

        if category in KEYWORD_MAP:
            return category

        # If the model returns something unexpected, default to AI
        return "AI"

    except Exception:
        # Fail safe: treat unclassifiable input as a general AI query
        return "AI"


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def route_command(user_input: str) -> str:
    """
    Classify user input into: SYSTEM | AUTOMATION | MEMORY | AI

    Strategy:
      1. Normalize input.
      2. Fast rule-based keyword scan.
      3. If no match, delegate to AI model for classification.

    Args:
        user_input: Raw string from the user.

    Returns:
        A category string: 'SYSTEM', 'AUTOMATION', 'MEMORY', or 'AI'.
    """
    if not user_input or not user_input.strip():
        return "AI"

    normalized = _normalize(user_input)

    # Phase 1 — fast rule-based detection
    category = _keyword_match(normalized)
    if category:
        return category

    # Phase 2 — AI model fallback
    return _ai_fallback(user_input)


# ---------------------------------------------------------------------------
# Optional: Batch Routing
# ---------------------------------------------------------------------------

def route_commands(inputs: list[str]) -> list[dict[str, str]]:
    """
    Route multiple commands at once.

    Returns:
        List of dicts with 'input' and 'category' keys.
    """
    return [
        {"input": cmd, "category": route_command(cmd)}
        for cmd in inputs
    ]


# ---------------------------------------------------------------------------
# Dev / Debug Utility
# ---------------------------------------------------------------------------

def explain_route(user_input: str) -> dict[str, str]:
    """
    Return routing result along with the method used (rule-based or AI).
    Useful for debugging and logging.
    """
    if not user_input or not user_input.strip():
        return {"input": user_input, "category": "AI", "method": "default"}

    normalized = _normalize(user_input)
    category = _keyword_match(normalized)

    if category:
        return {"input": user_input, "category": category, "method": "rule-based"}

    category = _ai_fallback(user_input)
    return {"input": user_input, "category": category, "method": "ai-fallback"}


if __name__ == "__main__":
    test_inputs = [
        "open chrome",
        "start work mode",
        "remember my name is Alex",
        "what is quantum computing",
        "take a screenshot",
        "good morning",
    ]

    print("\n--- Cortex AI Router Test ---\n")
    for cmd in test_inputs:
        result = route_command(cmd)
        print(f"  Input : {cmd}")
        print(f"  Route : {result}\n")