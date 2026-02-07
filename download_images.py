#!/usr/bin/env python3
"""
Download product images from Pollinations.ai
Uses the free Pollinations API to generate and download authentic handicraft images.
"""

import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Add project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data.products_heritage import HERITAGE_DATA

PRODUCTS_DIR = "/Users/apple/Desktop/Craft/static/images/products"

def download_image(url, filepath, max_retries=3):
    """Download image from URL with retries."""
    for attempt in range(max_retries):
        try:
            print(f"    Downloading (attempt {attempt + 1}/{max_retries})...", end=" ")
            urllib.request.urlretrieve(url, filepath)
            file_size = os.path.getsize(filepath)
            print(f"✓ ({file_size // 1024} KB)")
            return True
        except Exception as e:
            print(f"✗ Error: {str(e)[:50]}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return False

def generate_all_images():
    """Generate and download all product images."""
    total_products = sum(len(data['items']) for data in HERITAGE_DATA.values())
    current = 0
    success_count = 0
    fail_count = 0
    
    print("=" * 80)
    print("DOWNLOADING PRODUCT IMAGES FROM POLLINATIONS.AI")
    print("=" * 80)
    print(f"Total products: {total_products}")
    print(f"Output directory: {PRODUCTS_DIR}")
    print("=" * 80)
    
    for state, data in HERITAGE_DATA.items():
        print(f"\n📍 {state} ({len(data['items'])} products)")
        print("-" * 80)
        
        for item in data['items']:
            current += 1
            product_name = item['name']
            image_query = item.get('image_query', f"{state} {product_name} Indian handicraft")
            local_image_path = item.get('local_image', '')
            
            # Get filename
            if local_image_path:
                filename = os.path.basename(local_image_path)
            else:
                safe_state = state.lower().replace(' ', '_')
                safe_product = product_name.lower().replace(' ', '_').replace('(', '').replace(')', '')
                filename = f"{safe_state}_{safe_product}.png"
            
            filepath = os.path.join(PRODUCTS_DIR, filename)
            
            # Enhanced prompt for better quality
            enhanced_query = (
                f"{image_query} professional product photography "
                f"white background detailed high quality authentic "
                f"Indian handicraft cultural heritage"
            )
            
            # Create Pollinations URL
            safe_query = urllib.parse.quote(enhanced_query)
            # Use seed based on product name for consistency
            seed = sum(ord(c) for c in product_name)
            url = f"https://pollinations.ai/p/{safe_query}?width=800&height=800&nologo=true&seed={seed}&model=flux"
            
            print(f"\n[{current}/{total_products}] {product_name}")
            print(f"  File: {filename}")
            print(f"  Query: {image_query[:60]}...")
            
            # Download image
            if download_image(url, filepath):
                success_count += 1
            else:
                fail_count += 1
                print(f"  ⚠️  Failed to download")
            
            # Small delay to be respectful to the API
            if current % 10 == 0:
                print(f"\n  Progress: {current}/{total_products} ({success_count} success, {fail_count} failed)")
                time.sleep(1)
    
    print("\n" + "=" * 80)
    print("DOWNLOAD COMPLETE")
    print("=" * 80)
    print(f"Total: {total_products}")
    print(f"✓ Success: {success_count}")
    print(f"✗ Failed: {fail_count}")
    print(f"Success rate: {(success_count/total_products*100):.1f}%")

if __name__ == "__main__":
    generate_all_images()
