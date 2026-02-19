import os
import time
import json
import uuid
from pathlib import Path

import requests
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS

# ---------------------------
# Config
# ---------------------------
LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY", "").strip()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
GEN_DIR = BASE_DIR / "generated"

UPLOAD_DIR.mkdir(exist_ok=True)
GEN_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
MAX_UPLOAD_MB = 12

# Leonardo endpoints (as per your snippet)
INIT_IMAGE_URL = "https://cloud.leonardo.ai/api/rest/v1/init-image"
GENERATE_URL = "https://cloud.leonardo.ai/api/rest/v2/generations"
GET_GEN_URL = "https://cloud.leonardo.ai/api/rest/v1/generations/{gid}"

# Prompt for PancakeSwap style
DEFAULT_PROMPT = (
    "Create a cute PancakeSwap CAKE themed profile picture. "
    "Keep the person's face identity and expression similar. "
    "Add pastel dreamy sky, sparkles, floating CAKE coins with bunny icon, "
    "cute bunny characters holding pancakes with syrup. "
    "High quality, vibrant, soft glow, centered portrait, no text, no watermark."
)

# ---------------------------
# App
# ---------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/generated/<path:filename>")
def serve_generated(filename):
    return send_from_directory(GEN_DIR, filename, as_attachment=False)

@app.get("/uploads/<path:filename>")
def serve_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

def _safe_ext(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1].lower() if "." in filename else "")

def _error(msg, code=400, extra=None):
    payload = {"ok": False, "error": msg}
    if extra:
        payload.update(extra)
    return jsonify(payload), code

def _leonardo_headers():
    if not LEONARDO_API_KEY:
        return None
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {LEONARDO_API_KEY}",
    }

def _poll_generation(generation_id: str, timeout_sec=120):
    """Poll Leonardo generation endpoint until it returns image URLs or timeout."""
    headers = _leonardo_headers()
    if not headers:
        return None, "LEONARDO_API_KEY not set."

    url = GET_GEN_URL.format(gid=generation_id)
    start = time.time()
    last_text = None

    while time.time() - start < timeout_sec:
        r = requests.get(url, headers=headers, timeout=60)
        last_text = r.text
        if r.status_code != 200:
            time.sleep(2)
            continue

        data = r.json()

        # Try multiple possible response shapes safely
        # Many APIs return something like: { "generations_by_pk": {... images: [...] } }
        # Or { "generations": [...] } etc.
        images = []

        if isinstance(data, dict):
            # Common: generations_by_pk.images
            gbpk = data.get("generations_by_pk") or data.get("generation") or data.get("generate")
            if isinstance(gbpk, dict):
                imgs = gbpk.get("images") or gbpk.get("generated_images") or gbpk.get("imageData") or []
                if isinstance(imgs, list):
                    images = imgs

            # Sometimes: data["images"]
            if not images and isinstance(data.get("images"), list):
                images = data["images"]

        # Find a usable URL in returned images
        for img in images:
            if isinstance(img, dict):
                # try typical keys
                u = img.get("url") or img.get("imageUrl") or img.get("src")
                if u:
                    return u, None

        time.sleep(2)

    return None, f"Timed out waiting for image. Last response: {last_text[:300] if last_text else 'no response'}"

@app.post("/api/upload")
def api_upload():
    f = request.files.get("file")
    if not f:
        return _error("No file uploaded.")

    # size limit (best-effort)
    request.content_length = request.content_length or 0
    if request.content_length > MAX_UPLOAD_MB * 1024 * 1024:
        return _error(f"File too large. Max {MAX_UPLOAD_MB}MB.")

    ext = _safe_ext(f.filename)
    if ext not in ALLOWED_EXT:
        return _error("Invalid file type. Use PNG/JPG/JPEG/WEBP.")

    file_id = str(uuid.uuid4())
    safe_name = f"upload_{file_id}.{ext}"
    path = UPLOAD_DIR / safe_name
    f.save(path)

    return jsonify({
        "ok": True,
        "upload_id": file_id,
        "upload_url": f"/uploads/{safe_name}"
    })

@app.post("/api/generate")
def api_generate():
    if not LEONARDO_API_KEY:
        return _error("LEONARDO_API_KEY is not set on server.", 500)

    upload_id = (request.form.get("upload_id") or "").strip()
    prompt = (request.form.get("prompt") or "").strip() or DEFAULT_PROMPT

    if not upload_id:
        return _error("upload_id missing. Upload first.")

    # find upload file by upload_id
    matches = list(UPLOAD_DIR.glob(f"upload_{upload_id}.*"))
    if not matches:
        return _error("Uploaded file not found on server. Upload again.")

    local_img_path = matches[0]

    headers = _leonardo_headers()
    if not headers:
        return _error("LEONARDO_API_KEY missing.", 500)

    # Step 1: init-image to get presigned upload url + fields + image_id
    init_payload = {"extension": _safe_ext(local_img_path.name) or "jpg"}
    init_resp = requests.post(INIT_IMAGE_URL, json=init_payload, headers=headers, timeout=60)

    if init_resp.status_code != 200:
        return _error("Leonardo init-image failed.", 502, {"details": init_resp.text[:500]})

    init_json = init_resp.json()
    up = init_json.get("uploadInitImage") or init_json.get("data") or init_json
    # expected keys
    upload_url = up.get("url")
    fields_raw = up.get("fields")
    image_id = up.get("id")

    if not upload_url or not fields_raw or not image_id:
        return _error("Leonardo init-image response missing fields.", 502, {"details": json.dumps(init_json)[:800]})

    # fields must be dict for requests.post(data=...)
    if isinstance(fields_raw, str):
        try:
            fields = json.loads(fields_raw)
        except Exception:
            return _error("Leonardo fields JSON parse failed.", 502)
    elif isinstance(fields_raw, dict):
        fields = fields_raw
    else:
        return _error("Leonardo fields invalid type.", 502, {"type": str(type(fields_raw))})

    # Step 2: upload to presigned url (NO headers)
    with open(local_img_path, "rb") as fp:
        files = {"file": fp}
        # IMPORTANT: data must be dict, not string
        up_resp = requests.post(upload_url, data=fields, files=files, timeout=120)

    if up_resp.status_code not in (200, 201, 204):
        return _error("Presigned upload failed.", 502, {"details": up_resp.text[:500], "status": up_resp.status_code})

    # Step 3: request generation with image reference
    gen_payload = {
        "public": False,
        "model": "gpt-image-1.5",
        "parameters": {
            "mode": "QUALITY",
            "prompt": prompt,
            "prompt_enhance": "OFF",
            "quantity": 1,
            "width": 1024,
            "height": 1024,
            "seed": 4294967295,
            "guidances": {
                "image_reference": [
                    {
                        "image": {"id": str(image_id), "type": "UPLOADED"},
                        "strength": "MID"
                    }
                ]
            }
        }
    }

    gen_resp = requests.post(GENERATE_URL, json=gen_payload, headers=headers, timeout=120)

    if gen_resp.status_code != 200:
        return _error("Leonardo generation request failed.", 502, {"details": gen_resp.text[:700]})

    gen_json = gen_resp.json()
    generate_block = gen_json.get("generate") or gen_json.get("data") or gen_json
    generation_id = generate_block.get("generationId") or generate_block.get("id")

    if not generation_id:
        return _error("generationId missing in response.", 502, {"details": json.dumps(gen_json)[:800]})

    # Step 4: poll for image url
    img_url, err = _poll_generation(str(generation_id), timeout_sec=140)
    if err or not img_url:
        return _error("Failed to fetch generated image.", 502, {"details": err or "Unknown"})

    # Step 5: download generated image into /generated for serving + download
    out_id = str(uuid.uuid4())
    out_png = f"cakepfp_{out_id}.png"
    out_path = GEN_DIR / out_png

    img_r = requests.get(img_url, timeout=120)
    if img_r.status_code != 200:
        return _error("Could not download generated image.", 502, {"details": img_r.text[:300]})

    out_path.write_bytes(img_r.content)

    return jsonify({
        "ok": True,
        "generated_url": f"/generated/{out_png}",
        "download_png": f"/generated/{out_png}",
        "download_jpg": f"/api/download-jpg/{out_png}",
    })

@app.get("/api/download-jpg/<path:filename>")
def api_download_jpg(filename):
    # convert saved PNG to JPG on the fly
    try:
        from PIL import Image
    except Exception:
        return _error("Pillow not installed. Can't convert to JPG.", 500)

    src = GEN_DIR / filename
    if not src.exists():
        return _error("File not found.", 404)

    outname = filename.rsplit(".", 1)[0] + ".jpg"
    outpath = GEN_DIR / outname

    # Convert
    im = Image.open(src).convert("RGB")
    im.save(outpath, "JPEG", quality=95)

    return send_from_directory(GEN_DIR, outname, as_attachment=True)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)