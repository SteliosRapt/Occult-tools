"""Weapon card view model: damage hero, property and mastery rules (no emblem)."""
import re
from html import escape

from .. import data, text
from ._common import html, key, paragraphs


def prop_label(p):
    bits = []
    if p.get("range"):
        bits.append(f"{p['range']['normal']}/{p['range']['long']}")
    if p.get("ammunition"):
        bits.append(p["ammunition"])
    if p.get("damage"):
        bits.append(p["damage"])
    if p.get("condition"):
        bits.append(p["condition"])
    return p["name"] + (f" ({'; '.join(bits)})" if bits else "")


def rule(ix, t, title):
    return next((r for r in ix.all(t) if r.title == title), None)


def card(ix, e):
    d = e.data
    props = []
    for p in d["properties"]:
        r = rule(ix, "weapon-property", p["name"])
        body = paragraphs(r) if r else ""
        m = re.match(r"(.+?\.)(\s|$)", body)
        first = m.group(1) if m else body
        label = prop_label(p)
        short = (f'<b class="lab">{escape(label)}.</b> {html(first)} <i class="see">({data.book_abbr(e.book)}{f" {e.page}" if e.page is not None else ""})</i>'
                 if first != body else None)        # HTML that fit.js swaps in (data-short)
        props.append({"label": label, "html": html(body), "short": short})
    m = rule(ix, "mastery-property", d["mastery"])
    finesse = any(p["name"] == "Finesse" for p in d["properties"])
    ability = "dexterity" if d["kind"] == "ranged" else ("finesse" if finesse else "strength")
    versatile = next((p.get("damage") for p in d["properties"] if p["name"] == "Versatile"), None)
    return {
        "kind": "weapon", "size": "poker", "key": key(e), "title": e.title, "page": e.page,
        "type_line": f"{d['category'].title()} {d['kind'].title()} Weapon",
        "damage": d["damage"], "damage_type": d["damage_type"], "versatile": versatile,
        "ability": ability, "props_short": [prop_label(p) for p in d["properties"]],
        "props": props, "mastery": d["mastery"], "mastery_html": html(paragraphs(m)) if m else "",
        "weight": d.get("weight") or "—", "cost": d.get("cost") or "—",
    }


# ---------------------------------------------------------------- `show` (Markdown)
def prop_label_md(p):
    bits = []
    if p.get("range"):
        bits.append(f"Range {p['range']['normal']}/{p['range']['long']}")
    if p.get("ammunition"):
        bits.append(p["ammunition"])
    if p.get("damage"):
        bits.append(p["damage"])
    if p.get("condition"):
        bits.append(p["condition"])
    return p["name"] + (f" ({'; '.join(bits)})" if bits else "")


def weapon_rules(ix, e):
    """Property and mastery rule text, so one `show` answers what the weapon does."""
    out = []
    for p in e.data["properties"]:
        rule = next((r for r in ix.all("weapon-property") if r.title == p["name"]), None)
        body = " ".join(b["text"] for b in rule.content if b["type"] == "paragraph") if rule else ""
        out.append(text.inline(f"**{prop_label_md(p)}.** {body}".rstrip()))
    m = next((r for r in ix.all("mastery-property") if r.title == e.data["mastery"]), None)
    if m:
        out.append(text.inline(f"**Mastery: {m.title}.** " + " ".join(b["text"] for b in m.content if b["type"] == "paragraph")))
    return out
