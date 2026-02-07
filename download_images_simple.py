#!/usr/bin/env python3
"""
Simple and robust image downloader for product images.
Downloads from Pollinations.ai with retries and progress tracking.
"""

import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data.products_heritage import HERITAGE_DATA

PRODUCTS_DIR = "/Users/apple/Desktop/Craft/static/images/products"

def download_with_retry(url, filepath, max_retries=3):
    """Download with retries"""
    for attempt in range(max_retries):
        try:
            urllib.request.urlretrieve(url, filepath)
            size = os.path.getsize(filepath)
            
            # Check if it's a real image (not error page)
            if size > 5000:
                return True, size
            else:
                # Small file, likely an error
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return False, size
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            return False, 0
    return False, 0

def main():
    total = sum(len(data['items']) for data in HERITAGE_DATA.values())
    current = 0
    success = 0
    skipped = 0
    failed = 0
    
    print("=" * 80)
    print("PRODUCT IMAGE DOWNLOAD")
    print("=" * 80)
    print(f"Total: {total} products")
    print(f"Output: {PRODUCTS_DIR}")
    print("=" * 80)
    
    for state, data in HERITAGE_DATA.items():
        print(f"\n📍 {state}")
        
        for item in data['items']:
            current += 1
            name = item['name']
            query = item.get('image_query', f"{state} {name} Indian handicraft")
            local_path = item.get('local_image', '')
            
            # Determine filename
            if local_path:
                filename = os.path.basename(local_path)
            else:
                safe_state = state.lower().replace(' ', '_')
                safe_name = name.lower().replace(' ', '_').replace('(', '').replace(')', '')
                filename = f"{safe_state}_{safe_name}.png"
            
            filepath = os.path.join(PRODUCTS_DIR, filename)
            
            # Skip if good image already exists
            if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
                print(f"  [{current}/{total}] {name[:40]:40} ✓ exists")
                skipped += 1
                success += 1
                continue
            
            # Build URL
            enhanced = f"{query} professional product photography white background"
            safe_query = urllib.parse.quote(enhanced)
            seed = sum(ord(c) for c in name)
            url = f"https://image.pollinations.ai/prompt/{safe_query}?width=800&height=800&seed={seed}"
            
            # Download
            ok, size = download_with_retry(url, filepath)
            
            if ok:
                print(f"  [{current}/{total}] {name[:40]:40} ✓ {size//1024}KB")
                success += 1
            else:
                print(f"  [{current}/{total}] {name[:40]:40} ✗ failed")
                failed += 1
            
            # Small delay to be nice to the API
            if current % 5 == 0:
                time.sleep(0.5)
    
    print("\n" + "=" * 80)
    print("COMPLETE")
    print("=" * 80)
    print(f"Total:   {total}")
    print(f"Success: {success} ({success/total*100:.1f}%)")
    print(f"Skipped: {skipped} (already existed)")
    print(f"Failed:  {failed}")

if __name__ == "__main__":
    main()
