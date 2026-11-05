"""The rules tables, read from the books (stdlib only).

Every number the engine looks up comes from a table printed in data/, found by the section that holds it
and the table's title. Nothing is copied into code, so a re-import that changes a table changes the
engine, and a table that moves or disappears fails loudly (`TableMissing`) instead of going stale.

    tables.xp_budget()          # {level: {"low": 50, "moderate": 75, "high": 100}}
    tables.multiclass_slots()   # {caster level: {spell level: slots}}
    tables.advancement()        # {level: (xp, proficiency bonus)}
    tables.cr_xp()              # {"1/4": 50, ...}
    tables.cr_pb()              # [(lo, hi, pb)] by challenge rating
    tables.point_costs()        # {8: 0, ..., 15: 9}
    tables.standard_array()     # {"barbarian": {"str": 15, ...}}
    tables.carrying()           # {"Small/Medium": (15, 30), ...}: carry, drag x Str
"""
import functools
import re
from fractions import Fraction

from .. import components, data, text

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
ABILITY_NAMES = {"str": "Strength", "dex": "Dexterity", "con": "Constitution",
                 "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma"}

# (section id, table title): where each table is printed. `cite()` turns these into page references.
SOURCES = {
    "xp_budget": ("section:combat-encounter-difficulty", "XP Budget per Character"),
    "multiclass_slots": ("section:multiclass-spellcaster-spell-slots-per-spell-level",
                         "Multiclass Spellcaster: Spell Slots per Spell Level"),
    "advancement": ("section:level-advancement", "Character Advancement"),
    "cr_xp": ("section:challenge-rating", "Experience Points by Challenge Rating"),
    "cr_pb": ("section:proficiency-bonus", "Proficiency Bonus by Challenge Rating"),
    "point_costs": ("section:generate-your-scores", "Ability Score Point Costs"),
    "standard_array": ("section:assign-ability-scores", "Standard Array by Class"),
    "carrying": ("term:carrying-capacity", "Carrying Capacity"),
}

components.apply("register_sources", SOURCES)


class TableMissing(LookupError):
    pass


def ability(name):
    """`Strength`, `str`, `STR` -> `str`; ValueError for anything else."""
    k = str(name).strip().lower()[:3]
    if k not in ABILITIES:
        raise ValueError(f"unknown ability '{name}'")
    return k


def num(s):
    """`1,100` -> 1100, `+3` -> 3, `—` -> 0."""
    s = text.inline(str(s), "plain").strip().replace(",", "").replace("−", "-")
    return 0 if s in ("—", "-", "") else int(s)


def find_table(sid, title, ix=None):
    ix = ix or data.load()
    def walk(ent):
        for b in ent.content:
            for t in ([b] if b.get("type") == "table" else
                      [x for x in b.get("content", []) if x.get("type") == "table"] if b.get("type") == "sidebar" else []):
                if t.get("title") == title:
                    return t
        for c in ent.children:
            hit = walk(c)
            if hit:
                return hit
        return None
    # Prefer the named section, but a table can move to another section or book.
    e = ix.resolve(sid).entity
    t = walk(e) if e else None
    if t:
        return t
    for root in ix.roots:
        t = walk(root)
        if t:
            return t
    raise TableMissing(f"table {title} is not in this data set")


def table(name, ix=None):
    return find_table(*SOURCES[name], ix=ix)


def cite(name, ix=None):
    """`DMG p114`: where a table is printed."""
    ix = ix or data.load()
    title = SOURCES[name][1]
    target = table(name, ix)
    e = next((e for e in ix.entities if target in e.content or any(
        target in b.get("content", []) for b in e.content)), None)
    if e is None:
        raise TableMissing(f"table {title} is not in this data set")
    return f"{data.book_abbr(e.book)} p{e.page}" if e.page else data.book_abbr(e.book)


@functools.lru_cache(maxsize=None)
def xp_budget():
    t = table("xp_budget")
    cols = [c.lower() for c in t["columns"][1:]]
    return {num(r[0]): {c: num(v) for c, v in zip(cols, r[1:])} for r in t["rows"]}


@functools.lru_cache(maxsize=None)
def multiclass_slots():
    t = table("multiclass_slots")
    lv = [int(c) for c in t["columns"][1:]]
    return {num(r[0]): {l: num(v) for l, v in zip(lv, r[1:]) if num(v)} for r in t["rows"]}


@functools.lru_cache(maxsize=None)
def advancement():
    return {num(r[0]): (num(r[1]), num(r[2])) for r in table("advancement")["rows"]}


def cr_key(cr):
    """A CR as the table prints it: 0.25 / Fraction(1, 4) / '1/4' -> '1/4'; 5 -> '5'."""
    f = Fraction(str(cr).strip())
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


@functools.lru_cache(maxsize=None)
def cr_xp():
    """CR 0 prints `0 or 10`: the table's first number (a creature's own XP is in its stat block)."""
    return {cr_key(r[0]): num(re.match(r"[\d,]+", r[1]).group()) for r in table("cr_xp")["rows"]}


@functools.lru_cache(maxsize=None)
def cr_pb():
    out = []
    for r in table("cr_pb")["rows"]:
        lo, _, hi = r[0].replace("–", "-").partition("-")
        out.append((int(lo), int(hi or lo), num(r[1])))
    return out


@functools.lru_cache(maxsize=None)
def point_costs():
    return {num(r[0]): num(r[1]) for r in table("point_costs")["rows"]}


@functools.lru_cache(maxsize=None)
def standard_array():
    t = table("standard_array")
    out = {}
    for r in t["rows"]:
        cls = data.slugify(text.inline(r[0], "plain"))
        out[cls] = {a: num(v) for a, v in zip(ABILITIES, r[1:])}
    return out


@functools.lru_cache(maxsize=None)
def carrying():
    """Size -> (carry, drag/lift/push) multipliers of the Strength score."""
    mult = lambda s: float(re.search(r"[\d.]+", s.replace("Str.", "")).group())
    return {r[0]: (mult(r[1]), mult(r[2])) for r in table("carrying")["rows"]}
