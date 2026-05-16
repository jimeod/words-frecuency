import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask, request, jsonify
from utils.word_counter import count_words

app = Flask(__name__)
WORKER_ID = "worker_2"
PORT = 5002

# Texto hardcodeado — usado al correr este worker directamente
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

    time.sleep(len(text.split()) / 1000)

    result = count_words(text)
    print(f"[{WORKER_ID}] Palabras únicas encontradas: {len(result)}")

    return jsonify({
        "worker_id": WORKER_ID,
        "result": result,
        "words_processed": len(text.split())
    }), 200


# ── Modo standalone: procesa SAMPLE_TEXT completo y muestra tiempos ──
def standalone_demo():
    import time as _time
    print(f"[{WORKER_ID}] Modo standalone — procesando SAMPLE_TEXT completo")
    print(f"[{WORKER_ID}] Total palabras: {len(SAMPLE_TEXT.split())}")

    t0 = _time.time()
    result = count_words(SAMPLE_TEXT)
    elapsed = _time.time() - t0

    sorted_words = sorted(result.items(), key=lambda x: x[1], reverse=True)
    print(f"\n[{WORKER_ID}] Top 10 palabras:")
    for word, count in sorted_words[:10]:
        print(f"  {word:<20} {count}")

    print(f"\n  GT= N/A  (solo este worker)")
    print(f"  D=  {elapsed:.4f} s  (este worker procesando el texto completo)")
    print(f"  Palabras únicas: {len(result)}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        standalone_demo()
    else:
        print(f"[{WORKER_ID}] Iniciando servidor en puerto {PORT}...")
        print(f"[{WORKER_ID}] Tip: usa --demo para procesar SAMPLE_TEXT localmente sin servidor")
        app.run(host="0.0.0.0", port=PORT, debug=False)