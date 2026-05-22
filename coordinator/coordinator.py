import sys
import os
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests as http_requests
from utils.text_splitter import split_text
from utils.word_counter import count_words, merge_counts

AMBASSADOR_URL = "http://127.0.0.1:6000/dispatch"
NUM_WORKERS = 3

# Ruta por defecto del archivo JSON de entrada (misma carpeta que este script)
DEFAULT_INPUT_JSON = os.path.join(os.path.dirname(__file__), "input.json")


def load_input_json(path: str) -> tuple[str, str]:
    """Lee el archivo JSON de entrada y retorna (title, text)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    title = data.get("title", "Sin título")
    text = data.get("text", "").strip()
    if not text:
        raise ValueError(f"El archivo '{path}' no contiene el campo 'text' o está vacío.")
    return title, text


def sequential_count(text: str) -> tuple[dict, float]:
    fragments = split_text(text, NUM_WORKERS)
    t0 = time.time()
    combined = {}
    for i, frag in enumerate(fragments, 1):
        print(f"[Coordinador] GT procesando fragmento #{i} secuencialmente...")
        time.sleep(1)
        partial = count_words(frag)
        for word, count in partial.items():
            combined[word] = combined.get(word, 0) + count
    elapsed = time.time() - t0
    return combined, elapsed


def send_to_ambassador(fragment: str, fragment_id: int) -> dict | None:
    print(f"\n[Coordinador]  Enviando fragmento #{fragment_id} "
          f"({len(fragment.split())} palabras) al Ambassador...")
    try:
        resp = http_requests.post(
            AMBASSADOR_URL,
            json={"text": fragment},
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"[Coordinador]  Ambassador retornó HTTP {resp.status_code}")
            return None
    except Exception as e:
        print(f"[Coordinador]  Error contactando Ambassador: {e}")
        return None


def distributed_count(text: str) -> tuple[dict, float, list[dict]]:
    fragments = split_text(text, NUM_WORKERS)
    print(f"\n[Coordinador]  Texto dividido en {len(fragments)} fragmentos:")
    for i, frag in enumerate(fragments, 1):
        words = frag.split()
        print(f"  Fragmento #{i}: {len(words)} palabras — '{frag[:50]}...'")

    t0 = time.time()
    partial_results = []
    worker_responses = []

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = {
            executor.submit(send_to_ambassador, frag, i): i
            for i, frag in enumerate(fragments, 1)
        }
        for future in as_completed(futures):
            frag_id = futures[future]
            try:
                response = future.result()
                if response and "result" in response:
                    partial_results.append(response["result"])
                    worker_responses.append(response)
                    print(f"[Coordinador]  Fragmento #{frag_id} procesado "
                          f"por {response.get('worker_id', 'desconocido')}")
                else:
                    print(f"[Coordinador]  Fragmento #{frag_id} sin resultado válido")
            except Exception as e:
                print(f"[Coordinador]  Error en fragmento #{frag_id}: {e}")

    elapsed = time.time() - t0
    combined = merge_counts(*partial_results)
    return combined, elapsed, worker_responses


def sep(char="═", width=65):
    print(char * width)


def print_results(dist_result: dict, dist_time: float,
                  seq_result: dict, seq_time: float,
                  worker_responses: list[dict]):

    sep()
    print("  RESULTADO DEL SISTEMA DISTRIBUIDO")
    sep()
    sorted_words = sorted(dist_result.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  Top 20 palabras más frecuentes (de {len(dist_result)} únicas):\n")
    for rank, (word, count) in enumerate(sorted_words[:20], 1):
        bar = "█" * min(count, 30)
        print(f"  {rank:2}. {word:<20} {count:4}  {bar}")

    print()
    sep()
    print("  RESUMEN POR WORKER")
    sep()
    for resp in worker_responses:
        wid = resp.get("worker_id", "?")
        words_proc = resp.get("words_processed", "?")
        unique = len(resp.get("result", {}))
        print(f"  {wid}: {words_proc} palabras procesadas | {unique} palabras únicas")

    print()
    sep()
    print("  COMPARACIÓN: GROUND TRUTH vs DISTRIBUIDO")
    sep()

    speedup = seq_time / dist_time if dist_time > 0 else float("inf")
    improvement = ((seq_time - dist_time) / seq_time * 100) if seq_time > 0 else 0

    print(f"\n  GT= {seq_time:.4f} s   (conteo secuencial local)")
    print(f"  D=  {dist_time:.4f} s   (conteo distribuido via Ambassador)")
    print(f"\n  Speedup  : {speedup:.2f}x")
    print(f"  Mejora   : {improvement:.1f}%")

    if set(dist_result.keys()) == set(seq_result.keys()):
        match = all(dist_result[k] == seq_result[k] for k in dist_result)
        status = "✔  CONSISTENTE" if match else "✘  DIFERENCIAS DETECTADAS"
    else:
        status = "✘  VOCABULARIOS DISTINTOS (revisión necesaria)"

    print(f"\n  Consistencia GT vs D : {status}")
    print()
    sep()


def main():
    # Acepta ruta al .json como argumento opcional; si no, usa input.json del mismo directorio
    json_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT_JSON

    sep("─")
    print(f"[Coordinador] Leyendo archivo de entrada: {json_path}")
    try:
        title, text_input = load_input_json(json_path)
    except FileNotFoundError:
        print(f"[Coordinador] ERROR: No se encontró el archivo '{json_path}'.")
        sys.exit(1)
    except ValueError as e:
        print(f"[Coordinador] ERROR: {e}")
        sys.exit(1)

    print(f"[Coordinador] Título  : {title}")
    print(f"[Coordinador] Palabras: {len(text_input.split())}")

    sep("─")
    print("[Coordinador] INICIANDO CONTEO SECUENCIAL — Ground Truth...")
    sep("─")
    seq_result, seq_time = sequential_count(text_input)
    print(f"[Coordinador] GT completado  →  GT= {seq_time:.4f} s  |  "
          f"Palabras únicas: {len(seq_result)}")

    print()
    sep("─")
    print("[Coordinador] INICIANDO CONTEO DISTRIBUIDO...")
    sep("─")
    dist_result, dist_time, worker_responses = distributed_count(text_input)
    print(f"\n[Coordinador] Distribuido completado  →  D= {dist_time:.4f} s  |  "
          f"Palabras únicas: {len(dist_result)}")

    print()
    print_results(dist_result, dist_time, seq_result, seq_time, worker_responses)

    # Guardar JSON con título incluido
    output_path = os.path.join(os.path.dirname(__file__), "..", "resultado_final.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "title":              title,
            "distributed_result": dist_result,
            "sequential_result":  seq_result,
            "GT_seconds":         round(seq_time, 4),
            "D_seconds":          round(dist_time, 4),
            "speedup":            round(seq_time / dist_time, 2) if dist_time > 0 else None
        }, f, ensure_ascii=False, indent=2)
    print(f"[Coordinador] Resultado guardado en resultado_final.json")


if __name__ == "__main__":
    main()