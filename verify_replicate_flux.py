
import os
import sys
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Set up path to import app.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import generate_image_replicate

def test_generation():
    print("Testing generate_image_replicate with Flux Dev...")
    prompt = "A futuristic pottery studio with glowing clay"
    try:
        url, error = generate_image_replicate(prompt)
        if url:
            print(f"SUCCESS: Generated image URL: {url}")
        else:
            print(f"FAILURE: {error}")
    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    test_generation()
