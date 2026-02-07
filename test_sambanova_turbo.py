import requests
import json

api_key = "0ea36a79-ae05-4941-9b09-3f72042d3142"
url = "https://api.sambanova.ai/v1/images/generations"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

model_ids = [
    "Stable-Diffusion-3.5-Large-Turbo",
    "stable-diffusion-3.5-large-turbo",
    "sd3.5-large-turbo",
    "stabilityai/stable-diffusion-3-5-large-turbo"
]

for model_id in model_ids:
    data = {
        "prompt": "A beautiful traditional Indian elephant statue",
        "model": model_id,
        "n": 1,
        "size": "1024x1024"
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"Model ID: {model_id} | Status Code: {response.status_code}")
        if response.status_code == 200:
            print(f"SUCCESS with {model_id}!")
            print(response.json())
            break
        else:
            print(response.text)
    except Exception as e:
        print(f"Exception for {model_id}: {str(e)}")
