import re

file_path = 'data/products_heritage.py'

with open(file_path, 'r') as f:
    content = f.read()

def get_time(category):
    cat = category.lower()
    if 'saree' in cat: return "3-4 Weeks"
    if 'jewellery' in cat: return "1-2 Weeks"
    if 'art' in cat: return "2-3 Weeks"
    if 'toy' in cat: return "3-5 Days"
    if 'textile' in cat: return "1-2 Weeks"
    if 'home' in cat: return "5-7 Days"
    if 'handicraft' in cat: return "4-7 Days"
    return "1-2 Weeks"

# Regex to find item dictionaries and inject production_time
# Looking for: "category": "Value",
def replacer(match):
    full_match = match.group(0)
    category = match.group(1)
    time_est = get_time(category)
    # Check if already exists to avoid double insertion if run twice
    if "production_time" in full_match:
        return full_match
    
    return f'"category": "{category}", "production_time": "{time_est}",'

# Pattern matches: "category": "Something",
pattern = r'"category": "([^"]*)",'

new_content = re.sub(pattern, replacer, content)

with open(file_path, 'w') as f:
    f.write(new_content)

print("Updated products_heritage.py")
