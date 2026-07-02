import time
import threading
from enum import Enum


class CircuitState(Enum):
    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:

    def __init__(self, worker_id: str, max_fails: int = 3, timeout_reset: float = 3.0):
        self.worker_id      = worker_id
        self.max_fails      = max_fails
        self.timeout_reset  = timeout_reset

        self._state              = CircuitState.CLOSED
        self._fail_count         = 0
        self._last_failure_time: float | None = None
        self._lock               = threading.Lock()


    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_half_open()
            return self._state

    @property
    def state_name(self) -> str:
        return self.state.value


    def allow_request(self) -> bool:
       
        with self._lock:
            self._check_half_open()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                print(f"  [CircuitBreaker:{self.worker_id}] OPEN – solicitud bloqueada.")
                return False

            print(f"  [CircuitBreaker:{self.worker_id}] HALF_OPEN – enviando solicitud de prueba.")
            return True

    def record_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.CLOSED)
            self._fail_count        = 0
            self._last_failure_time = None

    def record_failure(self):
        with self._lock:
            self._fail_count       += 1
            self._last_failure_time = time.time()
            print(
                f"  [CircuitBreaker:{self.worker_id}] Fallo "
                f"{self._fail_count}/{self.max_fails}."
            )

            if self._state == CircuitState.HALF_OPEN:

                self._transition(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED and self._fail_count >= self.max_fails:
                self._transition(CircuitState.OPEN)

   
    def _check_half_open(self):
        if (
            self._state == CircuitState.OPEN
            and self._last_failure_time is not None
            and (time.time() - self._last_failure_time) >= self.timeout_reset
        ):
            self._transition(CircuitState.HALF_OPEN)

    def _transition(self, new_state: CircuitState):
        old_state    = self._state
        self._state  = new_state
        print(
            f"  [CircuitBreaker:{self.worker_id}] Transición: "
            f"{old_state.value} → {new_state.value}"
        )

    def __repr__(self):
        return (
            f"CircuitBreaker(worker={self.worker_id}, "
            f"state={self._state.value}, "
            f"fails={self._fail_count}/{self.max_fails})"
        )