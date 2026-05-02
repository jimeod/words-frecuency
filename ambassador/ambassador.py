import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask, request, jsonify
import requests as http_requests

from ambassador.circuit_breaker import CircuitBreaker


PORT = 6000
MAX_RETRIES = 3
REQUEST_TIMEOUT = 5.0 

WORKERS = [
    {"id": "worker_1", "url": "http://127.0.0.1:5001/process"},
    {"id": "worker_2", "url": "http://127.0.0.1:5002/process"},
    {"id": "worker_3", "url": "http://127.0.0.1:5003/process"},
]


circuit_breakers: dict[str, CircuitBreaker] = {
    w["id"]: CircuitBreaker(worker_id=w["id"], max_fails=3, timeout_reset=10.0)
    for w in WORKERS
}


_rr_index = 0

app = Flask(__name__)


def _next_available_worker() -> dict | None:

    global _rr_index
    total = len(WORKERS)
    for _ in range(total):
        w = WORKERS[_rr_index % total]
        _rr_index += 1
        cb = circuit_breakers[w["id"]]
        if cb.allow_request():
            return w
    return None




def _call_worker(worker: dict, text: str) -> dict:

    cb = circuit_breakers[worker["id"]]
    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        print(
            f"\n  [Ambassador] a Worker: {worker['id']} | "
            f"Intento: {attempt}/{MAX_RETRIES} |"
            f"Circuito: {cb.state_name}"
        )
        t_start = time.time()
        try:
            resp = http_requests.post(
                worker["url"],
                json={"text": text},
                timeout=REQUEST_TIMEOUT
            )
            elapsed = time.time() - t_start

            if resp.status_code == 200:
                cb.record_success()
                data = resp.json()
                print(
                    f"  [Ambassador]  Respuesta OK | "
                    f"Tiempo: {elapsed:.3f}s  "
                    f"Palabras unicas: {len(data.get('result', {}))}"
                )
                return data
            else:
                raise ValueError(f"HTTP {resp.status_code}: {resp.text}")

        except Exception as exc:
            elapsed = time.time() - t_start
            last_exc = exc
            cb.record_failure()
            print(
                f"  [Ambassador]  Error en intento {attempt}: {exc}  "
                f"Tiempo: {elapsed:.3f}s"
            )
            if attempt < MAX_RETRIES:
                time.sleep(0.3 * attempt) 

    raise RuntimeError(
        f"Worker {worker['id']} no respondio despues d e {MAX_RETRIES} intentos: {last_exc}"
    )



@app.route("/health", methods=["GET"])
def health():
    states = {w_id: cb.state_name for w_id, cb in circuit_breakers.items()}
    return jsonify({"status": "ok", "circuit_states": states}), 200


@app.route("/dispatch", methods=["POST"])
def dispatch():

    data = request.get_json(force=True)
    if not data or "text" not in data:
        return jsonify({"error": "Campo 'text' requerido"}), 400

    text = data["text"]
    fragment_preview = text[:60].replace("\n", " ") + ("..." if len(text) > 60 else "")
    print(f"\n[Ambassador] Solicitud recibida | Fragmento: '{fragment_preview}'")

   
    tried_workers = set()
    global _rr_index

    for _ in range(len(WORKERS)):
        worker = _next_available_worker()
        if worker is None:
            print("[Ambassador]  No hay workers disponibles (todos estan en OPEN).")
            return jsonify({"error": "Ningun worker disponible"}), 503

        if worker["id"] in tried_workers:
            continue
        tried_workers.add(worker["id"])

        print(f"[Ambassador]  Worker seleccionado: {worker['id']}")

        try:
            result = _call_worker(worker, text)
            return jsonify(result), 200
        except RuntimeError as e:
            print(f"[Ambassador]  Fallback a otro worker. Razon: {e}")
           

    return jsonify({"error": "Todos los workers fallaron"}), 503




if __name__ == "__main__":
    print(f"[Ambassador] Iniciando en puerto {PORT}...")
    print(f"[Ambassador] Workers configurados: {[w['id'] for w in WORKERS]}")
    print(f"[Ambassador] Timeout: {REQUEST_TIMEOUT}s | Max reintentos: {MAX_RETRIES}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
