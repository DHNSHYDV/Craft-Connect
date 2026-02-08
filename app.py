import os
import requests
import json
import base64
import urllib.parse
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from models import db, User, Order, OrderItem
db.init_app(app)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")

login_manager = LoginManager(app)
login_manager.login_view = 'entry'  # /entry = splash (video + auth)
login_manager.login_message = 'Please sign in to continue.'


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except (ValueError, TypeError):
        return None


with app.app_context():
    db.create_all()



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

def generate_image_hf(image_prompt):
    """Generate image via Hugging Face InferenceClient (fal-ai, Tongyi-MAI/Z-Image). Returns data URL or None."""
    if not HF_TOKEN or not HF_TOKEN.strip():
        return None
    try:
        from huggingface_hub import InferenceClient
        import io
        client = InferenceClient(provider="fal-ai", api_key=HF_TOKEN.strip())
        image = client.text_to_image(image_prompt, model="Tongyi-MAI/Z-Image")
        if image is None:
            return None
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"HF image generation failed: {e}")
        return None


# Route for AI Design Generation
@app.route('/api/generate-design', methods=['POST'])
def generate_design():
    data = request.json
    description = data.get('description', '')
    style = data.get('style', 'Traditional')
    material = data.get('material', 'Clay')
    
    # Image prompt used for HF or Pollinations
    image_prompt = f"{style} {material} Indian handicraft, {description}".replace("/", " ").replace("\\", " ").strip()

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

        # Prefer Hugging Face (fal-ai + Tongyi-MAI/Z-Image) when HF_TOKEN is set
        image_url = generate_image_hf(image_prompt)
        engine = "SambaNova+fal-ai (Z-Image)"
        if image_url is None:
            safe_query = urllib.parse.quote(image_prompt)
            image_url = f"https://pollinations.ai/p/{safe_query}?width=1024&height=1024&nologo=true&model=flux"
            engine = "SambaNova"
        
        return jsonify({
            "title": title,
            "description": desc,
            "image_url": image_url,
            "mode": "live",
            "engine": engine
        })
    except Exception as e:
        print(f"DESIGN ERROR (Fallback active): {str(e)}")
        image_url = generate_image_hf(image_prompt)
        if image_url is None:
            safe_query = urllib.parse.quote(image_prompt)
            image_url = f"https://pollinations.ai/p/{safe_query}?width=1024&height=1024&nologo=true&model=flux"
        return jsonify({
            "title": f"The {style} {material} Artisan Concept",
            "description": f"A beautiful conceptualization of {description}. This piece combines the heritage of {style} techniques with the structural integrity of {material}. [SIMULATED DUE TO API LIMIT]",
            "image_url": image_url,
            "mode": "simulation",
            "engine": "fal-ai (Z-Image)" if image_url.startswith("data:") else "Pollinations"
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


# --- Craft Assistant Chatbot (Gemini-powered) ---
def build_chatbot_context():
    """Build context for the Craft Assistant from site data."""
    from data.products_heritage import HERITAGE_DATA

    # Full product list with details for semantic matching
    all_items = []
    for state, data in HERITAGE_DATA.items():
        for item in data["items"]:
            price = item["price_range"][0] + (len(item["name"]) % 10) * (item["price_range"][1] - item["price_range"][0]) // 10
            rating = 4.0 + (len(item["name"]) % 10) / 10
            all_items.append({
                "name": item["name"], "state": state, "category": item["category"],
                "price": price, "rating": rating, "fun_fact": item.get("fun_fact", "")
            })
    all_items.sort(key=lambda x: x["rating"], reverse=True)
    top_products = all_items[:15]

    # Pottery/pots/clay products for queries like "what pots do you have?"
    pottery_products = [
        {"name": "Jhajjar Pottery", "state": "Haryana", "desc": "Clay water pots that keep water cool naturally", "price": "₹199-1499"},
        {"name": "Blue Pottery Vase", "state": "Rajasthan", "desc": "Jaipur blue pottery, made from quartz not clay", "price": "₹399-14999"},
        {"name": "Black Pottery", "state": "Meghalaya", "desc": "Fire-proof pots from Sung Valley", "price": "₹299-3499"},
        {"name": "Bell Metal Crafts", "state": "Assam", "desc": "Utensils, bowls that last generations", "price": "₹999-9999"},
        {"name": "Brass Utensils", "state": "Haryana", "desc": "Traditional brass cooking utensils", "price": "₹999-14999"},
        {"name": "Terracotta Horse", "state": "West Bengal", "desc": "Bankura terracotta art icon", "price": "₹199-8999"},
        {"name": "Clay Diyas", "state": "Jharkhand", "desc": "Handmade festival lamps", "price": "₹49-499"},
        {"name": "Mud Clay Toys", "state": "Bihar", "desc": "Eco-friendly clay toys", "price": "₹149-999"},
    ]

    context = f"""
You are the Craft Assistant for Desh Ke Haath, an Indian heritage craft e-commerce site.
Answer ONLY from the data below. Be helpful and cite specific products when relevant.

ABOUT / MISSION (from our website—use when user asks "mission", "about", "who are you"):
Desh Ke Haath: "Connecting India's Soul to the Digital World." We empower Indian artisans by bridging traditional craftsmanship and modern technology. "States Alag, Jazba Ek" (Different States, One Spirit) reflects our commitment to unifying India's diverse artistic heritage.

SITE: deshkehaath.in | Pages: Home, Products, Artists, About, AI Craft (Computer Vision, Voice, Data Insights, AR/VR, Design Your Own)

POTTERY / POTS / CLAY / VASES / UTENSILS (when user asks about pots, pottery, clay, vases, utensils):
{json.dumps(pottery_products, indent=2)}

ALL PRODUCTS (use for "what do you have", "best selling", or specific queries):
{json.dumps([{"name": p["name"], "state": p["state"], "category": p["category"], "price": f"₹{p['price']}", "fun_fact": p["fun_fact"][:80]} for p in all_items[:80]], indent=2)}

SHIPPING: India-wide, 5-7 business days. RETURN: 7 days for damaged items. CONTACT: support@deshkehaath.in
PAYMENT: UPI, Card, Net Banking, COD. GST 3%.
"""
    return context


def get_user_orders_context():
    """Get user's orders for chatbot context (if logged in)."""
    if not current_user.is_authenticated:
        return "User is NOT logged in. For order tracking, user must sign in."
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(10).all()
    if not orders:
        return "User has no orders yet."
    lines = []
    for o in orders:
        items_str = ", ".join([f"{i.product_name} x{i.quantity}" for i in o.items])
        lines.append(f"- Order {o.order_number}: ₹{o.total_amount:.0f}, Status: {o.status}, Items: {items_str}, Date: {o.created_at.strftime('%Y-%m-%d')}")
    return "User's recent orders:\n" + "\n".join(lines)


def _fallback_response(msg):
    """Rule-based fallback when Gemini fails."""
    m = msg.lower()
    if any(x in m for x in ["hello", "hi", "namaste"]):
        return "Namaste! Welcome to Desh Ke Haath. How can I help you explore Indian crafts today?"
    if any(x in m for x in ["mission", "about", "who are you", "what do you do"]):
        return "Desh Ke Haath bridges traditional Indian craftsmanship with modern technology. 'States Alag, Jazba Ek'—Different States, One Spirit. We connect India's artisans to the digital world."
    if any(x in m for x in ["pot", "pottery", "clay", "vase", "utensils"]):
        return "We have Jhajjar clay pots (Haryana), Blue Pottery vases (Rajasthan), Black Pottery (Meghalaya), Bell Metal utensils (Assam), Brass utensils (Haryana), Terracotta horses (West Bengal), Clay diyas (Jharkhand), Mud clay toys (Bihar) & more. Check the Products page!"
    if any(x in m for x in ["saree", "sari"]):
        return "We stock Patola, Banarasi, Kanjeevaram, Bandhani & other sarees from Gujarat, UP, Tamil Nadu & more. Browse the Products page to explore."
    if any(x in m for x in ["track", "order"]):
        return "To track your order, please sign in first. Go to the profile icon and log in. Then I can show your order history."
    if any(x in m for x in ["return", "refund"]):
        return "We accept returns within 7 days of delivery for damaged items. Contact support@deshkehaath.in to initiate a return."
    if any(x in m for x in ["shipping", "delivery"]):
        return "We ship across India! Delivery usually takes 5-7 business days. Free shipping on orders over ₹2000."
    if any(x in m for x in ["contact", "support"]):
        return "Email us at support@deshkehaath.in for any queries. We typically respond within 24 hours."
    if any(x in m for x in ["best", "selling", "popular", "top"]):
        return "Check our Products page—we have Madhubani paintings, Patola sarees, Kutch embroidery, Dhokra crafts & more from across India!"
    if any(x in m for x in ["price", "cost"]):
        return "Prices vary by craft and artisan. Filter by price on the Products page. Most items range from ₹299 to ₹50,000+."
    return "You can browse Products, track orders (when logged in), or email support@deshkehaath.in. How else can I help?"


def call_gemini_chat(user_message, context):
    """Call Gemini API for chat response. Falls back to rule-based only when API fails."""
    if not GEMINI_API_KEY:
        return _fallback_response(user_message)
    orders_ctx = get_user_orders_context()
    # Use system instruction + user message so Gemini reliably uses the data
    system_instruction = """You are the Craft Assistant for Desh Ke Haath. NEVER give generic replies like "browse products" or "contact support" when the user asks about specific products. ALWAYS cite actual product names, states, and details from the data below."""
    user_content = context + "\n\n" + orders_ctx + "\n\nUser asks: " + user_message + "\n\nReply using the data above. List specific products when asked (e.g. pots, pottery, sarees). Keep it concise but informative."

    for model in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-pro"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"parts": [{"text": user_content}]}],
            "generationConfig": {"maxOutputTokens": 512, "temperature": 0.5}
        }
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                data = r.json()
                text = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text and text.strip():
                    return text.strip()
        except Exception:
            continue
    return _fallback_response(user_message)


@app.route('/api/chat', methods=['GET', 'POST'])
def chat():
    """Craft Assistant chat endpoint - Gemini-powered."""
    if request.method == 'GET':
        return jsonify({"status": "ok", "message": "Craft Assistant API"})
    data = request.json or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"reply": "Please type a message."})
    context = build_chatbot_context()
    reply = call_gemini_chat(message, context)
    return jsonify({"reply": reply})


@app.route('/api/place-order', methods=['POST'])
@login_required
def place_order():
    """Save order to DB when checkout completes."""
    data = request.json or {}
    items = data.get("items", [])
    total = float(data.get("total", 0))
    address = data.get("address", "")
    if not items or total <= 0:
        return jsonify({"error": "Invalid order data"}), 400
    import random
    order_num = "OD" + str(random.randint(10000, 99999))
    while Order.query.filter_by(order_number=order_num).first():
        order_num = "OD" + str(random.randint(10000, 99999))
    order = Order(user_id=current_user.id, order_number=order_num, total_amount=total, delivery_address=address, status="Placed")
    db.session.add(order)
    db.session.flush()
    for it in items:
        oi = OrderItem(order_id=order.id, product_name=it.get("name", ""), product_state=it.get("state", ""), quantity=int(it.get("quantity", 1)), price=float(it.get("price", 0)))
        db.session.add(oi)
    db.session.commit()
    return jsonify({"order_id": order_num, "success": True})


@app.route('/')
def index():
    # Redirect to /entry to bypass browser cache - splash is the gate
    resp = redirect(url_for('entry'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp


@app.route('/entry')
def entry():
    """Splash gate: Grok video + login/signup. Always shown first."""
    resp = make_response(render_template('splash.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/splash')
def splash():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('splash.html')


@app.route('/home')
@login_required
def home():
    return render_template('index.html')


@app.route('/login', methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        login_user(user)
        return redirect(url_for('home'))
    flash('Invalid email or password.', 'error')
    return redirect(url_for('entry'))


@app.route('/signup', methods=['POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    email = request.form.get('email', '').strip().lower()
    name = request.form.get('name', '').strip()
    password = request.form.get('password', '')
    if not email or not name or not password:
        flash('All fields are required.', 'error')
    elif User.query.filter_by(email=email).first():
        flash('An account with this email already exists.', 'error')
    elif len(password) < 6:
        flash('Password must be at least 6 characters.', 'error')
    else:
        user = User(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('home'))
    return redirect(url_for('entry'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('entry'))


@app.route('/reset')
def reset_session():
    """Clear session and show splash - useful when stuck or testing."""
    logout_user()
    return redirect(url_for('entry'))


from data.products_heritage import HERITAGE_DATA

@app.route('/products')
@login_required
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
@login_required
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
@login_required
def discover():
    return render_template('discover.html')

@app.route('/ai-craft')
@login_required
def ai_craft():
    return render_template('ai_craft.html')

@app.route('/voice')
@login_required
def voice():
    return render_template('voice.html')

@app.route('/ar-vr')
@login_required
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
@login_required
def artisans():
    artists_list = get_artists()
    return render_template('artisans.html', artists=artists_list)

@app.route('/cart')
@login_required
def cart():
    return render_template('cart.html')

@app.route('/checkout')
@login_required
def checkout():
    return render_template('checkout.html')

@app.route('/design-craft')
@login_required
def design_craft():
    return render_template('design_craft.html')

@app.route('/data')
@login_required
def data():
    return render_template('data.html')

@app.route('/about')
@login_required
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True)
