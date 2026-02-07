import os
import requests
import json
import base64
import urllib.parse
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")

app = Flask(__name__)

# SambaNova Helper
def call_sambanova(prompt, model="Meta-Llama-3.3-70B-Instruct", image_data=None):
    url = "https://api.sambanova.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {SAMBANOVA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    messages = []
    if image_data:
        # Multimodal request for Llama-4-Maverick
        base64_image = base64.b64encode(image_data).decode('utf-8')
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        }]
    else:
        messages = [{"role": "user", "content": prompt}]

    data = {
        "messages": messages,
        "model": model,
        "temperature": 0.1,
        "top_p": 0.1
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            raise Exception(f"SambaNova Error: {response.status_code} - {response.text}")
    except Exception as e:
        raise Exception(f"SambaNova Request Failed: {str(e)}")

# Route for AI Design Generation
@app.route('/api/generate-design', methods=['POST'])
def generate_design():
    data = request.json
    description = data.get('description', '')
    style = data.get('style', 'Traditional')
    material = data.get('material', 'Clay')
    
    try:
        prompt = f"Act as a master Indian artisan. Design a unique handicraft based on: {description}. Style: {style}, Material: {material}. Give me a short title, a poetic description, and a visual prompt for an image generator. Format your response exactly as: TITLE: [title] DESCRIPTION: [description]"
        
        # Use SambaNova for ultra-fast generation
        content = call_sambanova(prompt, model="Meta-Llama-3.3-70B-Instruct")
        
        title = "Artisan Concept"
        desc = content
        if "TITLE:" in content and "DESCRIPTION:" in content:
            parts = content.split("DESCRIPTION:")
            title = parts[0].replace("TITLE:", "").strip()
            desc = parts[1].strip()

        # Clean and encode the prompt for Pollinations
        image_prompt = f"{style} {material} Indian handicraft {description}".replace("/", " ").replace("\\", " ")
        safe_query = urllib.parse.quote(image_prompt)
        image_url = f"https://pollinations.ai/p/{safe_query}?width=1024&height=1024&nologo=true&model=flux"
        
        print(f"DEBUG: Generated Image URL: {image_url}")
        
        return jsonify({
            "title": title,
            "description": desc,
            "image_url": image_url,
            "mode": "live",
            "engine": "SambaNova"
        })
    except Exception as e:
        print(f"DESIGN ERROR (Fallback active): {str(e)}")
        fallback_prompt = f"{style} {material} Indian handicraft {description}".replace("/", " ").replace("\\", " ")
        safe_query = urllib.parse.quote(fallback_prompt)
        image_url = f"https://pollinations.ai/p/{safe_query}?width=1024&height=1024&nologo=true&model=flux"
        return jsonify({
            "title": f"The {style} {material} Artisan Concept",
            "description": f"A beautiful conceptualization of {description}. This piece combines the heritage of {style} techniques with the structural integrity of {material}. [SIMULATED DUE TO API LIMIT]",
            "image_url": image_url,
            "mode": "simulation"
        })

# Route for AI Image Analysis (Computer Vision)
@app.route('/api/analyze-craft', methods=['POST'])
def analyze_craft():
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400
    
    image_file = request.files['image']
    image_data = image_file.read()
    
    try:
        prompt = """Analyze this image of an Indian handicraft. Identify:
1. Name of the craft
2. Probable Origin (State/Region)
3. Authenticity Score (0-100%)
4. Materials used
5. Artisan Style
6. A short 2-3 sentence description.
Return the result in JSON format only with keys: name, origin, score, material, style, description."""

        # Use SambaNova Multimodal Vision (Llama-4-Maverick is the newer multimodal model)
        content = call_sambanova(prompt, model="Llama-4-Maverick-17B-128E-Instruct", image_data=image_data)
        
        text = content.replace('```json', '').replace('```', '').strip()
        result = json.loads(text)
        result["mode"] = "live"
        result["engine"] = "SambaNova-Vision"
        return jsonify(result)
    except Exception as e:
        print(f"VISION ERROR (Fallback active): {str(e)}")
        return jsonify({
            "name": "Authenticated Craft",
            "origin": "Regional Artisan Hub",
            "score": 92,
            "material": "Natural Fibers / Clay",
            "style": "Traditional Heritage",
            "description": "Our high-speed vision engine analyzed the structural patterns of this artifact. It shows authentic characteristics of traditional Indian handicraft. [SIMULATED]",
            "mode": "simulation"
        })

@app.route('/')
def index():
    return render_template('index.html')

from data.products_heritage import HERITAGE_DATA

@app.route('/products')
def products():
    search_query = request.args.get('search', '').lower()
    sort_by = request.args.get('sort', 'default')
    category_filter = request.args.get('category', 'All')
    state_filter = request.args.get('state', 'all')
    
    all_products = []
    for state, data in HERITAGE_DATA.items():
        if state_filter != 'all' and state != state_filter:
            continue
            
        for item in data['items']:
            if category_filter != 'All' and item['category'] != category_filter:
                continue
            if search_query and search_query not in item['name'].lower() and search_query not in state.lower():
                continue
                
            product_id = f"{state.replace(' ', '_')}_{item['name'].replace(' ', '_')}"
            price = item['price_range'][0] + (len(item['name']) % 10) * (item['price_range'][1] - item['price_range'][0]) // 10
            
            # Use local_image if available, otherwise generate Pollinations URL
            if 'local_image' in item:
                image_url = item['local_image']
            else:
                img_query = item.get('image_query', f"{state} {item['name']} Indian handicraft")
                image_url = f"https://pollinations.ai/p/{urllib.parse.quote(img_query)}?width=800&height=800&nologo=true&seed={len(item['name'])}"
            
            all_products.append({
                "id": product_id,
                "name": item['name'],
                "state": state,
                "category": item['category'],
                "price": price,
                "fun_fact": item['fun_fact'],
                "rating": 4.0 + (len(item['name']) % 10) / 10,
                "reviews": 10 + (len(item['name']) % 50),
                "image_url": image_url
            })
    
    # Sort
    if sort_by == 'price_low':
        all_products.sort(key=lambda x: x['price'])
    elif sort_by == 'price_high':
        all_products.sort(key=lambda x: x['price'], reverse=True)
    elif sort_by == 'rating':
        all_products.sort(key=lambda x: x['rating'], reverse=True)
    else:
        all_products.sort(key=lambda x: x['name'])
        
    all_states = sorted(list(HERITAGE_DATA.keys()))
    all_categories = sorted(list(set(i['category'] for d in HERITAGE_DATA.values() for i in d['items'])))
        
    return render_template('products.html', 
                         products=all_products, 
                         all_states=all_states,
                         all_categories=all_categories,
                         current_state=state_filter,
                         current_sort=sort_by,
                         search_query=search_query)

@app.route('/product/<product_id>')
def product_detail(product_id):
    # Parse ID: State_ItemName
    found_state = None
    found_item = None
    
    for state, data in HERITAGE_DATA.items():
        state_key = state.replace(' ', '_')
        if product_id.startswith(state_key):
            found_state = state
            item_name = product_id.replace(state_key + '_', '').replace('_', ' ')
            for item in data['items']:
                if item['name'] == item_name:
                    found_item = item
                    break
            if found_item:
                break
    
    if not found_item:
        return "Product not found", 404
        
    price = found_item['price_range'][0] + (len(found_item['name']) % 10) * (found_item['price_range'][1] - found_item['price_range'][0]) // 10
    story = HERITAGE_DATA[found_state]['stories'].get(found_item['name'], "Deeply rooted in Indian heritage, this craft represents centuries of tradition.")

    # Determine image query and URL
    img_query = found_item.get('image_query', f"{found_state} {found_item['name']} Indian handicraft")
    
    if 'local_image' in found_item:
        image_url = found_item['local_image']
    else:
        image_url = f"https://pollinations.ai/p/{urllib.parse.quote(img_query)}?width=1024&height=1024&nologo=true&seed={len(found_item['name'])}"

    product = {
        "id": product_id,
        "name": found_item['name'],
        "state": found_state,
        "category": found_item['category'],
        "price": price,
        "description": found_item['fun_fact'],
        "story": story,
        "rating": 4.0 + (len(found_item['name']) % 10) / 10,
        "reviews": 10 + (len(found_item['name']) % 50),
        "image_url": image_url,
        "image_query": img_query # Added for debugging/transparency
    }
    
    # Related Products: Find 4 products from the same state or category
    related = []
    for s_name, s_data in HERITAGE_DATA.items():
        for i in s_data['items']:
            if i['name'] == found_item['name'] and s_name == found_state:
                continue # Skip current
            
            if s_name == found_state or i['category'] == found_item['category']:
                r_id = f"{s_name.replace(' ', '_')}_{i['name'].replace(' ', '_')}"
                r_price = i['price_range'][0] + (len(i['name']) % 10) * (i['price_range'][1] - i['price_range'][0]) // 10
                if 'local_image' in i:
                    r_image_url = i['local_image']
                else:
                    r_img_query = i.get('image_query', f"{s_name} {i['name']} Indian handicraft")
                    r_image_url = f"https://pollinations.ai/p/{urllib.parse.quote(r_img_query)}?width=400&height=400&nologo=true&seed={len(i['name'])}"
                
                related.append({
                    "id": r_id,
                    "name": i['name'],
                    "state": s_name,
                    "price": r_price,
                    "image_url": r_image_url
                })
                if len(related) >= 4:
                    break
        if len(related) >= 4:
            break

    return render_template('product_detail.html', product=product, related_products=related)

@app.route('/discover')
def discover():
    return render_template('discover.html')

@app.route('/ai-craft')
def ai_craft():
    return render_template('ai_craft.html')

@app.route('/voice')
def voice():
    return render_template('voice.html')

@app.route('/ar-vr')
def ar_vr():
    return render_template('ar_vr.html')

# Helper to generate artist profiles
def get_artists():
    import random
    artists = []
    
    # Collect all items from heritage data to pick random images
    all_heritage_items = []
    for state, data in HERITAGE_DATA.items():
        for item in data['items']:
            all_heritage_items.append((state, item))
            
    # Names for variety with gender mapping
    male_names = ["Ramesh", "Abdul", "Gopal", "Mohammad", "Satish", "Vikram", "Sanjay", "Arjun", "Kishore", "Rajesh"]
    female_names = ["Sunita", "Meenakshi", "Priya", "Lakshmi", "Anjali", "Kavita", "Deepa", "Bhavna", "Urmila", "Sudha"]
    
    last_names = ["Kumar", "Devi", "Khan", "Sharma", "Prasad", "Patel", "Singh", "Das", "Rao", "Nair", "Joshi", "Mistri", "Khatri", "Thakur", "Behera", "Gupta", "Yadav", "Reddy", "Choudhary", "Varma"]
    
    for i in range(1, 41): # 40 artists
        random.seed(i + 1000) # Stable profiles
        
        # Decide gender first
        is_male = random.random() > 0.5
        gender = 'male' if is_male else 'female'
        fname = random.choice(male_names) if is_male else random.choice(female_names)
        lname = random.choice(last_names)
        
        # Pick a random heritage item for this artist
        state, item = random.choice(all_heritage_items)
        
        artists.append({
            'id': i,
            'name': f"{fname} {lname}",
            'gender': gender,
            'style': item['name'],
            'state': state,
            'description': f"Master artisan specializing in {item['name']} from {state}.",
            'image': f"https://pollinations.ai/p/{urllib.parse.quote(state + ' ' + item['name'] + ' Indian handicraft')}?width=800&height=800&nologo=true&seed={i}",
            'experience': random.randint(5, 45)
        })
    return artists

@app.route('/artisans')
def artisans():
    artists_list = get_artists()
    return render_template('artisans.html', artists=artists_list)

@app.route('/cart')
def cart():
    return render_template('cart.html')

@app.route('/checkout')
def checkout():
    return render_template('checkout.html')

@app.route('/design-craft')
def design_craft():
    return render_template('design_craft.html')

@app.route('/data')
def data():
    return render_template('data.html')

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True)
