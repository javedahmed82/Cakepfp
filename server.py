import os
import json
import time
import uuid
import requests
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

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
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]
    filename = str(uuid.uuid4()) + ".jpg"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    image.save(filepath)

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {LEONARDO_API_KEY}",
    }

    # Step 1: Init image upload
    init_res = requests.post(
        "https://cloud.leonardo.ai/api/rest/v1/init-image",
        json={"extension": "jpg"},
        headers=headers,
    )

    if init_res.status_code != 200:
        return jsonify({"error": "Init image failed"}), 400

    init_data = init_res.json()["uploadInitImage"]

    upload_url = init_data["url"]
    fields = init_data["fields"]

    if isinstance(fields, str):
        fields = json.loads(fields)

    image_id = init_data["id"]

    # Step 2: Upload to S3
    with open(filepath, "rb") as f:
        files = {"file": f}
        up_res = requests.post(upload_url, data=fields, files=files)

    if up_res.status_code not in [200, 201, 204]:
        return jsonify({"error": "Upload failed"}), 400

    # Step 3: Generate
    gen_res = requests.post(
        "https://cloud.leonardo.ai/api/rest/v2/generations",
        json={
            "public": False,
            "model": "gpt-image-1.5",
            "parameters": {
                "prompt": "PancakeSwap cake coin theme crypto avatar, glowing yellow, detailed, high quality",
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
        return jsonify({"error": "Generation failed"}), 400

    generation_id = gen_res.json()["generate"]["generationId"]

    time.sleep(20)

    result = requests.get(
        f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}",
        headers=headers,
    )

    images = result.json()["generations_by_pk"]["generated_images"]

    image_url = images[0]["url"]

    return jsonify({"image_url": image_url})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
