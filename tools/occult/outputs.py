"""Output catalogue: name -> how to select, view, template and lay out (stdlib only).

Adding an output means adding one Output row here plus its template; `pipeline.run` does the rest.
"""
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import components, query, views
from .types import TYPES
from .views import books
from .views._common import slug

PLURAL = {"armor": "armor"}            # filename and report nouns; default: the type's first alias


def noun(t, n=2):
    if n == 1:
        return t
    return PLURAL.get(t) or next((a for a in TYPES[t].get("aliases", []) if a.endswith("s")), t + "s")


def selector_stem(terms, filters, sid=None):
    """Deterministic file stem: `spells-class-wizard-level-3`, `conditions-actions`, `spell-shield`
    (one id keeps its type, so spell:shield and armor:shield differ), `picks` (a file of ids: its
    name) or `picks-<hash>` (a list of ids). `sid` maps an id term to its canonical short id."""
    from .types import resolve_type
    bits, ids = [], []
    for t in terms:
        if t.startswith("@"):
            bits.append(slug(Path(t[1:]).stem))
        elif resolve_type(t):
            bits.append(noun(resolve_type(t)))
        else:
            ids.append(sid(t) if sid else t)
    if ids:
        bits.append(slug(ids[0]) if len(ids) == 1 and not bits else
                    "picks-" + hashlib.sha1(" ".join(ids).encode()).hexdigest()[:8])
    for k, v in filters.items():
        bits += [k] if v is True else [k, slug(v)]
    return "-".join(slug(b) for b in bits if b) or "cards"


CARD_TYPES = ["spells", "weapons", "armor", "conditions", "actions", "terms", "creatures", "feats", "options",
              "magic-items", *components.values("card_types")]


def select_cards(ix, terms, filters):
    ents = query.selection(ix, terms, filters)
    bad = [e for e in ents if not views.supports(e)]
    if bad:
        kinds = ", ".join(sorted({e.type for e in bad}))
        raise query.QueryError(f"no card template for {kinds} ({', '.join(e.sid for e in bad[:3])}"
                               f"{', …' if len(bad) > 3 else ''})",
                               CARD_TYPES, "card types")
    return ents




@dataclass
class Output:
    name: str
    layout: str                        # cards | book | md | site
    template: Optional[str]            # under templates/ (md: templates/md/, chosen by collections.py)
    usage: str                         # for `make --list`
    summary: str
    help: str                          # `make <name> --help`, after the usage line
    runner: str                        # the pipeline function that builds it
    flags: dict = field(default_factory=dict)   # {flag: bool | "METAVAR" | (choices...)}
    selector: bool = False             # takes a selector (types, ids, @file) plus type filters
    priority: str = "P0"
    select: Callable = select_cards    # (ix, terms, filters) -> [Entity]
    group: Optional[Callable] = None   # books: (ix, **variant) -> the template context (views/books.py)
    variant: Optional[str] = None      # books: the flag that picks one book per value (`--class`; `all` = each)


CARD_FLAGS = {"mode": ("color", "bw"), "paper": ("a4", "letter"), "theme": "NAME", "png": True,
              "check-fit": True, "html": True, "backs": ("none", "category")}
BOOK_FLAGS = {"mode": ("color", "white", "bw"), "paper": ("a4", "letter"), "theme": "NAME", "png": True, "html": True,
              "compact": True}


class Choices:
    """Flag choices read from the loaded data when first needed (`--class`: every class, or the casters),
    plus fixed extras (`all`). Iterates like the tuple of choices make.py and pipeline.py expect."""

    def __init__(self, fn, extra=("all",)):
        self.fn, self.extra = fn, tuple(extra)

    def values(self):
        return tuple(self.fn()) + self.extra

    def __iter__(self):
        return iter(self.values())

    def __len__(self):
        return len(self.values())

    def __contains__(self, x):
        return x in self.values()


def classes():
    """Every loaded class, by slug ."""
    from . import data
    return tuple(sorted(e.slug for e in data.load().all("class")))


def casters():
    """The classes with a class-level spell list (data.spellcasting): the spellbook variants."""
    from . import data
    return tuple(sorted(e.slug for e in data.load().all("class") if e.data.get("spellcasting")))


BOOK_COMMON = """  --mode bw        ink-saver (default color); white: every colour on a white page, no parchment
  --paper letter   US Letter (default a4)
  --compact        smaller type (body 8.7pt instead of 9.6pt) to fit fewer pages; files gain .compact
  --theme NAME     a folder in style/themes/ (default grimoire)
  --png            also write one PNG per page (needs pdftoppm)
  --html           also print the built HTML path (dist/.build/)"""

CATALOGUE = {o.name: o for o in [
    Output("cards", "cards", "cards/deck.html.j2", "<selector>", "Card sheets, 67×96 3×3 on A4; tarot 2×2",
           """Card sheets in dist/cards/: 3×3 on A4 with crop marks (tarot: 70×120, 2×2).
A selector is types, ids or @file (one id per line), with the same filters as `list`.
Long text continues on the next card; `./occult types` lists the available types.
  --mode bw        ink-saver (default color)
  --paper letter   US Letter, 63×88 cards (default a4)
  --theme NAME     a folder in style/themes/ (default grimoire)
  --png            also write one PNG per sheet
  --check-fit      render without a PDF; exit 1 if a card is clipped
  --html           print the built HTML path
  --backs category mirrored duplex back sheets
Exit 1 if a card is clipped at the 6pt floor.""",
           "cards", CARD_FLAGS, selector=True),
    Output("md", "md", None, "[--check]", "Committed .md collections in collections/ (no render)",
           """Write the committed Markdown collections (collections/: spells by class and level, equipment,
classes, feats, rules, magic items ...) from every book in data/ through templates/md/. Deterministic: a second run
changes nothing. Line 1 of each file holds a hash of all inputs.
  --check     write nothing; list stale/missing/extra files and exit 1 if any differ
  --out DIR   another target directory (default collections/)
The pre-commit hook runs --check: enable it once with `git config core.hooksPath .githooks`.""",
           "md", {"check": True, "out": "DIR"}),
    Output("spellbook", "book", "book/spellbook.html.j2", "--class C|all", "Spellbook PDF per caster class (A4 or Letter, 2 columns)",
           f"""A spellbook in dist/books/: the class spell list (cantrip to level 9), then every description
by level, A-Z within a level. `--class all` writes one per caster class.
  --class C        a class with a spell list (`./occult list classes`), or all
  --level N        only the spells the class casts at class level N (1-20): dist/books/spellbook-C-lN.pdf
  --list-only      the spell list alone, no descriptions (files gain .list)
{BOOK_COMMON}
e.g. ./occult make spellbook --class wizard --mode bw · ./occult make spellbook --class warlock --level 5""",
           "book", {"class": Choices(casters), "level": "N", "list-only": True, **BOOK_FLAGS}, group=books.spellbook,
           variant="class"),
    Output("equipment", "book", "book/equipment.html.j2", "[--mode bw]", "Equipment catalogue PDF: cost and weight",
           f"""The equipment catalogue in dist/books/: coins, weapons (with properties and masteries), armor,
tools and adventuring gear with cost and weight, then mounts, vehicles and services as printed.
{BOOK_COMMON}""",
           "book", dict(BOOK_FLAGS), group=books.equipment),
    Output("quickref", "book", "book/quickref.html.j2", "[--mode bw]", "Conditions & actions quick reference (2 pages)",
           f"""A two-page quick reference in dist/books/: the 15 conditions and the areas of effect, then the
12 actions and cover, three columns each.
{BOOK_COMMON}""",
           "book", dict(BOOK_FLAGS), group=books.quickref),
    Output("class", "book", "book/class.html.j2", "--class C|all", "Class booklet PDF: traits, progression, features",
           f"""A class booklet in dist/books/: core traits, the 20-level progression, the class features by
level, option menus and the spell list as printed, then the subclasses. `--class all` writes one per class.
  --class C        any class (`./occult list classes`), or all
  --level N        a booklet to class level N (1-20): features, options and subclass features to N, the
                   subclass art together on one page, then the spells the class casts by then in full
                   (dist/books/class-C-lN.pdf)
  --subclass S     only that subclass of the class (`./occult list subclasses --class C`), any book:
                   its features, no class chapters (dist/books/class-C-S.pdf)
  --class-features N  with --subclass: the class features to level N (and those progression rows)
                   first (dist/books/class-C-S-cfN.pdf)
  --add ID,ID      backgrounds, species and feats in full at the end, under Character Options
                   (`--add background:acolyte,species:elf`; stem gains -plus)
{BOOK_COMMON}
e.g. ./occult make class --class warlock · ./occult make class --class warlock --level 5
     ./occult make class --class warlock --subclass fiend-patron --class-features 3""",
           "book", {"class": Choices(classes), "level": "N", "subclass": "S", "class-features": "N", "add": "ID,ID", **BOOK_FLAGS}, priority="P1", group=books.booklet, variant="class"),
    Output("glossary", "book", "book/glossary.html.j2", "[--mode bw]", "Rules glossary PDF: every term A-Z",
           f"""The rules glossary in dist/books/: the conventions, then all 154 terms A-Z with their tags and
See also lines, two columns.
{BOOK_COMMON}""",
           "book", dict(BOOK_FLAGS), priority="P1", group=books.glossary),
    Output("pwa", "site", None, "[--out DIR]", "Spell Explorer: offline web app (PWA) of every spell",
           """The Spell Explorer in dist/pwa/: a static, installable web app of every spell in data/, with
filters by class, level, school, ritual/concentration and book, sorting by level or A-Z, and full-text
search; each entry prints as in the spellbooks. Works offline once opened (service worker). Serve the
folder from any static host (Netlify: it includes _headers), or locally: python3 -m http.server -d dist/pwa
  --out DIR   another target directory (default dist/pwa/)""",
           "pwa", {"out": "DIR"}, priority="P1"),
]}

components.apply("register_outputs", CATALOGUE)
