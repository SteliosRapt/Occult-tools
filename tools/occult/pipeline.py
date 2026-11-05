"""select -> view -> template -> html -> render -> dist/ (the one generator pipeline).

    code = pipeline.run_cards(ix, outputs.CATALOGUE["cards"], ["spells"], {"class": "wizard"}, {"mode": "bw"})

Each catalogue row names its runner (run_cards, run_md); `make` (make.py) calls it. Jinja2 is imported here (only `make` needs it). Rendering runs tools/render/render.mjs once per
call with a batch of jobs; Node and Chromium are found via OCCULT_NODE and PLAYWRIGHT_BROWSERS_PATH.
"""
import json
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from . import components, query, views
from .outputs import noun, selector_stem
from .types import resolve_type

ROOT = Path(__file__).resolve().parents[2]
STYLE = ROOT / "style"
TEMPLATES = ROOT / "templates"
RENDER = ROOT / "tools" / "render"
DIST = ROOT / "dist"
DEFAULT_THEME = "grimoire"
SIZES = {"poker": (3, 3), "tarot": (2, 2)}      # cols x rows per sheet, A4 and Letter alike
PAPERS = ("a4", "letter")
MODES = ("color", "bw")


class PipelineError(RuntimeError):
    """A setup or render failure: one line for the user, exit 1."""


# ---------------------------------------------------------------- theme, icons, templates
def theme(name, layout, mode="color", paper="a4"):
    """CSS hrefs (file URIs) for a layout: the theme's files, its files for the mode (bw, white), then the paper file."""
    d = STYLE / "themes" / name
    try:
        spec = json.loads((d / "theme.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        have = sorted(p.name for p in (STYLE / "themes").iterdir() if (p / "theme.json").exists())
        raise PipelineError(f"no theme '{name}' (have: {', '.join(have)})") from None
    files = list(spec.get(layout, []))
    if mode != "color":
        files += spec.get(mode, {}).get(layout, [])
    enabled = {m.__name__.rsplit(".", 1)[-1] for m in components.installed()}
    files = [file for entry in files for file in ([entry] if isinstance(entry, str) else entry["files"] if entry["component"] in enabled and set(entry.get("requires", ())) <= enabled else [])]
    files.append(f"../../base/paper-{paper}.css")
    return {"name": name, "mode": mode, "css": [(d / f).resolve().as_uri() for f in files]}


_SPRITE = None


def sprite():
    """One hidden <svg> of <symbol id="<family>-<id>"> for every icon in style/icons/manifest.json."""
    global _SPRITE
    if _SPRITE is None:
        icons = STYLE / "icons"
        manifest = json.loads((icons / "manifest.json").read_text(encoding="utf-8"))
        syms = [_symbol(f"{fam}-{iid}", (icons / meta["svg"]).read_text(encoding="utf-8"))
                for fam, items in manifest.items() for iid, meta in items.items()]
        _SPRITE = '<svg xmlns="http://www.w3.org/2000/svg" style="display:none">' + "".join(syms) + "</svg>"
    return _SPRITE


def _symbol(sid, svg):
    m = re.match(r"<svg([^>]*)>(.*)</svg>", svg.strip(), re.S)
    attrs, inner = m.group(1), m.group(2)
    inner = re.sub(r"<title>.*?</title>", "", inner)
    vb = re.search(r'viewBox="([^"]+)"', attrs).group(1)
    keep = " ".join(re.findall(r'\b(?:fill|stroke|stroke-width|stroke-linecap|stroke-linejoin)="[^"]*"', attrs))
    return f'<symbol id="{sid}" viewBox="{vb}" {keep}>{inner}</symbol>'


_ENV = None


def env():
    global _ENV
    if _ENV is None:
        try:
            from jinja2 import Environment, FileSystemLoader, StrictUndefined
        except ImportError:
            raise PipelineError("make needs jinja2: pip install -r requirements.txt") from None
        from . import text
        from .views._common import book_table
        from markupsafe import Markup                                   # ships with jinja2
        # Autoescape: plain-text fields are escaped; view fields that are already HTML are `| safe`.
        _ENV = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True, trim_blocks=True,
                           lstrip_blocks=True, undefined=StrictUndefined)
        _ENV.filters["inline"] = lambda s: Markup(text.inline(s, "html"))   # stored markup -> HTML (books)
        components.apply("template_globals", _ENV.globals)
        _ENV.globals["book_table"] = book_table                       # a JSON table block -> rows + .num flags
    return _ENV


# ---------------------------------------------------------------- html
def decks(models):
    """Group card models by size (poker first), keeping selector order within a size."""
    out = []
    for size, (cols, rows) in SIZES.items():
        cards = [m for m in models if m["size"] == size]
        if cards:
            backs = list({m["back"]["key"]: m["back"] for m in cards}.values())
            out.append({"size": size, "cols": cols, "rows": rows, "cards": cards, "backs": backs})
    return out


def html_for(out, models, mode, paper, theme_name=DEFAULT_THEME, title="", backs=False, **options):
    ctx = dict(title=title, theme=theme(theme_name, out.layout, mode, paper), paper=paper,
               sprite=sprite(), decks=decks(models), backs=backs, body_class="sheet",
               scripts=[(RENDER / name).as_uri() for name in [*components.values("card_scripts"), "fit.js"]])
    return env().get_template(out.template).render(**components.transform("card_context", ctx, options))


# ---------------------------------------------------------------- render
def render(jobs):
    """Run render.mjs on a batch of jobs; returns its JSON results."""
    node = os.environ.get("OCCULT_NODE") or ("/opt/node22/bin/node" if Path("/opt/node22/bin/node").exists()
                                             else shutil.which("node"))
    if not node or not Path(node).exists():
        raise PipelineError("Node not found; set OCCULT_NODE to the node binary")
    e = dict(os.environ)
    e.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    if not Path(e["PLAYWRIGHT_BROWSERS_PATH"]).is_dir():
        raise PipelineError(f"Chromium not found at {e['PLAYWRIGHT_BROWSERS_PATH']}; set PLAYWRIGHT_BROWSERS_PATH")
    p = subprocess.run([node, str(RENDER / "render.mjs")], input=json.dumps(jobs), capture_output=True,
                       text=True, env=e)
    if p.returncode != 0:
        msg = (p.stderr.strip().splitlines() or [f"render.mjs exited {p.returncode}"])[-1]
        raise PipelineError(msg.removeprefix("error: "))
    return json.loads(p.stdout)


def write_build(stem, html, out=None):
    """dist/.build/<row>/<stem>.html: one folder per catalogue row, so stems never collide across rows."""
    page = DIST / ".build" / (out.name if out else "") / f"{stem}.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(html, encoding="utf-8")
    return page


# ---------------------------------------------------------------- run
def variant_suffix(paper, mode, theme_name, backs=False, **options):
    value = (f".{paper}" + (f".{theme_name}" if theme_name != DEFAULT_THEME else "")
             + (f".{mode}" if mode in ("bw", "white") else "") + (".backs" if backs else ""))
    return components.transform("suffix", value, options)


def clear_pngs(folder, stem):
    """Remove the `<stem>-p<n>.png` files of an earlier run, so fewer sheets or pages leave none behind."""
    pat = re.compile(re.escape(stem) + r"-p-?\d+(?:-diff)?\.png$")
    for old in Path(folder).glob(stem + "-p*.png"):
        if pat.fullmatch(old.name):
            old.unlink()


def rel(p):
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def kind(e):
    """Report noun: conditions and actions are terms with a tag."""
    tag = (e.data.get("tag") or "").lower() if e.type == "term" else ""
    return tag if tag in ("condition", "action") else e.type


def counts(ents):
    c = Counter(kind(e) for e in ents)
    return " + ".join(f"{n} {noun(t, n)}" for t, n in c.items())


def summary(ents, st):
    multi = sorted(st["multi"], key=lambda m: (-m["n"], m["key"]))
    runs = ", ".join(f"{m['key'].split(':', 1)[-1]} ×{m['n']}" for m in multi[:3]) + (", …" if len(multi) > 3 else "")
    clipped = len(st["clipped"])
    mfs = f"min {st['minFs']:.1f}pt" if st.get("minFs") is not None else "min -"
    detail = components.transform("card_summary", f" · {mfs}", st)
    return (f"{counts(ents)} → {st['cards']} card{'' if st['cards'] == 1 else 's'}" + (f" ({runs})" if runs else "")
            + f"{detail} · {clipped} clipped")


def histogram(st):
    return ", ".join(f"{n}×{k}" for k, n in sorted(st["runs"].items(), key=lambda kv: int(kv[0])))


def report(lines, ok):
    print("\n".join(lines))
    return 0 if ok else 1


def run_cards(ix, out, terms, filters, opts):
    """make cards <selector> [--mode bw] [--paper letter] [--png] [--check-fit] [--html] [--theme T].
    Prints one line per file (path plus stats); exit 1 when a card is still clipped."""
    mode, paper = opts.get("mode") or "color", opts.get("paper") or "a4"
    ents = out.select(ix, terms, filters)
    if not ents:
        raise PipelineError("the selector matches nothing")
    options = components.mapping("selection_options", ix, terms, opts)
    models = [views.for_(ix, e, **options.get(e.sid, {})) for e in ents]
    render_options = components.mapping("render_options", opts)
    canon = {}                                      # `--class wiz` names the file like `--class wizard`
    for t in filter(None, map(resolve_type, terms)):
        canon.update(query.prepare(ix, t, {k: v for k, v in filters.items() if k in query.filters_of(t)})[1])
    backs = opts.get("backs") == "category"
    theme_name = opts.get("theme") or DEFAULT_THEME
    stem = ((opts.get("stem") or selector_stem(terms, {k: canon.get(k, v) for k, v in filters.items()},
                                               lambda t: ix.get(t).sid))
            + variant_suffix(paper, mode, theme_name, backs, **render_options))
    page = write_build(stem, html_for(out, models, mode, paper, theme_name, stem, backs, **render_options), out)
    job = {"html": str(page)}
    pdf = Path(opts["pdf"]).resolve() if opts.get("pdf") else DIST / out.name / f"{stem}.pdf"
    if not opts.get("check-fit"):
        job["pdf"] = str(pdf)
    if opts.get("png"):
        clear_pngs(pdf.parent, pdf.stem)
        job["png"] = {"path": str(pdf.parent / f"{pdf.stem}-p{{n}}.png"), "selector": ".sheet-page", "scale": 2}
    res = render([job])[0]
    st = res["stats"]
    lines = []
    if opts.get("check-fit"):
        lines.append(f"check-fit {stem}: {summary(ents, st)}")
        lines.append(f"runs: {histogram(st)}")
    else:
        n = st["sheets"]
        sheets = f"{n} sheet{'' if n == 1 else 's'}" + (f" + {st['backs']} back{'' if st['backs'] == 1 else 's'}" if st.get("backs") else "")
        lines.append(f"{rel(pdf)}   {sheets} · {summary(ents, st)}")
    pngs = res["pngs"]
    if pngs:
        lines.append(rel(pngs[0]) if len(pngs) == 1 else
                     f"{rel(pngs[0])} … {Path(pngs[-1]).name}   {len(pngs)} PNGs")
    if opts.get("html"):
        lines.append(rel(page))
    lines += components.values("card_lines", models)
    if st["clipped"]:
        lines.append("clipped: " + " ".join(st["clipped"]))
    return report(lines, not st["clipped"])


def pdftoppm():
    """poppler's pdftoppm (optional; only book PNGs need it), or a one-line error."""
    exe = os.environ.get("OCCULT_PDFTOPPM") or shutil.which("pdftoppm")
    if not exe or not Path(exe).exists():
        raise PipelineError("book PNGs need pdftoppm (poppler-utils, e.g. apt install poppler-utils), "
                            "or set OCCULT_PDFTOPPM to it")
    return exe


def pdf_pngs(pdf, prefix, first=1, last=None, dpi=90):
    """PDF pages -> PNG files `<prefix>-p<n>.png` (poppler's pdftoppm); returns the paths."""
    exe = pdftoppm()
    prefix = Path(prefix)
    clear_pngs(prefix.parent, prefix.name)
    args = [exe, "-png", "-r", str(dpi), "-f", str(first)] + (["-l", str(last)] if last else [])
    try:
        p = subprocess.run(args + [str(pdf), str(prefix) + "-p"], capture_output=True, text=True)
    except OSError as x:
        raise PipelineError(f"cannot run pdftoppm ({exe}): {x.strerror}") from None
    if p.returncode != 0:
        msg = (p.stderr.strip().splitlines() or [f"exit {p.returncode}"])[-1]
        raise PipelineError(f"pdftoppm failed on {rel(pdf)}: {msg}")
    made = sorted(prefix.parent.glob(prefix.name + "-p-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
    out = []
    for p in made:                                   # pdftoppm pads the page number; normalise it
        q = p.with_name(f"{prefix.name}-p{int(p.stem.rsplit('-', 1)[1])}.png")
        p.replace(q)
        out.append(q)
    return out


def book_level(opts, key="level"):
    """`--level N` (spellbook, class) or `--class-features N` (class): the class level 1-20 to stop at, or None."""
    v = opts.get(key)
    if v in (None, False):
        return None
    if not str(v).isdigit() or not 1 <= int(v) <= 20:
        raise PipelineError(f"--{key.replace('_', '-')} '{v}' is not a class level (1-20)")
    return int(v)


def book_variants(out, opts):
    """[(stem, group args)]: one per value of the row's variant flag (`--class all` = every value);
    `--subclass S` adds `-S`, `--class-features N` `-cfN`, `--level N` `-lN`, `--add` `-plus` to the stem."""
    if not out.variant:
        return [(out.name, ())]
    choices = [c for c in out.flags[out.variant] if c != "all"]
    v = opts[out.variant]
    lv = book_level(opts)
    sub = opts.get("subclass")
    if sub:                                          # a file-name slug: `Fiend Patron`, `subclass:fiend-patron` -> fiend-patron
        sub = re.sub(r"[^a-z0-9]+", "-", str(sub).lower().removeprefix("subclass:")).strip("-")
    if sub and v == "all":
        raise PipelineError("--subclass needs one --class, not all")
    cf = book_level(opts, "class-features")
    plus = "-plus" if opts.get("add") else ""
    return [(f"{out.name}-{x}" + (f"-{sub}" if sub else "") + (f"-cf{cf}" if cf else "") + (f"-l{lv}" if lv else "") + plus, (x,))
            for x in (choices if v == "all" else [v])]


def book_html(out, ctx, mode, paper, theme_name=DEFAULT_THEME):
    th = theme(theme_name, out.layout, mode, paper)
    return env().get_template(out.template).render(
        title=ctx["title"], theme=th, paper=paper, sprite="", book=ctx, book_name=out.name,
        body_class="book" + (" compact" if ctx.get("compact") else ""), scripts=[(RENDER / "book.js").as_uri()])




def run_book(ix, out, terms, filters, opts):
    """make <book> [--class C|all] [--mode bw] [--paper letter] [--png] [--html] [--theme T].
    One PDF per variant in dist/books/; prints path, page count and contents."""
    mode, paper = opts.get("mode") or "color", opts.get("paper") or "a4"
    if opts.get("png"):
        pdftoppm()                                  # fail before rendering, not after
    items, jobs = [], []
    for stem, args in book_variants(out, opts):
        lv = book_level(opts)
        try:
            kw = {"level": lv} if lv else {}
            if opts.get("subclass"):
                kw["subclass"] = opts["subclass"]
            cf = book_level(opts, "class-features")
            if cf:
                kw["class_features"] = cf
            if opts.get("add"):
                kw["add"] = [r.strip() for r in str(opts["add"]).split(",") if r.strip()]
            ctx = out.group(ix, *args, **kw)
        except ValueError as x:                      # e.g. a level 1 class that casts no spells yet
            raise PipelineError(str(x)) from None
        theme_name = opts.get("theme") or DEFAULT_THEME
        stem += variant_suffix(paper, mode, theme_name)
        if opts.get("list-only"):                    # spellbook: the spell list without descriptions
            ctx["list_only"] = True
            stem += ".list"
        if opts.get("compact"):                      # smaller type (body.compact, book.css)
            ctx["compact"] = True
            stem += ".compact"
        page = write_build(stem, book_html(out, ctx, mode, paper, theme_name), out)
        pdf = DIST / "books" / f"{stem}.pdf"
        items.append((stem, ctx, page, pdf))
        jobs.append({"html": str(page), "pdf": str(pdf)})
    res = components.transform("book_render", None, out, items, jobs, mode, paper, theme_name)
    if res is None:
        res = render(jobs)
    lines = []
    w = max(len(rel(p)) for *_, p in items)
    for (stem, ctx, page, pdf), r in zip(items, res):
        lines.append(f"{rel(pdf).ljust(w)}   {r['pages']} page{'' if r['pages'] == 1 else 's'} · {ctx['stats']}")
        lines += components.values("book_lines", ctx)
        if opts.get("png"):
            pngs = pdf_pngs(pdf, DIST / "books" / stem)
            lines.append(rel(pngs[0]) if len(pngs) == 1 else f"{rel(pngs[0])} … {pngs[-1].name}   {len(pngs)} PNGs")
        if opts.get("html"):
            lines.append(rel(page))
        if r.get("errors"):
            lines.append("page errors: " + "; ".join(r["errors"]))
    return report(lines, not any(r.get("errors") for r in res))


def run_character(ix, sheet, opts):
    """`./occult character <spec> --pdf [PATH]`: the engine's sheet as a PDF character sheet (front sheet,
    features in full, spells). Default path dist/characters/<name>.<paper>[.bw].pdf; prints path and pages."""
    from .views import charsheet
    ctx = charsheet.context(ix, sheet)
    return run_sheet("character", "book/character.html.j2", ctx, slug_stem(sheet["name"], "character"), opts)


# The official sheet (forms/README.md): its file, and what identifies the edition the CSS was measured on.
FORMS = ROOT / "forms"
FORM_PDF = FORMS / "dnd-2024-character-sheet.pdf"
FORM_ID = "670D3898000001"          # the product code printed on page 2
FORM_SIZE = (603, 774)              # points, both pages


def form_template(path=None):
    """The blank official sheet: `path`, $OCCULT_FORM_PDF or forms/dnd-2024-character-sheet.pdf."""
    p = Path(path or os.environ.get("OCCULT_FORM_PDF") or FORM_PDF).expanduser()
    if not p.is_file():
        raise PipelineError(f"no character sheet form at {rel(p)}: put WotC's D&D 2024 character sheet PDF there "
                            "(forms/README.md), or pass --form-template PATH")
    return p


def pypdf():
    try:
        import pypdf as mod
    except ImportError:
        raise PipelineError("--form needs pypdf (optional: pip install pypdf)") from None
    return mod


def run_form(ix, sheet, opts):
    """`./occult character <spec> --form [PATH]`: the engine's sheet printed onto the official two-page
    D&D 2024 character sheet. The values render (Chromium) on transparent pages of the form's size, then
    pypdf stamps each page onto the form's. Default path dist/characters/<name>.dnd-2024[.bw].pdf (opts["stem"]
    in place of <name>: the spec's file name for a character without one)."""
    from .views import formsheet
    mod = pypdf()
    tpl = form_template(opts.get("template"))
    blank = mod.PdfReader(str(tpl))
    sizes = [(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in blank.pages]
    if sizes != [FORM_SIZE] * 2:
        raise PipelineError(f"{rel(tpl)} is not the 2-page D&D 2024 character sheet ({len(sizes)} pages, {sizes[:1]})")
    warn = [] if FORM_ID in (blank.pages[1].extract_text() or "") else [
        f"warning: {rel(tpl)} lacks the product code {FORM_ID}; the field positions were measured on that edition"]
    mode = opts.get("mode") or "color"
    if opts.get("png"):
        pdftoppm()
    ctx = formsheet.context(ix, sheet)
    stem = (opts.get("stem") or slug_stem(sheet["name"], "character")) + ".dnd-2024" + (".bw" if mode == "bw" else "")
    css = [(STYLE / "fonts" / "fonts.css").as_uri(), (STYLE / "forms" / "dnd-2024.css").as_uri()]
    html = env().get_template("form/dnd-2024.html.j2").render(
        title=ctx["title"], css=css, mode=mode, f=ctx, scripts=[(RENDER / "form.js").as_uri()])
    page = write_build(stem, html, SimpleNamespace(name="form"))
    pdf = Path(opts["pdf"]).resolve() if opts.get("pdf") else DIST / "characters" / f"{stem}.pdf"
    overlay = DIST / ".build" / "form" / f"{stem}.overlay.pdf"
    r = render([{"html": str(page), "pdf": str(overlay)}])[0]
    values = mod.PdfReader(str(overlay))
    if len(values.pages) != len(blank.pages):
        raise PipelineError(f"the overlay has {len(values.pages)} pages, the form {len(blank.pages)}")
    out = mod.PdfWriter(clone_from=str(tpl))
    for base, top in zip(out.pages, values.pages):
        base.merge_page(top)
    out.compress_identical_objects()
    pdf.parent.mkdir(parents=True, exist_ok=True)
    with open(pdf, "wb") as fh:
        out.write(fh)
    st = r.get("stats") or {}
    fit = f"{st.get('shrunk', 0)} shrunk" + (f" (min {st['minFs']:.1f}pt)" if st.get("minFs") else "")
    for k, what in (("firsts", "first paragraphs only"), ("titles", "titles only")):
        n = st.get(k)
        if n:
            fit += f", {n} box{'es' if n > 1 else ''} {what}"
    lines = warn + [f"{rel(pdf)}   2 pages · {ctx['stats']} · {fit} · {len(st.get('clipped') or [])} clipped"]
    if st.get("clipped"):
        lines.append("clipped: " + ", ".join(st["clipped"]))
    if opts.get("png"):
        pngs = pdf_pngs(pdf, pdf.with_suffix(""), dpi=110)
        lines.append(f"{rel(pngs[0])} … {pngs[-1].name}   {len(pngs)} PNGs")
    if opts.get("html"):
        lines.append(rel(page))
    if r.get("errors"):
        lines.append("page errors: " + "; ".join(r["errors"]))
    return report(lines, not r.get("errors") and not st.get("clipped"))


def run_encounter(ix, monsters, ev, opts):
    """`./occult encounter ... --pdf [PATH]`: a DM handout of the monsters' stat blocks (views.encounter):
    the summary and trackers, the stat blocks, then the conditions and spells they name. Default path
    dist/encounters/<creatures>.<paper>[.bw].pdf; prints path and pages."""
    from .views import encounter
    ctx = encounter.context(ix, monsters, ev, opts.get("title"), **{k: v for k, v in opts.items() if k != "title"})
    return run_sheet("encounter", "book/encounter.html.j2", ctx, encounter_stem(monsters, opts.get("title")), opts)


def encounter_stem(monsters, title=None):
    """`goblin-boss-6x-goblin-warrior`, or the title's slug; at most 80 characters."""
    stem = slug_stem(title or "-".join((f"{n}x-" if n > 1 else "") + e.slug for e, n in monsters), "encounter")
    return stem[:80].rstrip("-")


def slug_stem(name, fallback):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or fallback


DIRS = {"character": "characters", "encounter": "encounters"}


def run_sheet(name, template, ctx, stem, opts):
    """Render one book-style handout (a character sheet, an encounter) to dist/<DIRS[name]>/ or opts["pdf"]."""
    mode, paper = opts.get("mode") or "color", opts.get("paper") or "a4"
    theme_name = opts.get("theme") or DEFAULT_THEME
    if opts.get("png"):
        pdftoppm()
    stem += variant_suffix(paper, mode, theme_name)
    th = theme(theme_name, name, mode, paper)
    html = env().get_template(template).render(
        title=ctx["title"], theme=th, paper=paper, sprite=sprite(), book=ctx, book_name=name,
        body_class="book" + (" compact" if ctx.get("compact") else ""), scripts=[(RENDER / "book.js").as_uri()])
    page = write_build(stem, html, SimpleNamespace(name=name))
    pdf = Path(opts["pdf"]).resolve() if opts.get("pdf") else DIST / DIRS[name] / f"{stem}.pdf"
    r = render([{"html": str(page), "pdf": str(pdf)}])[0]
    lines = [f"{rel(pdf)}   {r['pages']} page{'' if r['pages'] == 1 else 's'} · {ctx['stats']}"]
    if opts.get("png"):
        pngs = pdf_pngs(pdf, pdf.with_suffix(""))
        lines.append(rel(pngs[0]) if len(pngs) == 1 else f"{rel(pngs[0])} … {pngs[-1].name}   {len(pngs)} PNGs")
    if opts.get("html"):
        lines.append(rel(page))
    if r.get("errors"):
        lines.append("page errors: " + "; ".join(r["errors"]))
    return report(lines, not r.get("errors"))


def run_md(ix, out, terms, filters, opts):
    """make md [--check] [--out DIR]: write collections/ (§6), or compare it with what would be written."""
    import sys

    from . import collections
    try:
        docs = collections.build(ix)
    except ImportError as x:
        if "jinja2" not in str(x):
            raise
        raise PipelineError("`make` needs jinja2: pip install -r requirements.txt") from None
    root = Path(opts["out"]).resolve() if opts.get("out") else collections.OUT
    shown = root.relative_to(collections.ROOT).as_posix() if root.is_relative_to(collections.ROOT) else str(root)
    digest = collections.inputs_hash()
    if opts.get("check"):
        diffs = collections.check(docs, root)
        for kind, path in diffs:
            print(f"{kind}: {shown}/{path}")
        if diffs:
            print(f"error: {len(diffs)} of {len(docs)} collection files differ; run `./occult make md` and commit {shown}/",
                  file=sys.stderr)
            return 1
        print(f"ok: {len(docs)} files in {shown}/ match · inputs sha256:{digest}")
        return 0
    res = collections.write(docs, root)
    w = max(len(p) for p, _ in res) + len(shown) + 1
    for path, status in res:
        stats = docs[path].stats if path in docs else ""
        print(f"{shown}/{path}".ljust(w) + f"  {status:<9}  {stats}".rstrip())
    n = {s: sum(1 for _, x in res if x == s) for s in ("written", "unchanged", "removed")}
    print(f"\n{len(docs)} files: {n['written']} written, {n['unchanged']} unchanged, {n['removed']} removed"
          f" · inputs sha256:{digest}")
    return 0


def run_pwa(ix, out, terms, filters, opts):
    """make pwa [--out DIR]: the Spell Explorer site (explorer.py)."""
    from . import explorer
    files = explorer.build(ix, env())
    root = explorer.write(files, Path(opts["out"]).resolve() if opts.get("out") else explorer.OUT)
    size = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    n = sum(1 for e in ix.all("spell"))
    return report([f"{rel(root)}/   {n} spells · {len(files)} files · {size / 1e6:.1f} MB",
                   f"preview: python3 -m http.server -d {rel(root)} 8000"], True)
