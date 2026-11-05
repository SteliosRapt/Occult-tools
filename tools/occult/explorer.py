"""`make pwa`: the Spell Explorer, an offline web app of every spell (dist/pwa/, a static site).

    index.html            the app shell (templates/pwa/index.html.j2): filters, list, reader
    spells.json           one row per spell: fields to filter and sort by, the entry as book HTML,
                          and its plain text to search (app.js folds it once, keeping offsets)
    app.js, sw.js         templates/pwa/ (sw.js caches the whole site for offline use)
    manifest.webmanifest  install metadata; icons/ from style/icons/app/
    style/                the theme's explorer.css and the fonts it uses (style/fonts/)
    _headers              Netlify: revalidate the shell and the service worker on every visit

The entry HTML comes from the books' own `spell` and `statblock` macros (templates/book/_blocks.j2),
so the app prints a spell exactly as the spellbooks do. Deterministic: the same data writes the
same files, and the service worker's cache name is a hash of them.
"""
import hashlib
import json
import re
import shutil
from pathlib import Path

from . import text
from .data import book_abbr
from .views import books

ROOT = Path(__file__).resolve().parents[2]
STYLE = ROOT / "style"
TEMPLATES = ROOT / "templates"
OUT = ROOT / "dist" / "pwa"
ICON_FAMILIES = ("school", "class", "ui")
# The faces explorer.css sets (a weight it names but lacks, like Sans 600, falls to the nearest).
FONTS = ("Alegreya-400.ttf", "Alegreya-400i.ttf", "Alegreya-700.ttf", "Alegreya-700i.ttf", "AlegreyaSC-700.ttf",
         "AlegreyaSans-400.ttf", "AlegreyaSans-500.ttf", "AlegreyaSans-700.ttf", "AlegreyaSansSC-500.ttf",
         "AlegreyaSansSC-700.ttf", "Cinzel-700.ttf")
APP_ICONS = ("icon.svg", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "favicon-32.png")

ENTRY = """{% import "book/_blocks.j2" as k %}{{ k.spell(s) }}{% for n in kids %}{{ k.statblock(n) }}{% endfor %}"""


def page_ref(e):
    """A book abbreviation and optional page number."""
    return f"{book_abbr(e.book)} p{e.page}" if e.page is not None else book_abbr(e.book)


def row(e, entry):
    d = e.data
    kids = [c for c in e.children if c.type == "creature"]
    words = [e.title]                     # the rules text first: search snippets quote it
    text.walk_text(e.content, words)
    words += [d["school"], d["casting_time"], d["range"], d["components"], d["duration"]]
    words += [c.title + "\n" + text.entity_text(c) for c in kids]
    html = entry.render(s=books.spell_entry(e), kids=[books.node(c, 1) for c in kids])
    return {"id": e.slug, "t": e.title, "l": d["level"], "s": d["school"], "c": list(e.classes),
            "b": e.book, "p": page_ref(e), "ct": d["casting_time"], "r": d["range"], "d": d["duration"],
            "v": "".join(d["component_types"]), "rit": d["ritual"], "con": d["concentration"],
            "h": re.sub(r"\n+", "\n", html).strip(),
            "x": re.sub(r"\s+", " ", " ".join(text.inline(w, "plain") for w in words if w))}


def sprite(families=ICON_FAMILIES):
    """The icon sprite of the families the app shows (pipeline.sprite holds every icon)."""
    from .pipeline import _symbol
    icons = STYLE / "icons"
    manifest = json.loads((icons / "manifest.json").read_text(encoding="utf-8"))
    syms = [_symbol(f"{fam}-{iid}", (icons / meta["svg"]).read_text(encoding="utf-8"))
            for fam, items in manifest.items() if fam in families for iid, meta in items.items()]
    return '<svg xmlns="http://www.w3.org/2000/svg" style="display:none">' + "".join(syms) + "</svg>"


def fonts_css():
    """style/fonts/fonts.css cut to FONTS, and those files."""
    keep = [ln for ln in (STYLE / "fonts" / "fonts.css").read_text(encoding="utf-8").splitlines()
            if any(f'url("{f}")' in ln for f in FONTS)]
    return "\n".join(keep) + "\n"


def build(ix, env, theme_name="grimoire"):
    """{relative path: bytes | str} of the whole site."""
    entry = env.from_string(ENTRY)
    spells = sorted(ix.all("spell"), key=lambda e: (e.data["level"], text.fold(e.title)))
    rows = [row(e, entry) for e in spells]
    classes = sorted({c for r in rows for c in r["c"]})
    schools = sorted({r["s"] for r in rows})
    bookset = sorted({e.book for e in spells}, key=lambda b: (b != ix.books[0]["short"], b))
    meta = {"classes": classes, "schools": schools,
            "books": [{"id": b, "abbr": book_abbr(b)} for b in bookset]}
    files = {"spells.json": json.dumps({"meta": meta, "spells": rows}, ensure_ascii=False, separators=(",", ":"))}

    theme = STYLE / "themes" / theme_name
    css = (theme / "explorer.css").read_text(encoding="utf-8")
    files["style/explorer.css"] = css
    files["style/fonts.css"] = fonts_css()
    for f in FONTS:
        files[f"style/{f}"] = (STYLE / "fonts" / f).read_bytes()
    for f in APP_ICONS:
        files[f"icons/{f}"] = (STYLE / "icons" / "app" / f).read_bytes()

    ctx = {"count": len(rows), "meta": meta, "sprite": sprite()}
    files["app.js"] = (TEMPLATES / "pwa" / "app.js").read_text(encoding="utf-8")
    files["manifest.webmanifest"] = env.get_template("pwa/manifest.webmanifest.j2").render(**ctx)
    files["index.html"] = env.get_template("pwa/index.html.j2").render(**ctx)
    files["_headers"] = (TEMPLATES / "pwa" / "_headers").read_text(encoding="utf-8")

    # The service worker precaches every file but itself and _headers; its cache name changes with them.
    assets = sorted(p for p in files if p != "_headers")
    h = hashlib.sha256()
    for p in assets:
        b = files[p]
        h.update(p.encode() + b"\0" + (b if isinstance(b, bytes) else b.encode()))
    files["sw.js"] = env.get_template("pwa/sw.js.j2").render(version=h.hexdigest()[:12], assets=["./"] + assets)
    return files


def write(files, out=OUT):
    if out.exists():
        shutil.rmtree(out)
    for p, b in files.items():
        f = out / p
        f.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(b, bytes):
            f.write_bytes(b)
        else:
            f.write_text(b, encoding="utf-8")
    return out
