"""Combat encounters from the loaded rules tables: XP budgets, difficulty, and suggestions.

    encounter.party("5,5,5,4") / party("4x5")       # -> [5, 5, 5, 4] / [5, 5, 5, 5]
    encounter.budget([5, 5, 5, 4])                  # {"low": 1750, "moderate": 2625, "high": 3800}
    encounter.evaluate([5]*4, [(goblin, 6), (boss, 1)])
    encounter.suggest([3]*4, "moderate", {"type": "undead"}, n=5, seed=1)

Difficulty: the budgets are ceilings ("spend as much of your XP budget as you can without going over"),
so an encounter is rated by the smallest budget its XP fits under: up to the Low budget is Low, up to
Moderate is Moderate, up to High is High, and anything past the High budget is "beyond High". There are
no multipliers for numbers of monsters in the 2024 rules; encounter troubleshooting advice is
turned into warnings instead.
"""
import random
import re

from .. import data, query
from . import core, tables

DIFFICULTIES = ("low", "moderate", "high")


class EncounterError(ValueError):
    pass


def party(spec):
    """'5,5,5,4', '4x5', '3x5,2x4', [5, 5] -> list of character levels."""
    if isinstance(spec, (list, tuple)):
        levels = [int(x) for x in spec]
    else:
        levels = []
        for part in re.split(r"[,\s]+", str(spec).strip()):
            if not part:
                continue
            m = re.fullmatch(r"(\d+)\s*[x×*]\s*(\d+)", part)
            if m:
                levels += [int(m.group(2))] * int(m.group(1))
            elif part.isdigit():
                levels.append(int(part))
            else:
                raise EncounterError(f"can't read party '{part}': use levels (5,5,4) or count x level (4x5)")
    if not levels:
        raise EncounterError("the party has no characters")
    for lv in levels:
        if not 1 <= lv <= 20:
            raise EncounterError(f"character level {lv} is not 1-20")
    return levels


def budget(levels):
    table = tables.xp_budget()
    return {d: sum(table[lv][d] for lv in levels) for d in DIFFICULTIES}


def rate(xp, b):
    for d in DIFFICULTIES:
        if xp <= b[d]:
            return d
    return "beyond high"


def creature_xp(e, lair=False):
    d = e.data
    if lair and d.get("xp_lair"):
        return d["xp_lair"]
    return d.get("xp") or 0


def evaluate(levels, monsters, lair=False):
    """monsters: [(creature entity, count)] -> totals, rating and warnings."""
    b = budget(levels)
    rows, total, count = [], 0, 0
    for e, n in monsters:
        if e.type != "creature":
            raise EncounterError(f"{e.sid} is not a creature")
        xp = creature_xp(e, lair)
        rows.append({"id": e.sid, "title": e.title, "cr": e.data.get("cr"), "count": n, "xp_each": xp, "xp": xp * n})
        total += xp * n
        count += n
    rating = rate(total, b)
    warnings = []
    pcs = len(levels)
    if count > 2 * pcs:
        warnings.append(f"{count} creatures for {pcs} characters: more than two per character; include fragile "
                        "creatures that fall quickly" + (" (this matters most at levels 1-2)" if min(levels) <= 2 else ""))
    top = max(levels)
    for r in rows:
        cr = core.cr_value(r["cr"])
        if cr is not None and cr > top:
            warnings.append(f"{r['title']} (CR {r['cr']}) is above the party's level {top}: one action of "
                            "its could take out a character")
        if cr == 0 and r["xp_each"] == 0:
            warnings.append(f"{r['title']} is worth 0 XP: use CR 0 creatures sparingly, or a swarm instead")
    if len(rows) > 3:
        warnings.append(f"{len(rows)} different stat blocks: more than two or three can be hard to run")
    left = {d: b[d] - total for d in DIFFICULTIES}
    return {"party": levels, "budget": b, "total_xp": total, "rating": rating, "creatures": rows,
            "creature_count": count, "remaining": left, "warnings": warnings, "lair": lair,
            "source": tables.cite("xp_budget")}


def pool(ix, filters=None, habitat=None, group=None, max_cr=None):
    filters = dict(filters or {})
    try:
        t, clean = query.prepare(ix, "creature", filters)
    except query.QueryError as x:
        raise EncounterError(str(x)) from None
    out = []
    for e in query.select(ix, t, clean):
        cr = core.cr_value(e.data.get("cr"))
        if cr is None or not e.data.get("xp"):
            continue
        if max_cr is not None and cr > max_cr:
            continue
        if habitat and not any(habitat.lower() in h.lower() for h in e.data.get("habitat") or []):
            continue
        if group and not any(group.lower() in g.lower() for g in e.data.get("group") or []):
            continue
        out.append(e)
    return out


def suggest(levels, difficulty="moderate", filters=None, habitat=None, group=None, n=5, seed=None,
            allow_strong=False, ix=None):
    """Encounters that spend 60-100% of the budget for `difficulty`: a solo creature, a group of one
    kind, or a leader with others of its group, habitat or type. Deterministic for a given seed."""
    ix = ix or data.load()
    if difficulty not in DIFFICULTIES:
        raise EncounterError(f"difficulty is one of {', '.join(DIFFICULTIES)}, not '{difficulty}'")
    b = budget(levels)[difficulty]
    floor = b * 0.6 if difficulty == "low" else max(b * 0.6, budget(levels)[DIFFICULTIES[DIFFICULTIES.index(difficulty) - 1]] + 1)
    cap = None if allow_strong else max(levels)
    mons = pool(ix, filters, habitat, group, cap)
    if not mons:
        raise EncounterError("no creatures match those filters")
    rng = random.Random(seed)
    pcs = len(levels)
    ideas, seen = [], set()

    def add(parts):
        key = tuple(sorted((e.sid, k) for e, k in parts))
        if key in seen:
            return
        xp = sum(e.data["xp"] * k for e, k in parts)
        if floor <= xp <= b:
            seen.add(key)
            ideas.append(parts)

    def kin(leader):
        g, h, ty = (set(leader.data.get(k) or []) for k in ("group", "habitat", "tags"))
        same_group = [m for m in mons if m is not leader and g & set(m.data.get("group") or [])]
        if same_group:
            return same_group
        return [m for m in mons if m is not leader and (h & set(m.data.get("habitat") or []))
                and m.data.get("type") == leader.data.get("type")] or \
               [m for m in mons if m is not leader and h & set(m.data.get("habitat") or [])]

    order = list(mons)
    rng.shuffle(order)
    tries = 0
    shapes = ["group", "leader", "solo"]
    while len(ideas) < n and tries < 400:
        shape = shapes[tries % 3]
        tries += 1
        e = rng.choice(order)
        x = e.data["xp"]
        if shape == "solo":
            solos = [m for m in order if floor <= m.data["xp"] <= b]
            if solos:
                add([(rng.choice(solos), 1)])
        elif shape == "group":
            k = int(b // x)
            k = min(k, 2 * pcs)
            if k >= 2:
                add([(e, k)])
        else:
            if not 0.3 * b <= x <= 0.7 * b:
                continue
            others = [m for m in kin(e) if m.data["xp"] <= (b - x)]
            if not others:
                continue
            m = rng.choice(others)
            k = min(int((b - x) // m.data["xp"]), 2 * pcs - 1)
            if k >= 1:
                add([(e, 1), (m, k)])
    return [evaluate(levels, parts) for parts in ideas]
