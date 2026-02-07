import requests
import json

api_key = "0ea36a79-ae05-4941-9b09-3f72042d3142"
url = "https://api.sambanova.ai/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

data = {
    "messages": [
        {"role": "user", "content": "Hello, can you generate images? If so, what is your model identifier for text-to-image generation?"}
    ],
    "model": "Meta-Llama-3.1-8B-Instruct"
}

try:
    response = requests.post(url, headers=headers, json=data)
    print(f"Status Code: {response.status_code}")
    print(response.text)
except Exception as e:
    print(f"Exception: {str(e)}")
