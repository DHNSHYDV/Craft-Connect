import requests
import json

api_key = "0ea36a79-ae05-4941-9b09-3f72042d3142"
url = "https://api.sambanova.ai/v1/images/generations"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

data = {
    "prompt": "A beautiful traditional Indian elephant statue",
    "model": "stable-diffusion-3-5-large",
    "n": 1,
    "size": "1024x1024"
}

try:
    response = requests.post(url, headers=headers, json=data)
    print(f"Status Code: {response.status_code}")
    print(response.text)
except Exception as e:
    print(f"Exception: {str(e)}")
