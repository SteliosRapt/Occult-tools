"""NPCs, settlements and taverns from the books' tables (DMG p84-86, p93, p110; PHB p40; MM lore tables).

    generate.npc(rng)                              # name, appearance, personality, secret, attitude, trinket
    generate.npc(rng, creature=priest)             # + the creature's stat block, alignment, its lore tables
    generate.settlement(rng, size="town")          # trait, fame, calamity, leader, taverns, shops
    generate.tavern(rng, level=5)                  # name, keeper, patrons, a hook and a rumour

Every entry is a roll on a table found in data/ (rolltables). The book leaves some choices to the DM,
decided here:

- *Name*: 1d6 picks the name table, as the DMG suggests, then the given name and the surname are rolled
  separately on that table (`names=` fixes the table).
- *Personality*: the DMG asks for a trait from the NPC's highest and lowest ability scores, using the PHB's
  ability tables. With a creature its scores decide (ties: the first in STR..CHA order); without one, two
  different abilities are picked at random.
- *Settlement*: a size not given is picked from the Settlements by Size rows. Taverns and shops scale with
  the row: 1 tavern and 2 shops for the first row (village), 2 and 4 for the next, 3 and 6 for a city.
- *Tavern*: the keeper is a full NPC, the patrons short ones (name, appearance, attitude); the hook is
  rolled on one of the DMG's three hook tables, the rumour on the Adventure Situations table of the
  party's tier (only with a level).
"""
import random
import re

from .. import data
from . import rolltables, tables

ABILITY_ORDER = ("str", "dex", "con", "int", "wis", "cha")


def _t(title):
    return rolltables.find(title)


def _roll(title, rng):
    return rolltables.roll(_t(title), rng)


def name_tables():
    return [t for t in rolltables.under("section:name") if t.title.endswith("Names")]


def name(rng, names=None):
    ts = name_tables()
    if not ts:
        raise tables.TableMissing("NPC name table is not in this data set")
    if names:
        key = data.slugify(names)
        hit = [t for t in ts if key in data.slugify(t.title)]
        if not hit:
            styles = ", ".join(re.sub(r"^\d+: | Names$", "", t.title).lower() for t in ts)
            raise ValueError(f"unknown name style '{names}'; one of {styles}")
        t = hit[0]
    else:
        t = ts[rng.randint(1, len(ts)) - 1]
    given, surname = rolltables.roll(t, rng).cells[0], rolltables.roll(t, rng).cells[1]
    return {"name": f"{given} {surname}", "style": re.sub(r"^\d+: | Names$", "", t.title).lower(), "table": t.id}


def personality_tables():
    """{'str': Table, ...}: the PHB's High/Low ability tables."""
    out = {}
    for t in rolltables.under("section:describe-appearance-and-personality"):
        try:
            out[tables.ability(t.title)] = t
        except ValueError:
            pass
    return out


def personality(rng, scores=None):
    ts = personality_tables()
    if scores:
        hi = max(ABILITY_ORDER, key=lambda a: (scores[a], -ABILITY_ORDER.index(a)))
        lo = min(ABILITY_ORDER, key=lambda a: (scores[a], ABILITY_ORDER.index(a)))
    else:
        hi, lo = rng.sample(list(ABILITY_ORDER), 2)
    return {"high": {"ability": hi, "trait": rolltables.roll(ts[hi], rng).cells[0]},
            "low": {"ability": lo, "trait": rolltables.roll(ts[lo], rng).cells[1]}}


def _scores(e):
    ab = e.data.get("abilities") or {}
    try:
        return {tables.ability(k): int(v["score"] if isinstance(v, dict) else v) for k, v in ab.items()}
    except (ValueError, KeyError, TypeError):
        return None


def lore_tables(e):
    """The roll tables printed with a creature: in its own entry and in the section it belongs to (MM)."""
    owners = [e] + ([e.parent] if e.parent is not None and e.parent.type == "section" else [])
    return [t for t in rolltables.all_tables() if any(t.entity is o for o in owners)]


def npc(rng=None, names=None, creature=None, short=False):
    rng = rng or random.Random()
    out = name(rng, names)
    out["appearance"] = _roll("NPC Appearance", rng).text
    out["attitude"] = _roll("Initial Attitude", rng).text
    if short:
        return out
    scores = _scores(creature) if creature is not None else None
    out["personality"] = personality(rng, scores if scores and len(scores) == 6 else None)
    out["secret"] = _roll("NPC Secrets", rng).text
    out["trinket"] = _roll("Trinkets", rng).text
    if creature is not None:
        out["creature"] = {"title": creature.title, "id": creature.sid, "cr": creature.data.get("cr"),
                           "alignment": creature.data.get("alignment")}
        out["lore"] = [{"table": t.title, "id": t.id, "result": rolltables.roll(t, rng).text}
                       for t in lore_tables(creature)]
    return out


# ---------------------------------------------------------------- settlements and taverns

def sizes():
    """[(name, population, max GP value)] from Settlements by Size (DMG p93)."""
    t = tables.table("settlement_sizes")
    return [tuple(rolltables.plain(c) for c in r[:3]) for r in t["rows"]]


def tavern_name(rng):
    t = _t("Tavern Names")
    first, second = rolltables.roll(t, rng).cells[0], rolltables.roll(t, rng).cells[1]
    return f"{first} {second}"


def settlement(rng=None, size=None):
    rng = rng or random.Random()
    rows = sizes()
    if size:
        hit = [i for i, r in enumerate(rows) if r[0].lower().startswith(size.lower())]
        if not hit:
            raise ValueError(f"unknown settlement size '{size}'; one of {', '.join(r[0].lower() for r in rows)}")
        i = hit[0]
    else:
        i = rng.randrange(len(rows))
    kind, pop, max_gp = rows[i]
    shops = []
    while len(shops) < 2 * (i + 1):
        s = _roll("Random Shops", rng).text
        if s not in shops:
            shops.append(s)
    return {"size": kind, "population": pop, "max_gp_value": max_gp,
            "trait": _roll("Defining Traits", rng).text, "fame": _roll("Claims to Fame", rng).text,
            "calamity": _roll("Current Calamities", rng).text, "leader": _roll("Local Leaders", rng).text,
            "taverns": [tavern_name(rng) for _ in range(i + 1)], "shops": shops,
            "source": tables.cite("settlement_sizes")}


HOOKS = ("Patron Hooks", "Supernatural Hooks", "Happenstance Hooks")


def situation_table(level):
    for t in rolltables.all_tables():
        m = re.fullmatch(r"Levels (\d+)–(\d+) Adventure Situations", t.title)
        if m and int(m.group(1)) <= level <= int(m.group(2)):
            return t
    raise ValueError(f"no Adventure Situations table for level {level}")


def tavern(rng=None, level=None, patrons=2, names=None):
    rng = rng or random.Random()
    hook_t = _t(HOOKS[rng.randrange(len(HOOKS))])
    out = {"name": tavern_name(rng), "keeper": npc(rng, names),
           "patrons": [npc(rng, names, short=True) for _ in range(patrons)],
           "hook": {"table": hook_t.title, "text": rolltables.roll(hook_t, rng).text}}
    if level:
        t = situation_table(int(level))
        out["rumour"] = {"table": t.title, "text": rolltables.roll(t, rng).text}
    return out
