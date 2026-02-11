
import requests
import os
from dotenv import load_dotenv
import urllib.parse
import sys

load_dotenv()

api_key = (os.getenv("POLLINATIONS_API_KEY") or "").strip()
print(f"API Key: {api_key[:5]}...")

prompt = "Traditional Silk/Fabric Indian handicraft: a yellow saree"
encoded_prompt = urllib.parse.quote(prompt)
base_url = "https://image.pollinations.ai/prompt"
target_url = f"{base_url}/{encoded_prompt}"

params = {
    'model': 'klein',
    'width': '1024',
    'height': '1024',
    'nologo': 'true',
    'seed': '62025'
}

headers = {}
if api_key:
    headers['Authorization'] = f"Bearer {api_key}"

print(f"Target URL: {target_url}")
print(f"Headers: {headers}")
print(f"Params: {params}")

try:
    resp = requests.get(target_url, params=params, headers=headers, stream=True, timeout=30)
    print(f"Status Code: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Error Body: {resp.text}")
    else:
        print("Success! Content preview:", resp.content[:20])
except Exception as e:
    print(f"Exception: {e}")
