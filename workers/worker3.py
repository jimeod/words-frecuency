import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask, request, jsonify
from utils.word_counter import count_words

app = Flask(__name__)
WORKER_ID = "worker_3"
PORT = 5003


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "worker_id": WORKER_ID}), 200


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json(force=True)
    if not data or "text" not in data:
        return jsonify({"error": "Campo 'text' requerido"}), 400

    text = data["text"]
    print(f"[{WORKER_ID}] Procesando fragmento de {len(text.split())} palabras...")

    time.sleep(0.05)

    result = count_words(text)

    print(f"[{WORKER_ID}] Palabras únicas encontradas: {len(result)}")

    return jsonify({
        "worker_id": WORKER_ID,
        "result": result,
        "words_processed": len(text.split())
    }), 200


if __name__ == "__main__":
    print(f"[{WORKER_ID}] Iniciando en puerto {PORT}...")
    app.run(host="0.0.0.0", port=PORT, debug=False)
