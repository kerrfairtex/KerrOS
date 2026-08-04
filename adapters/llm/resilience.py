"""
adapters/llm/resilience.py
==========================
KerrOS-native 3-layer LLM provider resilience (P6), inspired by OmniRoute's
circuit breaker / cooldown / lockout model — scoped to composite providers
(cloud, ollama, vllm, litellm, omniroute), not per-key catalogs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    LOCKED = "locked"


@dataclass
class ResilienceConfig:
    enabled: bool = True
    failure_threshold: int = 3
    cooldown_s: float = 30.0
    lockout_opens: int = 3
    lockout_s: float = 300.0

    @classmethod
    def from_mapping(cls, raw: Optional[dict[str, Any]] = None) -> "ResilienceConfig":
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", True)),
            failure_threshold=max(1, int(data.get("failure_threshold", 3))),
            cooldown_s=max(0.1, float(data.get("cooldown_s", 30.0))),
            lockout_opens=max(1, int(data.get("lockout_opens", 3))),
            lockout_s=max(0.1, float(data.get("lockout_s", 300.0))),
        )


@dataclass
class ProviderCircuit:
    name: str
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    open_count: int = 0
    opened_at: float | None = None
    locked_at: float | None = None
    last_error: str = ""
    half_open_probe_inflight: bool = False


@dataclass
class ProviderCircuitRegistry:
    """Per-provider circuit breaker with cooldown and lockout."""

    config: ResilienceConfig = field(default_factory=ResilienceConfig)
    clock: Callable[[], float] = time.time
    _circuits: dict[str, ProviderCircuit] = field(default_factory=dict)
    _bus: Any = None

    def _now(self) -> float:
        return float(self.clock())

    def _circuit(self, name: str) -> ProviderCircuit:
        key = (name or "").strip().lower() or "unknown"
        if key not in self._circuits:
            self._circuits[key] = ProviderCircuit(name=key)
        return self._circuits[key]

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            bus = self._bus
            if bus is None:
                from kernel.boot import resolve as kernel_resolve

                bus = kernel_resolve("event_bus")
                self._bus = bus
            bus.publish(topic, payload, source="llm_resilience")
        except Exception:
            pass

    def _transition(self, circuit: ProviderCircuit, new_state: CircuitState, detail: str = "") -> None:
        old = circuit.state
        if old == new_state:
            return
        circuit.state = new_state
        topic = {
            CircuitState.OPEN: "llm.circuit.open",
            CircuitState.HALF_OPEN: "llm.circuit.half_open",
            CircuitState.CLOSED: "llm.circuit.close",
            CircuitState.LOCKED: "llm.circuit.lockout",
        }.get(new_state, "llm.circuit.change")
        self._publish(
            topic,
            {
                "provider": circuit.name,
                "from": old.value,
                "state": new_state.value,
                "failures": circuit.consecutive_failures,
                "opens": circuit.open_count,
                "detail": detail,
            },
        )

    def _refresh(self, circuit: ProviderCircuit) -> None:
        now = self._now()
        if circuit.state == CircuitState.LOCKED:
            if circuit.locked_at is not None and (now - circuit.locked_at) >= self.config.lockout_s:
                circuit.locked_at = None
                circuit.open_count = 0
                circuit.consecutive_failures = 0
                circuit.half_open_probe_inflight = False
                self._transition(circuit, CircuitState.CLOSED, detail="lockout_expired")
            return

        if circuit.state == CircuitState.OPEN:
            if circuit.opened_at is not None and (now - circuit.opened_at) >= self.config.cooldown_s:
                circuit.half_open_probe_inflight = False
                self._transition(circuit, CircuitState.HALF_OPEN, detail="cooldown_elapsed")

    def allow(self, name: str) -> bool:
        if not self.config.enabled:
            return True
        circuit = self._circuit(name)
        self._refresh(circuit)

        if circuit.state == CircuitState.CLOSED:
            return True
        if circuit.state == CircuitState.LOCKED:
            return False
        if circuit.state == CircuitState.OPEN:
            return False
        if circuit.state == CircuitState.HALF_OPEN:
            if circuit.half_open_probe_inflight:
                return False
            circuit.half_open_probe_inflight = True
            return True
        return True

    def record_success(self, name: str) -> None:
        if not self.config.enabled:
            return
        circuit = self._circuit(name)
        circuit.consecutive_failures = 0
        circuit.half_open_probe_inflight = False
        circuit.last_error = ""
        if circuit.state != CircuitState.CLOSED:
            self._transition(circuit, CircuitState.CLOSED, detail="success")
        circuit.opened_at = None

    def record_failure(self, name: str, *, error: str = "", permanent: bool = False) -> None:
        if not self.config.enabled:
            return
        circuit = self._circuit(name)
        circuit.last_error = (error or "")[:200]
        circuit.half_open_probe_inflight = False
        circuit.consecutive_failures += 1

        if circuit.state == CircuitState.HALF_OPEN or permanent:
            self._open(circuit, detail="half_open_fail" if not permanent else "permanent")
            return

        if circuit.consecutive_failures >= self.config.failure_threshold:
            self._open(circuit, detail="threshold")

    def _open(self, circuit: ProviderCircuit, *, detail: str) -> None:
        circuit.opened_at = self._now()
        circuit.open_count += 1
        if circuit.open_count >= self.config.lockout_opens:
            circuit.locked_at = self._now()
            self._transition(circuit, CircuitState.LOCKED, detail=detail)
            return
        self._transition(circuit, CircuitState.OPEN, detail=detail)

    def reset(self, name: str | None = None) -> list[str]:
        """Manual unlock. Returns provider names that were reset."""
        names = [name.lower()] if name else list(self._circuits.keys())
        reset_names: list[str] = []
        for key in names:
            circuit = self._circuit(key)
            circuit.consecutive_failures = 0
            circuit.open_count = 0
            circuit.opened_at = None
            circuit.locked_at = None
            circuit.half_open_probe_inflight = False
            circuit.last_error = ""
            old = circuit.state
            circuit.state = CircuitState.CLOSED
            reset_names.append(circuit.name)
            if old != CircuitState.CLOSED:
                self._publish(
                    "llm.circuit.reset",
                    {
                        "provider": circuit.name,
                        "from": old.value,
                        "state": CircuitState.CLOSED.value,
                    },
                )
        return reset_names

    def snapshot(self) -> dict[str, Any]:
        now = self._now()
        providers: dict[str, Any] = {}
        for name, circuit in sorted(self._circuits.items()):
            self._refresh(circuit)
            cooldown_remaining = 0.0
            lockout_remaining = 0.0
            if circuit.state == CircuitState.OPEN and circuit.opened_at is not None:
                cooldown_remaining = max(
                    0.0, self.config.cooldown_s - (now - circuit.opened_at)
                )
            if circuit.state == CircuitState.LOCKED and circuit.locked_at is not None:
                lockout_remaining = max(
                    0.0, self.config.lockout_s - (now - circuit.locked_at)
                )
            providers[name] = {
                "state": circuit.state.value,
                "consecutive_failures": circuit.consecutive_failures,
                "open_count": circuit.open_count,
                "cooldown_remaining_s": round(cooldown_remaining, 1),
                "lockout_remaining_s": round(lockout_remaining, 1),
                "last_error": circuit.last_error,
            }
        return {
            "enabled": self.config.enabled,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "cooldown_s": self.config.cooldown_s,
                "lockout_opens": self.config.lockout_opens,
                "lockout_s": self.config.lockout_s,
            },
            "providers": providers,
        }


def load_resilience_config() -> ResilienceConfig:
    try:
        from kernel.config import load_config
        from kernel.flags import is_true
        import os

        cfg = load_config().values
        raw = dict(cfg.get("llm_resilience") or {})
        if "KERROS_LLM_RESILIENCE" in os.environ:
            raw["enabled"] = is_true(os.environ.get("KERROS_LLM_RESILIENCE", True))
        return ResilienceConfig.from_mapping(raw)
    except Exception:
        return ResilienceConfig()


_CLOUD_SOFT_FAIL_MARKERS = (
    "[all apis failed",
    "all apis failed",
    "use /offline mode",
    "[openrouter]",
)


def looks_like_provider_failure(result: Any) -> bool:
    """Detect soft-fail string returns from the cloud MultiAPI chain."""
    if not isinstance(result, str):
        return False
    lowered = result.strip().lower()
    return any(m in lowered for m in _CLOUD_SOFT_FAIL_MARKERS)
