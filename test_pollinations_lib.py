
import pollinations
import io
import base64
import random
import os
from PIL import Image

def test_pollinations():
    prompt_text = "Traditional Silk/Fabric Indian handicraft: a yellow saree"
    try:
        print("Generating Pollinations image via library (flux)...")
        model = pollinations.Image(model='flux', width=1024, height=1024, seed=random.randint(0, 999999), nologo=True)
        image = model(prompt_text[:1000])
        
        # Convert PIL Image to Base64
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        print("Success! Base64 length:", len(b64_str))
        return True
    except Exception as e:
        print(f"Pollinations library error: {e}")
        return False

if __name__ == "__main__":
    test_pollinations()
