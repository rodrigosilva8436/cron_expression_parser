from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta


__all__ = ["CronField", "CronExpression", "parse"]


@dataclass(frozen=True)
class CronField:
    """A single parsed cron field: the set of integer values it matches.

    Storing the full set (rather than a compact representation) keeps
    membership checks O(1) and avoids re-parsing on every iteration.
    """

    values: frozenset[int]
    name: str

    def matches(self, value: int) -> bool:
        return value in self.values


class CronExpression:
    """A compiled cron expression.

    Supports forward iteration from an arbitrary starting datetime via
    :meth:`next_after`. The expression is immutable after construction.
    """

    def __init__(
        self,
        minute: CronField,
        hour: CronField,
        day_of_month: CronField,
        month: CronField,
        day_of_week: CronField,
    ):
        self.minute = minute
        self.hour = hour
        self.day_of_month = day_of_month
        self.month = month
        self.day_of_week = day_of_week

    def __repr__(self) -> str:
        return (
            "CronExpression("
            f"minute={sorted(self.minute.values)}, "
            f"hour={sorted(self.hour.values)}, "
            f"day_of_month={sorted(self.day_of_month.values)}, "
            f"month={sorted(self.month.values)}, "
            f"day_of_week={sorted(self.day_of_week.values)})"
        )

    def next_after(self, start: datetime) -> datetime:
        """Return the next fire time strictly after *start*.

        The search is forward-only and bounded at ~366 days to guarantee
        termination even for expressions that never match (e.g.
        ``0 0 31 2 *``). When no match is found, ``ValueError`` is raised.
        """
        # Start at the top of the next minute so we never return *start* itself.
        candidate = start.replace(second=0, microsecond=0) + timedelta(minutes=1)

        limit = start + timedelta(days=366)

        while candidate <= limit:
            if not self.month.matches(candidate.month):
                # Jump to the first day of the next month.
                if candidate.month == 12:
                    candidate = candidate.replace(
                        year=candidate.year + 1, month=1, day=1, hour=0, minute=0
                    )
                else:
                    candidate = candidate.replace(
                        month=candidate.month + 1, day=1, hour=0, minute=0
                    )
                continue

            if not self._day_matches(candidate):
                candidate = candidate.replace(hour=0, minute=0) + timedelta(days=1)
                continue

            if not self.hour.matches(candidate.hour):
                candidate = candidate.replace(minute=0) + timedelta(hours=1)
                continue

            if not self.minute.matches(candidate.minute):
                candidate = candidate + timedelta(minutes=1)
                continue

            return candidate

        raise ValueError(
            f"No fire time found within one year for expression {self!r}"
        )

    def _day_matches(self, dt: datetime) -> bool:
        """Check whether the day-of-month and day-of-week constraints are satisfied.

        Standard cron semantics: if both day-of-month and day-of-week are
        restricted (not wildcards), the date matches when *either* matches.
        If only one is restricted, that one must match.
        """
        dom_wild = self.day_of_month.name == "*"
        dow_wild = self.day_of_week.name == "*"

        if dom_wild and dow_wild:
            return True
        if dom_wild:
            return self.day_of_week.matches(self._cron_dow(dt))
        if dow_wild:
            return self.day_of_month.matches(dt.day)

        # Both restricted — OR semantics.
        return self.day_of_month.matches(dt.day) or self.day_of_week.matches(
            self._cron_dow(dt)
        )

    @staticmethod
    def _cron_dow(dt: datetime) -> int:
        """Return the cron day-of-week for *dt*.

        Cron uses 0=Sunday. Python's ``weekday()`` returns 0=Monday..6=Sunday,
        so we convert: Sunday (6) -> 0, Monday (0) -> 1, etc.
        """
        py_dow = dt.weekday()  # Monday=0 .. Sunday=6
        return 0 if py_dow == 6 else py_dow + 1


def parse(expression: str) -> CronExpression:
    """Parse a five-field cron expression into a :class:`CronExpression`.

    Supported field syntax:
      - ``*``                  all values
      - ``5``                  a single value
      - ``1,2,3``              a list
      - ``1-5``                a range
      - ``*/2``                every Nth value from the field minimum
      - ``1-10/2``             every 2nd value in the range 1..10

    Day-of-week accepts both 0 and 7 for Sunday.
    """
    if not isinstance(expression, str):
        raise TypeError("expression must be a string")
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError(
            f"expected exactly 5 fields, got {len(parts)}: {expression!r}"
        )

    minute_field = _parse_field(parts[0], 0, 59, "minute")
    hour_field = _parse_field(parts[1], 0, 23, "hour")
    dom_field = _parse_field(parts[2], 1, 31, "day_of_month")
    month_field = _parse_field(parts[3], 1, 12, "month")
    dow_field = _parse_dow_field(parts[4])

    return CronExpression(minute_field, hour_field, dom_field, month_field, dow_field)


def _parse_field(
    raw: str, min_val: int, max_val: int, name: str
) -> CronField:
    values = set()
    for token in raw.split(","):
        values.update(_expand_token(token, min_val, max_val, name))
    return CronField(values=frozenset(values), name=raw)


def _expand_token(
    token: str, min_val: int, max_val: int, name: str
) -> set[int]:
    if token == "*":
        return set(range(min_val, max_val + 1))

    if "/" in token:
        range_part, step_part = token.split("/", 1)
        try:
            step = int(step_part)
        except ValueError:
            raise ValueError(
                f"invalid step {step_part!r} in {name} field"
            ) from None
        if step < 1:
            raise ValueError(f"step must be >= 1 in {name} field")

        if range_part == "*":
            lo, hi = min_val, max_val
        elif "-" in range_part:
            lo, hi = _parse_range(range_part, min_val, max_val, name)
        else:
            # ``5/2`` means "starting at 5, every 2 up to max".
            lo = _parse_single(range_part, min_val, max_val, name)
            hi = max_val

        return set(range(lo, hi + 1, step))

    if "-" in token:
        lo, hi = _parse_range(token, min_val, max_val, name)
        return set(range(lo, hi + 1))

    return {_parse_single(token, min_val, max_val, name)}


def _parse_range(
    token: str, min_val: int, max_val: int, name: str
) -> tuple[int, int]:
    lo_str, hi_str = token.split("-", 1)
    lo = _parse_single(lo_str, min_val, max_val, name)
    hi = _parse_single(hi_str, min_val, max_val, name)
    if lo > hi:
        raise ValueError(
            f"range start {lo} exceeds end {hi} in {name} field"
        )
    return lo, hi


def _parse_single(token: str, min_val: int, max_val: int, name: str) -> int:
    try:
        value = int(token)
    except ValueError:
        raise ValueError(
            f"invalid value {token!r} in {name} field"
        ) from None
    if value < min_val or value > max_val:
        raise ValueError(
            f"value {value} out of range [{min_val}, {max_val}] in {name} field"
        )
    return value


def _parse_dow_field(raw: str) -> CronField:
    """Parse the day-of-week field, normalising 7 to 0 (both = Sunday)."""
    if raw == "*":
        return CronField(values=frozenset(range(0, 7)), name=raw)

    values = set()
    for token in raw.split(","):
        values.update(_expand_dow_token(token))
    return CronField(values=frozenset(values), name=raw)


def _expand_dow_token(token: str) -> set[int]:
    if "/" in token:
        range_part, step_part = token.split("/", 1)
        try:
            step = int(step_part)
        except ValueError:
            raise ValueError(
                f"invalid step {step_part!r} in day_of_week field"
            ) from None
        if step < 1:
            raise ValueError("step must be >= 1 in day_of_week field")

        if range_part == "*":
            lo, hi = 0, 6
        elif "-" in range_part:
            lo, hi = _parse_dow_range(range_part)
        else:
            lo = _parse_dow_single(range_part)
            hi = 6

        return set(range(lo, hi + 1, step))

    if "-" in token:
        lo, hi = _parse_dow_range(token)
        return set(range(lo, hi + 1))

    return {_parse_dow_single(token)}


def _parse_dow_range(token: str) -> tuple[int, int]:
    lo_str, hi_str = token.split("-", 1)
    lo = _parse_dow_single(lo_str)
    hi = _parse_dow_single(hi_str)
    if lo > hi:
        raise ValueError(
            f"range start {lo} exceeds end {hi} in day_of_week field"
        )
    return lo, hi


def _parse_dow_single(token: str) -> int:
    try:
        value = int(token)
    except ValueError:
        raise ValueError(
            f"invalid value {token!r} in day_of_week field"
        ) from None
    if value == 7:
        return 0
    if value < 0 or value > 7:
        raise ValueError(
            f"value {value} out of range [0, 7] in day_of_week field"
        )
    return value
