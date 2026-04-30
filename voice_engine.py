import speech_recognition as sr
import pyttsx3

# Setup
recognizer = sr.Recognizer()
tts_engine = pyttsx3.init()

# Voice settings
tts_engine.setProperty('rate', 180)      # Speed of speech
tts_engine.setProperty('volume', 0.9)   # Volume

def speak(text: str):
    """Cortex speaks out loud"""
    print(f"Cortex: {text}")
    tts_engine.say(text)
    tts_engine.runAndWait()

def listen() -> str:
    """Cortex listens to your voice"""
    with sr.Microphone() as source:
        print("Cortex is listening...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            text = recognizer.recognize_google(audio)
            print(f"You said: {text}")
            return text.lower()
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            speak("Sorry I did not catch that. Please repeat.")
            return ""
        except sr.RequestError:
            speak("Voice service is unavailable right now.")
            return ""

# TEST
if __name__ == "__main__":
    speak("Hello Amul. Cortex voice system is online.")
    print("Say something...")
    result = listen()
    if result:
        speak(f"You said: {result}")