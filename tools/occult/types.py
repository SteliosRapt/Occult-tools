"""Type registry: one entry per type an agent can name.

Each entry may set:
  base     JSON node type (default: the entry name)
  where    (data_field, value) narrowing `base` (virtual types: condition, action)
  aliases  other names accepted by `list`, `find --type` and `alias:slug` ids
  filters  {flag: Filter}; shared by `list` and `make` selectors (every type also takes --book, BOOK_FILTER)
  cols     list column headers after `id title`; `row(e)` returns the cells
  brief    brief(e) -> list of lines shown under the `show` header
  sort     sort key for `list` (default: title)

Adding a type means adding one entry here. Stdlib only.
"""
import re
from dataclasses import dataclass
from typing import Callable, Union

from . import components, text


@dataclass(frozen=True)
class Filter:
    field: Union[str, Callable]   # data key, or callable(entity) -> value
    op: str                       # eq | in | range | cr | flag | contains
    metavar: str = "X"

    def get(self, e):
        return self.field(e) if callable(self.field) else e.data.get(self.field)

    @property
    def usage(self):
        return "" if self.op == "flag" else f" {self.metavar}"


def short(s, n):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def dash(v):
    return "-" if v in (None, "", [], "—") else str(v)


# ---------------------------------------------------------------- spells
SCHOOL_ABBR = {"Abjuration": "Abj", "Conjuration": "Conj", "Divination": "Div", "Enchantment": "Ench",
               "Evocation": "Evoc", "Illusion": "Illu", "Necromancy": "Necr", "Transmutation": "Trans"}


def spell_cast_short(d):
    """`1 Reaction, which you take when…` -> `Reaction*`; drop `or Ritual` (the R flag says it)."""
    ct = d["casting_time"].replace(" or Ritual", "")
    ct = re.sub(r"^1 (Action|Bonus Action|Reaction)", r"\1", ct)
    return re.sub(r", which you take.*", "*", ct)


def crm(d):
    return ("C" if d["concentration"] else "-") + ("R" if d["ritual"] else "-") + ("M" if d["material"] else "-")


def _spell_row(e):
    d = e.data
    return [f"L{d['level']}", SCHOOL_ABBR[d["school"]], short(spell_cast_short(d), 14),
            short(d["range"].replace(" feet", " ft"), 16), crm(d)]


def _spell_brief(e):
    d = e.data
    lvl = f"{d['school']} cantrip" if d["level"] == 0 else f"Level {d['level']} {d['school']}"
    ct = d["casting_time"]
    if d["ritual"] and "Ritual" not in ct:
        ct += " or Ritual"
    return [f"{lvl} · {ct} · {d['range']} · {d['components']} · {d['duration']}",
            "Classes: " + ", ".join(e.classes)]


# ---------------------------------------------------------------- equipment
PROP_SHORT = {"Ammunition": "Ammo", "Two-Handed": "2H"}


def weapon_props(d):
    out = []
    for p in d["properties"]:
        s = PROP_SHORT.get(p["name"], p["name"])
        if p.get("range"):
            s += f" {p['range']['normal']}/{p['range']['long']}"
        if p.get("damage"):
            s += f" {p['damage']}"
        if p.get("condition"):
            s += f" ({p['condition']})"
        out.append(s)
    return ", ".join(out) or "-"


def _weapon_row(e):
    d = e.data
    return [f"{d['category'][:3]} {d['kind']}", f"{d['damage']} {d['damage_type']}", weapon_props(d),
            d["mastery"], dash(d.get("weight")), dash(d.get("cost"))]


def _weapon_brief(e):
    d = e.data
    return [f"{d['category'].title()} {d['kind']} weapon · {d['damage']} {d['damage_type']} · "
            f"{d['properties_raw'] or 'no properties'} · Mastery: {d['mastery']} · {d.get('weight') or '—'} · {d.get('cost') or '—'}"]


def _armor_row(e):
    d = e.data
    return [d["category"], d["ac"], dash(d["strength_requirement"]), "Dis" if d["stealth_disadvantage"] else "-",
            d["weight"], d["cost"]]


def _armor_brief(e):
    d = e.data
    bits = [f"{d['category'].title()} armor", f"AC {d['ac']}"]
    if d["strength_requirement"]:
        bits.append(f"Str {d['strength_requirement']}")
    if d["stealth_disadvantage"]:
        bits.append("Stealth Disadvantage")
    bits += [f"Don {d['don']} / Doff {d['doff']}", d["weight"], d["cost"]]
    return [" · ".join(bits)]


def _item_row(e):
    d = e.data
    return [d["kind"], dash(d.get("category")), dash(d.get("weight")), dash(d.get("cost"))]


def _item_brief(e):
    d = e.data
    head = d.get("category") or d["kind"].title()
    return [f"{head} · {d.get('weight') or '—'} · {d.get('cost') or '—'}"]


def _att(d):
    a = d.get("attunement")
    return "-" if not a else "yes" if a is True else short(a, 18)


def _rarities(e):
    d = e.data
    return [r for r in [d.get("rarity"), *(v.get("rarity") for v in d.get("variants") or [])] if r]


def _magic_item_brief(e):
    d = e.data
    vs = d.get("variants") or []
    bits = []
    if d.get("charges"):
        bits.append(f"{d['charges']} charges")
    if d.get("recharge"):
        bits.append(f"recharge: {d['recharge']}")
    if vs:
        names = "; ".join(v["title"] for v in vs[:6]) + ("; …" if len(vs) > 6 else "")
        bits.append(f"{len(vs)} variant{'' if len(vs) == 1 else 's'}: {names}")
    spells = d.get("spells") or []
    return [d.get("subtitle") or ", ".join(x for x in (d.get("category"), d.get("rarity")) if x), " · ".join(bits),
            "Spells: " + ", ".join(spells) if spells else ""]


# ---------------------------------------------------------------- creatures
def _rated(d):
    return d.get("cr") not in (None, "None")      # summoned creatures and Objects have no CR


def _creature_brief(e):
    d = {k: text.inline(v, "md") if isinstance(v, str) else v for k, v in e.data.items()}     # stat values hold links
    # an Object stat block  prints no alignment, speed or CR: leave them out
    xp = f"XP {d.get('xp')}" + (f", or {d['xp_lair']} in lair" if d.get("xp_lair") else "")
    cr = (f" · CR {d['cr']}" + (f" ({xp}; PB {d['proficiency_bonus']})" if d.get("xp") else "")) if _rated(d) else ""
    init = f" · Initiative {d['initiative']}" if d.get("initiative") else ""
    speed = f" · Speed {d['speed']}" if d.get("speed") else ""
    align = f", {d['alignment']}" if d.get("alignment") else ""
    return [f"{d['size']} {d['type']}{align}{cr}",
            f"AC {d['ac']} · HP {d['hp']}{speed}{init}"]


# ---------------------------------------------------------------- rules text, character options
def _term_brief(e):
    d = e.data
    see = " · See also: " + ", ".join(d["see_also"]) if d.get("see_also") else ""
    where = "Skill" + (f" ({d['ability']})" if d.get("ability") else "") if d.get("tag") == "Skill" else \
        f"Rules glossary · {d['tag'] or 'Rule'}"
    return [where + (f" · {d['time']}" if d.get("time") and d.get("tag") != "Action" else "") + see]


# ---------------------------------------------------------------- 5e.tools rules & misc types


def _language_brief(e):
    d = e.data
    bits = [f"{(d.get('category') or 'standard').title()} language", f"Origin: {d['origin']}" if d.get("origin") else ""]
    if d.get("script"):
        bits.append(f"Script: {d['script']}")
    if d.get("dialects"):
        bits.append("Dialects: " + ", ".join(d["dialects"]))
    return [" · ".join(b for b in bits if b)]






def _hazard_brief(e):
    d = e.data
    out = [d.get("subtitle") or d.get("category") or ""]
    if e.type == "trap":
        out.append(f"Trigger: {d.get('trigger') or '—'} · Duration: {d.get('duration') or '—'}")
    return out








def _feat_brief(e):
    d = e.data
    bits = [f"{d['category']} feat", f"Prerequisite: {d['prerequisite'] or 'none'}"]
    if d.get("repeatable"):
        bits.append("Repeatable")
    return [" · ".join(bits)]


def _class_row(e):
    d = e.data
    ct, sc = d["core_traits"], d.get("spellcasting")
    return [f"d{ct['hit_die']}", short(ct["primary_ability"], 22),
            f"{sc['ability']}{' (pact)' if sc['kind'] == 'pact' else ''}" if sc else "-"]


def _class_brief(e):
    d = e.data
    ct, sc = d["core_traits"], d.get("spellcasting")
    lines = [d["tagline"],
             f"Hit die d{ct['hit_die']} · Primary {ct['primary_ability']} · Saves {', '.join(ct['saving_throw_proficiencies'])}"
             f" · Subclass at L{d['subclass_level']}"]
    if sc:
        lines.append(f"{'Pact Magic' if sc['kind'] == 'pact' else 'Spellcasting'} ({sc['ability']})"
                     + (" · prepares spells" if sc.get("prepares_spells") else ""))
    return lines


def _subclass_brief(e):
    d = e.data
    lvls = ", ".join(str(x) for x in d.get("feature_levels") or [])
    return [f"{(e.owner_class or '?').title()} subclass · {d.get('tagline') or ''}".rstrip(" ·"),
            f"Features at levels {lvls}" if lvls else ""]


def owner_label(e):
    if e.owner_subclass:
        return f"{e.owner_subclass.title} ({(e.owner_class or '').title()})"
    return (e.owner_class or "").title() or (e.parent.title if e.parent else "")


def _feature_brief(e):
    lvl = e.data.get("level")
    return [f"{owner_label(e)} feature" + (f" · Level {lvl}" if lvl else "")]


def _option_brief(e):
    p = e.parent
    return [f"Option of {p.sid if p else '?'} · {owner_label(e)}"]


def _species_brief(e):
    d = e.data
    return [f"{d['creature_type']} · Speed {d['speed']} · Size: {d['size']}",
            "Traits: " + ", ".join(d["traits"])]


def _background_brief(e):
    d = e.data
    return [f"Abilities {', '.join(d['ability_scores'])} · Feat: {d['feat']}",
            f"Skills: {', '.join(d['skill_proficiencies']) if isinstance(d['skill_proficiencies'], list) else d['skill_proficiencies']}"
            f" · Tool: {d['tool_proficiency']}"]


ABIL = {"Strength": "Str", "Dexterity": "Dex", "Constitution": "Con", "Intelligence": "Int", "Wisdom": "Wis", "Charisma": "Cha"}


def _owner_class(e):
    return e.owner_class


def _owner_subclass(e):
    s = e.owner_subclass
    return f"{s.title} {s.sid.split(':', 1)[1]}" if s else None


def _feature_sort(e):
    return (e.owner_class or "~", e.owner_subclass.title if e.owner_subclass else "", e.data.get("level") or 0, e.order)


TYPES = {
    "spell": dict(aliases=["spells"], cols=["lvl", "school", "cast", "range", "CRM"], row=_spell_row, brief=_spell_brief,
                  sort=lambda e: (e.data["level"], e.title),
                  filters={"class": Filter(lambda e: e.classes, "in", "CLASS"), "level": Filter("level", "range", "N|N-M"),
                           "school": Filter("school", "eq", "SCHOOL"), "ritual": Filter("ritual", "flag"),
                           "conc": Filter("concentration", "flag")}),
    "weapon": dict(aliases=["weapons"], cols=["cat", "damage", "properties", "mastery", "wt", "cost"],
                   row=_weapon_row, brief=_weapon_brief,
                   sort=lambda e: (e.data["category"] != "simple", e.data["kind"] != "melee", e.title),
                   filters={"category": Filter("category", "eq", "simple|martial"), "kind": Filter("kind", "eq", "melee|ranged"),
                            "mastery": Filter("mastery", "eq", "NAME"), "property": Filter("properties_raw", "contains", "NAME")}),
    "armor": dict(aliases=["armors", "armour", "armours"], cols=["cat", "AC", "str", "stealth", "wt", "cost"],
                  row=_armor_row, brief=_armor_brief, sort=lambda e: e.order,
                  filters={"category": Filter("category", "eq", "light|medium|heavy|shield")}),
    "item": dict(aliases=["items", "gear", "tool", "tools", "equipment"], cols=["kind", "category", "wt", "cost"],
                 row=_item_row, brief=_item_brief,
                 filters={"kind": Filter("kind", "eq", "gear|tool|mount|tack|vehicle|food|treasure|poison|explosive"),
                          "category": Filter("category", "eq", "CAT")}),
    "magic-item": dict(aliases=["magic-items", "magic", "mi"], cols=["category", "rarity", "att"], brief=_magic_item_brief,
                       row=lambda e: [short(dash(e.data.get("category")), 16), short(dash(e.data.get("rarity")), 12), _att(e.data)],
                       filters={"rarity": Filter(_rarities, "in", "RARITY"), "category": Filter("category", "eq", "CAT"),
                                "attunement": Filter("attunement", "flag")}),
    "creature": dict(base="stat-block", aliases=["creatures", "stat-block", "stat-blocks", "monster", "monsters", "beast", "beasts"],
                     cols=["CR", "size type", "AC", "HP"], brief=_creature_brief,
                     row=lambda e: [e.data["cr"] if _rated(e.data) else "-", f"{e.data['size']} {e.data['type']}",
                                   short(text.inline(e.data["ac"], "plain"), 14), short(text.inline(e.data["hp"], "plain"), 20)],
                     filters={"cr": Filter("cr", "cr", "CR|CR-CR"), "type": Filter("type", "eq", "TYPE"), "size": Filter("size", "eq", "SIZE")}),
    "condition": dict(base="term", where=("tag", "Condition"), aliases=["conditions"]),
    "action": dict(base="term", where=("tag", "Action"), aliases=["actions"]),
    "term": dict(aliases=["terms", "glossary", "rule", "rules"], cols=["tag"], row=lambda e: [dash(e.data["tag"])],
                 brief=_term_brief, filters={"tag": Filter("tag", "eq", "TAG")}),
    "skill": dict(base="term", where=("tag", "Skill"), aliases=["skills"], cols=["ability"],
                  row=lambda e: [dash(e.data.get("ability"))], brief=_term_brief, sort=lambda e: e.title,
                  filters={"ability": Filter("ability", "eq", "ABILITY")}),
    "feat": dict(aliases=["feats"], cols=["category", "prerequisite"], brief=_feat_brief,
                 row=lambda e: [e.data["category"], short(dash(e.data["prerequisite"]), 34)],
                 sort=lambda e: (["Origin", "General", "Fighting Style", "Epic Boon"].index(e.data["category"])
                                 if e.data["category"] in ("Origin", "General", "Fighting Style", "Epic Boon") else 9, e.title),
                 filters={"category": Filter("category", "eq", "CAT"), "repeatable": Filter("repeatable", "flag")}),
    "class": dict(aliases=["classes"], cols=["hit die", "primary", "casting"], row=_class_row, brief=_class_brief),
    "subclass": dict(aliases=["subclasses"], cols=["class", "features at"], brief=_subclass_brief,
                     row=lambda e: [(e.owner_class or "-").title(), ",".join(str(x) for x in e.data.get("feature_levels") or [])],
                     sort=lambda e: (e.owner_class or "", e.title),
                     filters={"class": Filter(_owner_class, "eq", "CLASS")}),
    "feature": dict(aliases=["features"], cols=["owner", "lvl"], brief=_feature_brief,
                    row=lambda e: [short(owner_label(e), 34), dash(e.data.get("level"))], sort=_feature_sort,
                    filters={"class": Filter(_owner_class, "eq", "CLASS"), "subclass": Filter(_owner_subclass, "contains", "SUBCLASS"),
                             "level": Filter("level", "range", "N|N-M")}),
    "option": dict(aliases=["options"], cols=["option of"], brief=_option_brief,
                   row=lambda e: [e.parent.sid if e.parent else "-"], sort=lambda e: e.order,
                   filters={"class": Filter(_owner_class, "eq", "CLASS"), "subclass": Filter(_owner_subclass, "contains", "SUBCLASS"),
                            "kind": Filter("kind", "eq", "KIND")}),
    "species": dict(aliases=["race", "races"], cols=["type", "speed"], brief=_species_brief,
                    row=lambda e: [e.data["creature_type"], e.data["speed"]]),
    "background": dict(aliases=["backgrounds"], cols=["abilities", "feat"], brief=_background_brief,
                       row=lambda e: [" ".join(ABIL.get(a, a) for a in e.data["ability_scores"]), e.data["feat"]]),
    "weapon-property": dict(aliases=["property", "properties", "weapon-properties"], sort=lambda e: e.order),
    "mastery-property": dict(aliases=["mastery", "masteries", "mastery-properties"], sort=lambda e: e.order),
    "section": dict(aliases=["sections"], sort=lambda e: e.order),
    "chapter": dict(aliases=["chapters", "appendix", "appendices"], sort=lambda e: e.order),
}
for _t in ("condition", "action"):
    TYPES[_t].update({k: TYPES["term"][k] for k in ("cols", "row", "brief")})

# Types from the 5e.tools import (docs/architecture.md §3.2), registered generically: their family
# converters will add filters and columns. JSON type -> extra aliases (the plural is always one).
NEW_TYPES = {'hazard': [], 'trap': [], 'language': [], 'disease': []}
for _t, _extra in NEW_TYPES.items():
    TYPES[_t] = dict(aliases=sorted({_t + "s", *_extra}), sort=lambda e: e.order)

_HAZARD = dict(cols=["category", "rating"], brief=_hazard_brief, sort=lambda e: e.order,
               row=lambda e: [short(dash(e.data.get("category")), 20),
                              short(dash(", ".join(f"{r['threat']} {r['levels']}" for r in e.data.get("ratings") or [])), 34)],
               filters={"category": Filter("category", "eq", "CAT"), "tier": Filter(lambda e: [r["tier"] for r in e.data.get("ratings") or []], "in", "1-4")})
for _t, _spec in {
    'language': dict(cols=["category", "origin"], brief=_language_brief, sort=lambda e: (e.book, e.title),
                     row=lambda e: [dash(e.data.get("category")), short(dash(e.data.get("origin")), 28)],
                     filters={"category": Filter("category", "eq", "standard|rare")}),
    'hazard': _HAZARD,
    'trap': _HAZARD,
    'disease': dict(cols=['category'], brief=lambda e: [e.data.get('category') or 'Disease'], sort=lambda e: e.order, row=lambda e: [dash(e.data.get('category'))]),
}.items():
    TYPES[_t].update(_spec)

components.apply("register_types", TYPES)
TYPES = components.transform("type_order", TYPES)

# Every type takes --book (listed in `types` and hints only when several books are loaded).
BOOK_FILTER = Filter(lambda e: e.book, "eq", "BOOK")

ALIAS = {a: t for t, r in TYPES.items() for a in [t, *r.get("aliases", [])]}

# Ambiguity order: when a name matches several entities, candidates are listed in this order.
RANK = ["spell", "condition", "action", "skill", "weapon", "armor", "item", "magic-item", "feat", "class", "subclass", "species", "background",
        "creature", "term", "feature", "option", "weapon-property", "mastery-property", "hazard", "trap", "card", "language", "disease", "chapter", "section"]
RANK = components.transform("rank_order", RANK)


# Types whose list row, brief and sort read `data`. The 5e.tools generic converter writes none yet:
# such an entity lists with dashes and no brief (has_data), until its family converter fills it in.
DATA_TYPES = {"spell", "weapon", "armor", "item", "magic-item", "creature", "term", "condition", "action", "feat",
              "class", "species", "background", "skill", "language", "hazard", "trap", "disease"}


def has_data(e):
    return bool(e.data) or not TYPES.get(e.type, {}).get("requires_data", e.type in DATA_TYPES)


def type_name(node_type):
    """Agent-facing type for a JSON node type."""
    return {"stat-block": "creature", "appendix": "chapter"}.get(node_type, node_type)


def rank(e):
    return RANK.index(e.type) if e.type in RANK else 99


def resolve_type(name):
    """User-typed type name -> registry type, or None."""
    return ALIAS.get((name or "").lower())
