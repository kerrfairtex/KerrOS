"""
adapters/llm/omniroute_telemetry.py
===================================
Parse OmniRoute X-OmniRoute-* cost/usage response headers and publish
kernel EventBus events (P3 touchpoint).

Header set matches OmniRoute API reference (non-streaming success responses).
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional

OMNIROUTE_USAGE_TOPIC = "omniroute.usage"
OMNIROUTE_HEADER_PREFIX = "x-omniroute-"

# Header name (without X-OmniRoute-) → payload key + coercer name
_HEADER_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("response-cost", "cost_usd", "float"),
    ("tokens-in", "tokens_in", "int"),
    ("tokens-out", "tokens_out", "int"),
    ("model", "model", "str"),
    ("provider", "upstream_provider", "str"),
    ("latency-ms", "latency_ms", "float"),
    ("cache-hit", "cache_hit", "bool"),
    ("cost-saved", "cost_saved_usd", "float"),
    ("fallback-attempts", "fallback_attempts", "int"),
    ("request-id", "request_id", "str"),
    ("version", "version", "str"),
    ("cache", "cache", "str"),  # HIT / MISS
)


def _coerce(kind: str, raw: str) -> Any:
    value = raw.strip()
    if kind == "str":
        return value
    if kind == "int":
        return int(float(value))
    if kind == "float":
        return float(value)
    if kind == "bool":
        return value.lower() in ("1", "true", "yes", "hit")
    return value


def _header_map(headers: Mapping[str, str]) -> dict[str, str]:
    """Normalize header keys to lowercase for case-insensitive lookup."""
    return {str(k).lower(): str(v) for k, v in headers.items()}


def has_omniroute_headers(headers: Mapping[str, str]) -> bool:
    for key in _header_map(headers):
        if key.startswith(OMNIROUTE_HEADER_PREFIX):
            return True
    return False


def parse_omniroute_headers(headers: Mapping[str, str]) -> dict[str, Any]:
    """Extract known X-OmniRoute-* fields into a typed payload dict.

    Unknown X-OmniRoute-* headers are collected under payload["extra"].
    Returns {} when no OmniRoute headers are present.
    """
    lowered = _header_map(headers)
    if not any(k.startswith(OMNIROUTE_HEADER_PREFIX) for k in lowered):
        return {}

    payload: dict[str, Any] = {}
    known_keys = set()
    for suffix, field, kind in _HEADER_FIELDS:
        key = OMNIROUTE_HEADER_PREFIX + suffix
        known_keys.add(key)
        if key not in lowered or lowered[key] == "":
            continue
        try:
            payload[field] = _coerce(kind, lowered[key])
        except (TypeError, ValueError):
            payload[field] = lowered[key]

    extra: dict[str, str] = {}
    for key, value in lowered.items():
        if key.startswith(OMNIROUTE_HEADER_PREFIX) and key not in known_keys:
            extra[key[len(OMNIROUTE_HEADER_PREFIX) :]] = value
    if extra:
        payload["extra"] = extra

    return payload


def publish_omniroute_usage(
    headers: Mapping[str, str],
    *,
    source: str = "omniroute",
    bus: Any = None,
    extras: Optional[MutableMapping[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Parse headers and publish ``omniroute.usage`` when telemetry is present.

    Soft-fails if the kernel EventBus is unavailable. Returns the payload
    that was published (or would be), or None if nothing to publish.
    """
    payload = parse_omniroute_headers(headers)
    if not payload:
        return None
    if extras:
        payload = {**payload, **dict(extras)}

    try:
        if bus is None:
            from kernel.boot import resolve as kernel_resolve

            bus = kernel_resolve("event_bus")
        bus.publish(OMNIROUTE_USAGE_TOPIC, payload, source=source)
    except Exception:
        # Kernel not booted or bus missing — keep chat path intact.
        pass
    return payload
