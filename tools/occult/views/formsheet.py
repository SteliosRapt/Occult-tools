"""The official D&D 2024 character sheet's fields, filled from an engine sheet (stdlib only).

    ctx = formsheet.context(ix, sheet)     # for templates/form/dnd-2024.html.j2

The form is Wizards of the Coast's two-page sheet (forms/README.md). The template prints only the
values, at the positions style/forms/dnd-2024.css measures on that PDF; pipeline.run_form stamps them
onto it. Fields the spec leaves out (appearance, backstory, current HP ...) stay blank for a pencil.
"""
import re

from .. import text
from ..rules import core
from ..rules.character import UNNAMED
from ..rules.tables import ABILITIES, ABILITY_NAMES
from .charsheet import POINTERS, _title

s = core.signed

WEAPON_ROWS = 6           # the form's Weapons & Damage Cantrips table
SPELL_ROWS = 30           # its Cantrips & Prepared Spells table
DAMAGE = re.compile(r"\b(\d+)(d\d+)(?: \+ \d+)? (" + text.DAMAGE_TYPES + r") damage\b")
SAVE = re.compile(r"\b(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) saving throw\b")
PERSONALITY = [("personality", "Personality"), ("ideals", "Ideals"), ("bonds", "Bonds"), ("flaws", "Flaws"),
               ("backstory", "Backstory"), ("allies", "Allies and Organizations")]


def plain(s):
    return text.inline(s, "plain").strip()


def paragraphs(e, first_only=False):
    """[(label, text)] of an entity's paragraphs, plain text; lists and tables are left to the full PDF."""
    out = []
    for b in e.content:
        if b["type"] == "paragraph" and b.get("text"):
            out.append((b.get("label"), plain(b["text"])))
            if first_only:
                break
    return out


def item(ix, sid, title, first_only=True, note=None):
    """A box entry: its title, a note (level, choice) and its text (the first paragraph, or every one)."""
    e = ix.get(sid) if sid else None
    return {"title": title, "note": note, "paras": paragraphs(e, first_only) if e else []}


def class_features(ix, sh):
    """Class features (each once), then the options (invocations ...) and the spec's free-form choices."""
    out, seen = [], set()
    for f in sh["features"]:
        if f["title"] in seen or POINTERS.match(f["title"]):
            continue
        seen.add(f["title"])
        note = f"{f['class']} {f['level']}" if len(sh["classes"]) > 1 else f"Level {f['level']}"
        out.append(item(ix, f["id"], f["title"], note=note))
    for o in sh.get("options") or []:
        out.append(item(ix, o["id"], o["title"], first_only=False, note=re.sub(r" Options$", "", o["of"])))
    for k, v in (sh.get("choices") or {}).items():
        out.append({"title": k.replace("_", " ").capitalize(), "note": None, "paras": [(None, str(v))]})
    return out


def species_traits(ix, sh):
    """The species' traits section, minus the lines the front already shows (type, size, speed)."""
    if not sh["species"]:
        return []
    sp = ix.get(sh["species"])
    r = ix.resolve(f"section:{sp.slug}-traits")
    e = r.entity if r else sp
    out = []
    for lab, t in paragraphs(e):
        if lab:
            out.append({"title": lab, "note": None, "paras": [(None, t)]})
        elif out:                                   # a trait's continuation paragraph
            out[-1]["paras"].append((None, t))
    return [x for x in out if x["title"] not in ("Size", "Speed")]


def feats(ix, sh):
    return [item(ix, f["id"], f["title"], first_only=False,
                 note="Background" if f["source"] == "background" else None) for f in sh["feats"]]


def cantrip_row(ix, x, caster, dice):
    """A damage cantrip as a weapon row: to hit or save DC, damage scaled by the cantrip upgrade."""
    e = ix.get(x["id"])
    body = " ".join(t for lab, t in paragraphs(e) if lab != "Cantrip Upgrade")
    m = DAMAGE.search(body)
    if not m:
        return None
    upgrade = " ".join(t for lab, t in paragraphs(e) if lab == "Cantrip Upgrade")
    n = int(m.group(1))
    beams = re.search(r"\bbeams?\b", upgrade)
    damage = f"{n * dice if not beams else n}{m.group(2)} {m.group(3)}"
    sv = SAVE.search(body)
    hit = f"DC {caster['save_dc']} {sv.group(1)[:3]}" if sv else s(caster["attack"])
    notes = [re.sub(r"\b(\d+) feet\b", r"\1 ft.", x["range"])]
    if beams and dice > 1:
        notes.append(f"{dice} beams")
    return {"name": x["title"], "hit": hit, "damage": damage, "notes": ", ".join(notes)}


def weapons(ix, sh):
    """The weapon rows (each weapon once; Unarmed Strike only when there is no other), then the damage
    cantrips, which keep their rows when the table is full."""
    rows, seen = [], set()
    attacks = [a for a in sh["attacks"] if a["name"] != "Unarmed Strike"] or sh["attacks"]
    for a in attacks:
        if a["name"] in seen:
            continue
        seen.add(a["name"])
        props = a.get("properties") if a.get("properties") not in ("—", "-") else None     # "—": no properties
        notes = "; ".join(x for x in (props, f"Mastery: {a['mastery']}" if a.get("mastery") else None,
                                      None if a["proficient"] else "not proficient") if x)
        rows.append({"name": a["name"], "hit": s(a["attack"]), "damage": a["damage"], "notes": notes})
    sc = sh.get("spellcasting") or {}
    by_class = {c["class"]: c for c in sc.get("casters", [])}
    cantrips = []
    for x in sh.get("spells") or []:
        caster = by_class.get(x["class"]) or next(iter(by_class.values()), None)
        if x["level"] == 0 and caster:
            r = cantrip_row(ix, x, caster, sc.get("cantrip_dice") or 1)
            if r:
                cantrips.append(r)
    cantrips = cantrips[:WEAPON_ROWS]
    return rows[:WEAPON_ROWS - len(cantrips)] + cantrips


def spell_rows(ix, sh):
    out = []
    for x in sh.get("spells") or []:
        e = ix.get(x["id"])
        mat = e.data.get("material") or ""
        notes = [re.sub(r"^Concentration, ", "", x["duration"])]
        if x["source"]:
            notes.append(x["source"])
        elif not x["prepared"]:
            notes.append("not prepared")
        out.append({"level": "C" if x["level"] == 0 else x["level"], "name": x["title"],
                    "time": re.sub(r",.*| or Ritual$", "", x["casting_time"]),
                    "range": re.sub(r"\b(\d+) feet\b", r"\1 ft.", x["range"]),
                    "c": x["concentration"], "r": x["ritual"],
                    "m": bool(re.search(r"\bGP\b|consume", mat)),         # a cost or consumed: no focus
                    "notes": " · ".join(notes)})
    return out[:SPELL_ROWS]


def slots(sh):
    """{level: total} for the slot table; Pact Magic slots go in at their level (a short-rest note says so)."""
    sc = sh.get("spellcasting") or {}
    out = {int(k): v for k, v in (sc.get("slots") or {}).items()}
    pact = sc.get("pact")
    if pact and pact.get("slots"):
        out[pact["level"]] = out.get(pact["level"], 0) + pact["slots"]
    return out


def casting_ability(casters):
    """`Charisma`, or `Intelligence (Wizard) / Wisdom (Cleric)` when the casters' abilities differ."""
    names = {ABILITY_NAMES[c["ability"]] for c in casters}
    if len(names) <= 1:
        return next(iter(names), "")
    return " / ".join(f"{ABILITY_NAMES[c['ability']]} ({c['class']})" for c in casters)


def context(ix, sh):
    ab, sk = sh["abilities"], sh["skills"]
    det = sh.get("details") or {}
    sc = sh.get("spellcasting") or {}
    casters = sc.get("casters") or []
    c0 = casters[0] if casters else None
    pr = sh["proficiencies"]
    cls = sh["classes"]
    pact = sc.get("pact") or {}
    weapon_names = ", ".join(x.replace("-", " ").title() + (" weapons" if x in ("simple", "martial") else "")
                             for x in pr["weapons"])
    coins = sh.get("coins") or {}
    rows = spell_rows(ix, sh)
    return {
        "title": f"{sh['name']}: D&D 2024 Character Sheet",
        "name": "" if sh["name"] == UNNAMED else sh["name"],          # no name in the spec: blank for pencil
        "background": _title(ix, sh["background"]) or "",
        "class": " / ".join(f"{c['title']} {c['level']}" if len(cls) > 1 else c["title"] for c in cls),
        "species": _title(ix, sh["species"]) or "",
        "subclass": " / ".join(c["subclass_title"] for c in cls if c["subclass_title"]),
        "level": sh["level"],
        "xp": f"{sh['xp']['this_level']:,}" if sh["xp"]["this_level"] else "",
        "ac": sh["armor_class"]["value"],
        "shield": "Shield" in sh["armor_class"]["breakdown"],
        "hp_max": sh["hit_points"]["max"],
        "hit_dice": " + ".join(f"{n}{d}" for d, n in sh["hit_dice"].items()),
        "pb": s(sh["proficiency_bonus"]),
        "initiative": s(sh["initiative"]["bonus"]) + (" adv." if sh["initiative"]["advantage"] else ""),
        "speed": f"{sh['speed']['walk']} ft.",
        "size": sh["size"],
        "passive": sh["passive_perception"],
        "abilities": {a: {"score": ab[a]["score"], "mod": s(ab[a]["mod"]), "save": s(ab[a]["save"]),
                          "prof": ab[a]["save_proficient"]} for a in ABILITIES},
        "skills": {k: {"bonus": s(v["bonus"]), "prof": v["proficient"] or v["expertise"], "expertise": v["expertise"]}
                   for k, v in sk.items()},
        "weapons": weapons(ix, sh),
        "class_features": class_features(ix, sh),
        "species_traits": species_traits(ix, sh),
        "feats": feats(ix, sh),
        "armor_training": {t: t in pr["armor"] for t in ("light", "medium", "heavy", "shields")},
        "weapon_training": weapon_names,
        "tools": ", ".join(pr.get("tools") or []),
        "casting_ability": casting_ability(casters),
        "casting_mod": s(ab[c0["ability"]]["mod"]) if c0 else "",
        "casting_dc": c0["save_dc"] if c0 else "",
        "casting_attack": s(c0["attack"]) if c0 else "",
        "slots": slots(sh),
        "pact_note": f"Pact Magic: {pact['slots']} × level {pact['level']}, regained on a Short Rest" if pact.get("slots") else "",
        "spells": rows,
        "appearance": det.get("appearance") or "",
        "personality": [(lab, det[k]) for k, lab in PERSONALITY if det.get(k)],
        "alignment": det.get("alignment") or "",
        "languages": ", ".join(sh.get("languages") or []),
        "equipment": sh.get("equipment") or [],
        "coins": {k: coins.get(k, "") for k in ("cp", "sp", "ep", "gp", "pp")},
        "stats": f"{len(rows)} spell{'' if len(rows) == 1 else 's'}",
    }
