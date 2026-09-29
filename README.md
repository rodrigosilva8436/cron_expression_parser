# cron-expression-parser

Parses standard five-field cron expressions and computes the next fire time after a given datetime. Zero third-party dependencies — standard library only.

## Usage

```python
from datetime import datetime
from cron_expression_parser import parse

expr = parse("*/15 9-17 * * 1-5")
start = datetime(2024, 1, 15, 10, 7, 0)
next_fire = expr.next_after(start)
print(next_fire)  # 2024-01-15 10:15:00
```

## Exported names

- `parse(expression: str) -> CronExpression` — parse a five-field cron string.
- `CronExpression` — the compiled expression object.
  - `next_after(start: datetime) -> datetime` — returns the next fire time strictly after `start`.
- `CronField` — a single parsed field (exposed for introspection; has `.values` and `.name`).

## Why this exists

The problem is narrow: given a cron expression and a starting datetime, find the next time it should fire. This library does that and nothing else. It does not schedule jobs, run commands, or handle timezone conversion. The trade-off is simplicity over feature coverage — if you need job scheduling, pair this with your own runner.

## Edge cases

**Day-of-month and day-of-week interaction.** When both fields are restricted (not `*`), the date matches if *either* matches (OR semantics). This is standard Vixie cron behaviour. When only one is restricted, that one must match. The wildcard `*` in either field means "no constraint from this field."

**Day-of-week 7.** Both 0 and 7 represent Sunday and are normalised internally to 0.

**Impossible expressions.** An expression like `0 0 30 2 *` (February 30th) will never match. `next_after` searches forward up to one year and raises `ValueError` if no match is found, rather than looping forever.

**`next_after` is exclusive.** It returns the first fire time strictly after the given datetime. If you pass a datetime that is itself a valid fire time, you get the *next* one.
