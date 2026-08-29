import webbrowser
import os
import subprocess

# -------- websites -------- #

def open_google():
    print("Opening Google...")
    webbrowser.open("https://www.google.com")

def open_youtube():
    print("Opening YouTube...")
    webbrowser.open("https://www.youtube.com")

def open_github():
    print("Opening GitHub...")
    webbrowser.open("https://www.github.com")


# -------- system apps -------- #

def open_calculator():
    print("Opening Calculator...")
    os.system("calc")

def open_cmd():
    print("Opening Command Prompt...")
    os.system("start cmd")

def open_notepad():
    print("Opening Notepad...")
    os.system("notepad")


# -------- software -------- #

def open_vscode():
    print("Opening VS Code...")
    subprocess.Popen("code")

def open_chrome():
    print("Opening Chrome...")
    subprocess.Popen("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")