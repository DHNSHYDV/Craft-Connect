#!/usr/bin/env python3
"""Verify all products have matching images, pricing, description, and story."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data.products_heritage import HERITAGE_DATA

STATIC_ROOT = Path(__file__).parent / "static"


def main():
    issues = []
    ok = 0

    for state, data in HERITAGE_DATA.items():
        items = data.get("items", [])
        stories = data.get("stories", {})

        for item in items:
            name = item["name"]

            # 1. Image exists
            local_image = item.get("local_image", "")
            if local_image:
                # local_image is like /static/images/products/xxx.png
                file_path = STATIC_ROOT / local_image.replace("/static/", "")
                if not file_path.exists():
                    issues.append(f"Missing image: {state} / {name} -> {local_image}")
                else:
                    ok += 1
            else:
                issues.append(f"No local_image: {state} / {name}")

            # 2. Description (fun_fact)
            if not item.get("fun_fact"):
                issues.append(f"Missing fun_fact: {state} / {name}")

            # 3. Story
            if name not in stories:
                issues.append(f"Missing story: {state} / {name}")

            # 4. Price range
            if "price_range" not in item or len(item["price_range"]) != 2:
                issues.append(f"Missing/invalid price_range: {state} / {name}")

    total = sum(len(d["items"]) for d in HERITAGE_DATA.values())

    print("=" * 60)
    print("PRODUCT VERIFICATION")
    print("=" * 60)
    print(f"Total products: {total}")
    print(f"Images verified: {ok}")
    print(f"Issues found: {len(issues)}")
    print()

    if issues:
        print("ISSUES:")
        for i in issues[:50]:  # Cap at 50
            print(f"  - {i}")
        if len(issues) > 50:
            print(f"  ... and {len(issues) - 50} more")
    else:
        print("All products OK: images, pricing, description, and story verified.")

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
