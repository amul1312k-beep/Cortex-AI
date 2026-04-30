from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

conversation_history = [
    {
        "role": "system",
        "content": (
            "You are Cortex AI, a Jarvis-like operating assistant. "
            "You help the user control their computer, answer questions, "
            "and assist with tasks. Be concise and intelligent."
        )
    }
]

def ask_groq(prompt: str) -> str:
    try:
        conversation_history.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=conversation_history,
            max_tokens=1000
        )
        reply = response.choices[0].message.content
        conversation_history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        return f"[Groq error]: {str(e)}"

def clear_memory():
    global conversation_history
    conversation_history = [conversation_history[0]]
    print("Memory cleared.")

    
def classify_intent(prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20
        )
        return response.choices[0].message.content
    except:
        return "NONE"
