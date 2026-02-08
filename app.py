import os
import re
import time
import tempfile
import requests
import json
import base64
import urllib.parse
import random
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from sqlalchemy import text

# Load environment variables
load_dotenv()
# Diffsynth model cache: default to project folder (E:\craft-site\.diffsynth_cache) so downloads stay with the app
if not os.getenv("DIFFSYNTH_CACHE"):
    os.environ["DIFFSYNTH_CACHE"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".diffsynth_cache")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from models import db, User, Order, OrderItem

# Import Data
from data.products_heritage import HERITAGE_DATA

db.init_app(app)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")

login_manager = LoginManager(app)
login_manager.login_view = 'entry'  # /entry = splash (video + auth)
login_manager.login_message = 'Please sign in to continue.'

# Configure Upload Folder
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads', 'profiles')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
    db.create_all()
    _migrate_add_missing_columns()

# --- Core Routes ---


# --- Product Routes ---



@app.route('/map')
@login_required
def map_page():
    return render_template('map.html')


@app.route('/about')
@login_required
def about():
    return render_template('about.html')

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
USE_DIFFSYNTH_ENGINE = os.getenv("USE_DIFFSYNTH_ENGINE", "").strip().lower() in ("1", "true", "yes")
# Design image provider: "replicate" | "together" (default replicate)
DESIGN_IMAGE_PROVIDER = (os.getenv("DESIGN_IMAGE_PROVIDER", "replicate").strip().lower() or "replicate")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "").strip()
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "").strip()

_diffsynth_pipe = None


def generate_image_diffsynth(image_prompt):
    """Generate image locally with Diffsynth-Engine (Qwen-Image-2512). Returns (data_url, error_message). Optional: set USE_DIFFSYNTH_ENGINE=1 in .env."""
    global _diffsynth_pipe
    if not USE_DIFFSYNTH_ENGINE:
        return None, None
    try:
        import math
        import sys
        import types
        # PyTorch 2.10+ removed torch.distributed.tensor.parallel._utils; shim for diffsynth_engine
        import torch.distributed.tensor.parallel  # noqa: F401
        if not hasattr(torch.distributed.tensor.parallel, "_utils"):
            _utils_mod = types.ModuleType("torch.distributed.tensor.parallel._utils")
            def _validate_tp_mesh_dim(device_mesh):
                pass
            _utils_mod._validate_tp_mesh_dim = _validate_tp_mesh_dim
            torch.distributed.tensor.parallel._utils = _utils_mod
            sys.modules["torch.distributed.tensor.parallel._utils"] = _utils_mod
        from diffsynth_engine import fetch_model, QwenImagePipeline, QwenImagePipelineConfig
        import io
    except ImportError as e:
        msg = str(e)
        if "diffsynth" in msg.lower() or "No module named 'diffsynth" in msg:
            return None, "Diffsynth not installed. Run: pip install diffsynth-engine"
        return None, f"Diffsynth dependency error: {msg}. Try: pip install -U torch"
    try:
        if _diffsynth_pipe is None:
            print("Loading Diffsynth-Engine (Qwen-Image-2512)...")
            config = QwenImagePipelineConfig.basic_config(
                model_path=fetch_model("Qwen/Qwen-Image-2512", path="transformer/*.safetensors"),
                encoder_path=fetch_model("Qwen/Qwen-Image-2512", path="text_encoder/*.safetensors"),
                vae_path=fetch_model("Qwen/Qwen-Image-2512", path="vae/*.safetensors"),
                offload_mode="cpu_offload",
            )
            _diffsynth_pipe = QwenImagePipeline.from_pretrained(config)
            try:
                _diffsynth_pipe.load_lora(
                    path=fetch_model("Wuli-art/Qwen-Image-2512-Turbo-LoRA-2-Steps", path="Wuli-Qwen-Image-2512-Turbo-LoRA-2steps-V1.0-bf16.safetensors"),
                    scale=1.0,
                    fused=True,
                )
            except Exception as e:
                print(f"Diffsynth LoRA load skipped: {e}")
            scheduler_config = {
                "exponential_shift_mu": math.log(2.5),
                "use_dynamic_shifting": True,
                "shift_terminal": 0.7155,
            }
            _diffsynth_pipe.apply_scheduler_config(scheduler_config)
        import random
        output = _diffsynth_pipe(
            prompt=image_prompt[:1000],
            cfg_scale=1,
            num_inference_steps=2,
            seed=random.randint(0, 2**31 - 1),
            width=1024,
            height=1024,
        )
        buf = io.BytesIO()
        output.save(buf, format="PNG")
        buf.seek(0)
        raw = buf.read()
        if len(raw) < 100:
            return None, "Diffsynth image too small"
        b64 = base64.b64encode(raw).decode("utf-8")
        return f"data:image/png;base64,{b64}", None
    except Exception as e:
        print(f"Diffsynth-Engine failed: {e}")
        import traceback
        traceback.print_exc()
        return None, str(e)


def generate_image_hf(image_prompt):
    """Generate image via Hugging Face. Uses free Inference API first (no fal-ai credits needed). Returns (data_url, error_message)."""
    if not HF_TOKEN or not HF_TOKEN.strip():
        return None, "HF_TOKEN is not set in .env"
    token = HF_TOKEN.strip()
    err_msg = "Hugging Face inference is busy (503). Wait a minute and try again, or set USE_DIFFSYNTH_ENGINE=1 in .env for local generation."
    # 1) Free HF Inference API first (no 402 / pre-paid credits); retry once on 503
    for model_id in ["stabilityai/stable-diffusion-xl-base-1.0", "runwayml/stable-diffusion-v1-5", "CompVis/stable-diffusion-v1-4"]:
        for attempt in range(2):
            try:
                url = f"https://router.huggingface.co/models/{model_id}"
                r = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    json={"inputs": image_prompt[:1000]},
                    timeout=90,
                )
                if r.status_code == 200 and len(r.content) >= 100:
                    b64 = base64.b64encode(r.content).decode("utf-8")
                    return f"data:image/png;base64,{b64}", None
                if r.status_code == 401 or r.status_code == 403:
                    return None, "HF token invalid or no permission. Use a token with 'Inference' at huggingface.co/settings/tokens."
                if r.status_code == 503:
                    if attempt == 0:
                        time.sleep(5)
                        continue
                    break
            except Exception as e:
                print(f"HF Inference API {model_id} failed: {e}")
                err_msg = str(e)
                break
    # 2) Optional: fal-ai (requires pre-paid credits; skip if you hit 402)
    try:
        from huggingface_hub import InferenceClient
        import io
        client = InferenceClient(provider="fal-ai", api_key=token)
        image = client.text_to_image(image_prompt, model=HF_IMAGE_MODEL)
        if image is not None and hasattr(image, "save"):
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            buf.seek(0)
            raw = buf.read()
            if len(raw) >= 100:
                b64 = base64.b64encode(raw).decode("utf-8")
                return f"data:image/png;base64,{b64}", None
    except Exception as e:
        if "402" not in str(e):
            err_msg = str(e)
        print(f"HF image (fal-ai) failed: {e}")
    return None, err_msg or "Image generation failed. Free HF models may be loading (503). Try again in a minute."


# FLUX design generation: Replicate, Together AI, or Hugging Face
FLUX_MODEL = "black-forest-labs/FLUX.1-dev"


def generate_image_replicate(prompt_text):
    """Generate image via Replicate FLUX 1.1 Pro. Returns (data_url, error_message)."""
    if not REPLICATE_API_TOKEN:
        return None, "REPLICATE_API_TOKEN is not set in .env. Get a token at replicate.com/account/api-tokens"
    try:
        import replicate
        output = replicate.run(
            "black-forest-labs/flux-1.1-pro",
            input={
                "prompt": prompt_text[:1000],
                "prompt_upsampling": True,
            },
        )
        if output is None:
            return None, "No image returned from Replicate."
        # FileOutput: .url and .read()
        raw = output.read() if hasattr(output, "read") else None
        if not raw or len(raw) < 100:
            url = getattr(output, "url", None) if output else None
            if url and isinstance(url, str):
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                raw = r.content
            if not raw or len(raw) < 100:
                return None, "Image too small or invalid Replicate output."
        b64 = base64.b64encode(raw).decode("utf-8")
        return f"data:image/png;base64,{b64}", None
    except Exception as e:
        err = str(e)
        print(f"Replicate FLUX error: {err}")
        if "401" in err or "403" in err or "Unauthorized" in err:
            return None, "Replicate token invalid. Check REPLICATE_API_TOKEN."
        return None, err[:500]


def generate_image_together(prompt_text):
    """Generate image via Together AI FLUX. Returns (data_url, error_message)."""
    if not TOGETHER_API_KEY:
        return None, "TOGETHER_API_KEY is not set in .env. Get a key at together.ai"
    url = "https://api.together.xyz/v1/images/generations"
    headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "black-forest-labs/FLUX.1-schnell",
        "prompt": prompt_text[:1000],
        "steps": 4,
        "n": 1,
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=120)
        r.raise_for_status()
        data = r.json()
        items = (data or {}).get("data") or []
        if not items:
            return None, "No image in Together response."
        item = items[0]
        b64 = item.get("b64_json")
        if b64:
            return f"data:image/png;base64,{b64}", None
        img_url = item.get("url")
        if img_url:
            r2 = requests.get(img_url, timeout=60)
            r2.raise_for_status()
            raw = r2.content
            if len(raw) < 100:
                return None, "Image too small."
            b64 = base64.b64encode(raw).decode("utf-8")
            return f"data:image/png;base64,{b64}", None
        return None, "Together response had no b64_json or url."
    except requests.RequestException as e:
        err = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                err = e.response.text or err
            except Exception:
                pass
        print(f"Together FLUX error: {err}")
        if "401" in err or "403" in err:
            return None, "Together API key invalid. Check TOGETHER_API_KEY."
        return None, err[:500]
    except Exception as e:
        err = str(e)
        print(f"Together FLUX error: {err}")
        return None, err[:500]


def generate_image_flux(prompt_text):
    """Generate image via Hugging Face FLUX.1-dev using InferenceClient. Returns (data_url, error_message)."""
    if not HF_TOKEN or not HF_TOKEN.strip():
        return None, "HF_TOKEN is not set in .env. Get a token at hf.co/settings/tokens"
    try:
        import io
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=HF_TOKEN.strip())
        image = client.text_to_image(
            prompt_text[:1000],
            model=FLUX_MODEL,
            guidance_scale=3.5,
            num_inference_steps=50,
        )
        if image is None:
            return None, "No image returned from FLUX."
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        raw = buf.getvalue()
        if len(raw) < 100:
            return None, "Image too small."
        b64 = base64.b64encode(raw).decode("utf-8")
        return f"data:image/png;base64,{b64}", None
    except Exception as e:
        err = str(e)
        print(f"FLUX InferenceClient error: {err}")
        if "401" in err or "403" in err or "Unauthorized" in err:
            return None, "HF token invalid. Use a token with Inference at hf.co/settings/tokens"
        if "503" in err or "loading" in err.lower():
            return None, "FLUX model is loading (503). Try again in a minute."
        return None, err[:500]


def generate_image_design(prompt_text):
    """Generate design image using DESIGN_IMAGE_PROVIDER (replicate | together). Falls back to HF if configured."""
    if DESIGN_IMAGE_PROVIDER == "replicate":
        url, err = generate_image_replicate(prompt_text)
        if url is not None:
            return url, None
        if err and "not set" in err.lower():
            if TOGETHER_API_KEY:
                return generate_image_together(prompt_text)
            if HF_TOKEN and HF_TOKEN.strip():
                return generate_image_flux(prompt_text)
        return None, err
    if DESIGN_IMAGE_PROVIDER == "together":
        url, err = generate_image_together(prompt_text)
        if url is not None:
            return url, None
        if err and "not set" in err.lower():
            if REPLICATE_API_TOKEN:
                return generate_image_replicate(prompt_text)
            if HF_TOKEN and HF_TOKEN.strip():
                return generate_image_flux(prompt_text)
        return None, err
    # default or unknown: try HF
    return generate_image_flux(prompt_text)


@app.route('/api/generate-design-flux', methods=['POST'])
def generate_design_flux():
    """Generate design image with FLUX (Replicate, Together AI, or HF). Returns image_url or error."""
    data = request.json or {}
    description = data.get('description', '').strip()
    style = data.get('style', 'Traditional')
    material = data.get('material', 'Metal/Brass')
    if not description:
        return jsonify({"error": "Please describe your design."}), 400
    prompt_text = f"{style} {material} Indian handicraft, {description}"
    title = f"{style} {material} Artisan Concept"
    desc = f"A {style} Indian handicraft in {material}. {description}"
    image_url, err_msg = generate_image_design(prompt_text)
    if image_url is None:
        print(f"Design FLUX failed: {err_msg}")
        return jsonify({"error": err_msg or "Image generation failed", "title": title, "description": desc}), 502
    return jsonify({"title": title, "description": desc, "image_url": image_url})


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
    for model in ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-pro"]:
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
            if r.status_code == 401 or r.status_code == 403:
                return None, "Gemini API key invalid or expired. Get a new key at https://aistudio.google.com/apikey"
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
        if error_hint and ("invalid" in error_hint.lower() or "expired" in error_hint.lower() or "401" in error_hint or "403" in error_hint):
            result["description"] = (result.get("description") or "") + " (Gemini key invalid or expired. Get a new key at https://aistudio.google.com/apikey and add to .env as GEMINI_API_KEY for better analysis.)"
        return jsonify(result)

    desc = "We couldn't run a full analysis on this image."
    if error_hint:
        desc += " " + error_hint
    else:
        desc += " Please try again with a clear photo."
    return jsonify({"error": desc}), 502


# --- AI Design Generation (Text-to-Image) ---
@app.route('/api/generate-design', methods=['POST'])
def generate_design():
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
            r = requests.post(model_url, json=payload, timeout=8)
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

    # 2. Generate Image URL using Pollinations.ai (Free, High Quality)
    # Adding 'nologo=true' and 'enhance=true'
    # We use the refined prompt from Gemini for best results
    base_url = "https://pollinations.ai/p/"
    
    # Encode the prompt
    encoded_prompt = urllib.parse.quote(refined_prompt)
    seed = random.randint(1, 99999)
    image_url = f"{base_url}{encoded_prompt}?width=1024&height=1024&nologo=true&seed={seed}&model=flux"

    return jsonify({
        "image_url": image_url,
        "title": title,
        "description": desc,
        "prompt_used": refined_prompt
    })



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
def build_chatbot_context():
    """Build context for the Craft Assistant from site data."""
    from data.products_heritage import HERITAGE_DATA

    # Full product list with details for semantic matching
    all_items = []
    for state, data in HERITAGE_DATA.items():
        for item in data["items"]:
            # Correcting index lookup for price range based on item name length
            idx = 0 if len(item["name"]) % 2 == 0 else 1
            price = item["price_range"][idx]
            rating = 4.0 + (len(item["name"]) % 10) / 10
            all_items.append({
                "name": item["name"], "state": state, "category": item["category"],
                "price": price, "rating": rating, "fun_fact": item.get("fun_fact", "")
            })
    all_items.sort(key=lambda x: x["rating"], reverse=True)
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
    lines = []
    for o in orders:
        order_label = o.order_number or f"#{o.id}"
        items_str = ", ".join([f"{i.product_name} x{i.quantity}" for i in o.items])
        lines.append(f"- Order {order_label}: ₹{o.total_amount:.0f}, Status: {o.status}, Items: {items_str}, Date: {o.created_at.strftime('%Y-%m-%d')}")
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
        orders_ctx = get_user_orders_context()
        if "NOT logged in" in orders_ctx:
            return "To track your order, please sign in first. Go to the profile icon and log in. Then I can show your order history."
        if "no orders yet" in orders_ctx:
            return "You don't have any orders yet. Start shopping on our Products page—we'd love to send you something beautiful!"
        # Has orders: show them
        return "Here are your recent orders:\n\n" + orders_ctx.replace("User's recent orders:\n", "") + "\n\nYou can view full details anytime from the profile menu → My Orders."
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
    system_instruction = """You are the Craft Assistant for Desh Ke Haath. NEVER give generic replies when the user asks about specific products or their orders. When the user asks to "track my order" or "track order", you MUST list their orders from "User's recent orders" above (order ID, amount, status, items, date). If they have no orders or are not logged in, say so. For products, cite actual names and details from the data below."""
    user_content = context + "\n\n" + orders_ctx + "\n\nUser asks: " + user_message + "\n\nReply using the data above. If they asked to track their order and orders are listed above, list each order clearly with order ID, total, status, items, and date. Otherwise list products when asked. Keep it concise but informative."

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


def _refine_design_prompt_gemini(raw_prompt):
    """Use Gemini to refine a design description into a strong image-generation prompt. Returns (refined_text, error)."""
    if not GEMINI_API_KEY or not GEMINI_API_KEY.strip():
        return None, "GEMINI_API_KEY is not set in .env."
    raw = (raw_prompt or "").strip()
    if not raw:
        return None, "No prompt to refine."
    instruction = """You are a prompt engineer for text-to-image (FLUX). The user will give a short or rough description of an Indian handicraft/artifact they want to visualize.

Your task: rewrite it as a single, clear image-generation prompt. Rules:
- One paragraph only, no bullet points, no markdown, no code.
- Include: subject, style (e.g. Madhubani, traditional, studio photo), materials if mentioned, lighting/quality (e.g. high resolution, sharp focus, clean background) if it helps.
- Keep it under 400 characters. Output ONLY the refined prompt, nothing else."""

    for model in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-pro"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY.strip()}"
        payload = {
            "contents": [{"parts": [{"text": instruction + "\n\nUser's description:\n" + raw[:800]}]}],
            "generationConfig": {"maxOutputTokens": 256, "temperature": 0.2}
        }
        for attempt in range(2):  # normal try + one retry on 429
            try:
                r = requests.post(url, json=payload, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    text = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if text and text.strip():
                        return text.strip()[:500], None
                if r.status_code == 429:
                    if attempt == 0:
                        time.sleep(4)  # wait then retry once
                        continue
                    return None, "Gemini is busy (rate limit). Wait 30–60 seconds and click ✨ again, or use your text as-is and hit Generate."
            except Exception:
                break
    return None, "Could not refine prompt. Check GEMINI_API_KEY in .env."


@app.route('/api/refine-design-prompt', methods=['POST'])
def refine_design_prompt():
    """Refine the user's design description using Gemini. Body: { \"prompt\": \"...\" }. Returns { \"prompt\": \"refined...\" } or error."""
    data = request.json or {}
    raw = (data.get("prompt") or "").strip()
    if not raw:
        return jsonify({"error": "No prompt provided."}), 400
    refined, err = _refine_design_prompt_gemini(raw)
    if err:
        return jsonify({"error": err}), 502
    return jsonify({"prompt": refined})


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
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('entry'))
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
    search_query = request.args.get('search', '').lower().strip()
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
    resp = make_response(render_template('voice.html'))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

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
    print(f"DEBUG: Accessing /checkout for user {current_user.id if current_user.is_authenticated else 'unauthenticated'}")
    return render_template('checkout.html')

@app.route('/design-craft')
@login_required
def design_craft():
    return render_template('design_craft.html')

@app.route('/data')
@login_required
def data():
    return render_template('data.html')

if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')
