"""Treasure by the DMG 2024 tables (DMG p120, p213-215, p218, p326-331).

    loot.individual("3", count=6, rng=rng)        # Random Individual Treasure: roll once, times the group
    loot.hoard("7", theme="arcana", rng=rng)        # Random Treasure Hoard + its magic items
    loot.magic_items(3, level=5, rng=rng)              # rarity by level, then any book's item of that rarity
    loot.for_creatures([(dragon, 1)], rng=rng)      # by the creatures' Treasure entries (MM)

Every number comes from a table in data/ (`tables.SOURCES` and the theme, gem and art tables found by
title), so nothing here is a copy of the book. What the book leaves to the DM is a decision, kept here:

- *Monetary form by theme* (the Treasure Themes table names the forms, not the split): Arcana is paid
  in gemstones, Relics in art objects, Armaments half in coins and half in trade bars, Implements a third
  each in coins, trade bars and trade goods; no theme ("Any") is coins. Pieces are bought greedily, the
  largest tier worth at most half the share first; what no piece fits stays in coins.
- *Item rarity* rolls on the Magic Item Rarities table in the party-level column; without a level, the
  column in the same place as the hoard's CR row (CR 0–4 → levels 1–4 ...: the bands are the same).
- *Item pool*: the DMG's Arcana / Armaments / Implements / Relics tables (DMG p326) list only DMG items, so
  without a theme an item of the rolled rarity is drawn from every book in data/, each entry equally likely (an
  entry counts for a rarity when it or one of its variants has it; a variant of that rarity is then picked).
  `weighted` keeps that roll but sends a DMG entry's result to the DMG tables (1d4 for the table, then d100), so
  the other books' items keep their chance and the DMG's share is spread as its tables spread it (Potion of
  Healing, on many rows, comes up more than a one-row item).
  With a theme (`--theme`, or a creature's MM Treasure) the item rolls on its table; with `dmg_tables` and no
  theme, on a table picked by 1d4 per item (DMG p326). A choice in the row (`Ioun Stone
  (awareness or ...)`) is picked at random; a spell level (`Spell Scroll (level 2 or 3 spell)`) is picked,
  then a spell of that level from every book in data/, of a school the item allows (Enspelled Armor and
  Weapons name theirs).
- *Creatures*: a group's hoard belongs to its leader (DMG p120), so `for_creatures` rolls one hoard for
  the highest-CR creature whose Treasure is Any or a theme, and Individual Treasure for each creature
  marked Individual (one roll times the number of them).
"""
import random
import re
from fractions import Fraction

from .. import data, text
from . import dice, rolltables, tables

AMOUNT = re.compile(r"(?P<dice>\d+d\d+(?:\s*[+-]\s*\d+)?)\s*(?:×\s*(?P<mult>[\d,]+))?\s*\((?P<avg>[\d,]+)\)\s*(?P<unit>[A-Z]{2})")
RARITIES = ("common", "uncommon", "rare", "very rare", "legendary")


class LootError(ValueError):
    pass


# ---------------------------------------------------------------- the tables

def _cr_rows(t):
    """[(lo, hi, row)] from a CR column: `0–4`, `17+`."""
    out = []
    for r in t["rows"]:
        s = text.inline(r[0], "plain").replace("–", "-").strip()
        if s.endswith("+"):
            lo, hi = int(s[:-1]), 99
        else:
            a, _, b = s.partition("-")
            lo, hi = int(a), int(b or a)
        out.append((lo, hi, r))
    return out


def _band(t, cr):
    v = float(Fraction(tables.cr_key(cr)))
    rows = _cr_rows(t)
    for i, (lo, hi, r) in enumerate(rows):
        if lo <= v < hi + 1:
            return i, r
    raise LootError(f"no row for CR {cr}")


def amount(cell):
    """`2d8 × 10 (90) GP` -> {"dice": "2d8", "mult": 10, "avg": 90, "unit": "GP"}."""
    m = AMOUNT.search(text.inline(cell, "plain"))
    if not m:
        raise tables.TableMissing(f"can't read treasure amount {cell!r}")
    return {"dice": m["dice"].replace(" ", ""), "mult": int((m["mult"] or "1").replace(",", "")),
            "avg": int(m["avg"].replace(",", "")), "unit": m["unit"]}


def themes():
    """['arcana', 'armaments', 'implements', 'relics'], from the Treasure Themes table (DMG p213)."""
    return [data.slugify(text.inline(r[0], "plain")) for r in tables.table("treasure_themes")["rows"]]


def theme_table(theme, rarity):
    sid = f"section:{theme}-tables"
    title = f"{theme.title()} - {rarity.title()}"
    t = rolltables.find(f"{sid}#{data.slugify(title)}")
    if t.title != title:
        raise tables.TableMissing(f"table '{title}' not found under {sid}")
    return t


def _tiers(sid, word):
    """{value: Table} of the `10 GP Gemstones` / `25 GP Art Objects` tables."""
    out = {}
    for t in rolltables.under(sid):
        m = re.fullmatch(rf"([\d,]+) GP {word}", t.title)
        if m:
            out[int(m.group(1).replace(",", ""))] = t
    if not out:
        raise tables.TableMissing(f"no '<value> GP {word}' tables under {sid}")
    return dict(sorted(out.items()))


def gem_tables():
    return _tiers("section:gemstones", "Gemstones")


def art_tables():
    return _tiers("section:art-objects", "Art Objects")


def trade_items(section):
    """The items a Trade Bars / Trade Goods section lists, with their GP value."""
    ix = data.load()
    return [(c, c.data["cost_gp"]) for c in ix.get(section).children if c.data.get("cost_gp")]


def cite(e):
    return f"{data.book_abbr(e.book)} p{e.page}" if e.page else data.book_abbr(e.book)


# ---------------------------------------------------------------- rolling

def _roll(expr, rng, avg=False):
    return int(dice.average(expr)) if avg else dice.roll(expr, rng).total


def _money(spec, rng, avg=False):
    if avg:
        return spec["avg"], f"average {spec['avg']:,}"
    r = dice.roll(spec["dice"], rng)
    return r.total * spec["mult"], f"{spec['dice']} = {r.total}" + (f" × {spec['mult']:,}" if spec["mult"] > 1 else "")


def individual(cr, count=1, rng=None, avg=False):
    """Random Individual Treasure (DMG p120): one roll for a creature of this CR, times `count`."""
    rng = rng or random.Random()
    t = tables.table("individual_treasure")
    _, row = _band(t, cr)
    spec = amount(row[1])
    v, how = _money(spec, rng, avg)
    return {"kind": "individual", "cr": tables.cr_key(cr), "count": count, "unit": spec["unit"],
            "each": v, "total": v * count, "roll": how, "source": tables.cite("individual_treasure")}


def hoard(cr, theme=None, level=None, rng=None, avg=False, double=False, details=False, dmg_tables=False,
          weighted=False):
    """Random Treasure Hoard (DMG p120) for a creature of this CR: money in the theme's forms, magic items."""
    rng = rng or random.Random()
    theme = _theme(theme)
    t = tables.table("treasure_hoard")
    band, row = _band(t, cr)
    spec = amount(row[1])
    total, rolls, n_items, item_rolls = 0, [], 0, []
    for _ in range(2 if double else 1):
        v, how = _money(spec, rng, avg)
        total += v
        rolls.append(how)
        expr = text.inline(row[2], "plain").strip().replace(" ", "")
        k = max(0, _roll(expr, rng, avg)) if expr not in ("—", "") else 0
        n_items += k
        item_rolls.append(f"{expr} = {k}")
    if level is None:
        level_col = band
    else:
        level_col = _level_col(level)
    items = magic_items(n_items, level_col=level_col, theme=theme, rng=rng, details=details, dmg_tables=dmg_tables,
                        weighted=weighted)
    money = split(total, theme, rng)
    return {"kind": "hoard", "cr": tables.cr_key(cr), "theme": theme, "level": level, "unit": spec["unit"],
            "total": total, "roll": "; ".join(rolls), "items_roll": "; ".join(item_rolls), "double": double,
            "money": money, "items": items, "source": tables.cite("treasure_hoard")}


def _theme(theme):
    if theme in (None, "", "any"):
        return None
    t = data.slugify(theme)
    for x in themes():
        if x.startswith(t):
            return x
    raise LootError(f"unknown treasure theme '{theme}'; one of {', '.join(themes())} or any")


def _level_col(level):
    t = tables.table("item_rarity")
    for i, c in enumerate(t["columns"][:-1]):
        m = re.search(r"(\d+)\D+(\d+)", text.inline(c, "plain"))
        if m and int(m.group(1)) <= int(level) <= int(m.group(2)):
            return i
    raise LootError(f"no Magic Item Rarities column for level {level}")


def rarity(level_col, rng):
    """Roll 1d100 on the Magic Item Rarities table (DMG p218) in one level column."""
    t = tables.table("item_rarity")
    n = rng.randint(1, 100)
    for r in t["rows"]:
        cell = text.inline(r[level_col], "plain").strip()
        rg = rolltables._range(cell, 100)
        if rg and rg[0] <= n <= rg[1]:
            return text.inline(r[-1], "plain").strip().lower(), n
    raise tables.TableMissing(f"Magic Item Rarities: no row for {n}")


def magic_items(n, level=None, level_col=None, theme=None, rarity_=None, rng=None, details=False, dmg_tables=False,
                weighted=False):
    """n random magic items: rarity by level (or fixed), then an item of every book (or the theme's DMG table)."""
    rng = rng or random.Random()
    ix = data.load()
    if level_col is None and rarity_ is None:
        level_col = _level_col(level if level is not None else 1)
    ths = themes()
    th = _theme(theme)
    out = []
    for _ in range(n):
        rar, rar_roll = (rarity_, None) if rarity_ else rarity(level_col, rng)
        pool, k, pool_roll = None, None, None
        if not (th or dmg_tables):
            pool = item_pool(rar)
            k = rng.randint(1, len(pool))
            if weighted and pool[k - 1][0].book == "dmg":
                pool_roll = f"All books - {rar.title()}, d{len(pool)} {k}"
        if pool is None or pool_roll:
            t = theme_table(th or ths[rng.randint(1, len(ths)) - 1], rar)
            res = rolltables.roll(t, rng)
            cell = res.row[1]
            nid = next((nid for _, nid in text.links(cell)), None)
            item = _item(ix, rolltables.plain(cell), ix.by_id.get(nid) if nid else None, rng)
            item.update(theme=t.title.split(" - ")[0].lower(), table=t.title, roll=res.n)
            if pool_roll:
                item["pool_roll"] = pool_roll
        else:
            e, variants = pool[k - 1]
            name = variants[rng.randrange(len(variants))]["title"] if variants else e.title
            item = _item(ix, name, e, rng)
            item.update(theme=None, table=f"All books - {rar.title()}", roll=k, pool=len(pool))
        item.update(rarity=rar, rarity_roll=rar_roll)
        if details:
            item["details"] = {t.title.replace("Magic Item's ", ""): rolltables.roll(t, rng).text for t in special_tables()}
        out.append(item)
    return out


def item_pool(rar):
    """[(entry, its variants of this rarity)]: every book's magic items of a rarity, in id order."""
    out = []
    for e in sorted(data.load().all("magic-item"), key=lambda e: e.sid):
        vs = [v for v in e.data.get("variants") or [] if str(v.get("rarity", "")).lower() == rar]
        if vs or str(e.data.get("rarity", "")).lower() == rar:
            out.append((e, vs))
    if not out:
        raise LootError(f"no {rar} magic items")
    return out


def _item(ix, name, e, rng):
    """{title, id, page, spell?} for an item name (a table row or a variant), its choice or spell level picked."""
    base, choice, spell = name, None, None
    m = re.fullmatch(r"(.+?)\s*\((.+)\)", name)
    if m:
        base, opts = m.group(1), m.group(2)
        opts = re.sub(r"\s+spell$", "", opts)
        parts = [p.strip() for p in re.split(r",\s*(?:or\s+)?|\s+or\s+", opts) if p.strip()]
        levels = [_spell_level(p) for p in parts]
        if all(lv is not None for lv in levels):
            lv = levels[rng.randrange(len(levels))]
            spell = _spell(ix, lv, rng, e)
            choice = "cantrip" if lv == 0 else f"level {lv}"
        else:
            choice = parts[rng.randrange(len(parts))]
    item = {"title": base + (f" ({choice})" if choice else ""), "id": e.sid if e else None,
            "page": cite(e) if e else None}
    if spell:
        item["spell"] = {"title": spell.title, "id": spell.sid}
    return item


def _spell_level(s):
    s = s.strip().lower()
    if s == "cantrip":
        return 0
    m = re.fullmatch(r"(?:level\s+)?(\d)", s)
    return int(m.group(1)) if m else None


def schools(item):
    """The schools an item's text allows its spell (`must belong to the Abjuration or Illusion school`), or None."""
    m = re.search(r"must belong to the (.+?) schools? of magic", text.entity_text(item) if item else "")
    return {x.lower() for x in re.split(r",\s*(?:or\s+)?|\s+or\s+", m.group(1))} if m else None


def _spell(ix, level, rng, item=None):
    allowed = schools(item)
    pool = sorted((e for e in ix.all("spell") if e.data.get("level") == level
                   and (allowed is None or str(e.data.get("school", "")).lower() in allowed)), key=lambda e: e.sid)
    return pool[rng.randrange(len(pool))] if pool else None


def special_tables():
    """Magic Item's Creator or Intended User, History, Minor Property, Quirk (DMG p222)."""
    return [t for t in rolltables.under("section:magic-item-special-features") if t.title.startswith("Magic Item's")]


# ---------------------------------------------------------------- money in the theme's forms

def split(total, theme, rng):
    """{coins: n, gems: [...], art: [...], bars: [...], goods: [...]} worth `total` GP."""
    out = {"coins": 0, "gems": [], "art": [], "bars": [], "goods": []}
    shares = {None: [("coins", 1)], "arcana": [("gems", 1)], "relics": [("art", 1)],
              "armaments": [("coins", 2), ("bars", 2)],
              "implements": [("coins", 3), ("bars", 3), ("goods", 3)]}[theme]
    left = total
    for i, (form, div) in enumerate(shares):
        share = left if i == len(shares) - 1 else total // div
        if form == "coins":
            out["coins"] += share
            left -= share
            continue
        spent, pieces = _buy(form, share, rng)
        out[form] = pieces
        out["coins"] += share - spent
        left -= share
    return out


def _buy(form, value, rng):
    """Spend `value` GP on pieces of one form: greedy by tier, each piece rolled on its table."""
    if form in ("gems", "art"):
        tiers = gem_tables() if form == "gems" else art_tables()
        spent, got = 0, {}
        for v in sorted(tiers, reverse=True):
            if v > max(value // 2, min(tiers)) or value - spent < v:
                continue
            n = (value - spent) // v
            for _ in range(n):
                name = rolltables.roll(tiers[v], rng).cells[0]
                got[(name, v)] = got.get((name, v), 0) + 1
            spent += n * v
        ix = data.load()
        pieces = [{"title": name, "value": v, "count": c, "id": _treasure_id(ix, name)}
                  for (name, v), c in sorted(got.items(), key=lambda x: (-x[0][1], x[0][0]))]
        return spent, pieces
    section = "section:trade-bars" if form == "bars" else "section:trade-goods"
    items = sorted(trade_items(section), key=lambda x: -x[1])
    if form == "goods":         # one kind of goods, worth at least 1 GP and no more than a tenth of the share
        fit = [x for x in items if 1 <= x[1] <= max(1, value // 10)]
        items = [fit[rng.randrange(len(fit))]] if fit else []
    spent, pieces = 0, []
    for e, v in items:
        n = int((value - spent) // v)
        if n:
            pieces.append({"title": e.title, "value": int(v), "count": n, "id": e.sid})
            spent += n * int(v)
    return spent, pieces


def _treasure_id(ix, name):
    """`Azurite (mottled deep blue)` -> item:azurite."""
    base = re.sub(r"\s*\(.*\)$", "", name).strip()
    for e in ix.by_title.get(base.lower(), []):
        if e.data.get("kind") == "treasure":
            return e.sid
    return None


# ---------------------------------------------------------------- creatures

def treasure_of(e):
    """A creature's Treasure entry (MM): ['Any'] / ['Individual'] / ['Arcana', ...] / []."""
    return [str(x) for x in e.data.get("treasure") or []]


def for_creatures(monsters, rng=None, level=None, avg=False, details=False, dmg_tables=False, weighted=False):
    """Treasure for an encounter: one hoard for its leader, Individual Treasure for the rest (see top)."""
    rng = rng or random.Random()
    out = {"kind": "creatures", "individual": [], "hoard": None, "none": []}
    keepers = []
    for e, n in monsters:
        tr = [t.lower() for t in treasure_of(e)]
        if "individual" in tr:
            out["individual"].append(dict(individual(e.data.get("cr") or 0, n, rng, avg), title=e.title, id=e.sid))
        hoard_kinds = [t for t in tr if t != "individual"]
        if hoard_kinds:
            keepers.append((Fraction(tables.cr_key(e.data.get("cr") or 0)), e, hoard_kinds))
        if not tr:
            out["none"].append({"title": e.title, "id": e.sid})
    if keepers:
        _, e, kinds = max(keepers, key=lambda x: x[0])
        th = next((k for k in kinds if k != "any"), None)
        h = hoard(e.data.get("cr") or 0, th, level, rng, avg, details=details, dmg_tables=dmg_tables,
                  weighted=weighted)
        h.update(keeper={"title": e.title, "id": e.sid, "treasure": treasure_of(e)})
        out["hoard"] = h
    return out


def total_gp(loot):
    """Every coin and piece of a result in GP (PP count 10 GP)."""
    rate = {"GP": 1, "PP": 10}
    if loot["kind"] == "individual":
        return loot["total"] * rate.get(loot["unit"], 1)
    if loot["kind"] == "hoard":
        m = loot["money"]
        return m["coins"] + sum(p["value"] * p["count"] for f in ("gems", "art", "bars", "goods") for p in m[f])
    return sum(total_gp(x) for x in loot["individual"]) + (total_gp(loot["hoard"]) if loot["hoard"] else 0)
