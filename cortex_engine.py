import ollama

conversation_history = []

def ask_cortex(prompt: str) -> str:
    try:
        conversation_history.append({
            "role": "user",
            "content": prompt
        })

        messages = [
            {
                "role": "system",
                "content": (
                    "You are Cortex AI, a Jarvis-like personal AI assistant "
                    "built by Amul. You run locally on the user's computer. "
                    "You are intelligent, concise, and helpful. "
                    "You NEVER say you are LLaMA, Meta, or any other AI. "
                    "You ALWAYS say you are Cortex AI built by Amul. "
                    "You help with computer control, answering questions, "
                    "coding, planning, and any task the user needs. "
                    "Always address the user as Amul."
                )
            }
        ] + conversation_history

        response = ollama.chat(
            model="llama3",
            messages=messages
        )

        reply = response['message']['content']
        conversation_history.append({
            "role": "assistant",
            "content": reply
        })
        return reply

    except Exception as e:
        return f"[Cortex Engine error]: {str(e)}"


def classify_intent(prompt: str) -> str:
    """
    Router.py's AI fallback calls this when keyword matching misses.
    Same local Ollama connection as ask_cortex — replaces what
    grok_engine.py used to do, no Groq needed.
    """
    try:
        response = ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0}  # deterministic — same input, same category
        )
        return response['message']['content'].strip()
    except Exception as e:
        print(f"[Cortex Engine] Classification error: {e}")
        return "AI"  # safe fallback so the router still returns something usable


def clear_cortex_memory():
    global conversation_history
    conversation_history = []
    print("Cortex memory cleared.")


# TEST
if __name__ == "__main__":
    print("Testing Cortex Engine...")
    print(ask_cortex("who are you?"))
    print()
    print("Testing classify_intent...")
    test_prompt = (
        "Classify this into SYSTEM, AUTOMATION, MEMORY, or AI. "
        "Respond with one word only.\nUser input: \"open chrome\""
    )
    print(classify_intent(test_prompt))