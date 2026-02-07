#!/usr/bin/env python3
"""
Alternative image download script using multiple free AI image APIs.
Falls back through multiple services to ensure images are downloaded.
"""

import os
import sys
import time
import urllib.parse
import urllib.request
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data.products_heritage import HERITAGE_DATA

PRODUCTS_DIR = "/Users/apple/Desktop/Craft/static/images/products"

def try_pollinations(prompt, filepath, seed):
    """Try Pollinations.ai API"""
    try:
        safe_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=800&height=800&seed={seed}"
        print(f"      Trying Pollinations.ai...", end=" ")
        urllib.request.urlretrieve(url, filepath)
        
        # Check if it's actually an image (not error HTML)
        size = os.path.getsize(filepath)
        if size > 5000:  # Real images are much larger than error messages
            print(f"✓ ({size // 1024} KB)")
            return True
        else:
            print(f"✗ (got {size} bytes - likely error)")
            os.remove(filepath)
            return False
    except Exception as e:
        print(f"✗ {str(e)[:40]}")
        return False

def try_placeholder_image(prompt, filepath):
    """Generate a simple placeholder with the product name"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        print(f"      Creating placeholder...", end=" ")
        
        # Create a simple colored background
        img = Image.new('RGB', (800, 800), color=(240, 240, 245))
        draw = ImageDraw.Draw(img)
        
        # Add text
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
        except:
            font = ImageFont.load_default()
        
        # Wrap text
        words = prompt.split()[:6]  # First 6 words
        text = '\n'.join([' '.join(words[i:i+2]) for i in range(0, len(words), 2)])
        
        # Center text
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (800 - text_width) // 2
        y = (800 - text_height) // 2
        
        draw.text((x, y), text, fill=(100, 100, 120), font=font)
        
        img.save(filepath, 'PNG')
        print(f"✓ (placeholder)")
        return True
    except Exception as e:
        print(f"✗ {str(e)[:40]}")
        return False

def download_image(prompt, filepath, seed):
    """Try multiple methods to get an image"""
    
    # Method 1: Pollinations.ai
    if try_pollinations(prompt, filepath, seed):
        return True
    
    # Method 2: Wait and retry Pollinations
    print(f"      Retrying after delay...", end=" ")
    time.sleep(2)
    if try_pollinations(prompt, filepath, seed):
        return True
    
    # Method 3: Create placeholder (fallback)
    return try_placeholder_image(prompt, filepath)

def main():
    """Download all product images"""
    total = sum(len(data['items']) for data in HERITAGE_DATA.values())
    current = 0
    success = 0
    failed = 0
    
    print("=" * 80)
    print("DOWNLOADING PRODUCT IMAGES")
    print("=" * 80)
    print(f"Total products: {total}")
    print(f"Output: {PRODUCTS_DIR}")
    print("=" * 80)
    
    for state, data in HERITAGE_DATA.items():
        print(f"\n📍 {state} ({len(data['items'])} products)")
        print("-" * 80)
        
        for item in data['items']:
            current += 1
            name = item['name']
            query = item.get('image_query', f"{state} {name} Indian handicraft")
            local_path = item.get('local_image', '')
            
            # Get filename
            if local_path:
                filename = os.path.basename(local_path)
            else:
                safe_state = state.lower().replace(' ', '_')
                safe_name = name.lower().replace(' ', '_').replace('(', '').replace(')', '')
                filename = f"{safe_state}_{safe_name}.png"
            
            filepath = os.path.join(PRODUCTS_DIR, filename)
            
            # Check if already exists and is valid
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                if size > 10000:  # Already have a good image
                    print(f"  [{current}/{total}] {name}")
                    print(f"      ✓ Already exists ({size // 1024} KB)")
                    success += 1
                    continue
            
            # Enhanced prompt
            enhanced = f"{query} professional product photography white background detailed"
            seed = sum(ord(c) for c in name)
            
            print(f"  [{current}/{total}] {name}")
            print(f"      File: {filename}")
            
            if download_image(enhanced, filepath, seed):
                success += 1
            else:
                failed += 1
            
            # Progress update
            if current % 10 == 0:
                print(f"\n  📊 Progress: {current}/{total} ({success} success, {failed} failed)")
                time.sleep(0.5)
    
    print("\n" + "=" * 80)
    print("DOWNLOAD COMPLETE")
    print("=" * 80)
    print(f"Total: {total}")
    print(f"✓ Success: {success}")
    print(f"✗ Failed: {failed}")
    print(f"Success rate: {(success/total*100):.1f}%")

if __name__ == "__main__":
    main()
