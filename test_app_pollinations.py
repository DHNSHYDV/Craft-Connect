
import sys
import os

# Mock Flask app and other globals since they are at top level of app.py
from unittest.mock import MagicMock
sys.modules['flask'] = MagicMock()
sys.modules['flask_login'] = MagicMock()
sys.modules['models'] = MagicMock()
sys.modules['data.products_heritage'] = MagicMock()

# Now import the functions from app.py
from app import generate_image_pollinations, POLLINATIONS_IMAGE_MODELS

def verify_fix():
    print(f"POLLINATIONS_IMAGE_MODELS: {POLLINATIONS_IMAGE_MODELS}")
    prompt = "Traditional Silk Indian handicraft: a yellow saree"
    image_url, err = generate_image_pollinations(prompt)
    
    if image_url and image_url.startswith("data:image/jpeg;base64,"):
        print("Success! Image URL generated and format is correct.")
        print("Base64 length:", len(image_url))
        return True
    else:
        print(f"Failure. Error: {err}")
        return False

if __name__ == "__main__":
    if verify_fix():
        sys.exit(0)
    else:
        sys.exit(1)
