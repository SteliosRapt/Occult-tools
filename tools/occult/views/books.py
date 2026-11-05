"""Book view models: one plain-dict context per book PDF (stdlib only).

    books.spellbook(ix, "wizard")   books.equipment(ix)   books.quickref(ix)
    books.booklet(ix, "warlock")    books.glossary(ix)

Content blocks stay as in the JSON; templates/book/_blocks.j2 maps them to page.css classes
(the `inline` filter converts the stored markup). Every context has `title`, `kicker`, `footer`
(the running footer text) and `stats` (the counts printed by `make`).
"""
import re

from .. import components, data, query
from ._common import book_table, book_titles, caster_classes, page_ref
from . import creature
from .klass import progression

LEVEL_NAMES = {0: "Cantrips"}


def level_name(n):
    return LEVEL_NAMES.get(n, f"Level {n} Spells")


def plural(n, word, many=None):
    return f"{n} {word if n == 1 else many or word + 's'}"


def table(cols, rows, title=None):
    """A table built from data (not a JSON block) in the book_table shape."""
    return book_table({"title": title, "columns": cols, "rows": [[("" if c is None else str(c)) for c in r] for r in rows]})


def statblock(e):
    """A stat block printed inside a feature (Steel Defender, Beast of the Land) for the `statblock` macro.
    Values keep their stored markup (the `inline` filter converts it); every field but the name is optional."""
    d = e.data
    core = [(k, d.get(f)) for k, f in (("AC", "ac"), ("Initiative", "initiative"), ("HP", "hp"), ("Speed", "speed"))
            if d.get(f)]
    ab = d.get("abilities") or {}
    abilities = [[k, v.get("score"), v.get("modifier"), v.get("save") or v.get("modifier")] for k, v in ab.items()]
    return {"type_line": creature.type_line(d), "core": core, "abilities": abilities,
            "lines": [(lab, d[k]) for lab, k in creature.LINES if d.get(k)],
            "sections": [(t, [dict(x, more_texts=creature.more_texts(x.get("more"))) for x in d[k]])
                         for t, k in creature.SECTIONS if d.get(k)],
            "intros": {t: d[creature.INTROS[k]] for t, k in creature.SECTIONS if d.get(creature.INTROS.get(k, ""))}}


def node(e, depth, *, heading=None, skip=(), drop_tables=False, subtitle=None):
    """An entity subtree for the generic `tree` macro: heading level from depth (1 = h2)."""
    content = [b for b in e.content if b["type"] != "caption" and not (drop_tables and b["type"] == "table")]
    return {"sid": e.sid, "title": heading or e.title, "page": e.page, "depth": depth, "subtitle": subtitle,
            "content": content, "statblock": statblock(e) if e.type == "creature" else None,
            "children": [node(c, depth + 1, skip=skip) for c in e.children if c.type not in skip]}


# ---------------------------------------------------------------- spellbook
def spell_entry(e):
    d = e.data
    lvl = f"{d['school']} Cantrip" if d["level"] == 0 else f"Level {d['level']} {d['school']}"
    ct = d["casting_time"]
    if d["ritual"] and "Ritual" not in ct:
        ct += " or Ritual"
    return {"sid": e.sid, "title": e.title, "page": e.page, "meta": f"{lvl} ({', '.join(e.classes)})",
            "stats": [("Casting Time", ct), ("Range", d["range"]), ("Components", d["components"]),
                      ("Duration", d["duration"])],
            "content": [b for b in e.content if b["type"] != "caption"]}


# The spell-list Special column marks M only for a material with a cost or one the spell consumes.
COSTLY = re.compile(r"\bworth\b|\d[\d,]*\+? ?[GCSP]P\b|consume", re.I)


def special(d):
    costly = bool(COSTLY.search(d.get("material") or ""))
    return ", ".join(k for k, on in (("C", d["concentration"]), ("R", d["ritual"]), ("M", costly)) if on) or "—"


def max_spell_level(d, level):
    """The highest spell level a class casts at class level `level`: its slots, Pact Magic and Mystic
    Arcanum (0: cantrips only; None: no spells yet)."""
    seen = [x for x in d["levels"] if x["level"] <= level]
    top = max([int(k) for k in (seen[-1].get("spell_slots") or {})] + [seen[-1].get("pact_slot_level") or 0])
    for x in seen:
        for f in x["features"]:
            m = re.search(r"Mystic Arcanum \(level (\d) spell\)", f)
            top = max(top, int(m.group(1)) if m else 0)
    return top if top or seen[-1].get("cantrips_known") else None


def spellbook(ix, cls, level=None):
    """The spellbook context; `level` (class level 1-20) keeps the spells the class casts by then."""
    klass = ix.get(f"class:{cls}")
    ss = query.select(ix, "spell", {"class": cls})
    top = max_spell_level(klass.data, level) if level else 9
    if top is None:
        raise ValueError(f"a level {level} {klass.title} casts no spells yet")
    ss = [e for e in ss if e.data["level"] <= top]
    levels = []
    for e in ss:
        lv = e.data["level"]
        if not levels or levels[-1]["level"] != lv:
            levels.append({"level": lv, "name": level_name(lv), "spells": []})
        levels[-1]["spells"].append(e)
    for g in levels:
        g["index"] = table(["Spell", "School", "Special", "Page"],
                           [[e.title, e.data["school"], special(e.data), page_ref(e)] for e in g["spells"]], g["name"])
        g["spells"] = [spell_entry(e) for e in g["spells"]]
    sl = ix.resolve(f"section:{cls}-spell-list").entity
    note = next((b for b in sl.content if b["type"] == "paragraph"), None) if sl else None
    upto = f" (Level {level} {klass.title})" if level else ""
    return {"title": f"{klass.title} Spells", "kicker": f"Spellbook{' to Level ' + str(level) if level else ''}",
            "footer": f"Spellbook | {klass.title} Spells{upto}", "class": klass.title, "source_title": ix.books[0]["title"], "class_id": cls,
            "count": len(ss), "note": note, "levels": levels, "books": book_titles(ix, ss), "class_level": level,
            "stats": f"{plural(len(ss), 'spell')} · {plural(len(levels), 'level')}"}


# ---------------------------------------------------------------- equipment
def group_rows(ents, key, label, row):
    rows = []
    for e in ents:
        g = label(key(e))
        if not rows or rows[-1][1] != g:
            rows.append(([f"*{g}*"], g))
        rows.append((row(e), g))
    return [r for r, _ in rows]


def padded(rows, n):
    return [r + [""] * (n - len(r)) for r in rows]


ARMOR_ORDER = ["light", "medium", "heavy", "shield"]


def equipment(ix):
    """The first equipment chapter and the equipment entries in its book."""
    ch = next((e for e in ix.all("chapter") if e.title.lower().endswith("equipment")), None)
    if ch is None:
        raise data.NotFound("equipment chapter is not in this data set", data.Lookup())
    book_filter = {"book": ch.book}
    ws = query.select(ix, "weapon", book_filter)
    weapons = table(["Name", "Damage", "Properties", "Mastery", "Weight", "Cost"], padded(group_rows(
        ws, lambda e: (e.data["category"], e.data["kind"]), lambda k: f"{k[0].title()} {k[1].title()} Weapons",
        lambda e: [e.title, f"{e.data['damage']} {e.data['damage_type']}", e.data["properties_raw"] or "—",
                   e.data["mastery"], e.data.get("weight") or "—", e.data["cost"]]), 6), "Weapons")
    arm = sorted(query.select(ix, "armor", book_filter), key=lambda e: (ARMOR_ORDER.index(e.data["category"]), e.order))
    don = {e.data["category"]: e.data["don"] + " to Don and " + e.data["doff"] + " to Doff" for e in arm}
    armor = table(["Armor", "Armor Class (AC)", "Strength", "Stealth", "Weight", "Cost"], padded(group_rows(
        arm, lambda e: e.data["category"],
        lambda c: "Shield (" + don[c] + ")" if c == "shield" else f"{c.title()} Armor ({don[c]})",
        lambda e: [e.title, e.data["ac"], f"Str {e.data['strength_requirement']}" if e.data["strength_requirement"] else "—",
                   "Disadvantage" if e.data["stealth_disadvantage"] else "—", e.data["weight"], e.data["cost"]]), 6), "Armor")
    items = query.select(ix, "item", book_filter)
    tools = sorted((e for e in items if e.data.get("kind") == "tool"), key=lambda e: e.order)
    tool_t = table(["Tool", "Ability", "Weight", "Cost"], padded(group_rows(
        tools, lambda e: e.data["category"], lambda c: c,
        lambda e: [e.title, e.data.get("ability") or "—", e.data.get("weight") or "—", e.data.get("cost") or "—"]), 4), "Tools")
    gear = [e for e in items if e.data.get("kind") == "gear" and e.chapter() is ch]    # not the Trinket (ch. 2)
    gear_t = table(["Item", "Weight", "Cost"], [[e.title, e.data.get("weight") or "—", e.data.get("cost") or "—"] for e in gear],
                   "Adventuring Gear")

    def entry(e):
        cost = e.data.get("cost")
        return node(e, 3, heading=f"{e.title} ({cost})" if cost and cost != "Varies" else e.title)

    def sec(sid, built=None, skip=(), entries=None, wide=False):
        e = ix.get(sid)
        n = node(e, 0, skip=skip + ("weapon", "armor", "item"), drop_tables=built is not None)
        n.update(built=built, wide=wide, entries=entries or [])
        return n

    tool_secs = next((e for e in ch.children if e.slug == "tools"), None)
    sections = []
    for ref, built, entries, wide in (
        ("section:coins", None, None, False),
        ("section:weapons", weapons, None, True),
        ("section:armor", armor, None, True),
        (tool_secs.sid if tool_secs else None, tool_t, None, False),
        ("section:adventuring-gear", gear_t, [entry(e) for e in gear], False),
        ("section:mounts-and-vehicles", None, None, False),
        ("section:services", None, None, False),
    ):
        if ref and ix.resolve(ref):
            section = sec(ref, built, entries=entries, wide=wide)
            if tool_secs and ref == tool_secs.sid:
                for child, c in zip(section["children"], tool_secs.children):
                    child["entries"] = [entry(t) for t in c.children if t.type == "item"]
            sections.append(section)
    intro = [b for b in ch.content if b["type"] == "paragraph"]
    n = len(ws) + len(arm) + len(tools) + len(gear)
    return {"title": "Equipment", "kicker": "Catalogue", "footer": "Equipment Catalogue", "intro": intro,
            "sections": sections,
            "stats": f"{len(ws)} weapons + {len(arm)} armor + {len(tools)} tools + {len(gear)} gear = {n} items"}


# ---------------------------------------------------------------- quick reference
def term_entry(e):
    """A glossary term. The See also line is printed only when the prose does not already say it."""
    content = [b for b in e.content if b["type"] != "caption"]
    said = any("See also" in (b.get("text") or "") for b in content)
    return {"sid": e.sid, "title": e.title, "page": e.page, "tag": e.data.get("tag"),
            "see_also": [] if said else e.data.get("see_also") or [], "content": content}


def quickref(ix):
    cond = [term_entry(e) for e in query.select(ix, "condition")]
    act = [term_entry(e) for e in query.select(ix, "action")]
    aoe = [term_entry(e) for e in query.select(ix, "term", {"tag": "Area of Effect"})]
    cover_node = ix.resolve("term:cover").entity
    cover = [term_entry(cover_node)] if cover_node else []
    pages = [{"title": "Conditions", "groups": [("Conditions", cond), ("Areas of Effect", aoe)]},
             {"title": "Actions", "groups": [("Actions", act), ("Cover", cover)]}]
    return {"title": "Conditions & Actions", "kicker": "Quick Reference", "footer": "Quick Reference",
            "pages": pages,
            "stats": f"{len(cond)} conditions + {len(act)} actions + {len(aoe)} areas of effect + cover"}


# ---------------------------------------------------------------- glossary
def glossary(ix):
    rd = ix.resolve("section:rules-definitions").entity
    terms = sorted((term_entry(e) for e in (rd.children if rd else ix.all("term")) if e.type == "term"), key=lambda t: t["title"].lower())
    letters = []
    for t in terms:
        L = t["title"][:1].upper()
        if not letters or letters[-1]["letter"] != L:
            letters.append({"letter": L, "terms": []})
        letters[-1]["terms"].append(t)
    conv = ix.resolve("section:glossary-conventions").entity
    return {"title": "Rules Glossary", "kicker": "Appendix C", "footer": "Rules Glossary",
            "intro": conv.content if conv else [], "intro_title": conv.title if conv else "", "letters": letters,
            "stats": f"{plural(len(terms), 'term')} · {plural(len(letters), 'letter')}"}


# ---------------------------------------------------------------- class booklet
def spell_list(ix, klass, secs, top=None):
    """Rebuild the printed spell-list tables from the data, so spells other books add to the class
    are listed too; each table keeps its printed title and gains a Source column.
    `top`: only spell levels up to it (a subclass booklet with --class-features)."""
    try:
        sl = ix.get(f"section:{klass.title.lower()}-spell-list")
    except data.NotFound:                # not a caster
        return
    found = next((n for s in secs for n in walk_nodes(s) if n["sid"] == sl.sid), None)
    if not found:
        return
    by_level = {}
    for sp in query.select(ix, "spell", {"class": klass.title.lower()}):
        by_level.setdefault(sp.data["level"], []).append(sp)
    tables = []
    for lv, ss in sorted(by_level.items()):
        if top is not None and lv > top:
            continue
        title = f"Cantrips (Level 0 {klass.title} Spells)" if lv == 0 else f"Level {lv} {klass.title} Spells"
        rows = [[f"*{sp.title}*", sp.data["school"], special(sp.data), page_ref(sp)]
                for sp in sorted(ss, key=lambda s: s.title)]
        tables.append({"type": "table", "title": title, "columns": ["Spell", "School", "Special", "Source"],
                       "rows": rows})
    found["content"] = [b for b in found["content"] if b["type"] != "table"] + tables


def walk_nodes(n):
    yield n
    for c in n.get("children", []):
        yield from walk_nodes(c)


# A booklet to a class level (`make class --level N`): features, options and subclass features up to N,
# the subclass art together on one gallery page, and the spells the class casts by then in full.
OPTION_LEVEL = re.compile(r"\bLevel (\d+)\+")


def over_level(ix, n, level):
    """Whether a booklet node is past `level`: a feature of a higher level, an option whose prerequisite
    asks for one, or a subclass the class only takes later."""
    try:
        e = ix.get(n["sid"])
    except (data.NotFound, KeyError):
        return False
    if e.type == "feature":
        return (e.data.get("level") or 0) > level
    if e.type == "option":
        m = OPTION_LEVEL.search(e.data.get("prerequisite") or "")
        return bool(m) and int(m.group(1)) > level
    return False


def prune(ix, n, level):
    n["children"] = [prune(ix, c, level) for c in n.get("children") or [] if not over_level(ix, c, level)]
    return n




def class_subclass(ix, cls, ref):
    """The subclass of class `cls` that `ref` names (slug, id or title), from any book; ValueError otherwise."""
    subs = query.select(ix, "subclass", {"class": cls})
    for se in subs:
        if ref in (se.slug, se.sid, se.sid.split(":", 1)[1]) or ref.lower() == se.title.lower():
            return se
    raise ValueError(f"--subclass '{ref}' is not a {cls} subclass; try one of: {', '.join(se.slug for se in subs)}")


ADD_TYPES = ("background", "species", "feat")


def extras(ix, refs, sid):
    """`--add`: a Character Options section of backgrounds, species and feats, in the order given, each in
    full under a subtitle that names its kind and book. ValueError for an unknown id or another type."""
    titles = {b["short"]: b["title"] for b in ix.books}
    kids = []
    for ref in refs:
        e = ix.get(ref)
        if e.type not in ADD_TYPES:
            raise ValueError(f"--add takes {', '.join(ADD_TYPES)} ids, not {e.sid} ({e.type})")
        kind = {"background": "Background", "species": "Species"}.get(e.type) or (
            f"{e.data.get('category') or ''} Feat".strip() + (f" (Prerequisite: {e.data['prerequisite']})"
                                                             if e.data.get("prerequisite") else ""))
        kids.append(node(e, 2, subtitle=" · ".join(x for x in (kind, titles.get(e.book)) if x)))
    return {"sid": f"{sid}/character-options", "title": "Character Options", "page": None, "depth": 1,
            "subtitle": None, "content": [], "statblock": None, "children": kids}


def booklet(ix, cls, level=None, subclass=None, class_features=None, add=None):
    e = ix.get(f"class:{cls}")
    only = class_subclass(ix, cls, subclass) if subclass else None
    d = e.data
    traits = next((b for b in e.content if b["type"] == "table"), None)
    intro = [b for b in e.content if b["type"] == "paragraph"]
    cols, rows = progression(d)
    prog = table(cols, rows, f"{e.title} Features")
    secs = []
    for c in e.children:
        if c.title.endswith("Class Features"):
            n = node(c, 1, drop_tables=True)
            n["built"] = prog
            for f, fe in zip(n["children"], c.children):
                if fe.type == "feature":
                    f["title"] = f"Level {fe.data['level']}: {fe.title}"
        elif c.title.endswith("Subclasses"):
            n = node(c, 0)
            n["break"] = True
            for s, se in zip(n["children"], c.children):
                if se.type == "subclass":
                    s["subtitle"] = se.data.get("tagline")
                    components.apply("subclass_model", s, se)
                    for f, fe in zip(s["children"], se.children):
                        if fe.type == "feature" and fe.data.get("level"):
                            f["title"] = f"Level {fe.data['level']}: {fe.title}"
        else:
            n = node(c, 1)
        secs.append(n)
    # subclasses other books print for this class (data.class), labelled with their book
    others = [s for s in query.select(ix, "subclass", {"class": cls}) if e not in s.ancestors()]
    if others:
        titles = {b["short"]: b["title"] for b in ix.books}
        kids = []
        for se in others:
            s = node(se, 1, subtitle=" · ".join(x for x in (se.data.get("tagline"), titles.get(se.book)) if x))
            components.apply("subclass_model", s, se)
            for f, fe in zip(s["children"], se.children):
                if fe.type == "feature" and fe.data.get("level"):
                    f["title"] = f"Level {fe.data['level']}: {fe.title}"
            kids.append(s)
        group = {"sid": f"{e.sid}/other-subclasses", "title": f"{e.title} Subclasses in Other Books", "group": True}
        subsec = next((s for s in secs if s.get("break")), None)
        if subsec:                                   # run on in the same columns, under a group heading
            subsec["children"] += [group] + kids
        else:
            secs.append({**group, "page": None, "depth": 0, "subtitle": None, "content": [], "statblock": None,
                         "children": kids, "break": True})
    if only:                                         # `--subclass S`: that subclass alone, no class chapters
        sec = next(s for s in secs if s.get("break"))
        sec["children"] = [n for n in sec["children"] if n.get("sid") == only.sid]
        sec["title"], sec["content"], sec["only"] = None, [], True
        sec["run_on"] = not class_features            # under the opener; after class features, a new page
        feats_sec = next((s for s in secs if s.get("built")), None)
        list_sec = next((s for s in secs if s["sid"].endswith("-spell-list")), None)
        secs = [sec]
        if class_features and feats_sec:             # `--class-features N`: the class features to level N first
            feats_sec["built"]["rows"] = feats_sec["built"]["rows"][:class_features]
            fs = prune(ix, feats_sec, class_features)
            # "Warlock Subclass: you gain a subclass" is only a pointer: the booklet prints the subclass in full
            fs["children"] = [n for n in fs["children"] if ix.get(n["sid"]).title != f"{e.title} Subclass"]
            secs.insert(0, fs)
            top = max_spell_level(d, class_features)
            if list_sec and top is not None:         # the class spell list, to the spell levels cast by level N
                spell_list(ix, e, [list_sec], top)
                secs.insert(1, list_sec)
    elif class_features:
        raise ValueError("--class-features needs --subclass")
    else:
        spell_list(ix, e, secs)
    if add:                                          # `--add`: backgrounds, species and feats at the end, or, after
        extra = extras(ix, add, e.sid)               # class features, before the subclass (level 1 choices first)
        if only and class_features:
            secs.insert(len(secs) - 1, extra)        # just before the subclass
        else:
            secs.append(extra)
    subs = query.select(ix, "subclass", {"class": cls})
    feats = query.select(ix, "feature", {"class": cls})
    opts = [o for o in ix.all("option") if o.owner_class == cls]
    sc = d.get("spellcasting")
    spells = None
    if level:
        prog["rows"] = prog["rows"][:level]
        secs = [prune(ix, s, level) for s in secs if not s["sid"].endswith("-spell-list")]
        if level < (d.get("subclass_level") or 0):
            if only:
                raise ValueError(f"a level {level} {e.title} has no subclass yet (level {d.get('subclass_level')})")
            secs = [s for s in secs if not s.get("break")]
        components.apply("booklet_level", secs)
        if e.title in caster_classes(ix) and max_spell_level(d, level) is not None:
            spells = spellbook(ix, cls, level)
        ids = {n["sid"] for s in secs for n in walk_nodes(s)}
        subs, feats, opts = ([x for x in xs if x.sid in ids] for xs in (subs, feats, opts))
    upto = f" to Level {level}" if level else ""
    if only:
        ids = {n["sid"] for s in secs for n in walk_nodes(s)}
        feats = [f for f in feats if f.sid in ids]
        return {"title": only.title, "kicker": f"{e.title} Subclass{upto}",
                "footer": f"{e.title} Subclass | {only.title}{upto}", "tagline": None,
                "source_title": ix.books[0]["title"], "class_id": cls, "class_title": e.title, "intro": [], "sections": secs, "level": level, "spells": None,
                # with the class features, the Core Traits box too: saves, skills, equipment at level 1
                "traits": book_table(traits) if traits and class_features else None,
                "caster": False, "span_heads": bool(class_features),
                "stats": " · ".join([plural(len(feats), "feature"), "1 subclass"]
                                    + ([plural(len(add), "added option")] if add else []))}
    return {"title": e.title, "kicker": f"Class Booklet{upto}", "footer": f"Class Booklet | {e.title}{upto}",
            "tagline": d.get("tagline"), "source_title": ix.books[0]["title"], "class_id": cls, "intro": intro,
            "traits": book_table(traits) if traits else None, "sections": secs, "level": level, "spells": spells,
            "caster": e.title in caster_classes(ix) and bool(sc),
            "stats": " · ".join([plural(len(feats), "feature"), plural(len(subs), "subclass", "subclasses")]
                                + ([plural(len(opts), "option")] if opts else [])
                                + ([plural(spells["count"], "spell")] if spells else [])
                                + ([plural(len(add), "added option")] if add else []))}
