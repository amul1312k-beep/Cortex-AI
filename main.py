import app_control
from grok_engine import clear_memory, classify_intent
from cortex_engine import ask_cortex, clear_cortex_memory
from voice_engine import speak, listen
from Router import route_command

def handle_command(user_input: str):
    category = route_command(user_input)

    if category == "SYSTEM":
        # Use Groq to detect exact app command
        prompt = f"""
You are a command classifier for an AI assistant.
Given user input, return ONLY one of these exact command keys if it matches:
['open_google', 'open_youtube', 'open_github', 'open_calculator',
'open_notepad', 'open_cmd', 'open_vscode', 'open_chrome']
If it doesn't match any command, return: NONE
User input: "{user_input}"
Reply with just the command key or NONE. Nothing else.
"""
        intent = classify_intent(prompt).strip()
        COMMAND_MAP = {
            "open_google": app_control.open_google,
            "open_youtube": app_control.open_youtube,
            "open_github": app_control.open_github,
            "open_calculator": app_control.open_calculator,
            "open_notepad": app_control.open_notepad,
            "open_cmd": app_control.open_cmd,
            "open_vscode": app_control.open_vscode,
            "open_chrome": app_control.open_chrome,
        }
        if intent in COMMAND_MAP:
            COMMAND_MAP[intent]()
            speak("Done!")
        else:
            response = ask_cortex(user_input)
            speak(response)

    elif category == "MEMORY":
        speak("Memory feature coming soon!")

    elif category == "AUTOMATION":
        speak("Automation feature coming soon!")

    elif category == "AI":
        response = ask_cortex(user_input)
        speak(response)

print("🧠 Cortex AI Online")
print("=" * 40)
print("Type 'voice' to switch to voice mode")
print("Type 'text' to switch to text mode")
print("=" * 40)

voice_mode = False
speak("Hello Amul. Cortex AI is online and ready.")

while True:
    if voice_mode:
        user_input = listen()
        if not user_input:
            continue
    else:
        user_input = input("You: ").strip()
        if not user_input:
            continue

    if "exit" in user_input.lower():
        speak("Cortex shutting down. Goodbye Amul.")
        break
    elif "clear memory" in user_input.lower():
        clear_memory()
        clear_cortex_memory()
        speak("Memory cleared.")
        continue
    elif "voice mode" in user_input.lower() or user_input.lower() == "voice":
        voice_mode = True
        speak("Voice mode activated. I am listening.")
        continue
    elif "text mode" in user_input.lower() or user_input.lower() == "text":
        voice_mode = False
        speak("Switching to text mode.")
        print("Text mode activated.")
        continue

    handle_command(user_input)