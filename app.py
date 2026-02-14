import os
import re
import sys
import time
import tempfile
import requests
import json
import base64
import urllib.parse
import urllib.parse
import random
import time
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, make_response, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from sqlalchemy import text

# Enable unbuffered output for immediate logging
sys.stdout.flush()
sys.stderr.flush()

# Load environment variables
load_dotenv()
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")


from datetime import timedelta

# Trigger Reload for Template Update 5
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Session Configuration for Better Persistence
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)  # Remember me for 30 days
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Regular sessions last 7 days
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent XSS attacks
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection

# Vercel-specific DB handling (Read-only file system workarounds)
is_vercel = os.getenv('VERCEL') or os.getenv('AWS_LAMBDA_FUNCTION_NAME')
if is_vercel:
    # Use /tmp for writable SQLite db (Ephemeral, but works for demo)
    db_path = "/tmp/site.db"
    # Optional: copy existing DB if we want pre-populated data (not doing it here to keep it simple/safe)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///site.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fail-safe Import Strategy for Vercel Debugging
try:
    from models import db, User, Order, OrderItem
    # Import Data
    from data.products_heritage import HERITAGE_DATA
    db.init_app(app)
    print("✅ Database and Models loaded successfully")
except Exception as e:
    print(f"❌ CRITICAL IMPORT ERROR: {e}")
    # Define dummy objects to prevents NameError later in code
    db = None
    User = None
    Order = None
    OrderItem = None
    HERITAGE_DATA = {}

# --- Global Naming Pools for Artisans ---
STATE_NAMING = {
    "Andhra Pradesh": {
        "male": ["Ramesh", "Suresh", "Venkatesh", "Srinivas", "Nagarjuna", "Chandra", "Kishore"],
        "female": ["Lakshmi", "Padma", "Sunita", "Anjali", "Swathi", "Deepa", "Sravani"],
        "last": ["Reddy", "Rao", "Naidu", "Chowdary", "Gupta", "Murthy", "Goud"]
    },
    "Arunachal Pradesh": {
        "male": ["Tashi", "Dorjee", "Karsang", "Passang", "Jampa", "Sangey", "Wangchu"],
        "female": ["Pema", "Sonam", "Tsering", "Diki", "Yangchen", "Rinchin", "Dechen"],
        "last": ["Lama", "Dorjee", "Tsering", "Khandu", "Wangsa", "Libang", "Perme"]
    },
    "Assam": {
        "male": ["Manas", "Pranjal", "Dipankar", "Bishal", "Utpal", "Gautam", "Rahul"],
        "female": ["Barsha", "Priyanka", "Mousumi", "Pompy", "Nayanmoni", "Gayatri", "Daisy"],
        "last": ["Baruah", "Gogoi", "Saikia", "Bora", "Kalita", "Sarma", "Das"]
    },
    "Bihar": {
        "male": ["Mukesh", "Rajesh", "Sanjay", "Amit", "Alok", "Prakash", "Ravi"],
        "female": ["Pooja", "Neha", "Suman", "Kiran", "Rekha", "Rani", "Shila"],
        "last": ["Kumar", "Singh", "Yadav", "Mishra", "Jha", "Prasad", "Gupta"]
    },
    "Chhattisgarh": {
        "male": ["Rakesh", "Vijay", "Anil", "Dinesh", "Suresh", "Manish", "Pawan"],
        "female": ["Meena", "Geeta", "Sita", "Lalita", "Kavita", "Anita", "Radha"],
        "last": ["Baghel", "Sahu", "Baghel", "Verma", "Dewangan", "Netam", "Kashyap"]
    },
    "Goa": {
        "male": ["Mario", "Pedro", "Anthony", "Francisco", "Joao", "Caitan", "Savio"],
        "female": ["Maria", "Fatima", "Isabella", "Rosie", "Ana", "Josephine", "Carmina"],
        "last": ["Fernandes", "D'Souza", "Rodrigues", "Pereira", "Gomes", "Dias", "Costa"]
    },
    "Gujarat": {
        "male": ["Hitesh", "Jignesh", "Viral", "Chirag", "Hardik", "Mayur", "Pratik"],
        "female": ["Bhumika", "Dhara", "Kinjal", "Peral", "Falguni", "Jigisha", "Mittal"],
        "last": ["Patel", "Shah", "Mehta", "Dave", "Joshi", "Bhatt", "Ammani"]
    }
}

GENERIC_NAMING = {
    "male": ["Ramesh", "Abdul", "Gopal", "Mohammad", "Satish", "Vikram"],
    "female": ["Sunita", "Meenakshi", "Priya", "Lakshmi", "Anjali"],
    "last": ["Kumar", "Devi", "Khan", "Sharma", "Singh", "Das"]
}


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
# Prompt refinement: use this key first so refine has its own quota; if unset, falls back to GEMINI_API_KEY
PROMPT_REFINE_API_KEY = (os.getenv("PROMPT_REFINE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
# Pollinations AI: optional key for prompt refine (text chat completions)
POLLINATIONS_API_KEY = (os.getenv("POLLINATIONS_API_KEY") or os.getenv("POLLINATION_API_KEY") or "").strip()

# Configure Gemini AI for chatbot
# Configure Gemini AI for chatbot (Lightweight Vercel Version)
# import google.generativeai as genai (REMOVED: Too heavy for Vercel)
class GeminiClient:
    """Lightweight wrapper for Gemini API to avoid 150MB+ grpc dependencies."""
    def __init__(self, api_key, model="gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def generate_content(self, prompt, timeout=12):
        if not self.api_key:
            return type('obj', (object,), {'text': "Error: AI key missing."})
        
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"parts": [{"text": str(prompt)}]}]
        }
        
        try:
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                headers=headers,
                json=data,
                timeout=timeout
            )
            response.raise_for_status()
            result = response.json()
            # mimic genai response object
            text_result = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            return type('obj', (object,), {'text': text_result})
        except Exception as e:
            print(f"Gemini API Error: {e}")
            return type('obj', (object,), {'text': f"AI Error: {e}"})

class GeminiImageClient:
    """Client for generating images using Gemini Imagen 3 (via REST)."""
    def __init__(self, api_key):
        self.api_key = api_key
        # Using Imagen 4.0 Fast endpoint
        self.url = "https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict"

    def generate_image(self, prompt):
        if not self.api_key:
            return None, "Gemini API Key missing"

        
        headers = {"Content-Type": "application/json"}
        payload = {
            "instances": [
                {"prompt": prompt}
            ],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "1:1"
            }
        }
        
        try:
            print(f"Generating image with Gemini Imagen 3: {prompt[:50]}...")
            resp = requests.post(
                f"{self.url}?key={self.api_key}",
                headers=headers,
                json=payload,
                timeout=15
            )
            
            if resp.status_code != 200:
                print(f"Gemini Image Error {resp.status_code}: {resp.text}")
                return None, f"Gemini Error {resp.status_code}: {resp.text[:200]}"
                
            result = resp.json()
            # Response format: { "predictions": [ { "bytesBase64Encoded": "..." } ] }
            predictions = result.get('predictions')
            if not predictions:
                # Sometimes it might be directly in bytesBase64Encoded if the format differs
                print(f"Unexpected Gemini response: {str(result)[:200]}")
                return None, "No image predictions returned"
                
            b64_data = predictions[0].get('bytesBase64Encoded')
            if b64_data:
                # Return data URI
                return f"data:image/jpeg;base64,{b64_data}", None
                
            return None, "No base64 data in response"
            
        except Exception as e:
            print(f"Gemini Image Exception: {e}")
            return None, str(e)

class HFImageClient:
    """Client for generating images via Hugging Face Inference API."""
    def __init__(self, token, model="black-forest-labs/FLUX.1-schnell"):
        self.token = token
        self.model = model
        self.url = f"https://router.huggingface.co/hf-inference/models/{model}"

    def generate_image(self, prompt):
        if not self.token:
            return None, "HF Token missing"
        
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"inputs": prompt}
        
        try:
            print(f"Generating image with HF ({self.model}): {prompt[:50]}...")
            
            # Implementation of retry logic for 503 (Model Loading)
            import time
            max_retries = 3
            for i in range(max_retries):
                resp = requests.post(self.url, headers=headers, json=payload, timeout=90)
                
                if resp.status_code == 200:
                    # HF returns raw bytes of the image
                    import base64
                    b64_data = base64.b64encode(resp.content).decode("utf-8")
                    return f"data:image/jpeg;base64,{b64_data}", None
                
                if resp.status_code == 503:
                    # Model is loading, wait and retry
                    wait_time = resp.json().get('estimated_time', 20)
                    print(f"HF Model loading, waiting {wait_time}s (try {i+1}/{max_retries})...")
                    time.sleep(min(wait_time, 30))
                    continue
                
                print(f"HF Image Error {resp.status_code}: {resp.text}")
                return None, f"HF Error {resp.status_code}: {resp.text[:200]}"
            
            return None, "HF Error: Model still loading after retries"
            
        except Exception as e:
            print(f"HF Image Exception: {e}")
            return None, str(e)

# Initialize Image Clients
gemini_img_client = GeminiImageClient(GEMINI_API_KEY)
hf_img_client = HFImageClient(HF_TOKEN)


if GEMINI_API_KEY:
    # genai.configure(api_key=GEMINI_API_KEY)
    chatbot_model = GeminiClient(GEMINI_API_KEY, model='gemini-pro')
else:
    chatbot_model = None

login_manager = LoginManager(app)
login_manager.login_view = 'entry'  # /entry = splash (video + auth)
login_manager.login_message = 'Please sign in to continue.'

# Configure Upload Folder
# Configure Upload Folder
if is_vercel:
    app.config['UPLOAD_FOLDER'] = os.path.join('/tmp', 'uploads', 'profiles')
else:
    app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads', 'profiles')

try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
except OSError as e:
    print(f"⚠️ Warning: Could not create upload folder {app.config['UPLOAD_FOLDER']}: {e}")

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except (ValueError, TypeError):
        return None


def _migrate_add_missing_columns():
    """Add missing columns to existing tables (SQLite-safe)."""
    conn = db.engine.connect()
    try:
        # Users: ensure profile columns exist
        if db.engine.dialect.name == "sqlite":
            r = conn.execute(text("PRAGMA table_info(users)"))
            existing = {row[1] for row in r}
            for col, spec in [
                ("phone", "VARCHAR(20)"),
                ("profile_image", "VARCHAR(255)"),
                ("address", "TEXT"),
                ("city", "VARCHAR(100)"),
                ("state", "VARCHAR(100)"),
                ("pincode", "VARCHAR(10)"),
            ]:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {spec}"))
                    conn.commit()
            # Orders: ensure items_json, shipping_address, order_number, delivery_address exist
            r = conn.execute(text("PRAGMA table_info(orders)"))
            existing = {row[1] for row in r}
            for col, spec in [
                ("order_number", "VARCHAR(20)"),
                ("delivery_address", "TEXT"),
                ("items_json", "TEXT"),
                ("shipping_address", "TEXT"),
            ]:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE orders ADD COLUMN {col} {spec}"))
                    conn.commit()
    finally:
        conn.close()


with app.app_context():
    try:
        db.create_all()
        _migrate_add_missing_columns()
    except Exception as e:
        print(f"DATABASE ERROR (Non-fatal): {e}")

# --- Core Routes ---


# --- Product Routes ---



@app.route('/map')
def map_page():
    return render_template('map.html')


@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/ar-experience')
def ar_vr():
    return render_template('ar_experience.html')

# --- Profile & Orders Routes ---

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # Update details
        current_user.name = request.form.get('name')
        current_user.phone = request.form.get('phone')
        current_user.address = request.form.get('address')
        current_user.city = request.form.get('city')
        current_user.state = request.form.get('state')
        current_user.pincode = request.form.get('pincode')
        
        # Handle Profile Image Upload
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename != '':
                from werkzeug.utils import secure_filename
                filename = secure_filename(f"user_{current_user.id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.profile_image = filename
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
        
    return render_template('profile.html', user=current_user)

@app.route('/api/place_order', methods=['POST'])
@login_required
def place_order():
    try:
        data = request.get_json(silent=True) or {}
        items = data.get('items') or []
        total = data.get('totalAmount')
        if total is None:
            total = 0
        try:
            total = float(total)
        except (TypeError, ValueError):
            total = 0
        if not items or total <= 0:
            return jsonify({'success': False, 'error': 'Invalid order: no items or invalid total'}), 400

        # Update user profile from order address
        current_user.phone = data.get('phone') or current_user.phone
        current_user.address = data.get('address') or current_user.address
        current_user.city = data.get('city') or current_user.city
        current_user.state = data.get('state') or current_user.state
        current_user.pincode = data.get('pincode') or current_user.pincode

        shipping_address = f"{data.get('address') or ''}, {data.get('city') or ''}, {data.get('state') or ''} - {data.get('pincode') or ''}".strip(' ,-')
        if not shipping_address or shipping_address == '-':
            shipping_address = "Address not provided"

        # Generate unique order_number (DB may have NOT NULL constraint from older schema)
        import random
        order_num = "OD" + str(random.randint(10000, 99999))
        while Order.query.filter_by(order_number=order_num).first():
            order_num = "OD" + str(random.randint(10000, 99999))

        new_order = Order(
            user_id=current_user.id,
            order_number=order_num,
            total_amount=total,
            items_json=json.dumps(items),
            shipping_address=shipping_address,
            delivery_address=shipping_address
        )
        db.session.add(new_order)
        db.session.commit()
        return jsonify({'success': True, 'order_id': order_num})
    except Exception as e:
        db.session.rollback()
        print(f"place_order error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/orders')
@login_required
def orders():
    # Fetch orders sorted by newest first
    user_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    
    # Process orders for display (items from items_json or OrderItem rows)
    orders_data = []
    for order in user_orders:
        item_list = order.items
        order_items = [
            {
                "name": getattr(i, "product_name", ""),
                "quantity": getattr(i, "quantity", 1),
                "price": getattr(i, "price", 0),
                "image": getattr(i, "image", "") or "",
            }
            for i in item_list
        ]
        orders_data.append({
            'id': order.id,
            'order_number': order.order_number,
            'date': order.created_at.strftime('%d %b %Y'),
            'total': order.total_amount,
            'status': order.status,
            'order_items': order_items,
            'address': order.shipping_address or order.delivery_address or ""
        })
        
    return render_template('orders.html', orders=orders_data)



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


# fal-ai text-to-image model (use one that supports HF token: e.g. zai-org/GLM-Image)
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "zai-org/GLM-Image")

# Pollinations image models to try in order; first successful response is used. Override with POLLINATIONS_IMAGE_MODEL=flux,kontext,klein
POLLINATIONS_IMAGE_MODELS = [
    m.strip() for m in os.getenv("POLLINATIONS_IMAGE_MODEL", "flux,kontext,klein,klein-large,gptimage").split(",") if m.strip()
]
if not POLLINATIONS_IMAGE_MODELS:
    POLLINATIONS_IMAGE_MODELS = ["flux"]


def generate_image_pollinations(prompt_text):
    """Generate image via Pollinations.ai (Free Tier) using REST API with model fallback.
    
    Returns a Base64 Data URI so the image is embedded directly in the response.
    """
    # Use the configured models or fallback to flux
    models = POLLINATIONS_IMAGE_MODELS if POLLINATIONS_IMAGE_MODELS else ["flux"]
    
    base_url = "https://image.pollinations.ai/prompt"
    encoded_prompt = urllib.parse.quote(prompt_text)
    
    headers = {}
    if POLLINATIONS_API_KEY:
        headers['Authorization'] = f"Bearer {POLLINATIONS_API_KEY}"

    last_error = "Unknown error"
    
    start_time = time.time()
    for model_name in models:
        # Check if we have enough time left (leave 5s for artisan match and overhead)
        elapsed = time.time() - start_time
        if elapsed > 20: 
            print(f"Pollinations loop timed out after {elapsed:.1f}s. Skipping remaining models.")
            break

        try:
            target_url = f"{base_url}/{encoded_prompt}"
            params = {
                'model': model_name,
                'width': '1024',
                'height': '1024',
                'nologo': 'true',
                'seed': str(random.randint(0, 999999))
            }
            
            print(f"Attempting Pollinations REST API with model '{model_name}'...")
            # Tight 10s timeout per model
            resp = requests.get(target_url, params=params, headers=headers, stream=True, timeout=10)
            
            if resp.status_code == 200:
                print(f"✓ Pollinations model '{model_name}' succeeded")
                b64_str = base64.b64encode(resp.content).decode("utf-8")
                return f"data:image/jpeg;base64,{b64_str}", "Pollinations", None
            else:
                last_error = f"Model '{model_name}' failed with status {resp.status_code}: {resp.text[:100]}"
                print(f"Pollinations model '{model_name}' error: {last_error}")
                continue
                
        except Exception as e:
            last_error = f"Model '{model_name}' exception: {str(e)}"
            print(f"Pollinations model '{model_name}' exception: {last_error}")
            continue
            
    return None, "Pollinations", f"All Pollinations models failed. Last error: {last_error}"

@app.route('/api/image/gen')
def proxy_pollinations_gen():
    """Proxy request to gen.pollinations.ai (No API Key needed for free tier)."""
    prompt = request.args.get('prompt')
    if not prompt:
        return "Missing prompt", 400
        
    try:
        # Use the working legacy endpoint structure: https://pollinations.ai/p/{encoded_prompt}
        base_url = "https://pollinations.ai/p"
        
        encoded_prompt = urllib.parse.quote(prompt)
        target_url = f"{base_url}/{encoded_prompt}"
        
        params = request.args.copy()
        params.pop('prompt', None)
        
        # DEBUG: Pollinations is free, keys sometimes cause "text/html" errors on this endpoint
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/jpeg, image/png, */*'
        }
        
        print(f"Proxying to Pollinations: {target_url}")
        print(f"DEBUG: Params: {params}")
        
        resp = requests.get(target_url, params=params, headers=headers, stream=True, timeout=60)
        
        print(f"DEBUG: Response Status: {resp.status_code}")
        print(f"DEBUG: Response Headers: {resp.headers}")
        
        content_type = resp.headers.get('Content-Type', '')
        if resp.status_code != 200 or 'image' not in content_type:
            # If it's HTML/text, print it to see the error message
            error_text = resp.text[:500]
            print(f"Pollinations Proxy Error {resp.status_code} ({content_type}): {error_text}")
            
        return make_response(resp.content, resp.status_code, {'Content-Type': content_type or 'image/jpeg'})
        
    except Exception as e:
        print(f"Pollinations Proxy Error: {e}")
        return f"Image generation failed: {e}", 502


def generate_image_design(prompt_text):
    """Generate image. Primary: Gemini Imagen 3 (if billed). Fallback: Pollinations (Direct URL)."""
    
    # 1. PRIMARY: GEMINI IMAGEN 3 (Requires Billing)
    if GEMINI_API_KEY:
        print("Attempting Gemini Imagen...")
        # Note: This will fail with 400 if the account is free tier.
        # We catch that inside generate_image() and it returns error message, so we fall through.
        img_url, err = gemini_img_client.generate_image(prompt_text)
        if img_url:
            print("✓ Gemini Imagen succeeded")
            return img_url, "Gemini", None
        print(f"Gemini Imagen failed: {err}")

    # 2. FALLBACK: POLLINATIONS (Free Tier, Direct URL)
    # We always attempt this if Gemini fails, as it's the only free reliable option.
    print("Attempting Pollinations.ai (Direct URL Fallback)...")
    url, provider, err = generate_image_pollinations(prompt_text)
    if url:
         print("✓ Pollinations URL generated")
         return url, provider, None
    print(f"Pollinations failed ({err}).")

    # 3. LEGACY FALLBACK: Hugging Face (Starts broken, user might fix token)
    if HF_TOKEN:
        img_url, err = hf_img_client.generate_image(prompt_text)
        if img_url:
            print("✓ Hugging Face succeeded")
            return img_url, "HuggingFace", None
        print(f"Hugging Face failed: {err}")
    
    return None, "Error", "Image generation failed using all available providers."





def find_artisan_match(material, style, description=""):
    """
    Enhanced matching logic using user description and HERITAGE_DATA.
    Optimized for speed: Uses keyword scoring first, Gemini only as fallback.
    """
    import random
    from data.products_heritage import HERITAGE_DATA
    
    # 1. Flatten HERITAGE_DATA into a searchable list
    heritage_items = []
    for state, data in HERITAGE_DATA.items():
        for item in data.get("items", []):
            item_copy = item.copy()
            item_copy["state"] = state
            # Add story if available
            item_copy["story"] = data.get("stories", {}).get(item["name"], "")
            heritage_items.append(item_copy)

    # 2. Get the hardcoded list of artisans
    all_artists = get_artists()
    
    # 3. Optimized Keyword Scoring (FAST)
    best_match = None
    best_score = -1
    
    query_text = f"{description} {style} {material}".lower()
    query_terms = query_text.split()
    
    for item in heritage_items:
        score = 0
        search_text = (item["name"] + " " + item["state"] + " " + item.get("category", "") + " " + item.get("story", "")).lower()
        
        # Word-based name match (High weight)
        name_lower = item["name"].lower()
        if name_lower in query_text:
            score += 20
        else:
            # Check for significant keywords from the name
            name_words = name_lower.split()
            found_words = 0
            for nw in name_words:
                if len(nw) > 3 and nw in query_text:
                    found_words += 1
            if found_words > 0:
                score += 15 * (found_words / len(name_words))
            
        # Material match
        if material.lower() in search_text:
            score += 5
            
        # Style/Category match
        if style.lower() in search_text:
            score += 3
            
        # Keyword matching for description
        for term in query_terms:
            if len(term) > 3 and term in search_text:
                score += 1
                
        # Random tie-breaker
        score += random.random()
        
        if score > best_score:
            best_score = score
            best_match = item
            
    # HIGH CONFIDENCE KEYWORD MATCH (Skip Gemini to avoid timeout)
    if best_score > 18:
        return _realize_artisan_from_heritage(best_match, all_artists)

    # 4. LLM-Based Matching (Gemini) - Fallback for low confidence
    if GEMINI_API_KEY and (description or style or material):
        try:
            # Use 1.5-flash-latest which is highly available
            model_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
            
            # Create a list of craft options for Gemini to pick from
            options = []
            for i, item in enumerate(heritage_items):
                options.append(f"{i}: {item['name']} ({item['state']})")
            
            # We only send the first 80 items to stay within context/token reasonable limits for a quick search
            options_text = "\n".join(options[:80]) 
            
            prompt = f"""You are a Heritage Matching Expert. A user wants to create:
Description: {description}
Selected Style: {style}
Selected Material: {material}

From the following list of Indian heritage crafts, pick the index of the one that is the BEST match.
PRIORITIZE specific art styles (like 'Madhubani', 'Warli', 'Blue Pottery') found in the description even if the 'Selected Material' is different. 

List:
{options_text}

Reply with ONLY the index number (integer). If no good match, reply with 'NONE'."""
            
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            # Tight 6s timeout for matching
            r = requests.post(model_url, json=payload, timeout=6)
            if r.status_code == 200:
                gemini_resp = r.json()
                res_text = (gemini_resp.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                
                # Extract number
                import re
                match = re.search(r'\d+', res_text)
                if match:
                    idx = int(match.group())
                    if 0 <= idx < len(heritage_items):
                        return _realize_artisan_from_heritage(heritage_items[idx], all_artists)
        except Exception as e:
            print(f"Gemini artisan matching failed: {e}")

    if best_match:
        return _realize_artisan_from_heritage(best_match, all_artists)

    # 5. Final Fallback (Generic)
    return {
        "name": "Traditional Artisan",
        "state": "India",
        "fact": "Handcrafted with love and tradition.",
        "category": "Handicrafts",
        "production_time": "1-2 Weeks",
        "price_range": "₹2,000 – ₹5,000",
        "artist_name": "Master Craftsman"
    }

def _realize_artisan_from_heritage(heritage_item, all_artists):
    """Utility to turn a heritage item into a full artisan match object."""
    import random
    
    # Try to find if we already have an artist for this craft in all_artists
    for artist in all_artists:
        if artist.get("style", "").lower() == heritage_item["name"].lower():
            return {
                "name": artist.get("style", "Handicraft"),
                "state": artist.get("state", "India"),
                "fact": artist.get("description", "Handcrafted excellence.").split('.')[0] + '.',
                "category": artist.get("style", "Handicraft"),
                "production_time": artist.get("meta", {}).get("labor", "1-2 Weeks"),
                "price_range": artist.get("meta", {}).get("price", "₹2,000 – ₹5,000"),
                "artist_name": artist.get("name")
            }
            
    # Generate a deterministic but realistic artist name based on state
    state = heritage_item["state"]
    naming_pool = STATE_NAMING.get(state, GENERIC_NAMING)
    
    # Use seed based on item name for determinism
    rng = random.Random(heritage_item["name"])
    is_male = rng.random() > 0.4
    fname = rng.choice(naming_pool["male"]) if is_male else rng.choice(naming_pool["female"])
    lname = rng.choice(naming_pool["last"])
    artist_name = f"{fname} {lname}"
    
    return {
        "name": heritage_item["name"],
        "state": heritage_item["state"],
        "fact": heritage_item.get("fun_fact", "Handcrafted with traditional techniques."),
        "category": heritage_item.get("category", "Heritage"),
        "production_time": heritage_item.get("production_time", "2-3 Weeks"),
        # Standardize price range display
        "price_range": f"₹{heritage_item['price_range'][0]:,} – ₹{heritage_item['price_range'][1]:,}" if isinstance(heritage_item.get("price_range"), (list, tuple)) else "₹2,000 – ₹5,000",
        "artist_name": artist_name
    }
        
def is_premium_category(description):
    """Check if the description suggests a high-value item like an idol or statue."""
    premium_keywords = ['idol', 'statue', 'sculpture', 'temple', 'deity', 'artifact', 'masterpiece', 'figurine']
    desc_lower = description.lower()
    return any(k in desc_lower for k in premium_keywords)

def get_database_average_price(material, style):
    """Scan HERITAGE_DATA to find average prices for a given material or style."""
    prices = []
    mat_lower = material.lower()
    style_lower = style.lower()
    
    # Access HERITAGE_DATA which is global or imported
    for state, data in HERITAGE_DATA.items():
        for item in data.get('items', []):
            item_name = item.get('name', '').lower()
            item_cat = item.get('category', '').lower()
            
            # Match by material or style/category
            if mat_lower in item_name or mat_lower in item_cat or style_lower in item_name or style_lower in item_cat:
                pr = item.get('price_range', (0, 0))
                if pr[0] > 0:
                    mid = (pr[0] + pr[1]) / 2
                    prices.append(mid)
    
    if not prices:
        return 2999  # Fallback if no matches found
        
    return int(sum(prices) / len(prices))

def get_authentic_price(description, material, style, artisan_range):
    """Suggest an authentic price using Gemini with premium multipliers and database baseline."""
    baseline = get_database_average_price(material, style)
    is_premium = is_premium_category(description)
    
    # Hard floor for Metal/Brass premium items
    if is_premium and "metal" in material.lower():
        baseline = max(baseline, 5500)
    elif is_premium:
        baseline = max(baseline, 3500)
        
    if not GEMINI_API_KEY:
        return baseline
        
    client = GeminiClient(GEMINI_API_KEY)
    quality_tier = "Museum Grade / Collector Edition" if is_premium else "High-Quality Artisan"
    
    prompt = f"""You are a Senior Indian Handicraft Appraiser for a Luxury Heritage Brand. 
Item Description: {description}
Material: {material}
Style: {style}
Quality Tier: {quality_tier}
Database Baseline Reference: ₹{baseline}
Artisan Price Context: {artisan_range}

Suggest a realistic 'Fair Trade' price in INR for an authentic, hand-made version of this masterpiece. 
Metal idols should reflect professional foundry and hand-chiseling labor.
Large sculptures should be significantly more expensive.

Reply with ONLY the integer number. No currency, no extra text. Ensure it is a multiple of 100 or 500."""
    
    try:
        # Strict 5s timeout for price estimation to prevent gateway timeout
        response = client.generate_content(prompt, timeout=5)
        price_text = response.text.strip()
        
        import re
        all_numbers = re.findall(r'\d+', price_text)
        if all_numbers:
            # Sort by value and pick the one that fits our baseline best or is most realistic
            # Gemini sometimes returns IDs or counts first. We want a number > 400.
            for num_str in all_numbers:
                val = int(num_str)
                if 500 <= val <= 150000: # Sanity range: 500 to 1.5 Lac
                    return val
            
            val = int(all_numbers[0])
            return min(max(val, baseline), 80000)
            
    except Exception as e:
        sys.stderr.write(f"Price AI Error: {e}\n")
        
    return baseline

@app.route('/api/generate-design-flux', methods=['POST'])
@login_required
def generate_design_flux():
    """Generate design image with FLUX and find an artisan match."""
    try:
        import sys
        sys.stderr.write("DEBUG: generate_design_flux HIT!\n")
        sys.stderr.flush()
        
        data = request.json or {}
        description = data.get('description', '').strip()
        style = data.get('style', 'Traditional')
        material = data.get('material', 'Metal/Brass')
        if not description:
            return jsonify({"error": "Please describe your design."}), 400
            
        prompt_text = f"{style} {material} Indian handicraft, {description}"
        title = f"{style} {material} Artisan Concept"
        desc = f"A {style} Indian handicraft in {material}. {description}"
        
        image_url, provider, err_msg = generate_image_design(prompt_text)
        
        if image_url is None:
            return jsonify({
                "error": err_msg or "Image generation phase failed",
                "title": title,
                "description": desc
            }), 502
            
        # Add Artisan Match
        artisan_match = find_artisan_match(material, style, description)
        
        # Get Authentic Price via AI
        final_price = get_authentic_price(description, material, style, artisan_match.get("price_range"))
        artisan_match["price"] = final_price
            
        return jsonify({
            "title": title, 
            "description": desc, 
            "image_url": image_url,
            "artisan_match": artisan_match,
            "provider": provider
        })
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"CRASH in generate_design_flux: {error_detail}")
        return jsonify({
            "error": f"Internal Server Crash: {str(e)}",
            "traceback": error_detail,
            "note": "This debug info is provided to help fix the Render 500 error."
        }), 500


def _analyze_craft_gemini(image_data, mime_type="image/jpeg"):
    """Use Gemini vision to analyze image. Returns (result_dict, error_hint). result_dict is None on failure."""
    if not GEMINI_API_KEY or not GEMINI_API_KEY.strip():
        return None, "GEMINI_API_KEY is not set in .env. Get a key at https://aistudio.google.com/apikey"
    if not image_data or len(image_data) < 100:
        return None, None
    prompt = """Analyze this image. It can be anything Indian traditional: clothing (kurta, saree, sherwani), handicraft, pottery, painting, jewellery, textile, metalwork, etc.

Reply with ONLY a valid JSON object (no markdown, no code block) with exactly these keys: name, origin, score, material, style, description.

- name: specific item name (e.g. "Men's Silk Kurta Dhoti Set with Angavastram", "Madhubani Painting", "Blue Pottery vase")
- origin: Indian state or region if you can tell (e.g. "South India", "Rajasthan"), else "India"
- score: number 0-100 (confidence it is traditional Indian)
- material: the ONE primary material you see—e.g. Silk, Cotton, Clay, Brass, Gold, Paper, Wood. Not a list; pick the main one.
- style: e.g. "Traditional ethnic wear", "Kantha embroidery", "Terracotta"
- description: 2-3 sentences describing what you see (e.g. "An elegant cream-colored silk ensemble featuring...")"""
    b64 = base64.b64encode(image_data).decode("utf-8")
    last_error = None
    # Use current model IDs that support image input (see https://ai.google.dev/gemini-api/docs/models)
    for model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY.strip()}"
        payload = {
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": b64}},
                    {"text": prompt}
                ]
            }],
            "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.2}
        }
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 401:
                return None, "Gemini API key is invalid. Please check your .env file."
            if r.status_code == 403:
                return None, "Gemini API key expired or has insufficient permissions."
            if r.status_code == 429:
                time.sleep(3)
                r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 429:
                return None, "Gemini quota exceeded. Wait a minute and try again, or create a new free API key at https://aistudio.google.com/apikey and add it to .env as GEMINI_API_KEY for more quota."
            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}"
                print(f"Gemini vision {model}: {r.status_code} {r.text[:300]}")
                continue
            data = r.json()
            candidates = data.get("candidates") or []
            if not candidates:
                block = (data.get("promptFeedback") or {}).get("blockReason") or "No candidates"
                last_error = block
                print(f"Gemini vision {model}: no candidates, promptFeedback={data.get('promptFeedback')}")
                continue
            parts = (candidates[0].get("content") or {}).get("parts") or []
            if not parts:
                last_error = "Empty response"
                continue
            text = (parts[0].get("text") or "").strip()
            if not text:
                last_error = "Empty text"
                continue
            text = text.replace("```json", "").replace("```", "").strip()
            start, end = text.find("{"), text.rfind("}") + 1
            if start < 0 or end <= start:
                last_error = "No JSON in response"
                print(f"Gemini vision {model}: no JSON found, got: {text[:200]}")
                continue
            raw = text[start:end]
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                last_error = "Invalid JSON"
                print(f"Gemini vision {model} JSON error: {e}, snippet: {raw[:150]}")
                continue
            if isinstance(obj.get("score"), (int, float)):
                obj["score"] = int(obj["score"])
            else:
                obj["score"] = 85
            return {k: str(obj.get(k, "")) for k in ["name", "origin", "score", "material", "style", "description"]}, None
        except requests.exceptions.Timeout:
            last_error = "Timeout"
            continue
        except Exception as e:
            last_error = str(e)
            print(f"Gemini vision {model} error: {e}")
            continue
    return None, last_error


def _analyze_craft_local_fallback(image_data):
    """Run local GLM-OCR for craft analysis (no Gemini). Returns result dict or None."""
    if not image_data:
        return None
    print("Running local GLM-OCR analysis...")
    return _analyze_craft_glm_ocr(image_data)


# Cached tokenizer/model for GLM-OCR (loaded once)
_glm_ocr_tokenizer = None
_glm_ocr_model = None


def _analyze_craft_glm_ocr(image_data):
    """Local analysis using zai-org/GLM-OCR with AutoTokenizer + AutoModelForImageTextToText only."""
    if not image_data or len(image_data) < 100:
        return None
    try:
        from transformers import AutoTokenizer, AutoModelForImageTextToText
        import torch
    except ImportError:
        print("GLM-OCR skip: transformers or torch not installed")
        return None
    global _glm_ocr_tokenizer, _glm_ocr_model
    model_path = os.environ.get("GLM_OCR_MODEL", "zai-org/GLM-OCR")
    tmp_path = None
    try:
        if _glm_ocr_tokenizer is None or _glm_ocr_model is None:
            print("Loading GLM-OCR model (first time)...")
            _glm_ocr_tokenizer = AutoTokenizer.from_pretrained(model_path)
            try:
                _glm_ocr_model = AutoModelForImageTextToText.from_pretrained(
                    model_path,
                    torch_dtype="auto",
                    device_map="auto",
                )
            except ValueError as e:
                if "accelerate" in str(e).lower():
                    print("accelerate not installed; loading model without device_map (pip install accelerate for GPU).")
                    _glm_ocr_model = AutoModelForImageTextToText.from_pretrained(
                        model_path,
                        torch_dtype="auto",
                    )
                else:
                    raise
        fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
        try:
            os.write(fd, image_data)
        finally:
            os.close(fd)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "url": tmp_path},
                    {"type": "text", "text": "Describe in one short sentence: object type, material (e.g. silk, cotton, fabric, clay, wood, textile), and style. Be specific."},
                ],
            }
        ]
        inputs = _glm_ocr_tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs = {k: v.to(_glm_ocr_model.device) if hasattr(v, "to") else v for k, v in inputs.items()}
        inputs.pop("token_type_ids", None)
        generated_ids = _glm_ocr_model.generate(**inputs, max_new_tokens=512)
        output_text = _glm_ocr_tokenizer.decode(
            generated_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=False
        ).strip()
        # Strip special tokens that may appear in model output (e.g. <|user|>, <|end|>)
        for token in ["<|user|>", "<|end|>", "<|assistant|>", "<|im_end|>", "<|im_start|>", "<|system|>"]:
            output_text = output_text.replace(token, "")
        output_text = re.sub(r"\s+", " ", output_text).strip()
        if not output_text or len(output_text) < 3:
            return None
        output_lower = output_text.lower()
        material = "—"
        # Map model words to display material; order doesn't matter — we use first occurrence in output
        craft_words = [
            "wood", "wooden", "silk", "cotton", "fabric", "cloth", "clay", "ceramic", "brass", "metal",
            "paper", "gold", "embroidery", "textile", "leather", "jute", "terracotta", "stone", "woven", "handmade",
            "bamboo", "copper", "silver", "bronze", "pottery", "glass", "bead", "beads"
        ]
        first_pos = len(output_lower) + 1
        for word in craft_words:
            pos = output_lower.find(word)
            if pos >= 0 and pos < first_pos:
                first_pos = pos
                material = "Wood" if word in ("wood", "wooden") else "Beads" if word in ("bead", "beads") else word.title()
        # If model gave a generic/wrong description (e.g. "plastic", "rectangular object"), replace with neutral text
        generic_markers = [
            "plastic", "rectangular object", "smooth surface", "minimalist", "glossy finish", "geometric shape",
            "glossy", "reflect light", "clean lines", "single object", "similar material"
        ]
        has_craft = any(w in output_lower for w in craft_words)
        has_generic = any(m in output_lower for m in generic_markers)
        if has_generic and not has_craft:
            description = "Indian handicraft (image-based analysis). For best material and style details, use a clear photo of the item or any text/labels on it."
        else:
            raw_desc = output_text[:500] + ("..." if len(output_text) > 500 else "")
            # Normalize "object type: x material: y style: z" into readable "Object: x. Material: y. Style: z."
            raw_desc = raw_desc.replace("object type:", "Object:").replace("object type ", "Object: ")
            raw_desc = raw_desc.replace("material:", "Material:").replace("material ", "Material: ")
            raw_desc = raw_desc.replace("style:", "Style:").replace("style ", "Style: ")
            if "Object:" in raw_desc or "Material:" in raw_desc or "Style:" in raw_desc:
                raw_desc = re.sub(r"\s+", " ", raw_desc).strip()
            description = raw_desc
        print("GLM-OCR fallback succeeded.")
        return {
            "name": "Indian Handicraft",
            "origin": "India",
            "score": 82,
            "material": material,
            "style": "Heritage craft",
            "description": description,
            "engine": "GLM-OCR (local)",
        }
    except Exception as e:
        print(f"GLM-OCR fallback error: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# Route for AI Image Analysis (Computer Vision)
@app.route('/api/analyze-craft', methods=['POST'])
@login_required
def analyze_craft():
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400
    image_file = request.files['image']
    if not image_file or not image_file.filename:
        return jsonify({"error": "No image file selected"}), 400
    image_data = image_file.read()
    if not image_data or len(image_data) < 100:
        return jsonify({"error": "Image file is empty or too small"}), 400
    # Cap size for API (e.g. 4 MB)
    if len(image_data) > 4 * 1024 * 1024:
        return jsonify({"error": "Image too large. Use an image under 4 MB."}), 400

    mime = image_file.content_type or "image/jpeg"
    if not mime.startswith("image/"):
        mime = "image/jpeg"

    # Try Gemini when key is set; on failure (e.g. invalid/expired key) try local GLM-OCR so user still gets an analysis
    error_hint = None
    if GEMINI_API_KEY and GEMINI_API_KEY.strip():
        result, error_hint = _analyze_craft_gemini(image_data, mime_type=mime)
        if result:
            result["mode"] = "live"
            result["engine"] = "Gemini Vision"
            return jsonify(result)
    # No Gemini key or Gemini failed: try local GLM-OCR
    result = _analyze_craft_local_fallback(image_data)
    if result:
        result["mode"] = "live"
        if error_hint and any(x in error_hint.lower() for x in ["invalid", "expired", "permission", "401", "403"]):
            result["description"] = (result.get("description") or "") + f" (Note: Analysis used local fallback because: {error_hint})"
        return jsonify(result)

    desc = "We couldn't run a full analysis on this image."
    if error_hint:
        desc += " " + error_hint
    else:
        desc += " Please try again with a clear photo."
    return jsonify({"error": desc}), 502


# --- AI Design Generation (Text-to-Image) ---
@app.route('/api/generate-design', methods=['POST'])
@login_required
def generate_design():
    start_time = time.time()
    data = request.json or {}
    user_prompt = (data.get("description") or "").strip()
    style = (data.get("style") or "Traditional").strip()
    material = (data.get("material") or "Clay").strip()

    if not user_prompt:
        return jsonify({"error": "Please describe your design."}), 400

    # 1. Refine Prompt using Gemini Text
    refined_prompt = f"{style} {material} Indian handicraft: {user_prompt}"
    title = "Custom Craft Design"
    desc = f"A unique {style} design made of {material}."

    if GEMINI_API_KEY:
        try:
            # Ask Gemini to create a better image generation prompt
            model_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + GEMINI_API_KEY
            payload = {
                "systemInstruction": {
                    "parts": [{"text": "You are an expert prompt engineer for Indian heritage crafts. Your goal is to take a user's rough idea and turn it into a high-quality, photorealistic image generation prompt for AI. Focus on lighting, texture, cultural details, and camera angle. Output ONLY the prompt text, no intro."}]
                },
                "contents": [{
                    "parts": [{"text": f"User Idea: {user_prompt}\nStyle: {style}\nMaterial: {material}\n\nCreate a detailed image prompt:"}]
                }]
            }
            r = requests.post(model_url, json=payload, timeout=6)
            if r.status_code == 200:
                gemini_resp = r.json()
                text = (gemini_resp.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text and len(text) > 10:
                    refined_prompt = text.strip()
                    # Generate a nice title/desc too?
                    title = f"{style} {material} Concept"
                    desc = f"AI-enhanced design based on '{user_prompt}'."
        except Exception as e:
            print(f"Gemini prompt refinement failed: {e}")

    # 2. Generate Image (Server-Side Proxy with Key)
    # We use the refined prompt from Gemini for best results
    try:
        image_url, provider, err_msg = generate_image_design(refined_prompt)
        
        if not image_url:
             return jsonify({"error": err_msg or "Image generation failed."}), 502

        # Final check: Don't start artisan matching if we are already over the 26s limit
        elapsed = time.time() - start_time
        if elapsed > 26:
            print(f"Request breach: {elapsed:.1f}s. Abandoning artisan match to prevent gateway 502.")
            return jsonify({
                "image_url": image_url,
                "title": title,
                "description": desc,
                "prompt_used": refined_prompt,
                "provider": provider,
                "warning": "Artisan matching skipped due to processing timeout."
            })

        # 4. Add Artisan Match
        artisan_match = find_artisan_match(material, style, user_prompt)
        
        # 5. Get Realistic Price
        price_range = artisan_match.get("price_range", "₹2,000 – ₹5,000")
        final_price = get_authentic_price(user_prompt, material, style, price_range)

        # Inject price back into match for UI consistency
        artisan_match["price"] = final_price

        return jsonify({
            "image_url": image_url, # Now a Base64 data URI
            "title": title,
            "description": desc,
            "prompt_used": refined_prompt,
            "artisan_match": artisan_match,
            "provider": provider
        })
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"CRASH in generate_design: {error_detail}")
        return jsonify({
            "error": f"Internal Server Crash: {str(e)}",
            "traceback": error_detail
        }), 500


@app.route('/api/proxy-image')
def proxy_image():
    """Proxy image requests to bypass CORS/Referer blocks on Render."""
    url = request.args.get('url')
    if not url:
        return "No URL provided", 400
    
    try:
        # User-Agent to look like a real browser (avoids 403 blocks)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        r = requests.get(url, headers=headers, stream=True, timeout=20)
        
        # Pass along the content type (e.g., image/jpeg)
        return make_response(r.content, r.status_code, {'Content-Type': r.headers.get('Content-Type', 'image/jpeg')})
    except Exception as e:
        print(f"Proxy error for {url}: {e}")
        return f"Proxy failed: {e}", 502


# --- Whisper speech-to-text (optional, for voice page when browser speech API fails) ---
_whisper_pipe = None


def _get_whisper_pipeline():
    """Lazy-load Whisper ASR pipeline. Uses WHISPER_MODEL from env (default: openai/whisper-small)."""
    global _whisper_pipe
    if _whisper_pipe is not None:
        return _whisper_pipe
    try:
        import torch
        from transformers import pipeline as hf_pipeline
        model_id = os.environ.get("WHISPER_MODEL", "openai/whisper-small")
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        _whisper_pipe = hf_pipeline(
            "automatic-speech-recognition",
            model=model_id,
            torch_dtype=dtype,
            device=device,
        )
        print(f"Whisper loaded: {model_id} on {device}")
        return _whisper_pipe
    except Exception as e:
        print(f"Whisper load failed: {e}")
        import traceback
        traceback.print_exc()
        return None


@app.route('/api/transcribe', methods=['POST'])
def transcribe():
    """Transcribe audio using Whisper. Accepts multipart file 'audio' (webm, mp3, wav, etc.). Returns { text } or { error }."""
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400
    audio_file = request.files["audio"]
    if not audio_file or not audio_file.filename:
        return jsonify({"error": "No audio file selected"}), 400
    data = audio_file.read()
    if not data or len(data) < 100:
        return jsonify({"error": "Audio file too small or empty"}), 400
    if len(data) > 25 * 1024 * 1024:
        return jsonify({"error": "Audio too large (max 25 MB)"}), 400
    ext = os.path.splitext(audio_file.filename)[1].lower() or ".webm"
    if ext not in (".webm", ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".mp4"):
        ext = ".webm"
    tmp_path = None
    try:
        pipe = _get_whisper_pipeline()
        if pipe is None:
            return jsonify({"error": "Whisper not available. Install: pip install transformers torch; set WHISPER_MODEL in .env (e.g. openai/whisper-small)."}), 503
        fd, tmp_path = tempfile.mkstemp(suffix=ext)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        try:
            out = pipe(tmp_path, generate_kwargs={"language": "en", "task": "transcribe"})
        except Exception as path_err:
            # WebM/Opus may need ffmpeg; try ffmpeg_read(bytes, sampling_rate)
            try:
                from transformers.pipelines.audio_utils import ffmpeg_read
                raw = ffmpeg_read(data, 16000)
                if raw is not None and (hasattr(raw, "size") and raw.size > 0 or len(raw) > 0):
                    out = pipe({"array": raw, "sampling_rate": 16000}, generate_kwargs={"language": "en", "task": "transcribe"})
                else:
                    raise path_err
            except Exception:
                raise path_err
        text = (out.get("text") or "").strip()
        return jsonify({"text": text})
    except Exception as e:
        print(f"Transcribe error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.route('/api/test-gemini', methods=['GET'])
def test_gemini():
    """Check if GEMINI_API_KEY works. Open in browser: http://127.0.0.1:5000/api/test-gemini"""
    key = (GEMINI_API_KEY or "").strip()
    if not key:
        return jsonify({
            "ok": False,
            "key_set": False,
            "message": "GEMINI_API_KEY is not set in .env",
            "hint": "Add your key to .env and restart the app."
        })
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": "Reply with exactly: OK"}]}],
        "generationConfig": {"maxOutputTokens": 10}
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            text = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return jsonify({
                "ok": True,
                "key_set": True,
                "status": 200,
                "message": "API key works. Gemini responded: " + (text.strip()[:50] or "(empty)")
            })
        if r.status_code == 401 or r.status_code == 403:
            return jsonify({
                "ok": False,
                "key_set": True,
                "status": r.status_code,
                "message": "API key invalid or expired",
                "detail": r.text[:200]
            })
        if r.status_code == 429:
            return jsonify({
                "ok": False,
                "key_set": True,
                "status": 429,
                "message": "Quota exceeded (rate limit). Wait a few minutes or use a different key.",
                "detail": r.text[:200]
            })
        return jsonify({
            "ok": False,
            "key_set": True,
            "status": r.status_code,
            "message": f"Unexpected response: {r.status_code}",
            "detail": r.text[:300]
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "key_set": True,
            "message": "Request failed: " + str(e)
        })


# --- Craft Assistant Chatbot (Gemini-powered) ---
# --- Craft Assistant Chatbot (Gemini-powered with RAG) ---

def search_products_heritage(query):
    """Search HERITAGE_DATA for products relevant to the query."""
    from data.products_heritage import HERITAGE_DATA

    query = query.lower().strip()
    results = []
    
    # Flatten and score
    for state, data in HERITAGE_DATA.items():
        for item in data["items"]:
            score = 0
            # Search fields
            text_corpus = f"{item['name']} {item['category']} {state} {item.get('fun_fact', '')}".lower()
            
            # Simple keyword matching
            if query in text_corpus:
                score += 10 # Exact phrase match
            
            query_words = query.split()
            for word in query_words:
                if len(word) > 2 and word in text_corpus:
                    score += 3
                if word in item['name'].lower():
                    score += 5 # Bonus for name match
            
            if score > 0:
                # Add price logic for display
                idx = 0 if len(item["name"]) % 2 == 0 else 1
                price = item["price_range"][idx]
                
                results.append({
                    "name": item["name"],
                    "state": state,
                    "category": item["category"],
                    "price_range": f"₹{item['price_range'][0]}-{item['price_range'][1]}",
                    "fun_fact": item.get("fun_fact", ""),
                    "score": score
                })
    
    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:15] # Return top 15 most relevant


def build_chatbot_context(user_query=""):
    """Build dynamic context based on user query (RAG-lite)."""
    
    # 1. Search for relevant products
    relevant_products = search_products_heritage(user_query)
    
    # 2. Search for relevant Artisans (New Logic)
    # Re-generate the stable list of artists to check for name matches
    all_artists = get_artists() 
    found_artist_info = ""
    
    # Check for specific artisan matches (Name, Craft, State)
    matched_artisans = []
    q_lower = user_query.lower()

    for artist in all_artists:
        # Match by Name (e.g. "Vihaan"), Craft (e.g. "Kondapalli"), or State (e.g. "Andhra")
        if (artist['name'].lower() in q_lower) or \
           (artist['style'].lower() in q_lower) or \
           (artist['state'].lower() in q_lower):
            matched_artisans.append(artist)
    
    # If query is generic about "artists" or "artisans" but no specific match found, show a sample
    if not matched_artisans and any(k in q_lower for k in ['artist', 'artisan', 'maker', 'who makes', 'creator']):
        import random
        matched_artisans = random.sample(all_artists, min(len(all_artists), 5))

    # Limit to top 5 matches to avoid context overflow
    for artist in matched_artisans[:5]:
        found_artist_info += f"""
### FOUND ARTISAN PROFILE
- Name: {artist['name']}
- State: {artist['state']}
- Craft: {artist['style']}
- Experience: {artist['experience']} Years
- Work Hours: {artist['meta']['labor']} (Labor Time)
- Bio: {artist['description']}
"""
    
    # 3. If no specific results, provide a diverse mix (fallback to 'featured')
    if not relevant_products and not found_artist_info:
        # Fallback: Get 1 item from each valid state to show diversity
        from data.products_heritage import HERITAGE_DATA
        for state, data in list(HERITAGE_DATA.items())[:8]:
             if data["items"]:
                 item = data["items"][0]
                 relevant_products.append({
                    "name": item["name"],
                    "state": state,
                    "category": item["category"],
                    "price_range": f"₹{item['price_range'][0]}-{item['price_range'][1]}",
                    "fun_fact": item.get("fun_fact", "")
                 })

    # 4. Format product list for LLM
    products_json = json.dumps(relevant_products, indent=2)

    context = f"""
You are the Craft Assistant for Desh Ke Haath, India's premier heritage craft platform.
Your goal is to be a knowledgeable, warm, and culturally rich guide to Indian handicrafts and culture.

{found_artist_info}

### CORE IDENTITY
- Name: Craft Assistant (Desh Ke Haath)
- Mission: "Prachin Kala, Adhunik Disha" (Ancient Art, Modern Direction).
- Tone: Warm, respectful (use "Namaste"), informative.

### CONTEXT: RELEVANT PRODUCTS
Based on the user's interest in "{user_query}", here are the most relevant products from our catalog:
{products_json}

### GENERAL SITE INFO
- Platform: Desh Ke Haath (Heritage E-commerce)
- Pages: Home, Map (Explore by State), Products, Artists, AI Craft (Design your own).
- Shipping: India-wide (5-7 days), Free > ₹2000.
- Payment: UPI, Cards, COD.
- Authenticity: 100% Verified Artisans.

### STRICT GUIDELINES (SCOPE CONTROL)
1. **Site Only**: You ONLY answer questions about Desh Ke Haath, its products, its artisans, and site features (AI Craft, Map, Voice Search, etc.).
2. **No General Knowledge**: You MUST NOT answer general questions about India (geography, history, population, etc.) if they aren't directly related to a product or artisan on our site.
3. **No Unrelated Topics**: If asked about anything else (tech, science, jokes, other platforms), refuse politely.
4. **Style**: Concise (2-3 sentences), warm, and professional.
5. **Goal**: Help the user discover and buy heritage crafts on Desh Ke Haath.

"""
    return context


def get_user_orders_context():
    """Get user's orders for chatbot context (if logged in)."""
    if not current_user.is_authenticated:
        return "User is NOT logged in. For order tracking, ask them to sign in via the profile api."
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(5).all()
    if not orders:
        return "User is logged in but has NO orders yet."
    
    lines = []
    for o in orders:
        order_label = o.order_number or f"#{o.id}"
        items_str = ", ".join([f"{i.product_name} (x{i.quantity})" for i in o.items])
        lines.append(f"- Order {order_label}: ₹{o.total_amount:.0f} | Status: {o.status} | Items: {items_str} | Date: {o.created_at.strftime('%d %b %Y')}")
    return "USER'S RECENT ORDERS:\n" + "\n".join(lines)


def _fallback_response(msg):
    """Rule-based fallback when Gemini fails."""
    m = msg.lower()
    if any(x in m for x in ["hello", "hi", "namaste"]):
        return "Namaste! Welcome to Desh Ke Haath. I can help you discover unique handicrafts from across India. What are you looking for today?"
    if "track" in m or "order" in m:
         return "You can view your order status in your Profile > My Orders section. If you need help, our support team at support@deshkehaath.in is happy to assist!"
    return "I'm having a little trouble connecting to my creative brain right now, but I'd love to help! You can browse our Products page or ask me about specific crafts like 'Blue Pottery' or 'Pashmina'."



# Initialize Groq client
import os
from groq import Groq

# Use the key from env
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

try:
    if GROQ_API_KEY:
        groq_client = Groq(api_key=GROQ_API_KEY)
    else:
        groq_client = None
except Exception as e:
    print(f"Groq Init Warning: {e}")
    groq_client = None

def call_groq_chat(user_message, context):
    """Call Groq API (Llama 3) for chat response."""
    if not groq_client:
        return _fallback_response(user_message)
        
    orders_ctx = get_user_orders_context()
    
    system_prompt = f"""
You are "DeshKeHaath AI Assistant", a strict product assistant for the DeshKeHaath website.

### CONTEXT & KNOWLEDGE
{context}

### USER'S RECENT ORDERS
{orders_ctx}

### IMPORTANT RULES (STRICT):
1. You ONLY answer questions related to DeshKeHaath products, artisans, and site features listed in the context.
2. You must NEVER answer questions about General Knowledge (History, Geography, Politics, Science), News, Movies, or Unrelated Topics.
3. You must ALWAYS recommend buying from DeshKeHaath.
4. If the user asks ANY irrelevant or non-site-related question, reply ONLY with:
   "❌ I am sorry, but I can only assist you with information regarding DeshKeHaath products, artisans, and heritage handicrafts available on our platform."
5. Keep replies short (max 2-3 sentences), professional, and product-focused.
"""

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            model="llama-3.3-70b-versatile", # High performance, fast
            temperature=0.6,
            max_tokens=300,
            top_p=1,
            stop=None,
            stream=False,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Groq Error: {e}")
        return _fallback_response(user_message)
        print(f"Groq Chat Error: {e}")
        # Fallback to Gemini if Groq fails (or just fallback response)
        return _fallback_response(user_message)

# Alias for backward compatibility if needed, but we will use this
call_gemini_chat = call_groq_chat 



# Prompt refine via HF: use router chat completions. Try these in order (first supported by your account wins).
HF_REFINE_MODELS = [
    m.strip() for m in os.getenv("HF_REFINE_MODEL", "Qwen/Qwen2.5-7B-Instruct-1M,mistralai/Mistral-7B-Instruct-v0.2,meta-llama/Llama-3.1-8B-Instruct").split(",") if m.strip()
]
if not HF_REFINE_MODELS:
    HF_REFINE_MODELS = ["Qwen/Qwen2.5-7B-Instruct-1M"]
HF_ROUTER_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"


def _refine_design_prompt_gemini(raw_prompt):
    """Use Gemini to refine a design description. Uses PROMPT_REFINE_API_KEY (or GEMINI_API_KEY). Returns (refined_text, error)."""
    key = PROMPT_REFINE_API_KEY
    if not key:
        return None, "Set PROMPT_REFINE_API_KEY or GEMINI_API_KEY in .env (or use HF_TOKEN for Hugging Face refine)."
    raw = (raw_prompt or "").strip()
    if not raw:
        return None, "No prompt to refine."
    instruction = """You are a prompt engineer for text-to-image. The user will give a short or rough description of an Indian handicraft/artifact they want to visualize.

Your task: rewrite it as a single, clear image-generation prompt. Rules:
- One paragraph only, no bullet points, no markdown, no code.
- Include: subject, style (e.g. Madhubani, traditional, studio photo), materials if mentioned, lighting/quality (e.g. high resolution, sharp focus) if it helps.
- Keep it under 400 characters. Output ONLY the refined prompt, nothing else."""

    for model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-001"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": instruction + "\n\nUser's description:\n" + raw[:800]}]}],
            "generationConfig": {"maxOutputTokens": 256, "temperature": 0.2}
        }
        for attempt in range(2):
            try:
                r = requests.post(url, json=payload, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    text = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if text and text.strip():
                        return text.strip()[:500], None
                if r.status_code == 429:
                    if attempt == 0:
                        time.sleep(4)
                        continue
                    return None, "Gemini is busy (rate limit). Wait 30–60 seconds and click ✨ again, or use your text as-is and hit Generate."
            except Exception:
                break
    return None, "Could not refine prompt. Check PROMPT_REFINE_API_KEY or GEMINI_API_KEY in .env (or add HF_TOKEN for HF fallback)."


def _refine_design_prompt_pollinations(raw_prompt):
    """Use Pollinations AI chat completions to refine the prompt when POLLINATIONS_API_KEY is set."""
    if not POLLINATIONS_API_KEY:
        return None, "POLLINATIONS_API_KEY not set."
    raw = (raw_prompt or "").strip()
    if not raw:
        return None, "No prompt to refine."
    instruction = (
        "Rewrite this as a single, vivid image-generation prompt for an Indian handicraft. "
        "One short paragraph, under 400 characters. No bullet points, no markdown, no extra text. "
        "Output ONLY the refined prompt."
    )
    user_content = f"User's description: {raw[:600]}"
    url = "https://gen.pollinations.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openai",
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 256,
        "temperature": 0.4,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=40)
        if r.status_code in (401, 403):
            return None, "Pollinations API key invalid or missing permissions."
        try:
            data = r.json()
        except Exception:
            data = None
        if not isinstance(data, dict):
            r.raise_for_status()
            return None, "Pollinations returned invalid JSON."
        if data.get("error"):
            err_obj = data.get("error")
            err_str = err_obj if isinstance(err_obj, str) else str(err_obj)
            return None, err_str[:200]
        choices = (data or {}).get("choices") or []
        if choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            text = (msg.get("content") or "") if isinstance(msg, dict) else ""
            if isinstance(text, str) and text.strip():
                return text.strip()[:500], None
        return None, "Pollinations returned no text."
    except Exception as e:
        return None, str(e)[:200]


def _refine_design_prompt_hf(raw_prompt):
    """Use Hugging Face router chat completions (v1) for prompt refine. Tries multiple models if one is not supported."""
    if not HF_TOKEN or not HF_TOKEN.strip():
        return None, "HF_TOKEN not set (needed for fallback refine)."
    raw = (raw_prompt or "").strip()
    if not raw:
        return None, "No prompt to refine."
    instruction = "Rewrite as a single image-generation prompt for an Indian handicraft. One short paragraph, under 400 characters. Output ONLY the refined prompt, nothing else."
    user_content = f"User's description: {raw[:600]}"
    headers = {"Authorization": f"Bearer {HF_TOKEN.strip()}", "Content-Type": "application/json"}
    last_error = "No model succeeded."
    for model in HF_REFINE_MODELS:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 256,
            "temperature": 0.2,
        }
        try:
            r = requests.post(HF_ROUTER_CHAT_URL, headers=headers, json=payload, timeout=60)
            if r.status_code == 503:
                last_error = "Refine model is loading (503). Try again in a minute."
                continue
            if r.status_code in (401, 403):
                return None, "HF token invalid. Use a token with 'Make calls to Inference Providers' at hf.co/settings/tokens."
            try:
                data = r.json()
            except Exception:
                data = None
            if data is None:
                r.raise_for_status()
                continue
            if isinstance(data, dict) and data.get("error"):
                err_obj = data.get("error") or data.get("message") or "Request failed."
                err_str = err_obj if isinstance(err_obj, str) else str(err_obj)
                code = (data.get("code") or "").lower()
                if "model_not_supported" in code or "model_not_found" in code or "not supported" in err_str.lower() or "does not exist" in err_str.lower():
                    last_error = err_str[:200]
                    continue
                return None, err_str[:200]
            choices = (data or {}).get("choices") or []
            if choices:
                msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                text = (msg.get("content") or "") if isinstance(msg, dict) else ""
                if isinstance(text, str) and text.strip():
                    return text.strip()[:500], None
            last_error = "No text in response."
        except requests.RequestException:
            continue
    return None, last_error[:200]


@app.route('/api/refine-design-prompt', methods=['POST'])
def refine_design_prompt():
    """Refine design description: try Pollinations (if key set), then Gemini, then HF. Never 502."""
    data = request.json or {}
    raw = (data.get("prompt") or "").strip()
    if not raw:
        return jsonify({"error": "No prompt provided."}), 400
    err = None
    # 1) Try Pollinations if key is set
    if POLLINATIONS_API_KEY:
        refined_poll, err_poll = _refine_design_prompt_pollinations(raw)
        if refined_poll:
            return jsonify({"prompt": refined_poll, "refined": True})
        err = err_poll or err
    # 2) Try Gemini if key is set
    if PROMPT_REFINE_API_KEY:
        refined_gem, err_gem = _refine_design_prompt_gemini(raw)
        if refined_gem:
            return jsonify({"prompt": refined_gem, "refined": True})
        err = err_gem or err or "No Gemini key set."
    else:
        err = err or "No Gemini key set."
    # 3) Try HF (works with only HF_TOKEN, no Gemini/Pollinations needed)
    if HF_TOKEN and HF_TOKEN.strip():
        refined_hf, err_hf = _refine_design_prompt_hf(raw)
        if refined_hf:
            return jsonify({"prompt": refined_hf, "refined": True})
        err = err_hf or err
    else:
        err = err or "Set HF_TOKEN in .env for prompt refinement (or PROMPT_REFINE_API_KEY / GEMINI_API_KEY for Gemini)."
    # Ensure message is always a user-friendly string (never a slice or internal repr)
    msg = err if isinstance(err, str) else str(err)
    if "slice(None" in msg or msg.strip().startswith("slice("):
        msg = "Refine unavailable. Using your text as-is. You can still click Generate."
    msg = (msg or "Using your text as-is. You can still click Generate.")[:500]
    return jsonify({"prompt": raw, "refined": False, "message": msg})





@app.route('/', methods=['GET', 'HEAD'])
def index():
    """Home page - Public Access."""
    return render_template('index.html')


@app.route('/entry')
def entry():
    """Splash gate: Grok video + login/signup. Always shown first."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    resp = make_response(render_template('splash.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/splash')
def splash():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('splash.html')


@app.route('/home')
def home():
    """Alias for index"""
    return redirect(url_for('index'))


@app.route('/login', methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        login_user(user, remember=True)  # Enable remember me for 30 days
        session.permanent = True  # Make session persistent
        return redirect(url_for('index'))
    flash('Invalid email or password.', 'error')
    return redirect(url_for('entry'))


@app.route('/signup', methods=['POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
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
        login_user(user, remember=True)  # Auto-login after signup
        session.permanent = True  # Make session persistent
        flash('Account created successfully! Welcome!', 'success')
        return redirect(url_for('index'))
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

STATE_POPULAR_CRAFTS = {
    "Andhra Pradesh": ["Kondapalli Toys", "Uppada Silk", "Temple Jewellery"],
    "Arunachal Pradesh": ["Bamboo Crafts", "Bead Jewellery", "Wooden Masks"],
    "Assam": ["Jaapi Hat", "Muga Silk", "Bell Metal Crafts"],
    "Bihar": ["Madhubani Painting", "Tussar Silk", "Sikki Grass Crafts"],
    "Chhattisgarh": ["Dhokra Metal", "Kosa Silk", "Wrought Iron"],
    "Goa": ["Coconut Shell Crafts", "Azulejos Tiles", "Kunbi Saree"],
    "Gujarat": ["Bandhani Textile", "Patola Saree", "Kutch Embroidery"],
    "Haryana": ["Phulkari", "Jhajjar Pottery", "Brass Utensils"],
    "Himachal Pradesh": ["Kullu Shawls", "Chamba Rumal", "Silver Jewellery"],
    "Jharkhand": ["Sohrai Painting", "Tussar Silk", "Bamboo Crafts"],
    "Karnataka": ["Mysore Silk", "Channapatna Toys", "Sandalwood Carvings"],
    "Kerala": ["Kasavu Saree", "Coir Crafts", "Nettur Petti"],
    "Madhya Pradesh": ["Gond Art", "Chanderi Saree", "Maheshwari Fabric"],
    "Maharashtra": ["Warli Art", "Paithani Saree", "Kolhapuri Jewellery"],
    "Meghalaya": ["Bamboo Bowls", "Eri Silk", "Black Pottery"],
    "Mizoram": ["Puan Saree", "Bamboo Hats", "Beadwork"],
    "Nagaland": ["Warrior Shawls", "Hornbill Art", "Beaded Necklaces"],
    "Odisha": ["Pattachitra", "Sambalpuri Saree", "Silver Filigree"],
    "Punjab": ["Phulkari", "Punjabi Jutti", "Parandi"],
    "Rajasthan": ["Blue Pottery", "Bandhani", "Thewa Jewellery"],
    "Sikkim": ["Thangka Painting", "Lepcha Weaving", "Wooden Tables"],
    "Tamil Nadu": ["Kanchipuram Silk", "Tanjore Painting", "Temple Jewellery"],
    "Telangana": ["Pochampally Ikat", "Bidriware", "Nirmal Paintings"],
    "Tripura": ["Bamboo Art", "Handloom", "Cane Furniture"],
    "Uttar Pradesh": ["Chikan Embroidery", "Banarasi Silk", "Brassware"],
    "Uttarakhand": ["Pichora Saree", "Ringaal Basketry", "Aipan Art"],
    "West Bengal": ["Baluchari Silk", "Terracotta Horse", "Kantha Embroidery"],
    "Jammu and Kashmir": ["Pashmina Shawl", "Papier Mache", "Walnut Carving"],
    "Ladakh": ["Tibetan Jewelry", "Woolen Rugs", "Prayer Wheels"]
}

@app.route('/products')
def products():
    search_query = request.args.get('search', '').lower().strip()
    sort_by = request.args.get('sort', 'default')
    category_filter = request.args.get('category', 'All')
    state_filter = request.args.get('state', 'all')
    
    all_products = []
    for state, data in HERITAGE_DATA.items():
        if state_filter != 'all' and state.lower() != state_filter.lower():
            continue
            
        for item in data['items']:
            if category_filter != 'All' and item['category'] != category_filter:
                continue
            # Improved Search Logic: Token-based (stop words, all keywords); include image_query
            if search_query:
                q_tokens = search_query.replace(',', ' ').replace('.', ' ').split()
                stop_words = {'show', 'me', 'find', 'the', 'a', 'an', 'please', 'i', 'want', 'looking', 'for', 'in', 'from', 'of', 'with'}
                keywords = [w for w in q_tokens if w not in stop_words]
                if keywords:
                    product_text = f"{item['name']} {state} {item['category']} {item.get('fun_fact','')} {item.get('image_query','')}".lower()
                    if not all(k in product_text for k in keywords):
                        continue

            product_id = f"{state.replace(' ', '_')}_{item['name'].replace(' ', '_')}"
            price = item['price_range'][0] + (len(item['name']) % 10) * (item['price_range'][1] - item['price_range'][0]) // 10
            
            # Use local_image if available, otherwise generate Pollinations URL
            if 'local_image' in item:
                image_url = item['local_image']
            else:
                img_query = item.get('image_query', f"{state} {item['name']} Indian handicraft")
                image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(img_query)}?width=800&height=800&nologo=true&seed={len(item['name'])}"
            
            # Check if this product is popular in its state (for GI tag)
            popular_list = STATE_POPULAR_CRAFTS.get(state, [])
            is_popular = any(p_name.lower() in item['name'].lower() for p_name in popular_list)

            # Get story from state data
            story = data.get('stories', {}).get(item['name'], "Deeply rooted in Indian heritage, this craft represents centuries of tradition.")

            all_products.append({
                "id": product_id,
                "name": item['name'],
                "state": state,
                "category": item['category'],
                "price": price,
                "fun_fact": item['fun_fact'],
                "story": story,
                "rating": 4.0 + (len(item['name']) % 10) / 10,
                "reviews": 10 + (len(item['name']) % 50),
                "image_url": image_url,
                "is_popular": is_popular,
                "model_3d": item.get('model_3d')
            })
    
    # Sort
    if sort_by == 'price_low':
        all_products.sort(key=lambda x: x['price'])
    elif sort_by == 'price_high':
        all_products.sort(key=lambda x: x['price'], reverse=True)
    elif sort_by == 'rating':
        all_products.sort(key=lambda x: x['rating'], reverse=True)
    else:
        # Default sort: Name, but prioritize 3D models at the very top
        all_products.sort(key=lambda x: (not x.get('model_3d'), x['name']))
        
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
        image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(img_query)}?width=1024&height=1024&nologo=true&seed={len(found_item['name'])}"

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
        "image_query": img_query,
        "model_3d": found_item.get('model_3d')
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
                    r_image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(r_img_query)}?width=400&height=400&nologo=true&seed={len(i['name'])}"
                
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
    resp = make_response(render_template('voice.html'))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp



# Helper to generate artist profiles
def get_artists():
    import random
    
    # Real data from Google Sheet
    real_artisans = [
        {
            "craft": "Kondapalli Toys",
            "state": "Andhra Pradesh",
            "labor_time": "15 – 25 Hours",
            "price_range": "₹499 – ₹2,999",
            "why_price": "Carved from Tella Poniki (softwood) and hand-painted. Prices vary by set size (e.g., a \"Marriage Set\" vs. a single figurine).",
            "description": "Specialist in Kondapalli Toys. Carved from Tella Poniki (softwood) and hand-painted. Prices vary by set size (e.g., a \"Marriage Set\" vs. a single figurine). Approx labor: 15 – 25 Hours."
        },
        {
            "craft": "Uppada Silk Saree",
            "state": "Andhra Pradesh",
            "labor_time": "150 – 400 Hours",
            "price_range": "₹3,999 – ₹18,000",
            "why_price": "Uses the Jamdani weaving technique. A bridal saree with pure zari can take up to 2 months of non-stop hand-weaving.",
            "description": "Specialist in Uppada Silk Saree. Uses the Jamdani weaving technique. A bridal saree with pure zari can take up to 2 months of non-stop hand-weaving. Approx labor: 150 – 400 Hours."
        },
        {
            "craft": "Temple Jewellery",
            "state": "Andhra Pradesh",
            "labor_time": "40 – 120 Hours",
            "price_range": "₹1,299 – ₹8,500",
            "why_price": "Hand-crafted silver with 24k gold leaf plating (Kemp work). Complex bridal sets require weeks of intricate metalwork.",
            "description": "Specialist in Temple Jewellery. Hand-crafted silver with 24k gold leaf plating (Kemp work). Complex bridal sets require weeks of intricate metalwork. Approx labor: 40 – 120 Hours."
        },
        {
            "craft": "Kalamkari Textile",
            "state": "Andhra Pradesh",
            "labor_time": "60 – 80 Hours",
            "price_range": "₹899 – ₹4,500",
            "why_price": "Srikalahasti style involves 23 steps of natural dyeing and hand-painting with a bamboo pen (kalam) on cotton or silk.",
            "description": "Specialist in Kalamkari Textile. Srikalahasti style involves 23 steps of natural dyeing and hand-painting with a bamboo pen (kalam) on cotton or silk. Approx labor: 60 – 80 Hours."
        },
        {
            "craft": "Etikoppaka Toys",
            "state": "Andhra Pradesh",
            "labor_time": "8 – 12 Hours",
            "price_range": "₹299 – ₹1,499",
            "why_price": "Made from Ankudu wood and finished on a lathe with natural lacquer made from seeds and tree resins.",
            "description": "Specialist in Etikoppaka Toys. Made from Ankudu wood and finished on a lathe with natural lacquer made from seeds and tree resins. Approx labor: 8 – 12 Hours."
        },
        {
            "craft": "Folk Scrolls (Cheriyal)",
            "state": "Andhra Pradesh",
            "labor_time": "40 – 100 Hours",
            "price_range": "₹1,499 – ₹6,500",
            "why_price": "Hand-ground natural pigments on khadi canvas. A full narrative scroll depicting an epic can take several weeks.",
            "description": "Specialist in Folk Scrolls (Cheriyal). Hand-ground natural pigments on khadi canvas. A full narrative scroll depicting an epic can take several weeks. Approx labor: 40 – 100 Hours."
        },
        {
            "craft": "Bamboo Furniture",
            "state": "Arunachal Pradesh",
            "labor_time": "40 – 60 Hours",
            "price_range": "₹699 – ₹4,500",
            "why_price": "Includes deep-forest harvesting and \"curing\" (smoking/soaking) to make it termite-proof and water-strong.",
            "description": "Specialist in Bamboo Furniture. Includes deep-forest harvesting and \"curing\" (smoking/soaking) to make it termite-proof and water-strong. Approx labor: 40 – 60 Hours."
        },
        {
            "craft": "Tribal Wrap (Gale)",
            "state": "Arunachal Pradesh",
            "labor_time": "120 – 180 Hours",
            "price_range": "₹1,299 – ₹3,500",
            "why_price": "Woven on a \"Loin Loom\" (Backstrap loom). Each tribal motif is a \"secret code\" passed down through memory.",
            "description": "Specialist in Tribal Wrap (Gale). Woven on a \"Loin Loom\" (Backstrap loom). Each tribal motif is a \"secret code\" passed down through memory. Approx labor: 120 – 180 Hours."
        },
        {
            "craft": "Wancho Bead Jewelry",
            "state": "Arunachal Pradesh",
            "labor_time": "12 – 24 Hours",
            "price_range": "₹299 – ₹1,500",
            "why_price": "Recently GI-tagged. Authentic pieces use specific color codes (red, blue, orange) to signify bravery and status.",
            "description": "Specialist in Wancho Bead Jewelry. Recently GI-tagged. Authentic pieces use specific color codes (red, blue, orange) to signify bravery and status. Approx labor: 12 – 24 Hours."
        },
        {
            "craft": "Handwoven Textile",
            "state": "Arunachal Pradesh",
            "labor_time": "150 – 250 Hours",
            "price_range": "₹899 – ₹2,500",
            "why_price": "These are high-density weaves. Some ceremonial shawls take nearly 2 months of part-time weaving to complete.",
            "description": "Specialist in Handwoven Textile. These are high-density weaves. Some ceremonial shawls take nearly 2 months of part-time weaving to complete. Approx labor: 150 – 250 Hours."
        },
        {
            "craft": "Wooden Masks",
            "state": "Arunachal Pradesh",
            "labor_time": "50 – 80 Hours",
            "price_range": "₹999 – ₹2,999",
            "why_price": "Carved from Puma or Zokhu wood. Includes multiple layers of natural paint and manual chiseling for \"life-like\" detail.",
            "description": "Specialist in Wooden Masks. Carved from Puma or Zokhu wood. Includes multiple layers of natural paint and manual chiseling for \"life-like\" detail. Approx labor: 50 – 80 Hours."
        },
        {
            "craft": "Traditional Baskets",
            "state": "Arunachal Pradesh",
            "labor_time": "30 – 45 Hours",
            "price_range": "₹699 – ₹2,999",
            "why_price": "Woven with double-layered cane. The weave is so tight it creates surface tension that can briefly hold water.",
            "description": "Specialist in Traditional Baskets. Woven with double-layered cane. The weave is so tight it creates surface tension that can briefly hold water. Approx labor: 30 – 45 Hours."
        },
        {
            "craft": "Jaapi Hat (Fulam)",
            "state": "Assam",
            "labor_time": "12 – 18 Hours",
            "price_range": "₹600",
            "why_price": "Hand-knit from Tokou (palm) leaves and bamboo. Decorative versions (Fulam) require intricate velvet, wool, and sequin work.",
            "description": "Specialist in Jaapi Hat (Fulam). Hand-knit from Tokou (palm) leaves and bamboo. Decorative versions (Fulam) require intricate velvet, wool, and sequin work. Approx labor: 12 – 18 Hours."
        },
        {
            "craft": "Muga Silk Saree",
            "state": "Assam",
            "labor_time": "150 – 200 Hours",
            "price_range": "₹25,000 – ₹45,000",
            "why_price": "Exclusive to Assam. Price includes 2+ months of rearing rare golden silkworms. Hand-weaving a full saree takes 15–20 focused days.",
            "description": "Specialist in Muga Silk Saree. Exclusive to Assam. Price includes 2+ months of rearing rare golden silkworms. Hand-weaving a full saree takes 15–20 focused days. Approx labor: 150 – 200 Hours."
        },
        {
            "craft": "Bamboo Jewellery",
            "state": "Assam",
            "labor_time": "4 – 8 Hours",
            "price_range": "₹400 (Set)",
            "why_price": "Artisans must select 3-year-old \"mature\" bamboo, boil it to prevent cracks, and hand-carve it into lightweight, durable motifs.",
            "description": "Specialist in Bamboo Jewellery. Artisans must select 3-year-old \"mature\" bamboo, boil it to prevent cracks, and hand-carve it into lightweight, durable motifs. Approx labor: 4 – 8 Hours."
        },
        {
            "craft": "Mekhela Chador",
            "state": "Assam",
            "labor_time": "60 – 100 Hours",
            "price_range": "₹4,500 – ₹12,000",
            "why_price": "A two-piece set (skirt and wrap). Hand-weaving authentic motifs on a Taat Xaal (pit loom) is labor-intensive; sunlight \"shining through\" refers to the high thread count.",
            "description": "Specialist in Mekhela Chador. A two-piece set (skirt and wrap). Hand-weaving authentic motifs on a Taat Xaal (pit loom) is labor-intensive; sunlight \"shining through\" refers to the high thread count. Approx labor: 60 – 100 Hours."
        },
        {
            "craft": "Majuli Masks",
            "state": "Assam",
            "labor_time": "40 – 120 Hours",
            "price_range": "₹3,500 (Medium)",
            "why_price": "Made using a bamboo frame, clay, and cow dung layers. Each mask must dry naturally between coats before being painted with organic pigments.",
            "description": "Specialist in Majuli Masks. Made using a bamboo frame, clay, and cow dung layers. Each mask must dry naturally between coats before being painted with organic pigments. Approx labor: 40 – 120 Hours."
        },
        {
            "craft": "Bell Metal Crafts",
            "state": "Assam",
            "labor_time": "24 – 40 Hours",
            "price_range": "₹1,200 (per kg)",
            "why_price": "Made by Sarthebari artisans using an alloy of copper and tin. It involves manual hammering and heating—never machine-cast.",
            "description": "Specialist in Bell Metal Crafts. Made by Sarthebari artisans using an alloy of copper and tin. It involves manual hammering and heating—never machine-cast. Approx labor: 24 – 40 Hours."
        },
        {
            "craft": "Madhubani Painting",
            "state": "Bihar",
            "labor_time": "30 – 120 Hours",
            "price_range": "₹2,500 – ₹8,500",
            "why_price": "Painted with twigs and nibs using natural dyes (cow dung base, rice paste). Prices soar for \"Kachni\" (fine line) work vs \"Bharni\" (filled colors).",
            "description": "Specialist in Madhubani Painting. Painted with twigs and nibs using natural dyes (cow dung base, rice paste). Prices soar for \"Kachni\" (fine line) work vs \"Bharni\" (filled colors). Approx labor: 30 – 120 Hours."
        },
        {
            "craft": "Tussar Silk Saree",
            "state": "Bihar",
            "labor_time": "120 – 180 Hours",
            "price_range": "₹4,500 – ₹15,000",
            "why_price": "Sourced from wild silkworms in Bhagalpur. Includes boiling, hand-spinning, and hand-weaving. Real \"Peace Silk\" (non-violent) carries a premium.",
            "description": "Specialist in Tussar Silk Saree. Sourced from wild silkworms in Bhagalpur. Includes boiling, hand-spinning, and hand-weaving. Real \"Peace Silk\" (non-violent) carries a premium. Approx labor: 120 – 180 Hours."
        },
        {
            "craft": "Sikki Grass Crafts",
            "state": "Bihar",
            "labor_time": "10 – 40 Hours",
            "price_range": "₹600 – ₹2,500",
            "why_price": "Golden grass found in marshes is harvested and dyed. Boxes and dolls are woven so tightly they become sturdy structural items that last decades.",
            "description": "Specialist in Sikki Grass Crafts. Golden grass found in marshes is harvested and dyed. Boxes and dolls are woven so tightly they become sturdy structural items that last decades. Approx labor: 10 – 40 Hours."
        },
        {
            "craft": "Lac Bangles",
            "state": "Bihar",
            "labor_time": "4 – 10 Hours",
            "price_range": "₹200 – ₹500 (Set)",
            "why_price": "Muzaffarpur is the hub. Natural resin is heated on a furnace, colored with stone dyes, and hand-molded. Intricate \"Kundan\" inlay sets are pricier.",
            "description": "Specialist in Lac Bangles. Muzaffarpur is the hub. Natural resin is heated on a furnace, colored with stone dyes, and hand-molded. Intricate \"Kundan\" inlay sets are pricier. Approx labor: 4 – 10 Hours."
        },
        {
            "craft": "Manjusha Art",
            "state": "Bihar",
            "labor_time": "20 – 60 Hours",
            "price_range": "₹1,500 – ₹4,500",
            "why_price": "One of the world’s oldest scroll arts using only three colors (pink, green, yellow). Often painted on Jute/Silk boxes or handmade paper.",
            "description": "Specialist in Manjusha Art. One of the world’s oldest scroll arts using only three colors (pink, green, yellow). Often painted on Jute/Silk boxes or handmade paper. Approx labor: 20 – 60 Hours."
        },
        {
            "craft": "Mud Clay Toys",
            "state": "Bihar",
            "labor_time": "6 – 12 Hours",
            "price_range": "₹150 – ₹600",
            "why_price": "Unlike kiln-fired terracotta, these \"Mitti\" toys are often sun-dried and painted with organic colors, safe for children and eco-friendly.",
            "description": "Specialist in Mud Clay Toys. Unlike kiln-fired terracotta, these \"Mitti\" toys are often sun-dried and painted with organic colors, safe for children and eco-friendly. Approx labor: 6 – 12 Hours."
        },
        {
            "craft": "Dhokra Metal Craft",
            "state": "Chhattisgarh",
            "labor_time": "40 – 72 Hours",
            "price_range": "₹2,500 (10-12\" Figurine)",
            "why_price": "Uses the lost-wax technique. Since the clay mold must be broken to reveal the metal, every piece is a unique original that can never be replicated exactly.",
            "description": "Specialist in Dhokra Metal Craft. Uses the lost-wax technique. Since the clay mold must be broken to reveal the metal, every piece is a unique original that can never be replicated exactly. Approx labor: 40 – 72 Hours."
        },
        {
            "craft": "Kosa Silk Saree",
            "state": "Chhattisgarh",
            "labor_time": "120 – 180 Hours",
            "price_range": "₹7,500 – ₹12,000",
            "why_price": "Sourced from wild silkworms (Antheraea mylitta). The price reflects the rarity of the cocoons and the 10–15 days of painstaking hand-weaving on pit looms.",
            "description": "Specialist in Kosa Silk Saree. Sourced from wild silkworms (Antheraea mylitta). The price reflects the rarity of the cocoons and the 10–15 days of painstaking hand-weaving on pit looms. Approx labor: 120 – 180 Hours."
        },
        {
            "craft": "Wooden Tribal Masks",
            "state": "Chhattisgarh",
            "labor_time": "30 – 50 Hours",
            "price_range": "₹2,500 – ₹4,500",
            "why_price": "Carved from Teak or Shisham. Artisans use manual chisels to bring \"life\" to the wood, depicting gods and spirits with details that machine-carving cannot mimic.",
            "description": "Specialist in Wooden Tribal Masks. Carved from Teak or Shisham. Artisans use manual chisels to bring \"life\" to the wood, depicting gods and spirits with details that machine-carving cannot mimic. Approx labor: 30 – 50 Hours."
        },
        {
            "craft": "Wrought Iron Craft",
            "state": "Chhattisgarh",
            "labor_time": "12 – 20 Hours",
            "price_range": "₹800 – ₹1,800",
            "why_price": "Known as Loha Shilp. Blacksmiths from the Agaria community manually heat and beat scrap iron into slender, elegant tribal forms without using any joints or welding.",
            "description": "Specialist in Wrought Iron Craft. Known as Loha Shilp. Blacksmiths from the Agaria community manually heat and beat scrap iron into slender, elegant tribal forms without using any joints or welding. Approx labor: 12 – 20 Hours."
        },
        {
            "craft": "Bamboo Utility Items",
            "state": "Chhattisgarh",
            "labor_time": "15 – 30 Hours",
            "price_range": "₹300 – ₹900",
            "why_price": "Includes harvesting \"mature\" bamboo and hand-splitting it into thin strips. The \"precision\" comes from the tight weave used in traditional winnowing fans and baskets.",
            "description": "Specialist in Bamboo Utility Items. Includes harvesting \"mature\" bamboo and hand-splitting it into thin strips. The \"precision\" comes from the tight weave used in traditional winnowing fans and baskets. Approx labor: 15 – 30 Hours."
        },
        {
            "craft": "Terracotta Jewellery",
            "state": "Chhattisgarh",
            "labor_time": "10 – 15 Hours",
            "price_range": "₹250 – ₹700 (Set)",
            "why_price": "Each bead is hand-rolled from fine clay, etched with a needle, sun-dried, kiln-fired, and then hand-painted with earthy natural pigments.",
            "description": "Specialist in Terracotta Jewellery. Each bead is hand-rolled from fine clay, etched with a needle, sun-dried, kiln-fired, and then hand-painted with earthy natural pigments. Approx labor: 10 – 15 Hours."
        },
        {
            "craft": "Coconut Shell Crafts",
            "state": "Goa",
            "labor_time": "6 – 10 Hours",
            "price_range": "₹400 – ₹1,200",
            "why_price": "Involves removing fiber, sanding to a mirror finish, and seasoning with oils. Complex lamps with \"Jaali\" (perforated) work take more time.",
            "description": "Specialist in Coconut Shell Crafts. Involves removing fiber, sanding to a mirror finish, and seasoning with oils. Complex lamps with \"Jaali\" (perforated) work take more time. Approx labor: 6 – 10 Hours."
        },
        {
            "craft": "Kunbi Saree",
            "state": "Goa",
            "labor_time": "40 – 60 Hours",
            "price_range": "₹1,500 – ₹2,500",
            "why_price": "A traditional cotton weave with red/white checks. A skilled weaver takes about 5 days to complete one saree on a handloom.",
            "description": "Specialist in Kunbi Saree. A traditional cotton weave with red/white checks. A skilled weaver takes about 5 days to complete one saree on a handloom. Approx labor: 40 – 60 Hours."
        },
        {
            "craft": "Shell Jewellery",
            "state": "Goa",
            "labor_time": "4 – 12 Hours",
            "price_range": "₹200 – ₹800",
            "why_price": "Sourcing authentic local shells, cleaning, polishing, and delicate drilling/stringing. Price varies by the rarity of the shells used.",
            "description": "Specialist in Shell Jewellery. Sourcing authentic local shells, cleaning, polishing, and delicate drilling/stringing. Price varies by the rarity of the shells used. Approx labor: 4 – 12 Hours."
        },
        {
            "craft": "Azulejos Tile Art",
            "state": "Goa",
            "labor_time": "5 – 15 Hours",
            "price_range": "₹150 – ₹1,500",
            "why_price": "Hand-painted on ceramic and baked. Small 6x6 tiles are affordable, but large custom nameplates or Mario Miranda murals are premium.",
            "description": "Specialist in Azulejos Tile Art. Hand-painted on ceramic and baked. Small 6x6 tiles are affordable, but large custom nameplates or Mario Miranda murals are premium. Approx labor: 5 – 15 Hours."
        },
        {
            "craft": "Wooden Christian Icons",
            "state": "Goa",
            "labor_time": "20 – 50 Hours",
            "price_range": "₹1,500 – ₹5,500",
            "why_price": "Carved from seasoned wood (often Teak). Each figure is hand-chiseled and painted, reflecting the unique Goan-Baroque aesthetic.",
            "description": "Specialist in Wooden Christian Icons. Carved from seasoned wood (often Teak). Each figure is hand-chiseled and painted, reflecting the unique Goan-Baroque aesthetic. Approx labor: 20 – 50 Hours."
        },
        {
            "craft": "Handcrafted Lamps",
            "state": "Goa",
            "labor_time": "15 – 30 Hours",
            "price_range": "₹1,200 – ₹3,500",
            "why_price": "Made from brass or copper. Involves manual metal beating and intricate cut-work designs that cast geometric shadows.",
            "description": "Specialist in Handcrafted Lamps. Made from brass or copper. Involves manual metal beating and intricate cut-work designs that cast geometric shadows. Approx labor: 15 – 30 Hours."
        },
        {
            "craft": "Patan Patola Saree",
            "state": "Gujarat",
            "labor_time": "1,500 – 3,000 Hours",
            "price_range": "₹85,000 – ₹3,50,000",
            "why_price": "A \"Double Ikat\" masterpiece. Both warp and weft are dyed before weaving. Complex designs can take up to 2 years. It is an heirloom investment.",
            "description": "Specialist in Patan Patola Saree. A \"Double Ikat\" masterpiece. Both warp and weft are dyed before weaving. Complex designs can take up to 2 years. It is an heirloom investment. Approx labor: 1,500 – 3,000 Hours."
        },
        {
            "craft": "Bandhani Textile",
            "state": "Gujarat",
            "labor_time": "40 – 120 Hours",
            "price_range": "₹2,500 – ₹25,000",
            "why_price": "Price depends on the number of \"Bundi\" (knots). A high-end Jhankaar or Gharchola with 10,000+ tiny hand-tied knots justifies the premium.",
            "description": "Specialist in Bandhani Textile. Price depends on the number of \"Bundi\" (knots). A high-end Jhankaar or Gharchola with 10,000+ tiny hand-tied knots justifies the premium. Approx labor: 40 – 120 Hours."
        },
        {
            "craft": "Kutch Embroidery",
            "state": "Gujarat",
            "labor_time": "60 – 200 Hours",
            "price_range": "₹2,500 – ₹15,000",
            "why_price": "Includes various styles (Ahir, Mutwa, Rabari). Pricing is based on the density of silk thread work and real glass mirror integration.",
            "description": "Specialist in Kutch Embroidery. Includes various styles (Ahir, Mutwa, Rabari). Pricing is based on the density of silk thread work and real glass mirror integration. Approx labor: 60 – 200 Hours."
        },
        {
            "craft": "Rogan Art Painting",
            "state": "Gujarat",
            "labor_time": "20 – 60 Hours",
            "price_range": "₹1,800 – ₹7,500",
            "why_price": "Castor oil is boiled for 2 days to create a paste. Only one family in Nirona still practices the original technique. Price reflects this extreme rarity.",
            "description": "Specialist in Rogan Art Painting. Castor oil is boiled for 2 days to create a paste. Only one family in Nirona still practices the original technique. Price reflects this extreme rarity. Approx labor: 20 – 60 Hours."
        },
        {
            "craft": "Silver Tribal Jewellery",
            "state": "Gujarat",
            "labor_time": "20 – 40 Hours",
            "price_range": "₹3,500 – ₹25,000",
            "why_price": "Heavy 92.5 silver pieces (Kadas, necklaces). Priced by silver weight + \"making charges\" (approx. ₹150–₹300 per gram of labor).",
            "description": "Specialist in Silver Tribal Jewellery. Heavy 92.5 silver pieces (Kadas, necklaces). Priced by silver weight + \"making charges\" (approx. ₹150–₹300 per gram of labor). Approx labor: 20 – 40 Hours."
        },
        {
            "craft": "Lacquered Toys",
            "state": "Gujarat",
            "labor_time": "6 – 12 Hours",
            "price_range": "₹200 – ₹1,200",
            "why_price": "Made in Idar or Kutch. Wood is turned on a lathe and colored with natural shellac. They are lead-free, non-toxic, and incredibly durable.",
            "description": "Specialist in Lacquered Toys. Made in Idar or Kutch. Wood is turned on a lathe and colored with natural shellac. They are lead-free, non-toxic, and incredibly durable. Approx labor: 6 – 12 Hours."
        },
        # ... (Include all other parsed items here) ...
    ]
    
    artists = []
    
    for i, item in enumerate(real_artisans):
        # Use a local Random instance for thread-safety and determinism
        rng = random.Random(i + 5000)
        
        state = item.get('state', '')
        naming_pool = STATE_NAMING.get(state, GENERIC_NAMING)
        
        is_male = rng.random() > 0.4
        gender = 'male' if is_male else 'female'
        
        # Pick names from the specific state pool
        fname = rng.choice(naming_pool["male"]) if is_male else rng.choice(naming_pool["female"])
        lname = rng.choice(naming_pool["last"])
        
        # Use Pollinations for image if no real image
        # Use local proxy to hide API key and ensure correct endpoint
        p_text = 'Portrait of Indian artisan ' + gender + ' ' + item['state'] + ' ' + item['craft']
        image_url = f"/api/image/gen?prompt={urllib.parse.quote(p_text)}&width=400&height=400&nologo=true&seed={i}"
        
        artists.append({
            'id': i + 1,
            'name': f"{fname} {lname}",
            'gender': gender,
            'style': item['craft'],
            'state': item['state'],
            'description': item['description'],
            'image': image_url,
            'experience': rng.randint(10, 45),
            'meta': {
               'labor': item['labor_time'],
               'price': item['price_range']
            }
        })
        
    return artists

@app.route('/artisans')
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
    print(f"DEBUG: Accessing /checkout for user {current_user.id if current_user.is_authenticated else 'unauthenticated'}")
    return render_template('checkout.html')

@app.route('/design-craft')
@login_required
def design_craft():
    return render_template('design_craft.html', gemini_api_key=GEMINI_API_KEY)

@app.route('/data')
@login_required
def data():
    return render_template('data.html')

@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    """AI-powered chatbot endpoint using Groq (Llama-3)"""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({'error': 'Message is required'}), 400
        
        if not chatbot_model and not groq_client:
             return jsonify({'error': 'AI chatbot is not configured'}), 500
        
        # Build context specific to this message
        context = build_chatbot_context(user_message)
        
        # Use Groq (Llama-3) as primary, Gemini as backup (if implemented later)
        # For now, switching strictly to Groq as requested
        ai_response = call_groq_chat(user_message, context)
        
        return jsonify({
            'reply': ai_response,
            'success': True
        })
        
    except Exception as e:
        print(f"AI Chat Error: {str(e)}")
        return jsonify({
            'error': 'Failed to generate response',
            'message': 'I apologize, but I encountered an error. Please try again.'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0', threaded=True)
