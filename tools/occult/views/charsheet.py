"""The PDF character sheet's context: an engine sheet (rules.character.build) plus the texts it names (stdlib only).

    ctx = charsheet.context(ix, sheet)     # for templates/book/character.html.j2

Page 1 is the front sheet (abilities, saves, skills, combat, attacks, trackers, gear); then the
features, traits, feats and options in full; then the spells (slot trackers, the list, the texts).
"""
import re

from .. import data
from ..rules import core
from ..rules.tables import ABILITIES, ABILITY_NAMES
from ._common import page_ref
from .books import node, spell_entry

s = core.signed

# Class table columns that count uses (a checkbox each); the others print as values.
USES = {"Rages", "Channel Divinity", "Wild Shape", "Second Wind", "Focus Points", "Sorcery Points", "Favored Enemy"}
MAX_BOXES = 20
# Class features that only point elsewhere: the chosen subclass and feats print in their own place.
POINTERS = re.compile(r"^(?:.+ Subclass|Ability Score Improvement|Epic Boon|Fighting Style|Additional Fighting Style)$")
DETAILS = [("appearance", "Appearance"), ("personality", "Personality"), ("ideals", "Ideals"), ("bonds", "Bonds"),
           ("flaws", "Flaws"), ("backstory", "Backstory"), ("allies", "Allies and Organizations"), ("notes", "Notes")]
FIELDS = [("player", "Player"), ("alignment", "Alignment"), ("age", "Age"), ("deity", "Deity"), ("campaign", "Campaign")]


def _title(ix, sid):
    return ix.get(sid).title if sid else None


def _num(v):
    m = re.fullmatch(r"\d+", str(v).strip())
    return int(m.group()) if m else None


def _ref(e):
    p = page_ref(e)
    return f"p{p}" if isinstance(p, int) else p


def front(ix, sh):
    ab = sh["abilities"]
    sk = sh["skills"]
    skills = [{"title": v["title"], "ability": v["ability"].upper(), "bonus": s(v["bonus"]),
               "mark": "expertise" if v["expertise"] else "proficient" if v["proficient"] else ""}
              for v in sorted(sk.values(), key=lambda v: v["title"])]
    trackers = []
    for cls, cols in sh["resources"].items():
        for k, v in cols.items():
            n = _num(v)
            if k in USES and n:
                trackers.append({"label": k, "of": cls, "boxes": min(n, MAX_BOXES), "value": v if n > MAX_BOXES else None})
    counts = [{"label": k, "of": cls, "value": v} for cls, cols in sh["resources"].items()
              for k, v in cols.items() if not (k in USES and _num(v))]
    hd = sh["hit_dice"]
    sc = sh.get("spellcasting")
    pr = sh["proficiencies"]
    return {
        "abilities": [{"key": a, "name": ABILITY_NAMES[a], "short": a.upper(), "score": ab[a]["score"],
                       "mod": s(ab[a]["mod"]), "save": s(ab[a]["save"]), "save_prof": ab[a]["save_proficient"]}
                      for a in ABILITIES],
        "skills": skills,
        "ac": sh["armor_class"], "hp": sh["hit_points"]["max"], "hp_breakdown": sh["hit_points"]["breakdown"],
        "initiative": s(sh["initiative"]["bonus"]), "initiative_adv": sh["initiative"]["advantage"],
        "speed": sh["speed"]["walk"], "pb": s(sh["proficiency_bonus"]), "passive": sh["passive_perception"],
        "passive_investigation": 10 + sk["investigation"]["bonus"], "passive_insight": 10 + sk["insight"]["bonus"],
        "size": sh["size"],
        "hit_dice": [{"die": d, "n": n} for d, n in hd.items()],
        "attacks_per_action": sh["attacks_per_action"],
        "attacks": [{"name": a["name"], "attack": s(a["attack"]), "damage": a["damage"],
                     "notes": "; ".join(x for x in (f"two-handed {a['two_handed']}" if a.get("two_handed") else None,
                                                    a.get("properties"),
                                                    f"Mastery: {a['mastery']}" if a.get("mastery") else None,
                                                    None if a["proficient"] else "not proficient") if x)}
                    for a in sh["attacks"]],
        "casting": [{"class": c["class"] + (f" ({c['via']})" if c["via"] else ""), "ability": c["ability"].upper(),
                     "dc": c["save_dc"], "attack": s(c["attack"])} for c in (sc or {}).get("casters", [])],
        "trackers": trackers, "counts": counts,
        "armor": ", ".join(x.title() for x in pr["armor"]) or "None",
        "weapons": ", ".join(x.replace("-", " ").title() for x in pr["weapons"]) or "None",
        "tools": ", ".join(pr.get("tools") or []) or "None",
        "languages": ", ".join(sh.get("languages") or []),
        "equipment": sh.get("equipment") or [],
        "coins": [(k.upper(), (sh.get("coins") or {}).get(k, "")) for k in ("cp", "sp", "ep", "gp", "pp")],
        "carry": f"{_n(sh['carrying_capacity']['carry_lb'])} lb.",
        "drag": f"{_n(sh['carrying_capacity']['drag_lift_push_lb'])} lb.",
        "stealth_disadvantage": sh["armor_class"].get("stealth_disadvantage"),
        "notes": sh["notes"],
    }


def _n(x):
    return int(x) if float(x).is_integer() else x


def features(ix, sh):
    """[{title, items: [node]}]: class features by class (each once, at its first level), the subclass
    intro, species traits, feats and options, each with its full text."""
    groups = []
    seen = set()
    subs = {c["title"]: c["subclass"] for c in sh["classes"] if c["subclass"]}
    for c in sh["classes"]:
        items = []
        for f in (f for f in sh["features"] if f["class"] == c["title"]):
            key = f["id"] or (f["class"], f["title"])
            if key in seen or POINTERS.match(f["title"]):
                continue
            seen.add(key)
            if f["id"]:
                e = ix.get(f["id"])
                n = node(e, 2, heading=f"Level {f['level']}: {e.title}")
                n["ref"] = _ref(e)
            else:
                n = {"sid": "", "title": f"Level {f['level']}: {f['title']}", "depth": 2, "content": [],
                     "children": [], "statblock": None, "subtitle": None, "ref": None}
            if subs.get(c["title"]) and f["id"] and ix.get(f["id"]).parent is ix.get(subs[c["title"]]):
                n["sub"] = True
            items.append(n)
        sub = subs.get(c["title"])
        intro = None
        if sub:
            e = ix.get(sub)
            intro = {"title": e.title, "content": [b for b in e.content if b["type"] != "caption"], "ref": _ref(e)}
        groups.append({"title": f"{c['title']} Features", "intro": intro,
                       "items": [n for n in items if not n.get("sub")], "sub_items": [n for n in items if n.get("sub")]})
    if sh["species"]:
        sp = ix.get(sh["species"])
        traits = ix.resolve(f"section:{sp.slug}-traits")
        e = traits.entity if traits else sp
        groups.append({"title": f"{sp.title} Traits", "intro": None, "sub_items": [], "ref": _ref(e),
                       "items": [dict(node(e, 2, heading=e.title), ref=_ref(e), bare=True)]})
    if sh["feats"]:
        items = []
        for f in sh["feats"]:
            e = ix.get(f["id"])
            n = node(e, 2, subtitle=f"{e.data.get('category') or 'Feat'} Feat" + (
                f" (Prerequisite: {e.data['prerequisite']})" if e.data.get("prerequisite") else "")
                + (", from your background" if f["source"] == "background" else "")
                + (": " + ", ".join(f"{ABILITY_NAMES[a]} +{v}" for a, v in f["increase"].items()) if f.get("increase") else ""))
            n["ref"] = _ref(e)
            items.append(n)
        groups.append({"title": "Feats", "intro": None, "items": items, "sub_items": []})
    if sh.get("options"):
        items = []
        for o in sh["options"]:
            e = ix.get(o["id"])
            n = node(e, 2, subtitle=o["of"])
            n["ref"] = _ref(e)
            items.append(n)
        groups.append({"title": "Options", "intro": None, "items": items, "sub_items": []})
    return groups


def spells(ix, sh):
    sc = sh.get("spellcasting")
    chosen = sh.get("spells") or []
    if not sc and not chosen:
        return None
    slots = [{"level": int(k), "n": v} for k, v in ((sc or {}).get("slots") or {}).items()]
    pact = (sc or {}).get("pact")
    rows, levels = [], []
    for x in chosen:
        e = ix.get(x["id"])
        tags = "".join(t for t, on in (("C", x["concentration"]), ("R", x["ritual"])) if on)
        rows.append({"title": x["title"], "level": "Cantrip" if x["level"] == 0 else x["level"],
                     "time": re.sub(r",.*", "", x["casting_time"]).replace(" or Ritual", ""),
                     "range": re.sub(r"\b(\d+) feet\b", r"\1 ft.", x["range"]), "tags": tags,
                     "components": re.sub(r"\s*\(.*\)", "", x["components"]),
                     "via": x["source"] or x["class"] or "", "prepared": x["prepared"], "always": bool(x["source"]),
                     "page": _ref(e), "cantrip": x["level"] == 0})
        if not levels or levels[-1]["level"] != x["level"]:
            levels.append({"level": x["level"], "name": "Cantrips" if x["level"] == 0 else f"Level {x['level']} Spells",
                           "spells": []})
        levels[-1]["spells"].append(spell_entry(e))
    casters = [{"class": c["class"] + (f" ({c['via']})" if c["via"] else ""), "ability": ABILITY_NAMES[c["ability"]],
                "dc": c["save_dc"], "attack": s(c["attack"]), "cantrips": c["cantrips"], "prepared": c["prepared"],
                "top": c["max_spell_level"], "list": c["spell_list"].title()} for c in (sc or {}).get("casters", [])]
    return {"casters": casters, "slots": slots, "pact": pact, "rows": rows, "levels": levels,
            "blank_rows": 0 if rows else 24, "cantrip_dice": (sc or {}).get("cantrip_dice"),
            "multiclass": (sc or {}).get("multiclass_table"), "caster_level": (sc or {}).get("caster_level")}


def glance(sh):
    """Page 1's index of what the character has: [(heading, [title...])] (the texts follow on page 2)."""
    out = []
    for c in sh["classes"]:
        seen, items = set(), []
        for f in sh["features"]:
            if f["class"] == c["title"] and f["title"] not in seen and not POINTERS.match(f["title"]):
                seen.add(f["title"])
                items.append(f"{f['title']} ({f['level']})")
        out.append((f"{c['title']}" + (f" · {c['subclass_title']}" if c["subclass_title"] else ""), items))
    if sh.get("species_traits"):
        out.append(("Species", list(sh["species_traits"])))
    if sh["feats"]:
        out.append(("Feats", [f["title"] for f in sh["feats"]]))
    if sh.get("options"):
        out.append(("Options", [o["title"] for o in sh["options"]]))
    return out


def context(ix, sh):
    cls_line = " / ".join(f"{c['title']} {c['level']}" + (f" ({c['subclass_title']})" if c["subclass_title"] else "")
                          for c in sh["classes"])
    det = sh.get("details") or {}
    fields = [("Class & Level", cls_line), ("Species", _title(ix, sh["species"]) or ""),
              ("Background", _title(ix, sh["background"]) or "")]
    fields += [(lab, det[k]) for k, lab in FIELDS if det.get(k)]
    xp = sh["xp"]
    fields.append(("Experience", f"{xp['this_level']:,}" + (f" / {xp['next_level']:,}" if xp["next_level"] else "")))
    choices = [(k.replace("_", " ").title(), v) for k, v in (sh.get("choices") or {}).items()]
    first = data.slugify(sh["classes"][0]["title"])
    sp = spells(ix, sh)
    feats = features(ix, sh)
    n_feat = sum(len(g["items"]) + len(g["sub_items"]) for g in feats)
    return {"title": f"{sh['name']}: Character Sheet", "kicker": "Character Sheet", "name": sh["name"],
            "footer": f"Character Sheet | {sh['name']}", "level": sh["level"], "class_line": cls_line,
            "class_icon": f"class-{first}", "fields": fields, "choices": choices, "front": front(ix, sh), "glance": glance(sh),
            "glance_count": sum(len(x) for _, x in glance(sh)),
            "features": feats, "spells": sp,
            "details": [(lab, det[k]) for k, lab in DETAILS if det.get(k)],
            "stats": f"level {sh['level']} · {n_feat} feature texts"
                     + (f" · {len(sp['rows'])} spells" if sp and sp["rows"] else "")}
