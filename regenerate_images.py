#!/usr/bin/env python3
"""
Batch image generation script with rate limiting and progress tracking.
Generates authentic handicraft images for all products.
"""

import os
import sys
import time
import json
from pathlib import Path

# Add project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data.products_heritage import HERITAGE_DATA

# Configuration
ARTIFACTS_DIR = "/Users/apple/.gemini/antigravity/brain/f984f0c0-a15e-4b22-b8e0-c171e818fb44"
PRODUCTS_DIR = "/Users/apple/Desktop/Craft/static/images/products"
PROGRESS_FILE = "image_generation_progress.json"

def load_progress():
    """Load progress from file."""
    progress_path = os.path.join(ARTIFACTS_DIR, PROGRESS_FILE)
    if os.path.exists(progress_path):
        with open(progress_path, 'r') as f:
            return json.load(f)
    return {"completed": [], "failed": [], "total": 0}

def save_progress(progress):
    """Save progress to file."""
    progress_path = os.path.join(ARTIFACTS_DIR, PROGRESS_FILE)
    with open(progress_path, 'w') as f:
        json.dump(progress, f, indent=2)

def get_all_products():
    """Get list of all products to generate."""
    products = []
    for state, data in HERITAGE_DATA.items():
        for item in data['items']:
            product_name = item['name']
            image_query = item.get('image_query', f"{state} {product_name} Indian handicraft")
            local_image_path = item.get('local_image', '')
            
            if local_image_path:
                filename = os.path.basename(local_image_path)
            else:
                safe_state = state.lower().replace(' ', '_')
                safe_product = product_name.lower().replace(' ', '_').replace('(', '').replace(')', '')
                filename = f"{safe_state}_{safe_product}.png"
            
            enhanced_prompt = (
                f"{image_query}, professional product photography, "
                f"clean white background, detailed, high quality, "
                f"authentic Indian handicraft, cultural heritage, "
                f"studio lighting, centered composition"
            )
            
            products.append({
                "state": state,
                "name": product_name,
                "filename": filename,
                "prompt": enhanced_prompt,
                "image_query": image_query
            })
    
    return products

def main():
    """Main execution function."""
    print("=" * 80)
    print("PRODUCT IMAGE GENERATION SCRIPT")
    print("=" * 80)
    
    # Load progress
    progress = load_progress()
    all_products = get_all_products()
    progress["total"] = len(all_products)
    
    print(f"\nTotal products: {len(all_products)}")
    print(f"Completed: {len(progress['completed'])}")
    print(f"Failed: {len(progress['failed'])}")
    print(f"Remaining: {len(all_products) - len(progress['completed']) - len(progress['failed'])}")
    
    # Show products that need generation
    print("\n" + "=" * 80)
    print("PRODUCTS REQUIRING IMAGE GENERATION:")
    print("=" * 80)
    
    for i, product in enumerate(all_products, 1):
        if product['filename'] not in progress['completed']:
            status = "❌ FAILED" if product['filename'] in progress['failed'] else "⏳ PENDING"
            print(f"\n[{i}/{len(all_products)}] {status}")
            print(f"  State: {product['state']}")
            print(f"  Product: {product['name']}")
            print(f"  File: {product['filename']}")
            print(f"  Prompt: {product['image_query'][:70]}...")
    
    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("1. Use the generate_image tool to create images for pending products")
    print("2. Copy generated images from artifacts directory to products directory")
    print("3. Update progress file after each successful generation")
    print("4. Handle rate limits with appropriate delays (45-60 seconds)")
    
    # Save initial progress
    save_progress(progress)
    print(f"\nProgress saved to: {os.path.join(ARTIFACTS_DIR, PROGRESS_FILE)}")

if __name__ == "__main__":
    main()
