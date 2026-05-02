# Contador Distribuido de Frecuencia de Palabras

### Patrones Ambassador + Circuit Breaker · Python + Flask

Se requiere el uso de **Python 3.10+** (por el `X | Y` en type hints).
instalar flask si es que no se tiene

---

## Orden de ejecución (5 terminales separadas)

Abre **5 terminales** desde la raíz del proyecto (`/project`).

### Terminal 1 – Worker 1

python workers/worker1.py

### Terminal 2 – Worker 2

python workers/worker2.py

### Terminal 3 – Worker 3

python workers/worker3.py

### Terminal 4 – Ambassador

python ambassador/ambassador.py

### Terminal 5 – Coordinador (una vez que los demás están activos)

python coordinator/coordinator.py

> Esperar a que los 3 workers y el Ambassador muestren su mensaje de inicio
> antes de ejecutar el coordinador.

---

## Resultado guardado

Al finalizar, el coordinador guarda `resultado_final.json` en la raíz del
proyecto con el conteo completo y las métricas de rendimiento.
# words-frecuency
