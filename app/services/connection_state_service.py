"""Thread-safe source of truth for user-visible connection journeys."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import RLock
from time import monotonic


PHASES = {
    "idle", "preflight", "testing", "applying", "verifying",
    "active", "restoring", "failed",
}


@dataclass(frozen=True)
class Snapshot:
    generation: int
    scope: str
    phase: str
    message: str
    cancellable: bool
    owned_by_app: bool
    updated_at: float


class ConnectionState:
    def __init__(self):
        self._lock = RLock()
        self._generation = 0
        self._snapshot = Snapshot(0, "", "idle", "", False, False, monotonic())

    def begin(self, scope: str, message: str = "", cancellable: bool = True) -> int:
        if scope not in {"dns", "app", "warp", "game", "recovery"}:
            raise ValueError("دامنه اتصال معتبر نیست")
        with self._lock:
            self._generation += 1
            self._set(scope, "preflight", message, cancellable, False)
            return self._generation

    def advance(self, generation: int, phase: str, message: str = "",
                owned_by_app: bool | None = None) -> bool:
        if phase not in PHASES - {"idle", "preflight"}:
            raise ValueError("مرحله اتصال معتبر نیست")
        with self._lock:
            if generation != self._generation:
                return False
            owned = self._snapshot.owned_by_app if owned_by_app is None else bool(owned_by_app)
            self._set(self._snapshot.scope, phase, message,
                      phase not in {"active", "failed", "idle"}, owned)
            return True

    def cancel(self, generation: int, message: str = "") -> bool:
        with self._lock:
            if generation != self._generation or not self._snapshot.cancellable:
                return False
            self._set(self._snapshot.scope, "restoring", message, False,
                      self._snapshot.owned_by_app)
            return True

    def reset(self, message: str = "") -> None:
        with self._lock:
            self._generation += 1
            self._set("", "idle", message, False, False)

    def snapshot(self) -> dict:
        with self._lock:
            return asdict(self._snapshot)

    def _set(self, scope: str, phase: str, message: str,
             cancellable: bool, owned_by_app: bool) -> None:
        safe_message = " ".join(str(message).split())[:240]
        self._snapshot = Snapshot(
            self._generation, scope, phase, safe_message,
            bool(cancellable), bool(owned_by_app), monotonic(),
        )
