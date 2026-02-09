import csv
import json

def parse_csv():
    # Mapping for the first 6 items
    ap_items = [
        "Kondapalli Toys",
        "Uppada Silk Saree", 
        "Temple Jewellery",
        "Kalamkari Textile",
        "Etikoppaka Toys",
        "Folk Scrolls (Cheriyal)"
    ]

    current_state = None
    artisans = []
    
    with open('artisans_data.csv', 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not any(row): continue
            
            # Check if it's a state header (usually explicit in the CSV based on previous view, 
            # or it's a row with just one valid column or empty others)
            # Looking at the file content:
            # Line 8: "Arunachal Pradesh,,,"
            # Line 17: "Assam,,,"
            if row[0] and not row[1] and not row[2]:
                if row[0] != "Product" and row[0] != "Category":
                    current_state = row[0]
                continue
            
            # Header rows
            if row[0] in ["Product", "Category"]:
                continue
                
            product = row[0].strip()
            labor = row[1].strip()
            price = row[2].strip()
            desc = row[3].strip()
            
            if not product: continue

            # Determine state
            state = current_state
            if product in ap_items:
                state = "Andhra Pradesh"
            
            if not state:
                state = "Unknown" # Should not happen based on file structure

            artisans.append({
                "craft": product,
                "state": state,
                "labor_time": labor,
                "price_range": price,
                "why_price": desc,
                "description": f"Specialist in {product}. {desc} Approx labor: {labor}."
            })

    print(json.dumps(artisans, indent=4))

if __name__ == "__main__":
    parse_csv()
