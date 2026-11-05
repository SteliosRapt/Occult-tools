"""Creature (stat block) card view model: tarot size, 2x2 on a sheet.

Formula stat blocks (summons, companions) print values such as `12 + your Intelligence modifier`;
an Object stat block  has no abilities, speed, alignment or CR, so every
one of those is optional here and in `statblock_md`.

Traits and actions are `{name, text, more?}`: `text` is the run-in paragraph, `more` the blocks
that follow it (a list of options, a spellcasting list, extra paragraphs). A legendary creature
has `legendary_actions` with `legendary_header` as their intro, and may name its lair
(`legendary_group`, a legendary-group node id).
"""
from .. import text
from ._common import html, key

LINES = [("Skills", "skills"), ("Vulnerabilities", "vulnerabilities"), ("Resistances", "resistances"),
         ("Immunities", "immunities"), ("Gear", "gear"), ("Senses", "senses"), ("Languages", "languages")]
SECTIONS = [("Traits", "traits"), ("Actions", "actions"), ("Bonus Actions", "bonus_actions"), ("Reactions", "reactions"),
            ("Legendary Actions", "legendary_actions")]
INTROS = {"legendary_actions": "legendary_header"}


def type_line(d):
    """`Medium Construct, Neutral`; `Small or Tiny Object` when no alignment is printed."""
    head = " ".join(x for x in (d.get("size"), d.get("type")) if x)
    if d.get("tags"):
        head += f" ({', '.join(d['tags'])})"
    return f"{head}, {d['alignment']}" if d.get("alignment") else head


def more_texts(blocks):
    """The blocks after an entry's run-in, as inline-markup paragraphs (list items one each)."""
    out = []
    for b in blocks or []:
        if b["type"] == "list":
            out += [(f"**{i['label']}.** " if i.get("label") else "") + i.get("text", "") for i in b["items"]]
        elif b["type"] in ("paragraph", "heading"):
            out.append((f"**{b['label']}.** " if b.get("label") else "") + b.get("text", ""))
    return out


def lair(ix, d):
    """The legendary group's title, or None."""
    g = ix.get(d["legendary_group"]) if d.get("legendary_group") and ix is not None else None
    return g.title if g else None


def card(ix, e):
    d = e.data
    rated = d.get("cr") not in (None, "None")      # summoned creatures (spirits, steeds) have no CR
    abilities = list((d.get("abilities") or {}).items())

    def entries(k):
        return [{"name": x["name"], "html": html(x["text"]), "more": [html(m) for m in more_texts(x.get("more"))]}
                for x in d.get(k) or []]

    if rated:
        xp = f"{d.get('xp')} XP" + (f" ({d['xp_lair']} in lair)" if d.get("xp_lair") else "")
        foot = f"CR {d['cr']} · {xp} · PB {d.get('proficiency_bonus')}"
    elif abilities:
        foot = "No CR · uses your Proficiency Bonus"
    else:
        foot = "Object · no CR"
    lines = [(lab, html(d[k], False)) for lab, k in LINES if d.get(k)]
    if lair(ix, d):
        lines.append(("Lair", html(f"*{lair(ix, d)}*", False)))
    return {
        "kind": "creature", "size": "tarot", "key": key(e), "title": e.title, "page": e.page,
        "type_line": type_line(d),
        # stat values are HTML (stored inline markup such as the Cannon's *Mending*), no scan aids
        "ac": html(d.get("ac") or "—", False), "hp": html(d.get("hp") or "—", False),
        "speed": html(d["speed"], False) if d.get("speed") else None,
        "initiative": d.get("initiative") or "—", "object": not abilities,
        "abilities": abilities if len(abilities) == 6 else [],
        "lines": lines,
        "cr": d["cr"] if rated else "—",
        "foot": foot,
        "sections": [(t, entries(k)) for t, k in SECTIONS if d.get(k)],
        "intros": {t: html(d[INTROS[k]]) for t, k in SECTIONS if d.get(k) and d.get(INTROS.get(k, ""))},
    }


# ---------------------------------------------------------------- `show` (Markdown)
def statblock_md(d, ix=None):
    def ab(k, v):
        save = f", save {v['save']}" if v.get("save") and v["save"] != v["modifier"] else ""
        return f"{k} {v['score']} ({v['modifier']}{save})"
    md = lambda s: text.inline(s, "md")
    out = []
    if d.get("abilities"):
        out.append(" · ".join(ab(k, v) for k, v in d["abilities"].items()))
    misc = [f"{lab} {md(d[k])}" for lab, k in LINES if d.get(k)]
    if lair(ix, d):
        misc.append(f"Lair *{lair(ix, d)}*")
    if misc:
        out.append("\n".join(misc))
    for lab, k in SECTIONS:
        if d.get(k):
            intro = [md(d[INTROS[k]])] if d.get(INTROS.get(k, "")) else []
            items = []
            for x in d[k]:
                items.append(f"- **{md(x['name'])}.** {md(x['text'])}".rstrip())
                for chunk in text.blocks_md(x.get("more") or []):      # continuation of the list item
                    items.append("\n".join("  " + ln for ln in chunk.split("\n")))
            out.append(f"#### {lab}\n" + "\n".join(intro + items))
    return "\n\n".join(out)
