"""Inline markup and block rendering (stdlib only).

Text is stored as in the JSON: `*italic*` (names of spells, items...), `**bold**` and links
`[text](<node id>)` to other nodes (from the 5e.tools import).
`inline(s, to=...)` converts it: md passes through, html escapes and maps to <i>/<b>
(optionally adding scan aids: bold dice and saving throws), plain strips it. Every target
prints a link as its text (md too: collections do not link names); `links(s)` lists them.
"""
import html
import re
import unicodedata

def fold(s):
    """Lower case with accents dropped (`Faerûnian` -> `faerunian`), one character per character,
    so an index into fold(s) is an index into s. Every user-typed comparison goes through it."""
    s = str(s)
    if s.isascii():
        return s.lower()
    return "".join(unicodedata.normalize("NFD", c)[0] for c in s).lower()


LINK = re.compile(r"\[([^\]\n]+)\]\(([a-z0-9.-]+(?:/[a-z0-9-]+)+)\)")
ITALIC = re.compile(r"(?<![*\w])\*(?!\*)([^*\n]+?)\*(?![*\w])")
BOLD = re.compile(r"\*\*([^*\n]+?)\*\*")
# an italic name followed by a literal footnote asterisk: `*Identify**` (a school-list footnote)
ITALIC_MARKED = re.compile(r"(?<![*\w])\*(?!\*)([^*\n]+?)\*\*(?![*\w])")
DAMAGE_TYPES = ("Acid|Bludgeoning|Cold|Fire|Force|Lightning|Necrotic|Piercing|Poison|Psychic|Radiant|Slashing|Thunder")
# a dice expression, plus its damage type when one follows (`8d6 Fire damage` is bolded as one run)
DICE = re.compile(r"\b(\d*d\d+(?:\s*[+−-]\s*\d+)?\b(?: (?:" + DAMAGE_TYPES + r") damage\b)?)")
SAVE = re.compile(r"\b((?:Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) saving throws?)\b")

# Italic names that don't match a title, even after singular fallback. Keys are lower case.
REF_ALIASES = {
    "potions of healing": "item:potion-of-healing",
    "spell scroll": "item:spell-scroll",
    "spell scrolls": "item:spell-scroll",
    "bullets, sling": "item:ammunition",
    "bullets, firearm": "item:ammunition",
    "firearm bullets": "item:ammunition",
    "sling bullets": "item:ammunition",
    "needles": "item:ammunition",
    "arrows": "item:ammunition",
    "bolts": "item:ammunition",
}


def inline(s, to="md", scan_aids=False):
    """Convert stored inline markup to `md` (unchanged but links), `html` or `plain`. Links print as their text."""
    if s is None:
        return ""
    s = LINK.sub(r"\1", s) if "](" in s else s
    if to == "md":
        return s
    if to == "plain":
        return ITALIC.sub(r"\1", BOLD.sub(r"\1", ITALIC_MARKED.sub(r"\1*", s)))
    if to != "html":
        raise ValueError(f"unknown target {to!r}")
    out = html.escape(s, quote=False)
    out = ITALIC_MARKED.sub(r"<i>\1</i>&#42;", out)               # an entity, so ITALIC cannot pair it
    out = BOLD.sub(r"<b>\1</b>", out)
    out = ITALIC.sub(r"<i>\1</i>", out)
    if scan_aids:
        out = DICE.sub(r"<b>\1</b>", out)
        out = SAVE.sub(r"<b>\1</b>", out)
        out = out.replace("<b><b>", "<b>").replace("</b></b>", "</b>")
    return out


def links(s):
    """[(text, node id)] of the links in s, in order."""
    return LINK.findall(s or "")


def italic_names(s):
    """Italic runs in s that are not links (a link already names its target)."""
    s = LINK.sub("\x00", s or "")
    return [m.strip() for m in ITALIC.findall(BOLD.sub(" ", s)) if "\x00" not in m]


def singulars(name):
    """Singular forms to try for a plural name: `arrows` -> arrow, `potions of healing` -> potion of healing."""
    def sing(w):
        out = []
        if w.endswith("ies") and len(w) > 4:
            out.append(w[:-3] + "y")
        if w.endswith(("ches", "shes", "sses", "xes")):
            out.append(w[:-2])
        if w.endswith("ves"):
            out += [w[:-3] + "f", w[:-3] + "fe"]
        if w.endswith("s") and not w.endswith("ss"):
            out.append(w[:-1])
        return out
    words = name.split(" ")
    forms = [" ".join(words[:-1] + [s]) for s in sing(words[-1])]
    if len(words) > 2 and words[1] == "of":
        forms += [" ".join([s] + words[1:]) for s in sing(words[0])]
    return forms


def entity_text(e):
    """All prose of an entity (content blocks and string data fields), for cross-references."""
    parts = []
    walk_text(e.content, parts)
    for k, v in e.data.items():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            parts += [x if isinstance(x, str) else x.get("text", "") for x in v if isinstance(x, (str, dict))]
    return "\n".join(parts)


def walk_text(blocks, out):
    for b in blocks:
        t = b["type"]
        if t in ("paragraph", "heading", "caption"):
            out.append(b.get("text", ""))
        elif t == "list":
            for it in b["items"]:
                out.append(it.get("text", ""))
                walk_text([{"type": "list", "items": it["items"]}] if it.get("items") else [], out)
        elif t == "table":
            out += [str(c) for r in b["rows"] for c in r]
        elif t == "sidebar":
            walk_text(b.get("content", []), out)
        elif t == "dialogue":
            out += [ln.get("text", "") for ln in b["lines"]]


# ---------------------------------------------------------------- markdown output
def md_table(columns, rows, align=True):
    """A GitHub pipe table; padded so it also reads well as plain text."""
    rows = [[inline("" if c is None else str(c)).replace("|", "\\|").replace("\n", " ") for c in r] for r in rows]
    cols = [str(c) for c in columns]
    if not align:
        w = [3] * len(cols)
    else:
        w = [max([len(cols[i]), 3] + [len(r[i]) for r in rows if i < len(r)]) for i in range(len(cols))]
        w[-1] = max(3, len(cols[-1]))     # last column is not padded
    line = lambda r: "| " + " | ".join((r[i] if i < len(r) else "").ljust(w[i]) for i in range(len(cols))).rstrip() + " |"
    sep = "|" + "|".join("-" * (x + 2) for x in w) + "|"
    return "\n".join([line(cols), sep] + [line(r) for r in rows])


def label(x):
    return f"**{x['label']}.** " if x.get("label") else ""


def blocks_md(blocks, depth=0):
    """Content blocks -> list of Markdown chunks (joined with blank lines by the caller).

    Captions (art labels), images and embeds (the embedded entity is a child node) are dropped;
    dialogue is kept as `Speaker: text` lines; links print as their text.
    """
    out = []
    for b in blocks:
        t = b["type"]
        if t == "paragraph":
            out.append(label(b) + b["text"])
        elif t == "heading":
            out.append(f"#### {b.get('text', '')}")
        elif t == "list":
            out.append("\n".join(list_md(b, depth)))
        elif t == "table":
            head = f"*Table: {b['title']}*\n" if b.get("title") else ""
            out.append(head + md_table(b["columns"], b["rows"], align=len(b["columns"]) <= 8))
        elif t == "sidebar":
            inner = "\n\n".join(blocks_md(b.get("content", []), depth))
            out.append(f"> **{b.get('title') or 'Sidebar'}**\n>\n" + "\n".join(("> " + x).rstrip() for x in inner.split("\n")))
        elif t == "dialogue":
            out.append("\n".join(f"{ln['speaker']}{' (' + ln['as'] + ')' if ln.get('as') else ''}: {ln['text']}"
                                 for ln in b["lines"]))
    return [inline(x, "md") for x in out]


def list_md(b, depth=0):
    lines = []
    for i, it in enumerate(b["items"], b.get("start") or 1):
        mark = f"{i}." if b.get("ordered") else "-"
        lines.append("  " * depth + f"{mark} {label(it)}{it.get('text', '')}")
        if it.get("items"):
            lines += list_md({"items": it["items"]}, depth + 1)
    return lines


def truncate(s, max_chars, slack=1.25):
    """(text, hidden_chars). Cuts only when s is over slack*max_chars, at a line end if one is
    reasonably close (never mid table row), else at a word."""
    if max_chars is None or len(s) <= max_chars * slack:
        return s, 0
    cut = s.rfind("\n", 0, max_chars)
    if cut < max_chars * 0.6:
        cut = s.rfind(" ", 0, max_chars)
        head = s[:cut].rstrip() + " …"
    else:
        head = s[:cut].rstrip()
    return head, len(s) - cut
