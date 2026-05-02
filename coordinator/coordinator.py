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

SAMPLE_TEXT = """
Los sistemas distribuidos son un campo fundamental de la informática moderna.
Un sistema distribuido consiste en múltiples computadoras que se comunican entre sí
a través de una red para lograr un objetivo común. Estos sistemas ofrecen ventajas
significativas como escalabilidad, tolerancia a fallos y mejor rendimiento.

Python es uno de los lenguajes más populares para implementar sistemas distribuidos
debido a su simplicidad y a la gran cantidad de bibliotecas disponibles. Flask es un
microframework web de Python que permite crear servicios HTTP de manera sencilla.
Los servicios HTTP son fundamentales en arquitecturas de microservicios modernos.

El patrón Ambassador actúa como intermediario entre un servicio y sus clientes,
manejando tareas transversales como timeout, reintentos y logging. El Ambassador
simplifica la lógica del cliente al centralizar la comunicación con los servicios externos.
Este patrón es muy útil en arquitecturas de microservicios y sistemas distribuidos.

El patrón Circuit Breaker es esencial para la tolerancia a fallos en sistemas distribuidos.
Cuando un servicio falla repetidamente, el Circuit Breaker abre el circuito y evita
enviar más solicitudes al servicio fallido, permitiendo que el sistema se recupere.
El Circuit Breaker tiene tres estados: CLOSED, OPEN y HALF-OPEN, cada uno con
un comportamiento específico para manejar fallos y recuperaciones del sistema.

La frecuencia de palabras es una técnica fundamental en el procesamiento de texto
y análisis de lenguaje natural. Contar palabras de manera distribuida permite
procesar grandes volúmenes de texto de forma eficiente y escalable en sistemas modernos.
Los sistemas de conteo distribuido dividen el texto en fragmentos y los procesan
en paralelo, combinando los resultados parciales al final del procesamiento distribuido.
""".strip()


def sequential_count(text: str) -> tuple[dict, float]:
    t0 = time.time()
    result = count_words(text)
    elapsed = time.time() - t0
    return result, elapsed



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
            print(f"[Coordinador]  Ambassador retorno HTTP {resp.status_code}")
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
                    print(f"[Coordinador]   Fragmento #{frag_id} sin resultado valido")
            except Exception as e:
                print(f"[Coordinador]  Error en fragmento #{frag_id}: {e}")

    elapsed = time.time() - t0
    combined = merge_counts(*partial_results)
    return combined, elapsed, worker_responses



def print_separator(char="═", width=65):
    print(char * width)


def print_results(distributed_result: dict, dist_time: float,
                  sequential_result: dict, seq_time: float,
                  worker_responses: list[dict]):

    print_separator()
    print("  RESULTADO DEL SISTEMA DISTRIBUIDO")
    print_separator()


    sorted_words = sorted(distributed_result.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  Top 20 palabras más frecuentes (de {len(distributed_result)} unicas):\n")
    for rank, (word, count) in enumerate(sorted_words[:20], 1):
        bar = "█" * min(count, 30)
        print(f"  {rank:2}. {word:<20} {count:4}  {bar}")

    print()
    print_separator()
    print("  RESUMEN POR WORKER")
    print_separator()
    for resp in worker_responses:
        wid = resp.get("worker_id", "?")
        words_proc = resp.get("words_processed", "?")
        unique = len(resp.get("result", {}))
        print(f"  {wid}: {words_proc} palabras procesadas | {unique} palabras unicas")

    print()
    print_separator()
    print("  COMPARACION DE RENDIMIENTO")
    print_separator()
    speedup = seq_time / dist_time if dist_time > 0 else float("inf")
    improvement = ((seq_time - dist_time) / seq_time * 100) if seq_time > 0 else 0

    print(f"\n  Tiempo secuencial  : {seq_time:.4f} segundos")
    print(f"   Tiempo distribuido : {dist_time:.4f} segundos")
    print(f"   Speedup           : {speedup:.2f}x")
    print(f"   Mejora            : {improvement:.1f}%")

   
    if set(distributed_result.keys()) == set(sequential_result.keys()):
        match = all(distributed_result[k] == sequential_result[k]
                    for k in distributed_result)
        status = " CONSISTENTE" if match else " DIFERENCIAS DETECTADAS"
    else:
        status = " VOCABULARIOS DISTINTOS (revisión necesaria)"
    print(f"\n  Consistencia de resultados: {status}")
    print()
    print_separator()



def main():
    
    if len(sys.argv) > 1:
        text_input = " ".join(sys.argv[1:])
        print(f"[Coordinador] Usando texto desde argumentos ({len(text_input.split())} palabras).")
    else:
        text_input = SAMPLE_TEXT
        print(f"[Coordinador] Usando texto de prueba ({len(text_input.split())} palabras).")

    print_separator("─")
    print("[Coordinador] INICIANDO CONTEO SECUENCIAL (Ground Truth)...")
    print_separator("─")
    seq_result, seq_time = sequential_count(text_input)
    print(f"[Coordinador] Secuencial completado en {seq_time:.4f}s "
          f"| Palabras unicas: {len(seq_result)}")

    print()
    print_separator("─")
    print("[Coordinador]  INICIANDO CONTEO DISTRIBUIDO...")
    print_separator("─")
    dist_result, dist_time, worker_responses = distributed_count(text_input)
    print(f"\n[Coordinador]  Distribuido completado en {dist_time:.4f}s "
          f"| Palabras unicas: {len(dist_result)}")

    print()
    print_results(dist_result, dist_time, seq_result, seq_time, worker_responses)

    # Guardar resultado en JSON
    output_path = os.path.join(os.path.dirname(__file__), "..", "resultado_final.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "distributed_result": dist_result,
            "sequential_result": seq_result,
            "distributed_time_s": round(dist_time, 4),
            "sequential_time_s": round(seq_time, 4),
            "speedup": round(seq_time / dist_time, 2) if dist_time > 0 else None
        }, f, ensure_ascii=False, indent=2)
    print(f"[Coordinador]Resultado guardado en resultado_final.json")


if __name__ == "__main__":
    main()
