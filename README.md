# Contador Distribuido de Frecuencia de Palabras

### Patrones Ambassador y Circuit Breaker — Sistemas Distribuidos

## Descripción

Sistema distribuido que cuenta la frecuencia de palabras en corpus de gran tamaño (1 GB a 5 GB). El coordinador divide el corpus en fragmentos usando offsets de bytes y los distribuye a 3 workers mediante un Ambassador. Incluye tolerancia a fallos con el patrón Circuit Breaker.

## Estructura del proyecto

```
proyecto3/
├── ambassador/
│   ├── ambassador.py
│   └── circuit_breaker.py
├── coordinator/
│   ├── coordinator.py
│   ├── ground_truth.py
│   └── corpus_1,2,3,4,5 etc gb.txt
├── workers/
│   └── worker.py
├── utils/
│   ├── text_splitter.py
│   └── word_counter.py
└── README.md
```

## Instalación de dependencias

```bash
pip install flask requests
```

---

## Generar corpus de prueba

Ejecutar desde la raíz del proyecto:

```bash
# 1 GB
python -c "
text = 'Los sistemas distribuidos son un campo fundamental de la informática moderna. Python es uno de los lenguajes más populares para implementar sistemas distribuidos. El patrón Ambassador actúa como intermediario entre un servicio y sus clientes. El patrón Circuit Breaker es esencial para la tolerancia a fallos. ' * 100
target = 1 * 1024 * 1024 * 1024
with open('coordinator/corpus_1gb.txt', 'w') as f:
    written = 0
    while written < target:
        f.write(text)
        written += len(text.encode())
print('Listo: corpus_1gb.txt')
"

# 2 GB
python -c "
text = 'Los sistemas distribuidos son un campo fundamental de la informática moderna. Python es uno de los lenguajes más populares para implementar sistemas distribuidos. El patrón Ambassador actúa como intermediario entre un servicio y sus clientes. El patrón Circuit Breaker es esencial para la tolerancia a fallos. ' * 100
target = 2 * 1024 * 1024 * 1024
with open('coordinator/corpus_2gb.txt', 'w') as f:
    written = 0
    while written < target:
        f.write(text)
        written += len(text.encode())
print('Listo: corpus_2gb.txt')
"

# 3 GB
python -c "
text = 'Los sistemas distribuidos son un campo fundamental de la informática moderna. Python es uno de los lenguajes más populares para implementar sistemas distribuidos. El patrón Ambassador actúa como intermediario entre un servicio y sus clientes. El patrón Circuit Breaker es esencial para la tolerancia a fallos. ' * 100
target = 3 * 1024 * 1024 * 1024
with open('coordinator/corpus_3gb.txt', 'w') as f:
    written = 0
    while written < target:
        f.write(text)
        written += len(text.encode())
print('Listo: corpus_3gb.txt')
"
```

> **Nota:** Para 4 GB y 5 GB repetir el mismo comando cambiando el número. Los archivos tardan unos minutos en generarse.

---

## Ejecución del sistema

Abrir **5 terminales** en VS Code. En cada una navegar primero a la raíz del proyecto:

```bash
cd proyecto3
```

### Terminal 1 — Worker 1

```bash
WORKER_ID=worker_1 PORT=5001 python workers/worker.py
```

### Terminal 2 — Worker 2

```bash
WORKER_ID=worker_2 PORT=5002 python workers/worker.py
```

### Terminal 3 — Worker 3

```bash
WORKER_ID=worker_3 PORT=5003 python workers/worker.py
```

### Terminal 4 — Ambassador

```bash
python ambassador/ambassador.py
```

### Terminal 5 — Coordinador

Esperar a que los 4 servicios anteriores muestren `Running on http://...` antes de ejecutar.

```bash
python coordinator/coordinator.py coordinator/corpus_1gb.txt
```

---

## Ejecutar Ground Truth secuencial

```bash
python coordinator/ground_truth.py coordinator/corpus_1gb.txt
```

Con opciones:

```bash
python coordinator/ground_truth.py coordinator/corpus_1gb.txt --top 30
python coordinator/ground_truth.py coordinator/corpus_1gb.txt --json
```

---

## Casos de prueba con fallos de workers

### Caso 1 — 1 worker falla a mitad del procesamiento (1 GB)

1. Iniciar el sistema completo normalmente.
2. En la Terminal 5 ejecutar el coordinador con el corpus de 1 GB.
3. Cuando veas que los workers están procesando, ir a la **Terminal 1** y presionar `Ctrl+C` para matar worker_1.
4. Observar en el Ambassador cómo el Circuit Breaker pasa a OPEN y redistribuye el fragmento a worker_2 o worker_3.

```bash
python coordinator/coordinator.py coordinator/corpus_1gb.txt
```

### Caso 2 — 2 workers fallan simultáneamente (3 GB)

1. Iniciar el sistema completo normalmente.
2. Ejecutar el coordinador con el corpus de 3 GB.
3. Cuando los workers estén procesando, presionar `Ctrl+C` en **Terminal 1** y **Terminal 2** simultáneamente.
4. Verificar que worker_3 continúa solo y completa el trabajo.

```bash
python coordinator/coordinator.py coordinator/corpus_3gb.txt
```

### Caso 3 — Worker falla y se recupera (OPEN → HALF-OPEN → CLOSED)

1. Iniciar el sistema completo.
2. Ejecutar el coordinador.
3. Matar worker_1 con `Ctrl+C` en Terminal 1.
4. Esperar 10 segundos (timeout del Circuit Breaker).
5. Volver a iniciar worker_1:

```bash
WORKER_ID=worker_1 PORT=5001 python workers/worker.py
```

## Notas técnicas

- El coordinador **nunca lee el contenido** del corpus; solo obtiene el tamaño con `os.path.getsize()` y calcula offsets de bytes.
- Los workers ajustan los límites de lectura para no cortar palabras a la mitad (manejo de fronteras UTF-8).
- El Ambassador usa **Round Robin** para distribuir la carga entre workers.
- El Circuit Breaker abre el circuito después de **3 fallos consecutivos** y espera **10 segundos** antes de intentar recuperación.
- Se usa `ThreadPoolExecutor` para paralelismo real en una sola máquina.
