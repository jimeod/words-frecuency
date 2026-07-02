import argparse
import json
import os
import re
import sys
import time

_WORD_RE = re.compile(r"[^\w']+", re.UNICODE)


def count_words(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in _WORD_RE.split(text.lower()):
        token = token.strip("'")
        if token:
            counts[token] = counts.get(token, 0) + 1
    return counts



def sequential_count(file_path: str, chunk_size: int = 64 * 1024 * 1024) -> tuple[dict, float]:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

    file_size = os.path.getsize(file_path)
    print(f"[GroundTruth] Archivo : {file_path}")
    print(f"[GroundTruth] Tamaño  : {file_size / (1024**3):.3f} GB ({file_size:,} bytes)")
    print(f"[GroundTruth] Iniciando conteo secuencial...")

    counts: dict[str, int] = {}
    leftover = ""          
    bytes_read = 0
    t0 = time.time()

    with open(file_path, "rb") as f:
        while True:
            raw = f.read(chunk_size)
            if not raw:
                break
            bytes_read += len(raw)

            text = leftover + raw.decode("utf-8", errors="replace")

            if bytes_read < file_size:
                last_space = max(text.rfind(" "), text.rfind("\n"), text.rfind("\t"))
                if last_space != -1:
                    leftover = text[last_space + 1:]
                    text     = text[:last_space + 1]
                else:
                    leftover = text
                    text     = ""
            else:
                leftover = ""

            partial = count_words(text)
            for word, cnt in partial.items():
                counts[word] = counts.get(word, 0) + cnt

            pct = bytes_read / file_size * 100
            print(f"\r[GroundTruth] Progreso: {pct:5.1f}%  ({bytes_read:,} / {file_size:,} bytes)", end="", flush=True)


    if leftover.strip():
        partial = count_words(leftover)
        for word, cnt in partial.items():
            counts[word] = counts.get(word, 0) + cnt

    elapsed = time.time() - t0
    print(f"\n[GroundTruth] Completado en {elapsed:.4f}s | Palabras únicas: {len(counts):,}")
    return counts, elapsed



def compare(gt: dict[str, int], distributed: dict[str, int]) -> dict:

    gt_keys   = set(gt.keys())
    dist_keys = set(distributed.keys())

    missing = sorted(gt_keys - dist_keys)
    extra   = sorted(dist_keys - gt_keys)
    diffs   = {
        w: (gt[w], distributed[w])
        for w in gt_keys & dist_keys
        if gt[w] != distributed[w]
    }
    consistent = not missing and not extra and not diffs

    return {
        "consistent":    consistent,
        "missing_words": missing,
        "extra_words":   extra,
        "count_diffs":   diffs,
    }


def print_comparison(comparison: dict, dist_time: float, gt_time: float):
    sep = "═" * 65
    print(f"\n{sep}")
    print("  COMPARACIÓN: GROUND TRUTH vs DISTRIBUIDO")
    print(sep)

    speedup     = gt_time / dist_time if dist_time > 0 else float("inf")
    improvement = (gt_time - dist_time) / gt_time * 100 if gt_time > 0 else 0

    print(f"\n  GT= {gt_time:.4f} s   (conteo secuencial)")
    print(f"  D=  {dist_time:.4f} s   (conteo distribuido)")
    print(f"\n  Speedup : {speedup:.2f}x")
    print(f"  Mejora  : {improvement:.1f}%")

    status = "✔  CONSISTENTE" if comparison["consistent"] else "✘  DIFERENCIAS DETECTADAS"
    print(f"\n  Consistencia GT vs D : {status}")

    if not comparison["consistent"]:
        if comparison["missing_words"]:
            print(f"\n  Palabras faltantes ({len(comparison['missing_words'])}):")
            print("  ", comparison["missing_words"][:20])
        if comparison["extra_words"]:
            print(f"\n  Palabras extra ({len(comparison['extra_words'])}):")
            print("  ", comparison["extra_words"][:20])
        if comparison["count_diffs"]:
            print(f"\n  Diferencias en conteo ({len(comparison['count_diffs'])}):")
            for w, (g, d) in list(comparison["count_diffs"].items())[:10]:
                print(f"    {w:<25} GT={g}  D={d}")
    print(f"\n{sep}")



def main():
    parser = argparse.ArgumentParser(
        description="Ground Truth: conteo secuencial de palabras en un corpus."
    )
    parser.add_argument("file_path", help="Ruta al archivo de corpus.")
    parser.add_argument("--top",  type=int, default=20, help="Número de top palabras a mostrar.")
    parser.add_argument("--json", action="store_true",  help="Guardar resultado en JSON.")
    args = parser.parse_args()

    result, elapsed = sequential_count(args.file_path)


    sorted_words = sorted(result.items(), key=lambda x: x[1], reverse=True)
    print(f"\nTop {args.top} palabras más frecuentes (de {len(result):,} únicas):\n")
    for rank, (word, count) in enumerate(sorted_words[: args.top], 1):
        bar = "█" * min(count // max(sorted_words[0][1] // 30, 1), 30)
        print(f"  {rank:2}. {word:<25} {count:6}  {bar}")

    if args.json:
        out_path = os.path.splitext(args.file_path)[0] + "_ground_truth.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(
                {"elapsed_seconds": round(elapsed, 4), "word_counts": result},
                f, ensure_ascii=False, indent=2,
            )
        print(f"\n[GroundTruth] Resultado guardado en: {out_path}")


if __name__ == "__main__":
    main()