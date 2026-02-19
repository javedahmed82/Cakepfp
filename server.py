import os
import json
import time
import uuid
import requests
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Environment variable
LEONARDO_API_KEY = os.environ.get("LEONARDO_API_KEY")

UPLOAD_FOLDER = "uploads"
GENERATED_FOLDER = "generated"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def generate():
    if not LEONARDO_API_KEY:
        return jsonify({"error": "API key not configured"}), 500

    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]

    if image.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    filename = str(uuid.uuid4()) + ".jpg"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    image.save(filepath)

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {LEONARDO_API_KEY}",
    }

    # Step 1: Initialize image upload
    init_res = requests.post(
        "https://cloud.leonardo.ai/api/rest/v1/init-image",
        json={"extension": "jpg"},
        headers=headers,
    )

    if init_res.status_code != 200:
        return jsonify({"error": "Init image failed", "details": init_res.text}), 400

    init_data = init_res.json()["uploadInitImage"]

    upload_url = init_data["url"]
    fields = init_data["fields"]

    if isinstance(fields, str):
        fields = json.loads(fields)

    image_id = init_data["id"]

    # Step 2: Upload to S3
    with open(filepath, "rb") as f:
        files = {"file": f}
        upload_res = requests.post(upload_url, data=fields, files=files)

    if upload_res.status_code not in [200, 201, 204]:
        return jsonify({"error": "Upload failed", "details": upload_res.text}), 400

    # Step 3: Generate image
    gen_res = requests.post(
        "https://cloud.leonardo.ai/api/rest/v2/generations",
        json={
            "public": False,
            "model": "gpt-image-1.5",
            "parameters": {
                "prompt": "PancakeSwap cake coin crypto avatar, glowing yellow theme, cute bunny, high detail, high quality",
                "width": 1024,
                "height": 1024,
                "guidances": {
                    "image_reference": [
                        {
                            "image": {
                                "id": image_id,
                                "type": "UPLOADED"
                            },
                            "strength": "MID"
                        }
                    ]
                }
            }
        },
        headers=headers,
    )

    if gen_res.status_code != 200:
        return jsonify({"error": "Generation failed", "details": gen_res.text}), 400

    generation_id = gen_res.json()["generate"]["generationId"]

    # Wait for processing
    time.sleep(20)

    result = requests.get(
        f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}",
        headers=headers,
    )

    if result.status_code != 200:
        return jsonify({"error": "Fetching result failed"}), 400

    result_json = result.json()

    images = result_json.get("generations_by_pk", {}).get("generated_images", [])

    if not images:
        return jsonify({"error": "No generated image found"}), 400

    image_url = images[0]["url"]

    return jsonify({"image_url": image_url})


# IMPORTANT for Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)