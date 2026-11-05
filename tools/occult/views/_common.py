"""Helpers shared by the card view models (stdlib only)."""
import re

from .. import data, text

UPCAST = {"Using a Higher-Level Spell Slot": "At Higher Levels", "Cantrip Upgrade": "Cantrip Upgrade"}


def caster_classes(ix):
    """Titles of the classes with a class-level spell list (data.spellcasting), A-Z: Artificer, Bard, ..."""
    return sorted(e.title for e in ix.all("class") if e.data.get("spellcasting"))


def page_ref(e):
    """A page cell for tables that mix books: `274` for the PHB, `EFA 21` (or `DMG`) for another book."""
    if e.book == "phb":
        return e.page if e.page is not None else data.book_abbr(e.book)
    return f"{data.book_abbr(e.book)} {e.page}" if e.page is not None else data.book_abbr(e.book)


def book_titles(ix, ents):
    """The titles of the books the entities come from, in load order (PHB first)."""
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


ART_MODES = ("auto", "on", "off")


def art(refs, roles=("art",), box=None):
    """The first image of `refs` (node `images`) with one of `roles` (in role order) whose file is
    in img/, as a card art model {src (file URI), path, rel, role, width, height, ratio (h/w), title,
    credit}, or None; plus whether the data refers to such an image at all (a missing local copy is
    reported with a hint to run `./occult fetch images`). A missing file never raises. `box` (w, h in
    mm, the largest the image prints) makes `src` the print copy for that box (images.derived)."""
    from .. import images
    cands = [i for r in roles for i in refs or [] if i.get("role") == r and i.get("path")]
    if not cands:
        return None, False
    ref, p = next(((i, images.local_path(i["path"])) for i in cands if images.local_path(i["path"])), (None, None))
    if p is None:
        return None, True
    src, size = images.derived(p, box) if box else (p, None)
    w, h = size or (ref.get("width") or 1, ref.get("height") or 1)   # the copy's: trimmed cut-outs change shape
    return {"src": src.resolve().as_uri(), "path": str(p), "rel": ref["path"], "role": ref["role"],
            "width": w, "height": h, "ratio": round(h / w, 4), "title": ref.get("title"),
            "credit": ref.get("credit")}, True


# Weapon and armour art is laid out by its shape, at no less than PRINT_PPI (a print never
# enlarges a small file past that). A long weapon (a sword lying flat, or a spear stood upright,
# turned to lie flat with its head to the right) runs as a strip across the card under the
# header; anything squarer sits beside the damage / AC, and a tall piece (a handaxe, plate armour,
# a shield; armour always stays upright) stands in a column beside both the hero and the stats.
PRINT_PPI = 200
MM_PER_PX = 25.4 / PRINT_PPI
BAND_MM, BAND_HI_MM = 58, 15          # strip: the card's text width; tallest strip
BAND_R = 0.4                          # a strip from h/w 0.4 down (or, turned, from 2.5 up)
SIDE_HI_MM, SIDE_W_MM = 34, 30        # beside the hero: tallest, widest
TALL_R, TALL_LO_MM, TALL_HI_MM, TALL_W_MM = 1.4, 21, 32, 20   # a column beside hero and stats


def item_art(m, kind):
    """Add the layout of a weapon / armour card's art model (m["art"]): `layout` band | side | tall,
    `rot` (turn 90 degrees clockwise), `ratio` (h/w as shown) and `style` (the CSS custom properties
    that size the panel and let fit.js grow it no further than PRINT_PPI allows)."""
    a = m.get("art")
    if not a:
        return m
    w, h = a["width"], a["height"]
    rot = kind == "weapon" and h / w >= 1 / BAND_R
    if rot:
        w, h = h, w
    r = h / w
    if kind == "weapon" and r <= BAND_R:
        wmm = min(BAND_MM, w * MM_PER_PX)
        hi = min(BAND_HI_MM, h * MM_PER_PX, wmm * r)
        style = f"--art-wmm: {wmm:.1f}mm; --art-lo: 0mm; --art-hi: {hi:.1f}mm; --art-min: 22"
        layout = "band"
    elif r >= TALL_R:
        # a column at least as tall as the hero and stats beside it (about TALL_LO_MM, so fit.js
        # shrinking it further would free no text room); its width follows the image
        hi = min(TALL_HI_MM, h * MM_PER_PX, TALL_W_MM * r)
        style = f"--art-hi: {hi:.1f}mm; --art-lo: {min(hi, TALL_LO_MM):.1f}mm; --art-min: {TALL_LO_MM / 25.4 * 96:.0f}"
        layout = "tall"
    else:
        hi = min(SIDE_HI_MM, h * MM_PER_PX, SIDE_W_MM * r)
        style = f"--art-hi: {hi:.1f}mm; --art-lo: {min(hi, 16):.1f}mm"
        layout = "side"
    grow_px = hi / 25.4 * 96                       # fit.js grows a panel no taller than this
    a.update(layout=layout, rot=rot, ratio=round(r, 4),
             style=f"{style}; --art-grow: {grow_px:.0f}")
    return m


def with_art(m, refs, mode="auto", roles=("art",), box=None):
    """Set m["art"] (a model or None) and m["art_wanted"] from image refs; mode `off` sets neither."""
    m["art"], m["art_wanted"] = (None, False) if mode == "off" else art(refs, roles, box)
    return m
