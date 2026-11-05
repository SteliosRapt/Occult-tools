"""Helpers shared by the card view models (stdlib only)."""
import re

from .. import data, text

UPCAST = {"Using a Higher-Level Spell Slot": "At Higher Levels", "Cantrip Upgrade": "Cantrip Upgrade"}


def caster_classes(ix):
    """Titles of the classes with a class-level spell list (data.spellcasting), A-Z: Artificer, Bard, ..."""
    return sorted(e.title for e in ix.all("class") if e.data.get("spellcasting"))


def page_ref(e):
    """A page cell: omit the first loaded book's name, qualify other books."""
    if e.primary:
        return e.page if e.page is not None else data.book_abbr(e.book)
    return f"{data.book_abbr(e.book)} {e.page}" if e.page is not None else data.book_abbr(e.book)


def book_titles(ix, ents):
    """The titles of the books the entities come from, in load order."""
    used = {e.book for e in ents}
    return [b["title"] for b in ix.books if b["short"] in used]


def html(s, scan=True):
    """Stored inline markup -> HTML; scan aids (bold dice and saving throws) on by default."""
    return text.inline(s, "html", scan_aids=scan)


def body_blocks(content):
    """JSON content blocks -> simple render blocks (p, upcast, ul, table, sub).

    Captions (art labels) and sidebars are not printed on cards.
    """
    out = []
    for b in content:
        t = b["type"]
        if t == "paragraph":
            lab = b.get("label")
            if lab in UPCAST:
                out.append({"kind": "upcast", "label": UPCAST[lab], "html": html(b["text"])})
            else:
                out.append({"kind": "p", "label": lab, "html": html(b["text"])})
        elif t == "heading":
            out.append({"kind": "sub", "html": html(b.get("text", ""), False)})
        elif t == "list":
            out.append({"kind": "ul", "ordered": b.get("ordered"),
                        "items": [{"label": i.get("label"), "html": html(i.get("text", ""))} for i in b["items"]]})
        elif t == "table":
            out.append({"kind": "table", "title": b.get("title"), "columns": b["columns"],
                        "rows": [[html(str(c), False) for c in r] for r in b["rows"]]})
    return out


NUMERIC = re.compile(r"^(?:[—–-]|[+−-]?[\d,./]+(?:\s*(?:lb\.|oz\.|GP|SP|CP|EP|PP|ft\.|feet|mph|miles?)(?:\s*\(.*\))?)?"
                     r"|\d*d\d+(?:\s*[+−-]\s*\d+)?(?:\s+\w+)?|\d+(?:st|nd|rd|th)|×\d+|\d+×L\d|Varies|Free)$")
GROUP = re.compile(r"^\*([^*]+)\*$")


def book_table(b):
    """A JSON table block -> {title, cols: [{html, num}], rows: [{group} | {cells: [{html, num}]}]}.

    A column is numeric (centred, `.num`) when every non-empty cell looks like a number, cost,
    weight or dice. A row whose first cell is all italic and whose other cells are empty is a
    category row (`*Simple Melee Weapons*`).
    """
    cols, rows = b["columns"], [[("" if c is None else str(c)) for c in r] for r in b["rows"]]
    groups = [bool(GROUP.match(r[0])) and not any(c.strip() for c in r[1:]) for r in rows]
    body = [r for r, g in zip(rows, groups) if not g]
    num = [i > 0 and bool(body) and all(NUMERIC.match(text.inline(r[i], "plain").strip()) for r in body
                                        if i < len(r) and r[i].strip()) for i in range(len(cols))]
    out = []
    for r, g in zip(rows, groups):
        if g:
            out.append({"group": html(GROUP.match(r[0]).group(1), False), "span": len(cols)})
        else:
            out.append({"cells": [{"html": html(c, False), "num": num[i] if i < len(num) else False}
                                  for i, c in enumerate(r)]})
    return {"title": b.get("title"), "cols": [{"html": html(str(c), False), "num": n} for c, n in zip(cols, num)],
            "rows": out}


def paragraphs(e):
    """The plain paragraphs of an entity's content, joined with spaces."""
    return " ".join(b["text"] for b in e.content if b["type"] == "paragraph")


def short_units(s):
    """`30 feet` -> `30 ft.`, `10 minutes` -> `10 min`, for the stat fields."""
    s = re.sub(r"\b(\d+)[- ]feet\b", r"\1 ft.", s)
    s = re.sub(r"\b(\d+)[- ]foot\b", r"\1-ft.", s)
    s = re.sub(r"\b(\d+) miles?\b", r"\1 mi.", s)
    s = re.sub(r" minutes?\b", " min", s, flags=re.I)
    s = re.sub(r" hours?\b", " hr", s, flags=re.I)
    return s


def slug(s):
    """`Very Rare` -> `very-rare` (CSS classes and back keys)."""
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")


def key(e):
    """A card's run key (continuation cards share it); unique within a deck."""
    return e.sid
