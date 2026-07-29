"""
runtime/cron.py
===============
Minimal 5-field cron expression support (minute hour dom month dow).

No external deps — standard Unix crontab fields only:
  *        any
  n        exact
  n-m      inclusive range
  */n      step from field min
  n-m/s    stepped range
  a,b,c    lists

Dow: 0–6 (Sunday=0) or sun–sat. Month: 1–12 or jan–dec.
"""

from __future__ import annotations

import calendar
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_DOW_NAMES = {
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}


class CronError(ValueError):
    """Invalid cron expression."""


@dataclass(frozen=True)
class CronExpression:
    raw: str
    minutes: frozenset[int]
    hours: frozenset[int]
    doms: frozenset[int]
    months: frozenset[int]
    dows: frozenset[int]


def _parse_names(token: str, names: dict[str, int]) -> str:
    out = token
    for name, num in names.items():
        out = out.replace(name, str(num))
    return out


def _parse_field(field: str, minimum: int, maximum: int, *, names: dict[str, int] | None = None) -> frozenset[int]:
    field = field.strip().lower()
    if not field:
        raise CronError("empty cron field")
    if names:
        field = _parse_names(field, names)

    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise CronError(f"empty list item in cron field: {field}")
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError as exc:
                raise CronError(f"invalid step '{step_s}'") from exc
            if step < 1:
                raise CronError("cron step must be >= 1")
            part = base if base else "*"

        if part == "*":
            start, end = minimum, maximum
        elif "-" in part:
            a, b = part.split("-", 1)
            try:
                start, end = int(a), int(b)
            except ValueError as exc:
                raise CronError(f"invalid range '{part}'") from exc
        else:
            try:
                start = end = int(part)
            except ValueError as exc:
                raise CronError(f"invalid value '{part}'") from exc

        if start > end:
            raise CronError(f"range start > end in '{part}'")
        if start < minimum or end > maximum:
            raise CronError(
                f"value out of range [{minimum}-{maximum}] in '{part}'"
            )
        values.update(range(start, end + 1, step))

    if not values:
        raise CronError(f"cron field matched nothing: {field}")
    return frozenset(values)


def parse_cron(expr: str) -> CronExpression:
    """Parse a 5-field cron expression."""
    raw = (expr or "").strip()
    if not raw:
        raise CronError("empty cron expression")
    # Allow compact forms without collapsing internal spaces incorrectly.
    parts = raw.split()
    if len(parts) != 5:
        raise CronError(
            f"cron expression must have 5 fields (got {len(parts)}): {raw!r}"
        )
    minute, hour, dom, month, dow = parts
    return CronExpression(
        raw=raw,
        minutes=_parse_field(minute, 0, 59),
        hours=_parse_field(hour, 0, 23),
        doms=_parse_field(dom, 1, 31),
        months=_parse_field(month, 1, 12, names=_MONTH_NAMES),
        dows=_parse_field(dow, 0, 6, names=_DOW_NAMES),
    )


def _matches(cron: CronExpression, dt: datetime) -> bool:
    # Python weekday: Mon=0..Sun=6 → cron Sunday=0
    dow = (dt.weekday() + 1) % 7
    return (
        dt.minute in cron.minutes
        and dt.hour in cron.hours
        and dt.day in cron.doms
        and dt.month in cron.months
        and dow in cron.dows
    )


def next_run(expr: str | CronExpression, after: float | None = None) -> float:
    """Return the next matching unix timestamp strictly after ``after``."""
    cron = expr if isinstance(expr, CronExpression) else parse_cron(expr)
    base = after if after is not None else time.time()
    # Start at the next whole minute.
    dt = datetime.fromtimestamp(base, tz=timezone.utc).replace(second=0, microsecond=0)
    # Advance one minute so "after" is exclusive.
    dt = datetime.fromtimestamp(dt.timestamp() + 60, tz=timezone.utc).replace(
        second=0, microsecond=0
    )

    # Bound search: ~1 year of minutes.
    for _ in range(366 * 24 * 60):
        # Skip invalid calendar combos early (e.g. Feb 31 never matches).
        try:
            calendar.monthrange(dt.year, dt.month)
        except Exception:
            pass
        if _matches(cron, dt):
            return dt.timestamp()
        dt = datetime.fromtimestamp(dt.timestamp() + 60, tz=timezone.utc).replace(
            second=0, microsecond=0
        )
    raise CronError(f"no next run within a year for cron: {cron.raw}")


def validate_cron(expr: str) -> str:
    """Validate and return normalized expression string."""
    return parse_cron(expr).raw
