"""Filters and selectors shared by `list` and `make` (stdlib only).

    query.select(ix, "spell", {"class": "wizard", "level": "0-3", "ritual": True})

Filter ops (declared per type in types.TYPES):
  eq        case-insensitive; a unique prefix of a known value also works (--school evoc)
  in        the field is a list; same matching as eq
  range     N or N-M (integers)
  cr        a challenge rating or a range of them: 5, 1/4, 10-12, 0-1/2 (unrated creatures never match)
  flag      no value; the field is truthy
  contains  case-insensitive substring
Every type also takes --book (phb, dmg, mm, efa, frhof, au, rhw: the book short name).
"""
import difflib
import re
from fractions import Fraction

from .text import fold
from .types import ALIAS, BOOK_FILTER, TYPES, has_data, resolve_type


class QueryError(ValueError):
    """A bad type, filter or value. `hints` are shown as `did you mean` / valid values."""

    def __init__(self, msg, hints=(), label="did you mean"):
        super().__init__(msg)
        self.hints, self.label = list(hints), label


def type_or_error(name):
    t = resolve_type(name)
    if not t:
        raise QueryError(f"unknown type '{name}'", difflib.get_close_matches((name or "").lower(), ALIAS, 4, 0.6)
                         or ["`./occult types` lists them"])
    return t


def filters_of(t):
    return {**TYPES[t].get("filters", {}), "book": BOOK_FILTER}


def listed_filters(t, ix=None):
    """The filters named in `types` and in hints: --book only when several books are loaded."""
    if ix is None:
        from .data import load          # data imports types, not query; keep the import local
        ix = load()
    fs = filters_of(t)
    return fs if len(ix.books) > 1 else {k: v for k, v in fs.items() if k != "book"}


def known_values(ix, t, name):
    f = filters_of(t)[name]
    if f is BOOK_FILTER:                # every loaded book, even one without this type
        return [b["short"] for b in ix.books]
    vals = set()
    for e in ix.all(t):
        v = f.get(e)
        for x in v if isinstance(v, list) else [v]:
            if x not in (None, ""):
                vals.add(str(x))
    return sorted(vals, key=str.lower)


def normalize(ix, t, name, value):
    """Check and canonicalise one filter value; raises QueryError listing valid values."""
    f = filters_of(t)[name]
    if f.op == "flag":
        return True
    if value is None or value == "":
        raise QueryError(f"--{name} needs a value ({f.metavar})")
    if f.op == "range":
        lo, sep, hi = str(value).partition("-")
        if not lo.strip().isdigit() or (sep and not hi.strip().isdigit()):
            raise QueryError(f"--{name} takes N or N-M (e.g. --{name} 3 or --{name} 0-3), not '{value}'")
        return f"{int(lo)}-{int(hi)}" if sep else str(int(lo))
    if f.op == "cr":
        lo, sep, hi = str(value).partition("-")
        if cr_value(lo) is None or (sep and cr_value(hi) is None):
            raise QueryError(f"--{name} takes a CR or CR-CR (e.g. --{name} 5, --{name} 1/4, --{name} 10-12), not '{value}'")
        return f"{lo.strip()}-{hi.strip()}" if sep else lo.strip()
    if f.op == "contains":
        return value
    vals = known_values(ix, t, name)
    low = _key(value)
    exact = [v for v in vals if _key(v) == low]
    pref = exact or [v for v in vals if _key(v).startswith(low)]
    if len(pref) == 1:
        return pref[0]
    hints = pref if len(pref) > 1 else vals
    msg = f"--{name} '{value}' is ambiguous" if len(pref) > 1 else f"no {t} has --{name} '{value}'"
    raise QueryError(msg, hints[:40], "valid values")


def _key(v):
    """A filter value as compared: accents, case, and spaces/hyphens/underscores folded (`very-rare` = `Very Rare`)."""
    return " ".join(re.split(r"[\s_-]+", fold(v))).strip()


def cr_value(s):
    """`1/4` -> Fraction(1, 4), `10` -> 10; None for anything else (`None`, `-`, a summon's formula)."""
    try:
        return Fraction(str(s).strip())
    except (ValueError, ZeroDivisionError):
        return None


def match(e, f, value):
    x = f.get(e)
    if f.op == "flag":
        return bool(x)
    if f.op == "cr":
        lo, _, hi = value.partition("-")
        v = cr_value(x) if x is not None else None
        return v is not None and cr_value(lo) <= v <= cr_value(hi or lo)
    if f.op == "range":
        lo, _, hi = value.partition("-")
        return isinstance(x, int) and int(lo) <= x <= int(hi or lo)
    if f.op == "contains":
        return fold(value) in fold(x or "")
    vals = x if isinstance(x, list) else [x]
    return any(_key(v) == _key(value) for v in vals if v is not None)


def prepare(ix, t, filters=None):
    """Validate a selection: (registry type, {filter: canonical value}); raises QueryError."""
    t = type_or_error(t)
    fs = filters_of(t)
    clean = {}
    for name, value in (filters or {}).items():
        if name not in fs:
            shown = listed_filters(t, ix)
            close = difflib.get_close_matches(name, shown, 3, 0.5)
            raise QueryError(f"'{t}' has no filter --{name}",
                             ["--" + x for x in close + [x for x in shown if x not in close]]
                             or [f"none; `list {t}` takes no filters (try `find <text> --type {t}`)"],
                             "did you mean" if close else "valid filters")
        clean[name] = normalize(ix, t, name, value)
    return t, clean


def select(ix, t, filters=None):
    """Entities of type `t` matching all `filters` ({name: value}), in the type's list order."""
    t, clean = prepare(ix, t, filters)
    fs = filters_of(t)
    out = [e for e in ix.all(t) if all(match(e, fs[n], v) for n, v in clean.items())]
    if not all(has_data(e) for e in out):        # a sort on data needs the data (not converted yet)
        return sorted(out, key=lambda e: e.order)
    return sorted(out, key=TYPES[t].get("sort", lambda e: e.title.lower()))


def describe(t, clean):
    """`spell --class Wizard --level 3`: echoes the selection in footers."""
    bits = [t]
    for n, v in clean.items():
        bits.append(f"--{n}" if v is True else f"--{n} {v if ' ' not in str(v) else repr(v)}")
    return " ".join(bits)


def selection(ix, terms, filters=None):
    """A `make` selector: each term is a type (filters apply to every type term that has them),
    an id, or `@file` (ids, one per line; `#` comments). Returns [Entity] in selector order,
    without repeats. Raises QueryError (bad type, filter or value) or data.NotFound (bad id).
    """
    from .data import NotFound          # data imports types, not query; keep the import local
    out, filters = [], dict(filters or {})
    types = [resolve_type(t) for t in terms if not t.startswith("@") and resolve_type(t)]
    for name in filters:
        if not any(name in filters_of(t) for t in types):
            raise QueryError(f"no type in the selector has a filter --{name}",
                             sorted({f"--{x}" for t in types for x in listed_filters(t, ix)})
                             or ["filters need a type: make cards spells --class wizard"], "valid filters")
    for term in terms:
        if term.startswith("@"):
            try:
                with open(term[1:], encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            except OSError as x:
                raise QueryError(f"cannot read {term[1:]}: {x.strerror}") from None
            ents = [ix.get(ln.split()[0]) for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
        elif resolve_type(term):
            t = resolve_type(term)
            ents = select(ix, t, {k: v for k, v in filters.items() if k in filters_of(t)})
        else:
            lk = ix.resolve(term)
            if not lk:
                raise NotFound(term, lk)
            ents = [lk.entity]
        out += [e for e in ents if e not in out]
    return out
