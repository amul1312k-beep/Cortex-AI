import requests

def ask_ai(prompt):
    url = "http://localhost:11434/api/generate"

    data = {
        "model": "mistral",
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(url, json=data)
    return response.json()["response"]