import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask, request, jsonify
import requests as http_requests

from circuit_breaker import CircuitBreaker



PORT            = 6000
MAX_RETRIES     = 3
REQUEST_TIMEOUT = 300.0     
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
        w  = WORKERS[_rr_index % total]
        _rr_index += 1
        cb = circuit_breakers[w["id"]]
        if cb.allow_request():
            return w
    return None



def _call_worker(worker: dict, payload: dict) -> dict:
    cb            = circuit_breakers[worker["id"]]
    last_exc      = None
    offset_inicio = payload.get("offset_inicio", "?")
    offset_fin    = payload.get("offset_fin",    "?")

    for attempt in range(1, MAX_RETRIES + 1):
        print(
            f"\n  [Ambassador] Worker: {worker['id']} | "
            f"Intento: {attempt}/{MAX_RETRIES} | "
            f"Circuito: {cb.state_name} | "
            f"Rango: [{offset_inicio:,} – {offset_fin:,}]"
        )
        t_start = time.time()
        try:
            resp    = http_requests.post(
                worker["url"],
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            elapsed = time.time() - t_start

            if resp.status_code == 200:
                cb.record_success()
                data = resp.json()
                print(
                    f"  [Ambassador] ✔ OK | Worker: {worker['id']} | "
                    f"Tiempo: {elapsed:.3f}s | "
                    f"Palabras únicas: {len(data.get('result', {}))}"
                )
                return data
            else:
                raise ValueError(f"HTTP {resp.status_code}: {resp.text[:120]}")

        except Exception as exc:
            elapsed  = time.time() - t_start
            last_exc = exc
            cb.record_failure()
            print(
                f"  [Ambassador] ✘ Error en intento {attempt}: {exc} | "
                f"Tiempo: {elapsed:.3f}s | "
                f"Estado circuito: {cb.state_name}"
            )
            if attempt < MAX_RETRIES:
                time.sleep(0.3 * attempt)

    raise RuntimeError(
        f"Worker {worker['id']} no respondió después de {MAX_RETRIES} intentos: {last_exc}"
    )



@app.route("/health", methods=["GET"])
def health():
    states = {w_id: cb.state_name for w_id, cb in circuit_breakers.items()}
    return jsonify({"status": "ok", "circuit_states": states}), 200


@app.route("/dispatch", methods=["POST"])
def dispatch():
    data = request.get_json(force=True)

    for field in ("file_path", "offset_inicio", "offset_fin"):
        if field not in data:
            return jsonify({"error": f"Campo requerido: '{field}'"}), 400

    payload = {
        "file_path":     data["file_path"],
        "offset_inicio": int(data["offset_inicio"]),
        "offset_fin":    int(data["offset_fin"]),
    }

    print(
        f"\n[Ambassador] Solicitud recibida | "
        f"Rango: [{payload['offset_inicio']:,} – {payload['offset_fin']:,}] | "
        f"Archivo: {payload['file_path']}"
    )

    tried_workers: set[str] = set()

    for _ in range(len(WORKERS)):
        worker = _next_available_worker()

        if worker is None:
            print("[Ambassador] ✘ No hay workers disponibles (todos en OPEN).")
            return jsonify({"error": "Ningún worker disponible"}), 503

        if worker["id"] in tried_workers:
            continue
        tried_workers.add(worker["id"])

        print(f"[Ambassador] → Worker seleccionado: {worker['id']}")

        try:
            result = _call_worker(worker, payload)
            return jsonify(result), 200
        except RuntimeError as exc:
            print(f"[Ambassador] Fallback a otro worker. Razón: {exc}")

    return jsonify({"error": "Todos los workers fallaron"}), 503


if __name__ == "__main__":
    print(f"[Ambassador] Iniciando en puerto {PORT}...")
    print(f"[Ambassador] Workers: {[w['id'] for w in WORKERS]}")
    print(f"[Ambassador] Timeout: {REQUEST_TIMEOUT}s | Max reintentos: {MAX_RETRIES}")
    app.run(host="0.0.0.0", port=PORT, debug=False)