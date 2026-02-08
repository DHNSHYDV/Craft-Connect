#!/usr/bin/env python3
"""
Download product images from Google Drive and replace local product images.
Drive folder: https://drive.google.com/drive/folders/10xfxkMTf8tpQ40WV21AAAeOjWzfZcR-3
"""

import os
import re
import sys
import shutil
from pathlib import Path

# Drive folder ID from the sharing link
DRIVE_FOLDER_ID = "10xfxkMTf8tpQ40WV21AAAeOjWzfZcR-3"

# Mapping from Drive folder names (normalized) to our HERITAGE_DATA state keys
DRIVE_TO_STATE = {
    "andhra pradesh": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chhattisgarh": "Chhattisgarh",
    "goa": "Goa",
    "gujarat": "Gujarat",
    "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka",
    "kerala": "Kerala",
    "madhyapradesh": "Madhya Pradesh",
    "madhya pradesh": "Madhya Pradesh",
    "maharasthra": "Maharashtra",
    "maharashtra": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu",
    "telangana": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh",
    "uttarkhand": "Uttarakhand",
    "uttarakhand": "Uttarakhand",
    "west bengal": "West Bengal",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "chandigarh": "Chandigarh",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "delhi": "Delhi",
    "jammu and kashmir": "Jammu and Kashmir",
    "ladakh": "Ladakh",
    "lakshadweep": "Lakshadweep",
    "puducherry": "Puducherry",
}


def normalize_folder_name(name):
    """Extract state name from folder like '1. Andhra Pradesh' or '13.Madhyapradesh'"""
    # Remove leading number and dot/dot-space
    cleaned = re.sub(r"^\d+\.?\s*", "", name.strip()).lower()
    return cleaned


def find_drive_folder_for_state(downloaded_root, state_key):
    """Find the Drive subfolder that matches our state."""
    state_lower = state_key.lower()
    if not os.path.isdir(downloaded_root):
        return None
    for d in os.listdir(downloaded_root):
        path = os.path.join(downloaded_root, d)
        if not os.path.isdir(path):
            continue
        norm = normalize_folder_name(d)
        if norm in DRIVE_TO_STATE and DRIVE_TO_STATE[norm] == state_key:
            return path
        if norm == state_lower:
            return path
    return None


def get_image_files(folder_path):
    """Get list of image files (png, jpg, jpeg, webp, avif, jfif), excluding .part."""
    if not folder_path or not os.path.isdir(folder_path):
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".jfif"}
    files = []
    for f in os.listdir(folder_path):
        if f.endswith('.part'):
            continue
        fp = os.path.join(folder_path, f)
        if os.path.isfile(fp) and Path(f).suffix.lower() in exts:
            files.append(fp)
    return sorted(files)


def find_best_image_for_product(image_files, product_name):
    """Match product name to best image file by keyword overlap."""
    name_lower = product_name.lower()
    name_words = set(re.findall(r'\w+', name_lower))
    best_score = -1
    best_path = None
    for fp in image_files:
        fname = Path(fp).stem.lower()
        fname_words = set(re.findall(r'\w+', fname))
        overlap = len(name_words & fname_words)
        if overlap > best_score:
            best_score = overlap
            best_path = fp
    return best_path


def find_state_folders_root(path):
    """Find root that contains state folders (handles nested zip extract)."""
    path = Path(path)
    if not path.is_dir():
        return None
    # Check if this dir has state folders (e.g. "1. Andhra Pradesh")
    for d in path.iterdir():
        if d.is_dir() and re.match(r"^\d+\.?\s*\w+", d.name):
            return str(path)
    # One level down - Drive zip often has parent folder
    for d in path.iterdir():
        if d.is_dir():
            for sub in d.iterdir():
                if sub.is_dir() and re.match(r"^\d+\.?\s*\w+", sub.name):
                    return str(d)
    return str(path)


def main():
    script_dir = Path(__file__).parent.resolve()
    products_dir = script_dir / "static" / "images" / "products"

    # Allow custom source path: python download_from_drive.py "C:\path\to\folder"
    custom_source = sys.argv[1] if len(sys.argv) > 1 else None

    if custom_source:
        download_dir = Path(custom_source)
        if not download_dir.exists():
            print(f"Error: Path not found: {download_dir}")
            sys.exit(1)
        downloaded_root = find_state_folders_root(download_dir)
        print("=" * 70)
        print("MAPPING LOCAL IMAGES TO PRODUCTS")
        print("=" * 70)
        print(f"Source: {download_dir}")
        print(f"Products dir: {products_dir}")
        print("=" * 70)
    else:
        download_dir = script_dir / "drive_download"
        products_dir.mkdir(parents=True, exist_ok=True)

        script_dir_str = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, script_dir_str)
        from data.products_heritage import HERITAGE_DATA

        print("=" * 70)
        print("DOWNLOADING FROM GOOGLE DRIVE")
        print("=" * 70)
        print(f"Folder ID: {DRIVE_FOLDER_ID}")
        print(f"Download to: {download_dir}")
        print(f"Products dir: {products_dir}")
        print("=" * 70)

        try:
            import gdown
        except ImportError:
            print("Installing gdown...")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown", "-q"])
            import gdown

        url = f"https://drive.google.com/drive/folders/{DRIVE_FOLDER_ID}"
        if download_dir.exists() and any(download_dir.iterdir()):
            print("\nUsing existing download folder...")
        else:
            print("\nDownloading Drive folder (this may take a while)...")
            if download_dir.exists():
                shutil.rmtree(download_dir)
            download_dir.mkdir(parents=True, exist_ok=True)
            gdown.download_folder(url, output=str(download_dir), quiet=False, use_cookies=False)

        downloaded_root = find_state_folders_root(download_dir)

    products_dir.mkdir(parents=True, exist_ok=True)
    script_dir_str = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir_str)
    from data.products_heritage import HERITAGE_DATA

    print("\n" + "=" * 70)
    print("MAPPING IMAGES TO PRODUCTS")
    print("=" * 70)

    total = 0
    success = 0
    skipped = 0

    for state_key, data in HERITAGE_DATA.items():
        items = data.get("items", [])
        if not items:
            continue

        folder_path = find_drive_folder_for_state(str(downloaded_root), state_key)
        if not folder_path:
            print(f"\n  [{state_key}] No matching Drive folder found - skipping")
            skipped += len(items)
            total += len(items)
            continue

        image_files = get_image_files(folder_path)
        if not image_files:
            print(f"\n  [{state_key}] No images in folder - skipping")
            skipped += len(items)
            total += len(items)
            continue

        print(f"\n  [{state_key}] {len(image_files)} images -> {len(items)} products")

        used_images = set()
        for i, item in enumerate(items):
            total += 1
            local_image = item.get("local_image", "")
            if not local_image:
                skipped += 1
                continue

            filename = os.path.basename(local_image)
            dest_path = products_dir / filename

            # Match by product name first, else by index
            src_path = find_best_image_for_product(
                [f for f in image_files if f not in used_images],
                item["name"]
            )
            if not src_path:
                src_path = image_files[i] if i < len(image_files) else None

            if src_path:
                used_images.add(src_path)
                try:
                    # Copy to dest (keep .png extension for product paths)
                    ext = Path(src_path).suffix.lower()
                    if ext in ('.webp', '.avif', '.jfif'):
                        try:
                            from PIL import Image
                            img = Image.open(src_path)
                            if img.mode in ('RGBA', 'P'):
                                img = img.convert('RGB')
                            img.save(dest_path, 'PNG')
                        except Exception:
                            shutil.copy2(src_path, dest_path)
                    else:
                        shutil.copy2(src_path, dest_path)
                    print(f"      [{i+1}] {item['name']} <- {Path(src_path).name}")
                    success += 1
                except Exception as e:
                    print(f"      [{i+1}] {item['name']} FAILED: {e}")
                    skipped += 1
            else:
                print(f"      [{i+1}] {item['name']} (no matching image)")
                skipped += 1

    # Optional: delete download folder to save space (uncomment to enable)
    # print("\nCleaning up download folder...")
    # if download_dir.exists():
    #     shutil.rmtree(download_dir)

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    print(f"Total products: {total}")
    print(f"  Copied: {success}")
    print(f"  Skipped: {skipped}")


if __name__ == "__main__":
    main()
