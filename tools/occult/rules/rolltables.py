"""Roll on any die table printed in the books (stdlib only).

A table is rollable when its first column is a die (`1d20`, `d10`, `1d12*`, `1d100 (13-Card Deck)`) and every
row's first cell is a number or a range (`7`, `01–02`, `98–00`; `00` is 100). Nothing is copied into code: the
tables are found in data/ each time, so the generators (`loot`, `npc`, `settlement`, `tavern`) and
`./occult table` roll exactly what the books print.

    rolltables.all_tables()                     # every rollable table, in book order
    rolltables.find("Tavern Names")             # by title, table id or entity id (when it holds one table)
    rolltables.roll(t, rng)                     # Result(n=14, row=[...], text="Canals and bridges")

A table's id is `<entity id>#<slug of its title>` (`section:settlement-tables-and-tracker#tavern-names`), or
the entity id alone for an untitled table (`magic-item:bag-of-beans`).
"""
import functools
import re
from dataclasses import dataclass

from .. import data, text

DIE = re.compile(r"^\s*(\d*)d(\d+)", re.I)
RANGE = re.compile(r"(\d+)(?:\s*[–-]\s*(\d+))?")


@dataclass
class Table:
    id: str
    title: str
    entity: object
    columns: list
    rows: list          # [(lo, hi, row)]
    count: int          # dice rolled: 1d20 -> 1
    sides: int

    @property
    def die(self):
        return f"{self.count}d{self.sides}"

    def cite(self):
        e = self.entity
        return f"{data.book_abbr(e.book)} p{e.page}" if e.page else data.book_abbr(e.book)

    def lookup(self, n):
        for lo, hi, row in self.rows:
            if lo <= n <= hi:
                return row
        return None


@dataclass
class Result:
    table: Table
    n: int
    row: list

    @property
    def cells(self):
        return [plain(c) for c in self.row[1:]]

    @property
    def text(self):
        """One cell: its text. Several: `Column: value` pairs (`Golem: Clay · Time: 30 days`)."""
        cs = self.cells
        if len(cs) == 1:
            return cs[0]
        return " · ".join(f"{plain(h)}: {c}" for h, c in zip(self.table.columns[1:], cs))


def plain(s):
    return text.inline(str(s), "plain").strip()


def _range(cell, sides):
    s = plain(cell).rstrip("*").strip()
    m = RANGE.fullmatch(s)
    if not m:
        return None
    to_n = lambda x: 100 if x == "00" and sides == 100 else int(x)
    lo = to_n(m.group(1))
    hi = to_n(m.group(2)) if m.group(2) else lo
    return lo, hi


def parse(block, entity, tid):
    """A table block -> Table, or None when it isn't a die table."""
    cols = block.get("columns") or []
    m = DIE.match(plain(cols[0])) if cols else None
    if not m or not block.get("rows"):
        return None
    count, sides = int(m.group(1) or 1), int(m.group(2))
    rows = []
    for r in block["rows"]:
        if plain(r[0]) in ("—", "-", ""):
            continue
        rng = _range(r[0], sides)
        if not rng:
            return None
        rows.append((*rng, r))
    if not rows:
        return None
    return Table(tid, block.get("title") or entity.title, entity, cols, rows, count, sides)


def _blocks(e):
    for b in e.content:
        if b.get("type") == "table":
            yield b
        elif b.get("type") == "sidebar":
            yield from (x for x in b.get("content", []) if isinstance(x, dict) and x.get("type") == "table")


@functools.lru_cache(maxsize=None)
def _all(ix_id):
    ix = data.load()
    out, used = [], set()
    for e in ix.entities:
        if not e.sid:
            continue
        for b in _blocks(e):
            base = f"{e.sid}#{data.slugify(b['title'])}" if b.get("title") else e.sid
            tid, k = base, 1
            while tid in used:          # two untitled (or same-titled) tables in one entity
                k += 1
                tid = f"{base}{'-' if '#' in base else '#'}{k}"
            used.add(tid)
            t = parse(b, e, tid)
            if t:
                out.append(t)
    return out


def all_tables(ix=None):
    return _all(id(ix or data.load()))


def find(ref, ix=None):
    """A table by id (`section:x#tavern-names`), entity id (one table), or title (`Tavern Names`).

    Several titles match: the DMG's first, then the PHB's, then the rest in book order."""
    ts = all_tables(ix)
    key = ref.strip()
    for t in ts:
        if t.id == key.lower():
            return t
    low = key.lower()
    hits = [t for t in ts if t.title.lower() == low]
    if not hits:
        ix = ix or data.load()
        lk = ix.resolve(key)
        if lk:
            hits = [t for t in ts if t.entity is lk.entity]
            if len(hits) > 1:
                raise LookupError(f"{lk.entity.sid} has {len(hits)} tables; name one: "
                                  + ", ".join(t.id for t in hits))
    if not hits:
        hits = [t for t in ts if low in t.title.lower()]
        if len(hits) == 1:
            return hits[0]
        sug = ", ".join(f"'{t.title}'" for t in hits[:8])
        raise LookupError(f"no table '{ref}'" + (f"; did you mean: {sug}" if sug else
                                                 "; `./occult table --list` lists them"))
    order = {"dmg": 0, "phb": 1}
    return min(hits, key=lambda t: order.get(t.entity.book, 2))


def under(sid, ix=None):
    """The rollable tables in an entity and its subtree, in order."""
    ix = ix or data.load()
    e = ix.resolve(sid).entity
    if e is None:
        return []
    ents = set()
    stack = [e]
    while stack:
        x = stack.pop()
        ents.add(id(x))
        stack += x.children
    return [t for t in all_tables(ix) if id(t.entity) in ents]


def roll(t, rng, n=None):
    """Roll the table's die (or use n); a gap in the table rolls again."""
    for _ in range(100):
        v = n if n is not None else sum(rng.randint(1, t.sides) for _ in range(t.count))
        row = t.lookup(v)
        if row is not None or n is not None:
            return Result(t, v, row)
    raise ValueError(f"table {t.id} has no row for its rolls")
