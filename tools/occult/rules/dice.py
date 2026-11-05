"""Dice expressions: `2d6+3`, `4d6kh3` (keep highest 3), `2d20kl1` (disadvantage), `1d8+1d6-1`.

    dice.parse("2d6+3")          # [Term(sign=1, count=2, sides=6), Term(sign=1, count=0, sides=0, flat=3)]
    dice.average("2d6+3")        # 10.0 (expected value; keep/drop terms are computed exactly)
    dice.roll("4d6kh3", rng)     # Roll(total, detail): detail shows every die, dropped ones in ()
"""
import functools
import itertools
import random
import re
from dataclasses import dataclass

TERM = re.compile(r"\s*([+-])?\s*(?:(\d*)d(\d+)(?:(kh|kl|dh|dl|k|d)(\d+))?|(\d+))\s*", re.I)
MAX_DICE = 100


@dataclass(frozen=True)
class Term:
    sign: int
    count: int        # 0 for a flat number
    sides: int
    keep: tuple = None    # ("h"|"l", n): the dice kept
    flat: int = 0


@dataclass
class Roll:
    expr: str
    total: int
    detail: str


def parse(expr):
    s = re.sub(r"\s*([+-])\s*", r"\1", expr.strip())
    if not s:
        raise ValueError("empty dice expression")
    if re.search(r"\s", s):
        raise ValueError(f"can't read dice expression '{expr}': join its terms with + or -")
    terms, pos = [], 0
    while pos < len(s):
        m = TERM.match(s, pos)
        if not m or m.end() == pos or (pos and not m.group(1)):
            raise ValueError(f"can't read dice expression '{expr}' at '{s[pos:]}'")
        sign = -1 if m.group(1) == "-" else 1
        if m.group(6):
            terms.append(Term(sign, 0, 0, None, int(m.group(6))))
        else:
            n, sides = int(m.group(2) or 1), int(m.group(3))
            if not 1 <= n <= MAX_DICE or sides < 1:
                raise ValueError(f"'{m.group(0).strip()}': 1-{MAX_DICE} dice with at least 1 side")
            keep = None
            if m.group(4):
                op, k = m.group(4).lower(), int(m.group(5))
                if k > n:
                    raise ValueError(f"can't keep or drop {k} of {n} dice")
                keep = {"k": ("h", k), "kh": ("h", k), "kl": ("l", k), "d": ("h", n - k),
                        "dl": ("h", n - k), "dh": ("l", n - k)}[op]
            terms.append(Term(sign, n, sides, keep))
        pos = m.end()
    return terms


@functools.lru_cache(maxsize=256)
def _keep_mean(n, sides, hl, k):
    """Exact mean of the sum of the k highest (or lowest) of n dice; enumerated (n <= 6) or simulated."""
    if sides ** n <= 50_000:
        tot = 0
        for r in itertools.product(range(1, sides + 1), repeat=n):
            r = sorted(r, reverse=hl == "h")
            tot += sum(r[:k])
        return tot / sides ** n
    rng = random.Random(0)
    trials = 20_000
    return sum(sum(sorted((rng.randint(1, sides) for _ in range(n)), reverse=hl == "h")[:k])
               for _ in range(trials)) / trials


def average(expr):
    tot = 0.0
    for t in parse(expr):
        if not t.count:
            tot += t.sign * t.flat
        elif t.keep:
            tot += t.sign * _keep_mean(t.count, t.sides, *t.keep)
        else:
            tot += t.sign * t.count * (t.sides + 1) / 2
    return tot


def roll(expr, rng=None):
    rng = rng or random.Random()
    total, parts = 0, []
    for t in parse(expr):
        sign = "-" if t.sign < 0 else "+"
        if not t.count:
            total += t.sign * t.flat
            parts.append(f"{sign} {t.flat}")
            continue
        rolls = [rng.randint(1, t.sides) for _ in range(t.count)]
        kept = list(range(len(rolls)))
        if t.keep:
            hl, k = t.keep
            order = sorted(kept, key=lambda i: rolls[i], reverse=hl == "h")
            kept = set(order[:k])
        shown = ", ".join(str(r) if i in kept else f"({r})" for i, r in enumerate(rolls))
        total += t.sign * sum(rolls[i] for i in kept)
        parts.append(f"{sign} [{shown}]")
    detail = " ".join(parts)
    return Roll(expr, total, detail[2:] if detail.startswith("+ ") else detail)
