import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future

import requests as http_requests

sys.path.insert(0, os.path.dirname(__file__))
from ground_truth import sequential_count, compare, print_comparison


AMBASSADOR_URL  = "http://127.0.0.1:6000/dispatch"
DEFAULT_WORKERS = 3

def sep(char: str = "═", width: int = 65):
    print(char * width)


def merge_counts(*dicts: dict[str, int]) -> dict[str, int]:
    combined: dict[str, int] = {}
    for d in dicts:
        for word, cnt in d.items():
            combined[word] = combined.get(word, 0) + cnt
    return combined


def generate_offsets(file_size: int, num_workers: int) -> list[tuple[int, int]]:
    chunk   = file_size // num_workers
    offsets = []
    for i in range(num_workers):
        start = i * chunk
        end   = file_size if i == num_workers - 1 else (i + 1) * chunk
        offsets.append((start, end))
    return offsets


def send_fragment(file_path: str, offset_inicio: int, offset_fin: int, fragment_id: int) -> dict | None:

    payload = {
        "file_path":     file_path,
        "offset_inicio": offset_inicio,
        "offset_fin":    offset_fin,
    }
    print(
        f"\n[Coordinador] Enviando fragmento #{fragment_id} "
        f"[{offset_inicio:,} – {offset_fin:,}] al Ambassador..."
    )
    try:
        resp = http_requests.post(AMBASSADOR_URL, json=payload, timeout=120)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"[Coordinador] Ambassador retornó HTTP {resp.status_code} en fragmento #{fragment_id}")
            return None
    except Exception as exc:
        print(f"[Coordinador] Error contactando Ambassador (fragmento #{fragment_id}): {exc}")
        return None

def distributed_count(
    file_path: str,
    num_workers: int = DEFAULT_WORKERS,
) -> tuple[dict[str, int], float, list[dict]]:
    file_size = os.path.getsize(file_path)
    offsets   = generate_offsets(file_size, num_workers)

    print(f"\n[Coordinador] Archivo: {file_path}")
    print(f"[Coordinador] Tamaño : {file_size / (1024**3):.3f} GB ({file_size:,} bytes)")
    print(f"[Coordinador] Workers: {num_workers} | Fragmentos: {len(offsets)}")
    for i, (s, e) in enumerate(offsets, 1):
        print(f"  Fragmento #{i}: [{s:,} – {e:,}]  ({(e-s)/(1024**2):.1f} MB)")

    
    pending: list[tuple[int, int, int]] = [
        (s, e, i) for i, (s, e) in enumerate(offsets, 1)
    ]
    partial_results: list[dict] = []
    worker_responses: list[dict] = []
    max_redistrib_rounds = 3   

    t0 = time.time()

    for round_num in range(1, max_redistrib_rounds + 1):
        if not pending:
            break

        failed_this_round: list[tuple[int, int, int]] = []

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures: dict[Future, tuple[int, int, int]] = {
                executor.submit(send_fragment, file_path, s, e, fid): (s, e, fid)
                for s, e, fid in pending
            }

            for future in as_completed(futures):
                s, e, fid = futures[future]
                try:
                    response = future.result()
                    if response and "result" in response:
                        partial_results.append(response["result"])
                        worker_responses.append(response)
                        print(
                            f"[Coordinador] ✔ Fragmento #{fid} procesado "
                            f"por {response.get('worker_id', '?')}"
                        )
                    else:
                        print(f"[Coordinador] ✘ Fragmento #{fid} sin resultado válido. Reencolar.")
                        failed_this_round.append((s, e, fid))
                except Exception as exc:
                    print(f"[Coordinador] ✘ Error en fragmento #{fid}: {exc}. Reencolar.")
                    failed_this_round.append((s, e, fid))

        if failed_this_round:
            print(
                f"[Coordinador] Ronda {round_num}: {len(failed_this_round)} "
                f"fragmento(s) fallido(s). Reintentando..."
            )
            pending = failed_this_round
        else:
            pending = []

    if pending:
        failed_ids = [fid for _, _, fid in pending]
        print(f"[Coordinador] ✘ ADVERTENCIA: fragmentos sin procesar después de {max_redistrib_rounds} rondas: {failed_ids}")

    elapsed  = time.time() - t0
    combined = merge_counts(*partial_results)
    return combined, elapsed, worker_responses


def print_results(
    dist_result:      dict,
    dist_time:        float,
    seq_result:       dict,
    seq_time:         float,
    worker_responses: list[dict],
):
    sep()
    print("  RESULTADO DEL SISTEMA DISTRIBUIDO")
    sep()
    sorted_words = sorted(dist_result.items(), key=lambda x: x[1], reverse=True)
    top_count    = sorted_words[0][1] if sorted_words else 1
    print(f"\n  Top 20 palabras más frecuentes (de {len(dist_result):,} únicas):\n")
    for rank, (word, count) in enumerate(sorted_words[:20], 1):
        bar = "█" * min(count * 30 // max(top_count, 1), 30)
        print(f"  {rank:2}. {word:<25} {count:6}  {bar}")

    print()
    sep()
    print("  RESUMEN POR WORKER")
    sep()
    for resp in worker_responses:
        wid    = resp.get("worker_id", "?")
        w_proc = resp.get("words_processed", "?")
        unique = len(resp.get("result", {}))
        s      = resp.get("offset_inicio", "?")
        e      = resp.get("offset_fin",    "?")
        print(f"  {wid}: [{s:,} – {e:,}] | palabras: {w_proc} | únicas: {unique}")


    comparison = compare(seq_result, dist_result)
    print_comparison(comparison, dist_time, seq_time)


def generate_corpus(path: str, target_gb: float, seed_text: str | None = None):
    if seed_text is None:
        seed_text = (
            "Los sistemas distribuidos son fundamentales en la informática moderna. "
            "Python facilita la implementación de arquitecturas de microservicios. "
            "El patrón Ambassador mejora la resiliencia y la tolerancia a fallos. "
        ) * 10

    target_bytes = int(target_gb * 1024 ** 3)
    seed_bytes   = seed_text.encode("utf-8")
    written      = 0

    print(f"[Experimento] Generando corpus de {target_gb} GB en '{path}'...")
    with open(path, "wb") as f:
        while written < target_bytes:
            chunk = seed_bytes * min(1000, (target_bytes - written) // len(seed_bytes) + 1)
            chunk = chunk[: target_bytes - written]
            f.write(chunk)
            written += len(chunk)
    print(f"[Experimento] Corpus generado: {os.path.getsize(path) / (1024**3):.3f} GB")


def run_experiments(base_path: str, sizes_gb: list[float], num_workers: int):

    results = []
    sep("─")
    print(f"[Experimento] Ejecutando pruebas: {sizes_gb} GB con {num_workers} workers")
    sep("─")

    for gb in sizes_gb:
        corpus_path = f"{base_path}_{gb}GB.txt"

        if not os.path.isfile(corpus_path):
            generate_corpus(corpus_path, gb)
        else:
            print(f"[Experimento] Reutilizando corpus existente: {corpus_path}")

        print(f"\n[Experimento] === {gb} GB ===")

        # Ground Truth
        print("[Experimento] Iniciando Ground Truth secuencial...")
        gt_result, gt_time = sequential_count(corpus_path)

        # Distribuido
        print("[Experimento] Iniciando conteo distribuido...")
        dist_result, dist_time, _ = distributed_count(corpus_path, num_workers)

        speedup = gt_time / dist_time if dist_time > 0 else float("inf")
        comparison = compare(gt_result, dist_result)

        entry = {
            "size_gb":     gb,
            "gt_seconds":  round(gt_time,   4),
            "d_seconds":   round(dist_time, 4),
            "speedup":     round(speedup,   2),
            "consistent":  comparison["consistent"],
        }
        results.append(entry)

        print(
            f"\n[Experimento] {gb} GB → "
            f"GT={gt_time:.4f}s | D={dist_time:.4f}s | "
            f"Speedup={speedup:.2f}x | {'✔' if comparison['consistent'] else '✘'}"
        )

    print()
    sep()
    print("  RESUMEN EXPERIMENTOS")
    sep()
    print(f"  {'Tamaño':>8}  {'GT (s)':>10}  {'D (s)':>10}  {'Speedup':>8}  {'OK':>4}")
    print(f"  {'─'*8}  {'─'*10}  {'─'*10}  {'─'*8}  {'─'*4}")
    for r in results:
        ok = "✔" if r["consistent"] else "✘"
        print(
            f"  {r['size_gb']:>6} GB  "
            f"{r['gt_seconds']:>10.4f}  "
            f"{r['d_seconds']:>10.4f}  "
            f"{r['speedup']:>8.2f}x  "
            f"{ok:>4}"
        )
    sep()

    out_path = "experiments_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"[Experimento] Resultados guardados en: {out_path}")
    return results

def main():
    parser = argparse.ArgumentParser(
        description="Coordinador del sistema distribuido de conteo de palabras."
    )
    parser.add_argument("file_path", help="Ruta al corpus de texto.")
    parser.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS,
        help=f"Número de fragmentos / workers (default: {DEFAULT_WORKERS})."
    )
    parser.add_argument(
        "--experiment", action="store_true",
        help="Ejecutar experimentos de 1–5 GB (genera corpus automáticamente)."
    )
    parser.add_argument(
        "--sizes", nargs="+", type=float, default=[1.0, 2.0, 3.0, 4.0, 5.0],
        help="Tamaños en GB para el modo experimento (default: 1 2 3 4 5)."
    )
    args = parser.parse_args()

    if args.experiment:
        run_experiments(
            base_path   = args.file_path,
            sizes_gb    = args.sizes,
            num_workers = args.workers,
        )
        return

    if not os.path.isfile(args.file_path):
        print(f"[Coordinador] ERROR: No se encontró '{args.file_path}'.")
        sys.exit(1)

    file_size = os.path.getsize(args.file_path)
    print(f"[Coordinador] Corpus : {args.file_path}")
    print(f"[Coordinador] Tamaño : {file_size / (1024**3):.3f} GB ({file_size:,} bytes)")
    print(f"[Coordinador] Workers: {args.workers}")

    # Ground Truth
    sep("─")
    print("[Coordinador] INICIANDO GROUND TRUTH SECUENCIAL...")
    sep("─")
    seq_result, seq_time = sequential_count(args.file_path)
    print(f"[Coordinador] GT completado → {seq_time:.4f}s | Palabras únicas: {len(seq_result):,}")

    # Distribuido
    print()
    sep("─")
    print("[Coordinador] INICIANDO CONTEO DISTRIBUIDO...")
    sep("─")
    dist_result, dist_time, worker_responses = distributed_count(
        args.file_path, args.workers
    )
    print(
        f"\n[Coordinador] Distribuido completado → "
        f"{dist_time:.4f}s | Palabras únicas: {len(dist_result):,}"
    )

    # Resultados
    print()
    print_results(dist_result, dist_time, seq_result, seq_time, worker_responses)

    # Guardar JSON
    output_path = "resultado_final.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "file_path":          args.file_path,
                "file_size_bytes":    file_size,
                "num_workers":        args.workers,
                "distributed_result": dist_result,
                "sequential_result":  seq_result,
                "GT_seconds":         round(seq_time,  4),
                "D_seconds":          round(dist_time, 4),
                "speedup":            round(seq_time / dist_time, 2) if dist_time > 0 else None,
            },
            f, ensure_ascii=False, indent=2,
        )
    print(f"[Coordinador] Resultado guardado en: {output_path}")


if __name__ == "__main__":
    main()