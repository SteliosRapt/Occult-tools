"""`./occult`: agent-facing commands over every book in data/ (stdlib only on this path).

Results go to stdout, errors and hints to stderr.
Exit codes: 0 ok, 1 not found or ambiguous, 2 usage.
"""
import difflib
import json
import os
import re
import sys
from collections import Counter

from . import data, query, text
from .views.creature import statblock_md
from .views.klass import progression_md, traits_md
from .views.weapon import weapon_rules
from .types import ALIAS, TYPES, has_data, rank, resolve_type

PROG = "./occult"

USAGE = f"""usage: {PROG} <command> [args]      D&D 2024 data: PHB, DMG, MM, EFA, FRHoF, AU, RHW (data/<book>/; --book filters)

  types                                   types, counts and their list filters
  toc [id] [--depth N] [--limit N]        browse the book tree
  find <text>... [--type T] [--limit N]   search titles, then full text
  show <id>... [--brief|--full] [--max-chars N] [--json]
                                          read entities (truncated; says how to see more)
  list <type> [filters] [--limit N] [--offset N] [--ids|--json]
                                          filtered table, e.g. list spells --class wizard --level 0-3
  make <output> [selector] [opts]         run a generator (needs jinja2); `make --list` lists them
                                          e.g. make cards spells --class wizard --mode bw · make md
  fetch images [--book B] [--check]       copy the art the data refers to into img/ (gitignored)

Rules engine (tools/occult/rules):
  character <spec.json> [--json] [--level-up CLASS]
                                          a character's derived numbers: AC, HP, saves, skills, slots ...
  encounter --party 4x5 [creature[xN]...] [--suggest]
                                          rate an encounter by the DMG XP budget, or suggest some
  calc mod|pb|level|cr|slots|point-buy|budget ...   one rule number, e.g. calc slots wizard=5 cleric=3
  roll <expr>... [--avg]                  dice: 2d6+3, 4d6kh3, 2d20kl1
  loot individual|hoard|items|for ...     treasure by the DMG tables, e.g. loot hoard --cr 7 --theme arcana
  npc [--creature C] · settlement · tavern [--level L]
                                          NPCs, settlements and taverns rolled on the books' tables
  table <title|id> [--times N] · table --list [TEXT]
                                          roll on any die table in the books (351)

Ids look like spell:fireball, term:grappled, feature:wizard/spellcasting; every row starts with one.
`{PROG} <command> --help` for details."""

RULES_COMMANDS = ("character", "encounter", "calc", "roll", "loot", "npc", "settlement", "tavern", "table")

HELP = {
    "types": f"""usage: {PROG} types
Every type with its count and the filters `list` accepts. Filters with a value show its form
(--level N|N-M); the others are flags (--ritual).""",
    "toc": f"""usage: {PROG} toc [id] [--depth N] [--limit N]
Book tree as `id  title  page`. With no id: the chapters. [N] marks N children not shown.
  --depth N   levels below the root to show (default 0 for the whole book, 1 for an id)
  --limit N   max lines (default 60)
e.g. {PROG} toc chapter:03 · {PROG} toc class:wizard --depth 2""",
    "find": f"""usage: {PROG} find <text>... [--type T] [--limit N]
Title search (exact > prefix > substring > all words > fuzzy, spaces ignored); when there are
fewer than 3 title hits, it also searches the full text (content and data).
  --type T    only this type (see `types`; aliases and plurals work)
  --limit N   max rows (default 15)
e.g. {PROG} find fire ball · {PROG} find bat guano · {PROG} find darkvision --type option""",
    "show": f"""usage: {PROG} show <id>... [--brief|--full] [--max-chars N] [--json]
Read entities as Markdown: header, stat lines, body, children and cross-references (Refs:).
An id can be a short id (spell:fireball), a full id, alias:slug (spells:fireball,
condition:grappled), a bare slug (fireball) or an exact title ("Magic Missile").
  --brief          header and stat lines only (cheap for many ids)
  --full           no truncation
  --max-chars N    body budget before truncation (default 1200)
  --json           JSON Lines: one object per entity (raw data and content)
e.g. {PROG} show spell:fireball item:rope · {PROG} show $({PROG} list spells --class wizard --level 3 --ids) --brief""",
    "list": f"""usage: {PROG} list <type> [filters] [--limit N] [--offset N] [--ids|--json]
A filtered table of one type; `{PROG} types` shows each type's filters. Values match case-
insensitively and a unique prefix works (--school evoc). A footer gives the count and the next
--offset.
  --limit N    rows per page (default 40)
  --offset N   skip N rows
  --ids        ids only, one per line (for `show $(...) --brief`)
  --json       JSON Lines: one object per entity (sid, type, title, page, data)
e.g. {PROG} list spells --class wizard --level 0-3 --ritual · {PROG} list weapons --mastery vex""",
}

# name -> (positional, nargs, {option: kind})
SPECS = {
    "types": (None, None, {}),
    "toc": ("id", "?", {"depth": int, "limit": int}),
    "find": ("text", "+", {"type": str, "limit": int}),
    "show": ("ref", "+", {"brief": bool, "full": bool, "max-chars": int, "json": bool}),
    "list": ("type", "1", {"limit": int, "offset": int, "ids": bool, "json": bool}),
}


class Usage(Exception):
    def __init__(self, msg, hints=(), label="did you mean"):
        super().__init__(msg)
        self.hints, self.label = list(hints), label


class Failed(Exception):
    """Not found / ambiguous: exit 1 (messages already printed)."""


def out(s=""):
    print(s)


def err(msg, hints=(), label="did you mean"):
    print(f"error: {msg}", file=sys.stderr)
    if hints:
        print(f"{label}: " + ", ".join(hints), file=sys.stderr)


def note(msg):
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- argument parsing
def opt_usage(opts):
    return " ".join(f"--{k}" + ("" if kind is bool else " N" if kind is int else " T") for k, kind in opts.items())


def parse(cmd, argv):
    """-> (positionals, options, filters). Filters only for `list` (validated by query)."""
    pos_name, nargs, opts = SPECS[cmd]
    pos, o, filters = [], {}, {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            out(HELP[cmd])
            sys.exit(0)
        if a.startswith("--") and len(a) > 2:
            name, eq, val = a[2:].partition("=")
            kind = opts.get(name)
            if kind is None and cmd == "list" and pos:
                t = resolve_type(pos[0])
                if not t:
                    raise Usage(f"unknown type '{pos[0]}'", query_hints(pos[0]))
                f = query.filters_of(t).get(name)
                if f is not None:
                    kind = bool if f.op == "flag" else str
                    target = filters
                else:
                    known = [*query.listed_filters(t)]
                    close = difflib.get_close_matches(name, known + list(opts), 3, 0.5)
                    raise Usage(f"'{t}' has no filter --{name}",
                                ["--" + x for x in close + [x for x in known if x not in close]] or
                                [f"none; `list {t}` takes no filters (try `find <text> --type {t}`)"],
                                "did you mean" if close else "valid filters")
            elif kind is None:
                close = difflib.get_close_matches(name, opts, 3, 0.5)
                if cmd == "list" and not pos:
                    raise Usage("put the type first: list <type> [filters]", [f"`{PROG} types` lists types"], "hint")
                raise Usage(f"`{cmd}` has no flag --{name}",
                            ["--" + x for x in close] or [opt_usage(opts) or "(none)"],
                            "did you mean" if close else "valid flags")
            else:
                target = o
            if kind is bool:
                if eq:
                    raise Usage(f"--{name} takes no value")
                target[name] = True
                i += 1
                continue
            if not eq:
                if i + 1 >= len(argv) or (argv[i + 1].startswith("--") and len(argv[i + 1]) > 2):
                    raise Usage(f"--{name} needs a value")
                val = argv[i + 1]
                i += 1
            if kind is int:
                try:
                    val = int(val)
                except ValueError:
                    raise Usage(f"--{name} takes a whole number, not '{val}'") from None
                if val < 0:
                    raise Usage(f"--{name} cannot be negative")
            target[name] = val
            i += 1
            continue
        pos.append(a)
        i += 1
    if nargs is None and pos:
        raise Usage(f"`{cmd}` takes no arguments (got '{pos[0]}')")
    if nargs in ("+", "1") and not pos:
        raise Usage(f"`{cmd}` needs <{pos_name}>", [HELP[cmd].splitlines()[0].split(": ", 1)[1]], "usage")
    if nargs in ("?", "1") and len(pos) > 1:
        raise Usage(f"`{cmd}` takes one <{pos_name}>, got {len(pos)}: {' '.join(pos)}",
                    [f"filters are flags: list {pos[0]} --class wizard"] if cmd == "list" else [])
    return pos, o, filters


# ---------------------------------------------------------------- formatting
def table(rows, header):
    w = [max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))]
    fmt = lambda r: "  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)).rstrip()
    return "\n".join([fmt(header)] + [fmt(r) for r in rows])


def page_of(e):
    """`p274` (PHB); another book's entity carries its book: `dmg p234`, or `dmg` when it has no page."""
    p = f"p{e.page}" if e.page is not None else ""
    return (p or e.book) if e.book == "phb" else f"{e.book} {p}".rstrip()


def page_label(e):
    """The `show` header's `(p.274)`, `(DMG p.234)`, `(DMG)`; nothing for a PHB entity with no page."""
    p = f"p.{e.page}" if e.page is not None else ""
    s = (p or data.book_abbr(e.book)) if e.book == "phb" else f"{data.book_abbr(e.book)} {p}".rstrip()
    return f"  ({s})" if s else ""


def row_of(e, t=None):
    reg = TYPES.get(t or e.type, {})      # the listed type: `skill` rows show the ability, not the tag
    cells = reg["row"](e) if "row" in reg and has_data(e) else ["-"] * len(reg.get("cols", []))
    return [e.sid, text.inline(clip(e.title, 32), "plain"), *cells, page_of(e)]


def header_of(t):
    return ["id", "title", *TYPES.get(t, {}).get("cols", []), "page"]


def clip(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def more_hint(shown, total, flag):
    return f"; more: {flag}" if shown < total else ""


def candidates_msg(ref, lk, cap=12):
    cs = [e.sid for e in lk.candidates]
    if lk.ambiguous:
        tail = f", … (+{len(cs) - cap}: `find {ref}`)" if len(cs) > cap else ""
        return f"'{ref}' matches {len(cs)} entities; use an id: " + ", ".join(cs[:cap]) + tail
    if cs:
        return f"no entity '{ref}'; did you mean: " + ", ".join(cs)
    return f"no entity '{ref}'; try `find {ref.split(':')[-1]}`"


# ---------------------------------------------------------------- show
def first_para(e, n=160):
    p = next((b for b in e.content if b["type"] == "paragraph"), None)
    if not p:
        return None
    s = text.inline(p["text"], "plain")
    return s if len(s) <= n else s[: s.rfind(" ", 0, n)] + " …"


def see_also(e):
    c = e.title.lower()
    if e.type == "class":
        hints = [f"`list features --class {c}`", f"`list subclasses --class {c}`"]
        if e.data.get("has_spell_list") or e.data.get("spell_list"):
            hints.append(f"`list spells --class {c}`")
        return "See: " + " · ".join(hints)
    return None


def render(ix, e, brief=False, full=False, max_chars=1200):
    lines = [f"{e.sid} — {e.title}{page_label(e)}"]
    reg = TYPES.get(e.type, {})
    lines += [x for x in (reg["brief"](e) if "brief" in reg and has_data(e) else []) if x]
    if brief:
        if e.type not in ("spell", "weapon", "armor", "creature", "class", "species", "background"):
            fp = first_para(e)
            if fp:
                lines.append(fp)
        return "\n".join(lines)
    fixed = []                        # rendered from data: never cut (a half table is useless)
    content = e.content
    if e.type == "class":
        fixed += [traits_md(e.data["core_traits"]), progression_md(e.data)]
        content = [b for b in content if not (b["type"] == "table" and (b.get("title") or "").startswith("Core "))]
    if e.type == "creature":
        fixed.append(statblock_md(e.data, ix))
    prose = text.blocks_md(content)
    if e.type == "weapon":
        prose += weapon_rules(ix, e)
    body, hidden = text.truncate("\n\n".join(prose), None if full else max_chars)
    if hidden:
        body += f"\n[+{hidden} chars; `show {e.sid} --full`]"
    for part in fixed + [body]:
        if part:
            lines += ["", part]
    tail = []
    if e.children:
        if len(e.children) <= 8:
            tail.append("Children: " + " ".join(c.sid for c in e.children))
        else:
            cnt = Counter(c.type for c in e.children)
            tail.append(f"Children: {len(e.children)} (" + ", ".join(f"{k} ×{v}" for k, v in cnt.items())
                        + f"); `toc {e.sid}` lists them")
    sa = see_also(e)
    if sa:
        tail.append(sa)
    refs = [r.sid for r in ix.refs(e) if r not in e.children]
    if refs:
        tail.append("Refs: " + " ".join(refs[:15]) + (f" (+{len(refs) - 15}; `show {e.sid} --json` has the text)" if len(refs) > 15 else ""))
    if tail:
        lines += [""] + tail
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------- commands
def cmd_types(ix, pos, o, f):
    rows = []
    for t, reg in TYPES.items():
        if not ix.all(t):
            continue
        fs = " ".join(f"--{k}{x.usage}" for k, x in query.listed_filters(t, ix).items())
        base = f" (terms tagged {reg['where'][1]})" if "where" in reg else ""
        rows.append([t, str(len(ix.all(t))), (fs or "-") + base])
    out(table(rows, ["type", "count", "list filters"]))
    out()
    out("Ids are <type>:<slug>, e.g. spell:fireball, term:grappled (condition:grappled works too),")
    out("feature:wizard/spellcasting. Plurals and aliases work as type names (spells, armour, monsters).")
    out("Next: `list <type> [filters]`, `find <text>`, `show <id>`.")


def cmd_toc(ix, pos, o, f):
    limit = o.get("limit", 60)
    if pos:
        lk = ix.resolve(pos[0])
        if not lk:
            err(candidates_msg(pos[0], lk))
            raise Failed
        roots, depth = [lk.entity], o.get("depth", 1)
    else:
        roots, depth = ix.roots, o.get("depth", 0)
    lines = []
    hidden_kids = False

    def walk(e, d):
        nonlocal hidden_kids
        kids = f"  [{len(e.children)}]" if e.children and d >= depth else ""
        hidden_kids |= bool(kids)
        lines.append("  " * d + f"{e.sid}  {e.title}  {page_of(e)}{kids}")
        if d < depth:
            for c in e.children:
                walk(c, d + 1)
    for r in roots:
        walk(r, 0)
    out("\n".join(lines[:limit]))
    hints = []
    if len(lines) > limit:
        hints.append(f"[+{len(lines) - limit} lines; --limit {len(lines)}, or `toc <id>` on a branch]")
    elif hidden_kids:
        hints.append("[N] = children not shown; `toc <id>` expands one" + ("" if pos else ", --depth 1 shows all"))
    for h in hints:
        out(h)


def find_scores(ix, q, pool):
    toks = q.split()
    flat = q.replace(" ", "")
    scored = []
    for e in pool:
        ti = text.fold(e.title)
        tf = ti.replace(" ", "")
        if ti == q or tf == flat:
            s = 100
        elif ti.startswith(q) or tf.startswith(flat):
            s = 80
        elif q in ti or flat in tf:
            s = 60
        elif all(x in ti for x in toks):
            s = 40
        elif len(q) > 3:
            s = 30 * difflib.SequenceMatcher(None, q, ti).ratio()
        else:
            s = 0
        if s >= 20:
            scored.append((-s, rank(e), len(ti), ti, e))
    scored.sort(key=lambda x: x[:4])
    return [x[-1] for x in scored]


def snippet(e, toks, width=60):
    """The text around the first query word, from the paragraph or field that holds it."""
    parts = [re.sub(r"\s+", " ", text.inline(p, "plain")) for p in text.entity_text(e).split("\n")]
    s = next((p for p in parts if toks and toks[0] in text.fold(p)), "")
    i = text.fold(s).find(toks[0]) if s else -1
    if i < 0:
        return ""
    a = max(0, i - width // 3)
    a = s.rfind(" ", 0, a) + 1 if a else 0
    cut = s[a:a + width]
    if len(s) > a + width and " " in cut:
        cut = cut[: cut.rfind(" ")]
    return ("…" if a else "") + cut + ("…" if a + len(cut) < len(s) else "")


def cmd_find(ix, pos, o, f):
    q = " ".join(text.fold(" ".join(pos)).split())
    if not q:
        raise Usage("empty search text", ["find fire ball", "find bat guano"], "e.g.")
    limit = o.get("limit", 15)
    t = None
    if o.get("type"):
        t = resolve_type(o["type"])
        if not t:
            raise Usage(f"unknown type '{o['type']}'", query_hints(o["type"]))
    pool = ix.all(t) if t else ix.entities
    hits = find_scores(ix, q, pool)
    mode = "title match"
    text_hits = []
    if len(hits) < 3:
        toks = q.split()
        text_hits = sorted((e for e in pool if e not in hits and all(x in e.blob() for x in toks)),
                           key=lambda e: (rank(e), e.order))
        if text_hits:
            mode = "title+text match" if hits else "text match"
    allhits = hits + text_hits
    if not allhits:
        sug = [e.sid for e in ix.suggest(q, pool, 6)]
        if sug:
            err(f"nothing matches '{q}'" + (f" in {t}" if t else ""), sug)
        else:
            err(f"nothing matches '{q}'" + (f" in {t}" if t else "") + "; try fewer or shorter words"
                + ("" if not t else ", or drop --type"))
        raise Failed
    rows = []
    for e in allhits[:limit]:
        r = [e.sid, clip(e.title, 32), e.type, page_of(e)]
        if text_hits:
            r.append("" if e in hits else snippet(e, q.split()))
        rows.append(r)
    out(table(rows, ["id", "title", "type", "page"] + (["matched text"] if text_hits else [])))
    out()
    scope = f" in {t}" if t else ""
    out(f"{min(len(allhits), limit)} of {len(allhits)} ({mode}{scope}){more_hint(limit, len(allhits), f'--limit {len(allhits)}')}")


def query_hints(name):
    return difflib.get_close_matches(name.lower(), ALIAS, 4, 0.6) or [f"`{PROG} types` lists them"]


def cmd_show(ix, pos, o, f):
    if o.get("brief") and o.get("full"):
        raise Usage("--brief and --full exclusive; pick one")
    if not all(r.strip() for r in pos):
        raise Usage("empty id", ["spell:fireball", "find <text> to search"], "e.g.")
    chunks, missing = [], []
    for ref in pos:
        lk = ix.resolve(ref)
        if not lk:
            missing.append(candidates_msg(ref, lk))
            continue
        e = lk.entity
        if o.get("json"):
            chunks.append(json.dumps(e.as_json(full=not o.get("brief")), ensure_ascii=False))
        else:
            chunks.append(render(ix, e, brief=o.get("brief"), full=o.get("full"), max_chars=o.get("max-chars", 1200)))
    if chunks:
        sep = "\n" if o.get("json") else "\n\n" if o.get("brief") else "\n\n---\n\n"
        out(sep.join(chunks))
    for m in missing:
        err(m)
    if missing:
        raise Failed


def cmd_list(ix, pos, o, f):
    try:
        t, clean = query.prepare(ix, pos[0], f)
    except query.QueryError as x:
        raise Usage(str(x), x.hints, x.label) from None
    ents = query.select(ix, t, clean)
    off, limit = o.get("offset", 0), o.get("limit", 40)
    page = ents[off:off + limit]
    sel = query.describe(t, clean)
    shown = (f"{off + 1}-{off + len(page)}" if off else str(len(page))) if page else "0"
    nxt = f"; more: --offset {off + limit}" if off + limit < len(ents) else ""
    footer = f"{shown} of {len(ents)} {sel}{nxt}"
    if off and off >= len(ents) and ents:
        footer += f" (--offset {off} is past the end)"
    if o.get("ids") or o.get("json"):
        for e in page:
            out(e.sid if o.get("ids") else json.dumps(e.as_json(full=False), ensure_ascii=False))
        if nxt or not page:
            note(f"# {footer}")
        return
    if page:
        out(table([row_of(e, t) for e in page], header_of(t)))
        out()
    out(footer)


COMMANDS = {"types": cmd_types, "toc": cmd_toc, "find": cmd_find, "show": cmd_show, "list": cmd_list}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if not argv or argv[0] in ("-h", "--help", "help"):
        out(USAGE)
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "make":                        # generators: own argument parsing (tools/occult/make.py)
        from . import make
        return make.main(rest)
    if cmd == "fetch":                       # img/ from a 5etools-img checkout or GitHub (tools/occult/fetch.py)
        from . import fetch
        return fetch.main(rest)
    if cmd in RULES_COMMANDS:                # the rules engine (tools/occult/rules/cli.py)
        from .rules import cli as rules_cli
        return rules_cli.main(cmd, rest)
    if cmd not in COMMANDS:
        known = [*COMMANDS, "make", "fetch", *RULES_COMMANDS]
        err(f"unknown command '{cmd}'", difflib.get_close_matches(cmd, known, 2, 0.5) or known,
            "did you mean" if difflib.get_close_matches(cmd, known, 2, 0.5) else "commands")
        return 2
    try:
        pos, o, f = parse(cmd, rest)
        COMMANDS[cmd](data.load(), pos, o, f)
    except Usage as x:
        err(str(x), x.hints, x.label)
        if not x.hints:
            note(f"usage: see `{PROG} {cmd} --help`")
        return 2
    except Failed:
        return 1
    except BrokenPipeError:                  # `./occult list spells | head`
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
