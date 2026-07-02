import os
import re
import time

from flask import Flask, request, jsonify


WORKER_ID = os.environ.get("WORKER_ID", "worker_1")
PORT      = int(os.environ.get("PORT", 5001))

app = Flask(__name__)


_WORD_RE = re.compile(r"[^\w']+", re.UNICODE)

def count_words(text: str) -> dict[str, int]:
   
    counts: dict[str, int] = {}
    for token in _WORD_RE.split(text.lower()):
        token = token.strip("'")
        if token:
            counts[token] = counts.get(token, 0) + 1
    return counts

_WHITESPACE = b" \t\n\r"

def _adjusted_start(f, offset: int) -> int:
    if offset == 0:
        return 0
    # Retroceder hasta encontrar un byte de inicio de carácter UTF-8 válido
    f.seek(offset)
    for back in range(4):
        f.seek(offset - back)
        byte = f.read(1)
        if byte and (byte[0] & 0xC0) != 0x80:
            pos = offset - back
            break
    else:
        pos = offset
    # Desde ahí avanzar hasta el siguiente espacio
    f.seek(pos)
    while True:
        byte = f.read(1)
        if not byte or byte in _WHITESPACE:
            break
    return f.tell()


def _adjusted_end(f, offset_end: int, file_size: int) -> int:
    if offset_end >= file_size:
        return file_size
    # Retroceder hasta byte de inicio de carácter UTF-8 válido
    for back in range(4):
        if offset_end - back < 0:
            break
        f.seek(offset_end - back)
        byte = f.read(1)
        if byte and (byte[0] & 0xC0) != 0x80:
            offset_end = offset_end - back
            break
    # Retroceder hasta el último espacio
    pos = offset_end - 1
    while pos > 0:
        f.seek(pos)
        byte = f.read(1)
        if byte in _WHITESPACE:
            return pos + 1
        pos -= 1
    return 0

def read_fragment(file_path: str, offset_inicio: int, offset_fin: int) -> str:
    file_size = os.path.getsize(file_path)

    with open(file_path, "rb") as f:
        real_start = _adjusted_start(f, offset_inicio)
        real_end   = _adjusted_end(f, offset_fin, file_size)

        if real_end <= real_start:
            return ""

        f.seek(real_start)
        raw = f.read(real_end - real_start)

    return raw.decode("utf-8", errors="replace")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "worker_id": WORKER_ID}), 200


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json(force=True)

    # Validación de campos requeridos
    for field in ("file_path", "offset_inicio", "offset_fin"):
        if field not in data:
            return jsonify({"error": f"Campo requerido faltante: '{field}'"}), 400

    file_path      = data["file_path"]
    offset_inicio  = int(data["offset_inicio"])
    offset_fin     = int(data["offset_fin"])

    if not os.path.isfile(file_path):
        return jsonify({"error": f"Archivo no encontrado: {file_path}"}), 404

    print(
        f"[{WORKER_ID}] Procesando rango "
        f"[{offset_inicio:,} – {offset_fin:,}] bytes de '{file_path}'"
    )
    t0 = time.time()

    try:
        text   = read_fragment(file_path, offset_inicio, offset_fin)
        result = count_words(text)
    except Exception as exc:
        print(f"[{WORKER_ID}] Error procesando fragmento: {exc}")
        return jsonify({"error": str(exc)}), 500

    elapsed = time.time() - t0
    words_processed = len(text.split())

    print(
        f"[{WORKER_ID}] Listo en {elapsed:.3f}s | "
        f"palabras: {words_processed} | únicas: {len(result)}"
    )

    return jsonify({
        "worker_id":       WORKER_ID,
        "offset_inicio":   offset_inicio,
        "offset_fin":      offset_fin,
        "words_processed": words_processed,
        "result":          result,
    }), 200


if __name__ == "__main__":
    print(f"[{WORKER_ID}] Iniciando servidor en puerto {PORT}...")
    app.run(host="0.0.0.0", port=PORT, debug=False)