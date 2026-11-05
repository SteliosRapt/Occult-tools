"""Loader and Index for every book in data/ (stdlib only): data/phb-2024 first, then the others (LOAD_ORDER).

    ix = data.load()                 # cached per process
    e = ix.get("spell:fireball")     # full id, short id, alias:slug, bare slug, exact title or variant title
    e.id, e.sid, e.type, e.title, e.page, e.book, e.data, e.content, e.children, e.parent, e.owner_class
    e.classes                        # a spell's classes: data.classes plus class spell lists (derived)
    ix.all("spell")                  # registry type, virtual types too (condition, action)
    ix.refs(e)                       # entities e links to, then italic names in e's text resolved to entities

The loader never repairs data: fixes go into the JSON (see data/<book>/CHANGES.md).
"""
import difflib
import json
import os
import re
from collections import defaultdict
from pathlib import Path

from . import text
from .types import TYPES, rank, resolve_type, type_name

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get("OCCULT_DATA", ROOT / "data"))
# Book load order (see book_dirs): the PHB, then the books in the order they were added.
LOAD_ORDER = ["phb-2024", "dmg-2024", "efa-2025", "mm-2025", "frhof-2025", "au-2026", "rhw-2026"]

# Owners used to disambiguate repeated slugs, nearest first.
OWNER_TYPES = ("subclass", "class", "species", "feature")
# Types never used to resolve cross-references (headings, not things).
NOT_REFS = ("section", "chapter")


def slugify(s):
    """`'` and `’` dropped, accents folded (`Faerûn` -> `faerun`), other runs of non-alphanumerics -> `-`."""
    return re.sub(r"[^a-z0-9]+", "-", text.fold(s).replace("'", "").replace("’", "")).strip("-")


def book_short(book_id):
    """`dmg-2024` -> `dmg`: the book's name in short ids and `--book`."""
    return book_id.split("-", 1)[0]


BOOK_ABBR = {"frhof": "FRHoF"}


def book_abbr(short):
    """`phb` -> `PHB`, `frhof` -> `FRHoF`: a book's printed abbreviation (labels, `show` headers)."""
    return BOOK_ABBR.get(short, short.upper())


def _words(title):
    return frozenset(re.findall(r"[a-z0-9']+", title.lower()))


class Entity:
    __slots__ = ("id", "sid", "type", "node_type", "title", "page", "book", "data", "content", "children", "parent",
                 "owner_class", "owner_subclass", "classes", "order", "_blob", "images")

    def __init__(self, node, parent, order, book):
        self.id = node["id"]
        self.book = book
        self.sid = None
        self.node_type = node["type"]
        self.type = type_name(node["type"])
        self.title = node["title"]
        self.page = node.get("page")
        self.data = node.get("data") or {}
        self.content = node.get("content") or []
        self.images = node.get("images") or []          # art refs (img/ paths), e.g. magic items
        self.classes = list(self.data.get("classes") or []) if self.type == "spell" else None
        self.children = []
        self.parent = parent
        self.order = order
        self._blob = None
        anc = list(self.ancestors())
        cls = next((a for a in anc if a.type == "class"), None)
        self.owner_class = (self.title if self.type == "class" else cls.title if cls else None)
        self.owner_class = self.owner_class.lower() if self.owner_class else None
        self.owner_subclass = next((a for a in anc if a.type == "subclass"), None)

    @property
    def slug(self):
        return self.id.rsplit("/", 1)[-1]

    def ancestors(self):
        p = self.parent
        while p:
            yield p
            p = p.parent

    def chapter(self):
        *_, top = [self, *self.ancestors()]
        return top

    def blob(self):
        """Lower-cased full text (content and data) for text search."""
        if self._blob is None:
            self._blob = text.fold(self.title + "\n" + text.inline(text.entity_text(self), to="plain"))
        return self._blob

    def as_json(self, full=True):
        d = {"sid": self.sid, "type": self.type, "title": self.title, "page": self.page}
        if self.book != "phb":
            d["book"] = self.book
        d["data"] = {k: v for k, v in self.data.items() if not k.startswith("_")}
        if full:
            d.update(id=self.id, parent=self.parent.sid if self.parent else None, content=self.content,
                     children=[c.sid for c in self.children])
            if self.images:
                d["images"] = self.images
        return d

    def __repr__(self):
        return f"<{self.sid}>"


class Lookup:
    """Result of Index.resolve: an entity, or candidates (ambiguous) or suggestions (not found)."""

    def __init__(self, entity=None, candidates=(), ambiguous=False):
        self.entity, self.candidates, self.ambiguous = entity, list(candidates), ambiguous

    def __bool__(self):
        return self.entity is not None


class NotFound(LookupError):
    def __init__(self, ref, lookup):
        self.ref, self.lookup = ref, lookup
        kind = "ambiguous" if lookup.ambiguous else "not found"
        super().__init__(f"{ref!r} {kind}: {', '.join(e.sid for e in lookup.candidates)}")


def book_dirs(root):
    """Book folders under a data root (or the root itself when it is one book), in LOAD_ORDER, then by id.

    The order decides short ids on a slug collision (an earlier book keeps the plain `type:slug`),
    so the books that came first keep theirs as new ones are added.
    """
    root = Path(root)
    if (root / "book.json").is_file():
        return [root]
    dirs = [f.parent for f in root.glob("*/book.json")]
    rank = lambda d: LOAD_ORDER.index(d.name) if d.name in LOAD_ORDER else len(LOAD_ORDER)
    return sorted(dirs, key=lambda d: (rank(d), d.name))


class Index:
    def __init__(self, root=DATA_ROOT):
        self.root = Path(root)
        self.entities, self.roots, self.books, self.problems = [], [], [], []
        self.by_id, self.by_sid = {}, {}
        self.by_title = defaultdict(list)
        for d in book_dirs(self.root):
            meta = json.loads((d / "book.json").read_text(encoding="utf-8"))
            book = dict({k: v for k, v in meta.items() if k != "contents"}, short=book_short(meta["id"]))
            self.books.append(book)
            # the chapter files book.json lists (images.json and corrections.json are not chapters)
            for f in [d / c["file"] for c in meta["contents"]]:
                self.roots.append(self._walk(json.loads(f.read_text(encoding="utf-8")), None, book["short"]))
        self._cross_book_owners()
        for i, b in enumerate(self.books):
            self._assign_sids([e for e in self.entities if e.book == b["short"]], i != 0 or b["short"] != "phb")
        for e in self.entities:
            self.by_title[e.title.lower()].append(e)
        self.by_variant = defaultdict(list)    # slugified data.variants[].title and .record -> entries
        for e in self.entities:
            for v in e.data.get("variants") or []:
                # the printed title, and the dataset name when it differs (`record`: "+2 Weapon" for "Weapon, +2")
                for name in (v.get("title"), v.get("record")) if isinstance(v, dict) else ():
                    if name and e not in self.by_variant[slugify(name)]:
                        self.by_variant[slugify(name)].append(e)
        self._spell_lists()
        self._ref_titles = sorted(t for t, es in self.by_title.items() if any(e.type not in NOT_REFS for e in es))
        self._by_words = defaultdict(list)   # "Lantern, Bullseye" is cited as *Bullseye Lantern*
        for t in self._ref_titles:
            self._by_words[_words(t)] += self.by_title[t]
        self._ref_cache = {}

    # ------------------------------------------------------------ build
    def _walk(self, node, parent, book):
        e = Entity(node, parent, len(self.entities), book)
        assert e.id not in self.by_id, f"duplicate id {e.id}"
        self.by_id[e.id] = e
        self.entities.append(e)
        e.children = [self._walk(c, e, book) for c in node.get("children", [])]
        return e

    def _cross_book_owners(self):
        """A subclass printed in another book than its class (AU, FRHoF, RHW) names the class in `data.class`
        (node id; `data.class_name` as a fallback): it and its features get that owner class."""
        for e in self.entities:
            if e.owner_class is not None:
                continue
            s = e if e.type == "subclass" else e.owner_subclass
            if s is None:
                continue
            cls = self.by_id.get(s.data.get("class") or "")
            name = cls.title if cls is not None else s.data.get("class_name")
            e.owner_class = name.lower() if name else None

    def _assign_sids(self, ents, qualify):
        """`type:slug`, or `type:owner/slug` when the slug repeats within a type.

        A later book (`qualify`) treats a slug an earlier book has in the type as a repeat, and never
        takes a short id already given; when the owner is the chapter, it is book-qualified
        (`section:dmg/07/slug`, `chapter:dmg/07`). A later book's chapters are always book-qualified
        (`chapter:dmg/08`, though the PHB has no chapter 08).
        """
        taken = {(e.type, e.slug) for e in self.by_sid.values()}
        groups = defaultdict(list)
        for e in ents:
            groups[(e.type, e.slug)].append(e)
        for (t, slug), es in groups.items():
            if len(es) == 1 and (t, slug) not in taken and f"{t}:{slug}" not in self.by_sid and not (qualify and t == "chapter"):
                self._set(es[0], f"{t}:{slug}")
                continue
            def full_of(e):
                return f"{t}:{e.book}/{e.id.split('/', 1)[1]}" if qualify else f"{t}:{e.id.split('/', 1)[1]}"
            fulls = {full_of(e): e for e in es}
            for e in es:
                owner = next((a for a in e.ancestors() if a.type in OWNER_TYPES), None) or e.chapter()
                full = full_of(e)
                if not qualify:
                    sid = f"{t}:{owner.slug}/{slug}" if owner is not e else f"{t}:{slug}"
                elif owner.type == "chapter":
                    sid = f"{t}:{e.book}/{owner.slug}" + ("" if owner is e else f"/{slug}")
                else:
                    sid = f"{t}:{owner.slug}/{slug}"
                # an owner id that is another repeat's own full path is left to it (RHW genres-of-horror)
                taken_by_other = sid in self.by_sid or fulls.get(sid, e) is not e
                self._set(e, full if taken_by_other else sid)

    def _set(self, e, sid):
        assert sid not in self.by_sid, f"duplicate short id {sid}"
        e.sid = sid
        self.by_sid[sid] = e

    def _spell_lists(self):
        """A class's `data.spell_list` ({"0": [titles], ...}) adds the class to those spells' `classes`."""
        for c in self.entities:
            if c.type != "class" or not c.data.get("spell_list"):
                continue
            for lvl, titles in c.data["spell_list"].items():
                for title in titles:
                    es = [e for e in self.by_title.get(title.lower(), []) if e.type == "spell"]
                    if not es:
                        self.problems.append(f"{c.sid} spell_list[{lvl}]: no spell {title!r}")
                        continue
                    s = min(es, key=lambda e: self._book_rank(e, c))
                    if c.title not in s.classes:
                        s.classes = sorted(s.classes + [c.title])

    @staticmethod
    def _book_rank(e, src):
        """Same book as `src` first, then the PHB, then the rest."""
        return 0 if src is not None and e.book == src.book else 1 if e.book == "phb" else 2

    # ------------------------------------------------------------ access
    def all(self, t):
        """Entities of a registry type (or alias), in book order."""
        t = resolve_type(t) or t
        reg = TYPES[t]
        base = reg.get("base", t)
        out = [e for e in self.entities if e.node_type == base or e.type == base]
        if "where" in reg:
            k, v = reg["where"]
            out = [e for e in out if e.data.get(k) == v]
        return out

    def get(self, ref):
        lk = self.resolve(ref)
        if not lk:
            raise NotFound(ref, lk)
        return lk.entity

    def resolve(self, ref):
        """Exact id -> short id -> alias:slug -> bare slug or owner/slug, if unique -> exact title -> variant title.

        Not found: up to 8 suggestions (difflib, then substring). Several matches: all of them, ranked.
        """
        ref = ref.strip()
        if ref in self.by_id:
            return Lookup(self.by_id[ref])
        if ref.lower() in self.by_sid:
            return Lookup(self.by_sid[ref.lower()])
        t, sep, rest = ref.partition(":")
        t = resolve_type(t) if sep else None
        if not t:
            rest = ref
        pool = self.all(t) if t else self.entities
        base = TYPES[t].get("base", t) if t else None
        if base and f"{base}:{rest.lower()}" in self.by_sid and self.by_sid[f"{base}:{rest.lower()}"] in pool:
            return Lookup(self.by_sid[f"{base}:{rest.lower()}"])
        slug, low = slugify(rest), rest.lower()
        hits = [e for e in pool if e.slug == slug or e.sid.split(":", 1)[1] == low or e.title.lower() == low]
        if len(hits) == 1:
            return Lookup(hits[0])
        hits = hits or [e for e in self.by_variant.get(slug, []) if e in pool]
        if len(hits) == 1:
            return Lookup(hits[0])
        if hits:
            return Lookup(candidates=sorted(hits, key=lambda e: (rank(e), e.order)), ambiguous=True)
        return Lookup(candidates=self.suggest(rest, pool))

    def suggest(self, text_, pool=None, n=8):
        pool = pool or self.entities
        slug = slugify(text_)
        by_slug = defaultdict(list)
        for e in pool:
            by_slug[e.slug].append(e)
        near = difflib.get_close_matches(slug, list(by_slug), 4, 0.75)
        out = [e for k in near for e in sorted(by_slug[k], key=lambda e: (rank(e), e.order))]
        if len(out) < n and len(slug) >= 3:
            out += sorted((e for e in pool if slug in e.slug and e not in out), key=lambda e: (rank(e), len(e.slug)))
        return out[:n]

    # ------------------------------------------------------------ cross-references
    def ref_lookup(self, name, src=None):
        """An italic name (`*Arrows*`, `*Potions of Healing*`, `*+2 Weapon*`) -> one entity, or None.

        Tries the exact title, text.REF_ALIASES, singular forms, variant titles, then a close fuzzy
        match. Several hits: prefer one in the same chapter as `src`, then its book, then the PHB,
        then by type rank. Outside the PHB, a title (or singular, or variant) in src's own book beats an alias.
        """
        key = re.sub(r"\s+", " ", name.strip(" .,;:")).lower()
        chap = src.chapter() if src else None
        if (key, chap) in self._ref_cache:
            return self._ref_cache[(key, chap)]
        hit = None
        if src is not None and src.book != "phb":
            hit = next((e for k in [key, *text.singulars(key)] for e in self.by_title.get(k, []) + self.by_variant.get(slugify(k), [])
                        if e.book == src.book and e.type not in NOT_REFS), None)
        if not hit and key in text.REF_ALIASES:
            hit = self.by_sid.get(text.REF_ALIASES[key])
        best = lambda es: min(es, key=lambda e: (e.chapter() is not chap, self._book_rank(e, src), rank(e), e.order))
        for k in [key, *text.singulars(key)] if not hit else []:
            es = ([e for e in self.by_title.get(k, []) if e.type not in NOT_REFS] or self.by_variant.get(slugify(k), [])
                  or self._by_words.get(_words(k), []))
            es = [e for e in es if e.type not in NOT_REFS]
            if es:
                hit = best(es)
                break
        if not hit and len(key) >= 8:
            near = difflib.get_close_matches(key, self._ref_titles, 1, 0.9)
            if near:
                hit = best([e for e in self.by_title[near[0]] if e.type not in NOT_REFS])
        self._ref_cache[(key, chap)] = hit
        return hit

    def refs(self, e):
        """Distinct entities e's text links to, then those named in italics (excluding e), in order."""
        out = []
        body = text.entity_text(e)
        for _, nid in text.links(body):      # exact: the importer resolved these
            r = self.by_id.get(nid)
            if r is not None and r is not e and r not in out:
                out.append(r)
        for name in text.italic_names(body):
            r = self.ref_lookup(name, e)
            # a run listing several names: *Burning Hands, Faerie Fire, Scorching Ray*
            rs = [r] if r else [self.ref_lookup(x, e) for x in name.split(", ")] if ", " in name else []
            out += [r for r in rs if r is not None and r is not e and r not in out]
        return out


_INDEX = None


def load():
    """The Index of every book in data/, built once per process (~0.1 s for the PHB)."""
    global _INDEX
    if _INDEX is None:
        _INDEX = Index()
    return _INDEX
