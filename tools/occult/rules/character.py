"""Character sheets: a JSON spec in, every derived number out (stdlib only).

    sheet = character.build(spec)        # dict; sheet["warnings"] lists rule problems found in the spec
    character.level_up(spec, "wizard")   # what changes when the character gains a level in a class

A spec names entities by id or slug and records the player's choices; the engine looks the rest up in
the data (class tables, armor, weapons, feats, species, backgrounds) and applies the rules:

    {"name": "Brakka", "species": "dwarf", "background": "soldier",
     "abilities": {"str": 15, "dex": 13, "con": 14, "int": 8, "wis": 12, "cha": 10},   # before the background
     "method": "standard-array",                        # or point-buy, rolled, manual: checked when given
     "background_bonus": {"str": 2, "con": 1},          # +2/+1 or +1/+1/+1 among the background's three
     "classes": [{"class": "fighter", "level": 5, "subclass": "champion"}],   # the first is the starting class
     "hp": "average",                                   # or {"rolls": [7, 3, ...]}: one per level after 1st
     "feats": ["defense", {"feat": "ability-score-improvement", "increase": {"str": 2}}],
     "skills": ["athletics", "perception"],             # chosen skill proficiencies (the background's are added)
     "expertise": [],
     "armor": "chain-mail", "shield": true,             # or {"id": "chain-mail", "bonus": 1}
     "weapons": ["longsword", "javelin"],
     "mage_armor": false,
     "choices": {"elven_lineage": "High Elf"},          # free-form, echoed on the sheet
     "modifiers": {"ac": 1, "saves": 1},                # magic items and anything else the engine doesn't model
     "options": ["agonizing-blast"],                    # invocations, metamagic, maneuvers (`list options`)
     "spells": ["fire-bolt", {"spell": "detect-magic", "source": "High Elf"}],   # checked against the lists
     "languages": ["Common", "Elvish"], "equipment": ["Backpack"], "coins": {"gp": 8},
     "details": {"alignment": "Neutral Good", "backstory": "..."}}   # echoed (the PDF sheet prints them)

`modifiers` keys: ac hp speed initiative saves attack damage spell_dc spell_attack, and per-ability
saves (save_dex). `set_abilities` ({"str": 21}) models items that set a score.
"""
import math
import re

from .. import data, text
from . import core, tables
from .tables import ABILITIES, ABILITY_NAMES, ability

# Rules the engine applies when a character has the feature, feat or species. Each key is an entity
# id, so a test can check that all of them still resolve (tools/tests/test_rules.py).
EFFECTS = {
    "feature:barbarian/unarmored-defense": {"unarmored_ac": ("dex", "con"), "shield_ok": True},
    "feature:monk/unarmored-defense": {"unarmored_ac": ("dex", "wis"), "shield_ok": False},
    "feature:draconic-resilience": {"unarmored_ac": ("dex", "cha"), "shield_ok": True, "hp_per_class_level": 1},
    "feature:fast-movement": {"speed_unless_heavy": 10},
    "feature:unarmored-movement": {"speed_column": "Unarmored Movement"},
    "feature:primal-champion": {"ability_increase": {"str": 4, "con": 4}, "maximum": 25},
    "feature:body-and-mind": {"ability_increase": {"dex": 4, "wis": 4}, "maximum": 25},
    "feature:jack-of-all-trades": {"half_pb_skills": True},
    "feature:remarkable-athlete": {"initiative_advantage": True},
    "feature:barbarian/extra-attack": {"attacks": 2},
    "feature:fighter/extra-attack": {"attacks": 2},
    "feature:two-extra-attacks": {"attacks": 3},
    "feature:three-extra-attacks": {"attacks": 4},
    "feature:monk/extra-attack": {"attacks": 2},
    "feature:paladin/extra-attack": {"attacks": 2},
    "feature:ranger/extra-attack": {"attacks": 2},
    "feature:college-of-valor/extra-attack": {"attacks": 2},
    "feature:armorer/extra-attack": {"attacks": 2},
    "feature:battle-smith/extra-attack": {"attacks": 2},
    "feature:bladesinger/extra-attack": {"attacks": 2},
    "feat:tough": {"hp_per_level": 2},
    "feat:alert": {"initiative_pb": True},
    "feat:defense": {"ac_in_armor": 1},
    "feat:archery": {"ranged_attack": 2},
    "feat:dueling": {"note": "Dueling: +2 damage with a melee weapon in one hand and no other weapon"},
    "feat:great-weapon-fighting": {"note": "Great Weapon Fighting: treat 1s and 2s on damage dice as 3s (two-handed or versatile, held in two hands)"},
    "species:dwarf": {"hp_per_level": 1, "label": "Dwarven Toughness"},
    "species:warforged": {"ac": 1, "label": "Integrated Protection"},
    "species:goliath": {"size_up_for_carrying": True, "label": "Powerful Build"},
    "option:protector": {"armor": ("heavy",), "weapons": ("martial",)},        # Divine Order
}

CASTER_KINDS = ("spellcasting", "pact", "subclass")
UNNAMED = "Unnamed"                 # the sheet's name when the spec has none


class SpecError(ValueError):
    pass


# ---------------------------------------------------------------- lookups
def resolve(ix, kind, ref):
    if isinstance(ref, data.Entity):
        return ref
    ref = str(ref).strip()
    for cand in (ref if ref.startswith(kind + ":") else f"{kind}:{data.slugify(ref)}", ref):
        lk = ix.resolve(cand)
        if lk and lk.entity.type == kind:
            return lk.entity
    bare = re.sub(r"\s*\(.*\)$", "", ref)
    lk = ix.resolve(f"{kind}:{data.slugify(bare)}")
    if lk and lk.entity.type == kind:
        return lk.entity
    pool = ix.all(kind)
    sug = [e.sid for e in ix.suggest(ref, pool, 5)]
    raise SpecError(f"no {kind} '{ref}'" + (f"; did you mean {', '.join(sug)}" if sug else ""))


def _parse_hd(ct):
    return int(ct.get("hit_die") or re.search(r"\d+", ct["hit_point_die"]).group())


def speed_ft(s):
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else 30


def class_features(ix, cls, level, subclass=None):
    """[(level, entity or name)] of a class up to `level`, then its subclass's features."""
    owned = {}
    for f in ix.all("feature"):
        if f.owner_class == cls.title.lower() and f.owner_subclass is None:
            owned.setdefault(f.title.lower(), f)
    out = []
    for row in cls.data["levels"][:level]:
        for name in row["features"]:
            if name.lower() in ("subclass feature",):
                continue
            base = re.sub(r"\s*\(.*\)$", "", name).lower()
            out.append((row["level"], owned.get(name.lower()) or owned.get(base) or name))
    if subclass is not None:
        for f in subclass.children:
            if f.type == "feature" and (f.data.get("level") or 99) <= level:
                out.append((f.data["level"], f))
    out.sort(key=lambda x: x[0])
    return out


def caster_progression(cls, subclass=None, level=20):
    """'full' | 'half' | 'third' | 'pact' | None, read from the tables: a class whose level 20 row has
    9th-level slots is a full caster, one that stops at 5th a half caster (rounding up, as the PHB says
    for the Paladin and Ranger; the Artificer is treated the same, docs/architecture.md §10), and a subclass with
    its own spellcasting table counts a third of the class level (Eldritch Knight, Arcane Trickster,
    Warrior of the Mystic Arts)."""
    sc = cls.data.get("spellcasting") or {}
    if sc.get("kind") == "pact":
        return "pact"
    if sc.get("kind") == "spellcasting":
        top = max(int(k) for k in cls.data["levels"][19]["spell_slots"])
        return "full" if top == 9 else "half"
    if subclass is not None and (subclass.data.get("spellcasting") or {}).get("kind") == "subclass":
        return "third"
    return None


def caster_level(prog, level):
    return {"full": level, "half": math.ceil(level / 2), "third": level // 3}.get(prog, 0)


def own_slots(cls, level, subclass=None):
    """The class's (or subclass's) own table row: (slots {lvl: n}, cantrips, prepared)."""
    if (cls.data.get("spellcasting") or {}).get("kind") in ("spellcasting", "pact"):
        row = cls.data["levels"][level - 1]
        return {int(k): v for k, v in (row["spell_slots"] or {}).items()}, row["cantrips_known"], row["prepared_spells"]
    sc = (subclass.data.get("spellcasting") or {}) if subclass is not None else {}
    row = (sc.get("levels") or {}).get(str(level))
    if not row:
        return {}, None, None
    cantrips = _subclass_cantrips(subclass, level)
    return {int(k): v for k, v in row["spell_slots"].items()}, cantrips, row.get("prepared_spells")


def _subclass_cantrips(subclass, level):
    """Third casters know two cantrips, and one more at class level 10 (the feature's text)."""
    feat = next((f for f in subclass.children if f.title == "Spellcasting"), None)
    if feat is None:
        return None
    body = " ".join(b.get("text", "") for b in feat.content)
    m = re.search(r"You know (\w+) cantrips", body)
    words = {"two": 2, "three": 3, "four": 4}
    n = words.get(m.group(1).lower(), 2) if m else 2
    return n + (1 if level >= 10 and "level 10, you learn another" in body else 0)


def spell_slots(entries):
    """entries: [(cls, level, subclass)] -> (slots {lvl: n}, pact {"slots", "level"} or None, caster level).

    One class with the Spellcasting feature: its own table. Several: the Multiclass Spellcaster table at the
    combined caster level. Pact Magic is always separate."""
    casters, pact = [], None
    for cls, level, sub in entries:
        prog = caster_progression(cls, sub, level)
        if prog == "pact":
            row = cls.data["levels"][level - 1]
            pact = {"slots": row["pact_slots"], "level": row["pact_slot_level"]}
        elif prog and own_slots(cls, level, sub)[0]:
            casters.append((cls, level, sub, prog))
    if not casters:
        return {}, pact, 0
    if len(casters) == 1:
        cls, level, sub, prog = casters[0]
        return own_slots(cls, level, sub)[0], pact, caster_level(prog, level)
    total = sum(caster_level(prog, level) for _, level, _, prog in casters)
    return dict(tables.multiclass_slots()[min(total, 20)]), pact, total


def _primary_ok(primary, scores):
    names = re.split(r"\s+(and|or)\s+", primary)
    abil = [ability(n) for n in names[::2]]
    joiner = names[1] if len(names) > 1 else "and"
    hits = [scores[a] >= 13 for a in abil]
    return (any(hits) if joiner == "or" else all(hits)), primary


def _weapon_rules(s):
    """Class weapon text -> set of rules: simple, martial, martial-light, martial-finesse-or-light."""
    s = text.inline(s or "", "plain").lower()
    out = set()
    if "simple" in s:
        out.add("simple")
    if re.search(r"martial weapons that have the finesse or light", s):
        out.add("martial-finesse-or-light")
    elif re.search(r"martial weapons that have the light", s):
        out.add("martial-light")
    elif "martial" in s:
        out.add("martial")
    return out


def _armor_rules(s):
    s = text.inline(s or "", "plain").lower()
    m = re.search(r"training with ([^.;]*)", s)
    s = m.group(1) if m else s
    return {k for k in ("light", "medium", "heavy") if k in s} | ({"shields"} if "shield" in s else set())


def multiclass_traits(ix, cls):
    lk = ix.resolve(f"section:{cls.slug}/as-a-multiclass-character")
    if not lk:
        return set(), set(), ""
    first = text.inline(lk.entity.content[0]["items"][0]["text"], "plain")
    return _weapon_rules(first), _armor_rules(first), first


def weapon_proficient(rules, w, extra=()):
    d = w.data
    props = {p["name"].lower() for p in d.get("properties", [])}
    if w.slug in extra or w.sid in extra:
        return True
    if d["category"] == "simple":
        return "simple" in rules
    return ("martial" in rules or ("martial-light" in rules and "light" in props)
            or ("martial-finesse-or-light" in rules and props & {"finesse", "light"}))


# ---------------------------------------------------------------- the sheet
def build(spec, ix=None):
    ix = ix or data.load()
    warn = []
    S = _Sheet(ix, spec, warn)
    return S.run()


class _Sheet:
    def __init__(self, ix, spec, warn):
        self.ix, self.spec, self.warn = ix, spec, warn
        self.mods = {k: v for k, v in (spec.get("modifiers") or {}).items()}
        self.applied = []          # (what, where from): every automatic rule used, for the sheet

    def W(self, msg):
        self.warn.append(msg)

    def label(self, i):
        return EFFECTS.get(i, {}).get("label") or self.ix.get(i).title

    def run(self):
        ix, spec = self.ix, self.spec
        if not spec.get("classes"):
            raise SpecError("a character needs at least one class: \"classes\": [{\"class\": \"fighter\", \"level\": 1}]")
        self.classes = []
        for c in spec["classes"]:
            if isinstance(c, str):
                c = {"class": c, "level": 1}
            cls = resolve(ix, "class", c["class"])
            lvl = int(c.get("level", 1))
            sub = resolve(ix, "subclass", c["subclass"]) if c.get("subclass") else None
            if sub is not None and (sub.owner_class or "") != cls.title.lower():
                raise SpecError(f"{sub.sid} is a {sub.owner_class} subclass, not {cls.title}")
            if not 1 <= lvl <= 20:
                raise SpecError(f"{cls.title} level must be 1-20, not {lvl}")
            self.classes.append((cls, lvl, sub))
        if len({c.sid for c, _, _ in self.classes}) != len(self.classes):
            raise SpecError("each class appears once in \"classes\"; add the levels together")
        self.level = sum(l for _, l, _ in self.classes)
        if self.level > 20:
            raise SpecError(f"total character level is {self.level}; the maximum is 20")
        self.pb = core.proficiency_bonus(self.level)
        self.species = resolve(ix, "species", spec["species"]) if spec.get("species") else None
        self.background = resolve(ix, "background", spec["background"]) if spec.get("background") else None

        self.features = []                # (class title, level, entity or name)
        for cls, lvl, sub in self.classes:
            if lvl >= 3 and sub is None and any("Subclass" in n for r in cls.data["levels"][:lvl] for n in r["features"]):
                self.W(f"{cls.title} {lvl} has a subclass by level 3; add \"subclass\" to the class entry")
            for at, f in class_features(ix, cls, lvl, sub):
                self.features.append((cls.title, at, f))
        self.feats = self._feats()
        self.effect_ids = {f.sid for _, _, f in self.features if isinstance(f, data.Entity)}
        self.effect_ids |= {f.sid for f, _ in self.feats}
        if self.species is not None:
            self.effect_ids.add(self.species.sid)
        self.options = [resolve(ix, "option", x) for x in spec.get("options") or []]
        self.effect_ids |= {o.sid for o in self.options}

        self.scores = self._abilities()
        self.m = {a: core.mod(s) for a, s in self.scores.items()}
        self._multiclass_prereqs()
        self.prof = self._proficiencies()
        out = {
            "name": spec.get("name") or UNNAMED,
            "level": self.level,
            "classes": [{"class": c.sid, "title": c.title, "level": l, "subclass": s.sid if s else None,
                         "subclass_title": s.title if s else None} for c, l, s in self.classes],
            "species": self.species.sid if self.species else None,
            "background": self.background.sid if self.background else None,
            "proficiency_bonus": self.pb,
            "xp": {"this_level": core.xp_for_level(self.level),
                   "next_level": core.xp_for_level(self.level + 1) if self.level < 20 else None},
            "abilities": {a: {"score": self.scores[a], "mod": self.m[a],
                              "save": self.save(a), "save_proficient": a in self.prof["saves"]} for a in ABILITIES},
        }
        out["skills"] = self._skills()
        out["passive_perception"] = 10 + out["skills"].get("perception", {"bonus": self.m["wis"]})["bonus"]
        out["initiative"] = self._initiative()
        out["armor_class"] = self._ac()
        out["hit_points"], out["hit_dice"] = self._hp()
        out["speed"] = self._speed()
        out["size"] = self._size()
        out["carrying_capacity"] = self._carry(out["size"])
        out["attacks_per_action"] = max([1] + [EFFECTS[i]["attacks"] for i in self.effect_ids
                                              if "attacks" in EFFECTS.get(i, {})])
        out["attacks"] = self._attacks()
        out["spellcasting"] = self._spellcasting()
        out["resources"] = {c.title: dict(c.data["levels"][l - 1]["columns"]) for c, l, _ in self.classes
                            if c.data["levels"][l - 1]["columns"]}
        out["proficiencies"] = {"armor": sorted(self.prof["armor"]), "weapons": sorted(self.prof["weapons"]),
                                "saves": [a for a in ABILITIES if a in self.prof["saves"]],
                                "tools": self._tools()}
        out["spells"] = self._spells(out["spellcasting"])
        out["options"] = [{"id": o.sid, "title": o.title, "of": o.parent.title if o.parent else None}
                          for o in self.options]
        out["features"] = [{"class": c, "level": lv, "id": f.sid if isinstance(f, data.Entity) else None,
                            "title": f.title if isinstance(f, data.Entity) else f} for c, lv, f in self.features]
        out["feats"] = [{"id": f.sid, "title": f.title, "source": src,
                         **({"increase": {ability(k): v for k, v in self.feat_choices[i].items()}}
                            if self.feat_choices.get(i) else {})} for i, (f, src) in enumerate(self.feats)]
        out["choices"] = dict(spec.get("choices") or {})
        out["species_traits"] = list((self.species.data.get("traits") or []) if self.species else [])
        out["languages"] = list(spec.get("languages") or [])
        out["equipment"] = list(spec.get("equipment") or [])
        out["coins"] = {k: v for k, v in (spec.get("coins") or {}).items() if v}
        out["details"] = dict(spec.get("details") or {})
        out["notes"] = [EFFECTS[i]["note"] for i in sorted(self.effect_ids) if "note" in EFFECTS.get(i, {})]
        out["applied_rules"] = [{"rule": what, "from": where} for what, where in self.applied]
        out["warnings"] = self.warn
        return out

    # ---- abilities
    def _feats(self):
        ix, out = self.ix, []
        if self.background is not None and self.background.data.get("feat"):
            name = self.background.data["feat"]
            try:
                out.append((resolve(ix, "feat", name), "background"))
            except SpecError:
                self.W(f"background feat '{name}' not found in the data")
        self.feat_choices = {}
        for f in self.spec.get("feats") or []:
            ref = f["feat"] if isinstance(f, dict) else f
            e = resolve(ix, "feat", ref)
            if any(e is x for x, _ in out) and not e.data.get("repeatable"):
                if self.background is not None and (e, "background") in out:
                    self.W(f"{e.title} already comes from the {self.background.title} background; leave it out of \"feats\"")
                else:
                    self.W(f"{e.title} is not repeatable but is listed twice")
                continue
            out.append((e, "chosen"))
            self.feat_choices[len(out) - 1] = f.get("increase") if isinstance(f, dict) else None
        self._check_feat_slots(out)
        return out

    def _check_feat_slots(self, feats):
        slots = sum(1 for _, _, f in self.features
                    for t in [f.title if isinstance(f, data.Entity) else f]
                    if t in ("Ability Score Improvement", "Epic Boon"))
        styles = sum(1 for _, _, f in self.features
                     for t in [f.title if isinstance(f, data.Entity) else f]
                     if t in ("Fighting Style", "Additional Fighting Style"))
        cat = lambda e: e.data.get("category")
        chosen = [e for e, src in feats if src == "chosen"]
        general = [e for e in chosen if cat(e) in ("General", "Epic Boon")]
        style = [e for e in chosen if cat(e) == "Fighting Style"]
        if len(general) > slots:
            self.W(f"{len(general)} General/Epic Boon feats chosen but the classes give {slots} feat slot(s)")
        elif len(general) < slots:
            self.W(f"{slots - len(general)} feat slot(s) unused (Ability Score Improvement or Epic Boon levels)")
        if len(style) > styles:
            self.W(f"{len(style)} Fighting Style feats chosen but the classes give {styles}")
        for e in chosen:
            pre = e.data.get("prerequisite") or ""
            m = re.match(r"Level (\d+)\+", pre)
            if m and self.level < int(m.group(1)):
                self.W(f"{e.title} needs {pre}")

    def _abilities(self):
        spec = self.spec
        base = {a: 10 for a in ABILITIES}
        for k, v in (spec.get("abilities") or {}).items():
            base[ability(k)] = int(v)
        if not spec.get("abilities"):
            self.W("no \"abilities\" given; every score is 10")
        method = (spec.get("method") or "").lower()
        if method == "point-buy":
            cost, problems = core.point_buy_cost(base)
            for p in problems:
                self.W(p)
        elif method == "standard-array" and not core.is_standard_array(base):
            self.W(f"scores {sorted(base.values(), reverse=True)} are not the Standard Array {core.standard_array()}")
        scores = dict(base)
        bonus = {ability(k): int(v) for k, v in (spec.get("background_bonus") or {}).items()}
        if self.background is not None:
            allowed = {ability(a) for a in self.background.data.get("ability_scores") or []}
            if bonus:
                bad = [a for a in bonus if a not in allowed]
                if bad:
                    self.W(f"{self.background.title} raises {', '.join(ABILITY_NAMES[a] for a in sorted(allowed))}, "
                           f"not {', '.join(ABILITY_NAMES[a] for a in bad)}")
                if sorted(bonus.values()) not in ([1, 2], [1, 1, 1]):
                    self.W("background ability bonus is +2 and +1, or +1 to all three")
            else:
                self.W(f"no \"background_bonus\"; {self.background.title} gives +2/+1 or +1/+1/+1 among "
                       + ", ".join(ABILITY_NAMES[a] for a in ABILITIES if a in allowed))
        for a, v in bonus.items():
            scores[a] += v
        for i, (f, src) in enumerate(self.feats):
            inc = f.data.get("ability_increase")
            if not inc:
                continue
            allowed = [ability(a) for a in inc.get("abilities") or []] or list(ABILITIES)
            cap = inc.get("maximum") or 20
            choice = self.feat_choices.get(i)
            if choice is None and len(allowed) == 1:
                choice = {allowed[0]: inc["amount"]}
            if not choice:
                self.W(f"{f.title}: choose its ability increase, e.g. {{\"feat\": \"{f.slug}\", \"increase\": "
                       f"{{\"{allowed[0]}\": {inc['amount']}}}}}")
                continue
            choice = {ability(k): int(v) for k, v in choice.items()}
            total = sum(choice.values())
            if any(a not in allowed for a in choice):
                self.W(f"{f.title} can raise {', '.join(a.upper() for a in allowed)} only")
            if total != inc["amount"] or (inc["amount"] == 1 and len(choice) > 1):
                self.W(f"{f.title} raises abilities by {inc['amount']} in total, not {total}")
            for a, v in choice.items():
                if scores[a] + v > cap:
                    self.W(f"{f.title} can't raise {ABILITY_NAMES[a]} above {cap}")
                scores[a] = min(cap, scores[a] + v)
        for i in sorted(self.effect_ids):
            eff = EFFECTS.get(i, {})
            for a, v in (eff.get("ability_increase") or {}).items():
                scores[a] = min(eff["maximum"], scores[a] + v)
                self.applied.append((f"{ABILITY_NAMES[a]} +{v} (max {eff['maximum']})", i))
        for k, v in (spec.get("set_abilities") or {}).items():
            a = ability(k)
            if int(v) > scores[a]:
                scores[a] = int(v)
                self.applied.append((f"{ABILITY_NAMES[a]} set to {v}", "set_abilities"))
        return scores

    def _multiclass_prereqs(self):
        if len(self.classes) < 2:
            return
        for cls, _, _ in self.classes:
            ok, need = _primary_ok(cls.data["core_traits"]["primary_ability"], self.scores)
            if not ok:
                try:
                    citation = tables.cite("multiclass_slots", self.ix)
                except tables.TableMissing:
                    citation = data.book_abbr(cls.book)
                self.W(f"multiclassing needs {need} 13+ for {cls.title} ({citation})")

    # ---- proficiencies
    def _proficiencies(self):
        first, _, _ = self.classes[0]
        ct = first.data["core_traits"]
        saves = {ability(a) for a in ct["saving_throw_proficiencies"]}
        weapons = _weapon_rules(ct["weapon_proficiencies"])
        at = ct["armor_training"]
        armor = {k for k in ("light", "medium", "heavy") if at.get(k)} | ({"shields"} if at.get("shields") else set())
        for cls, _, _ in self.classes[1:]:
            w, a, _ = multiclass_traits(self.ix, cls)
            weapons |= w
            armor |= a
        for i in self.effect_ids:                       # options such as Divine Order: Protector
            weapons |= set(EFFECTS.get(i, {}).get("weapons", ()))
            armor |= set(EFFECTS.get(i, {}).get("armor", ()))
        extra = self.spec.get("proficiencies") or {}
        armor |= {x.lower() for x in extra.get("armor", [])}
        return {"saves": saves, "weapons": weapons, "armor": armor,
                "weapon_ids": {data.slugify(x.split(":")[-1]) for x in extra.get("weapons", [])}}

    def _tools(self):
        """The background's tool, then the spec's `proficiencies.tools`; a background that offers a choice
        ("Choose one kind of Gaming Set") takes the choice from the spec."""
        chosen = list((self.spec.get("proficiencies") or {}).get("tools", []))
        bg = (self.background.data.get("tool_proficiency") or "") if self.background is not None else ""
        if bg.lower().startswith("choose"):
            if not chosen:
                self.W(f"{self.background.title}: {bg[0].lower() + bg[1:]}; "
                       "add it to \"proficiencies\": {\"tools\": [...]}")
                return [bg]
            return chosen
        return ([bg] if bg else []) + [t for t in chosen if t != bg]

    def save(self, a):
        return (self.m[a] + (self.pb if a in self.prof["saves"] else 0)
                + int(self.mods.get("saves", 0)) + int(self.mods.get(f"save_{a}", 0)))

    def _skills(self):
        skills = {data.slugify(s.title): s for s in self.ix.all("skill")}
        prof, sources = set(), {}
        if self.background is not None:
            for s in self.background.data.get("skill_proficiencies") or []:
                prof.add(data.slugify(s))
                sources[data.slugify(s)] = "background"
        for s in self.spec.get("skills") or []:
            k = data.slugify(s.split(":")[-1])
            if k not in skills:
                raise SpecError(f"no skill '{s}'")
            if k in prof:
                self.W(f"{skills[k].title} is already proficient from {sources.get(k, 'another choice')}; "
                       f"pick a different skill ({data.book_abbr(self.ix.books[0]['short'])}: choose any other)")
            prof.add(k)
            sources.setdefault(k, "chosen")
        exp = {data.slugify(s.split(":")[-1]) for s in self.spec.get("expertise") or []}
        for k in exp - prof:
            self.W(f"Expertise in {skills[k].title if k in skills else k} needs proficiency in it")
        half = any(EFFECTS.get(i, {}).get("half_pb_skills") for i in self.effect_ids)
        out = {}
        for k, s in skills.items():
            a = ability(s.data["ability"])
            b = self.m[a]
            if k in exp and k in prof:
                b += 2 * self.pb
            elif k in prof:
                b += self.pb
            elif half:
                b += self.pb // 2
            out[k] = {"title": s.title, "ability": a, "bonus": b, "proficient": k in prof, "expertise": k in exp and k in prof}
        return out

    def _initiative(self):
        b = self.m["dex"] + int(self.mods.get("initiative", 0))
        adv = False
        for i in self.effect_ids:
            eff = EFFECTS.get(i, {})
            if eff.get("initiative_pb"):
                b += self.pb
                self.applied.append((f"Initiative +{self.pb} (Proficiency Bonus)", i))
            if eff.get("initiative_advantage"):
                adv = True
        return {"bonus": b, "advantage": adv}

    # ---- defense
    def _armor(self):
        spec = self.spec
        a = spec.get("armor")
        if not a:
            return None, 0
        ref, bonus = (a.get("id"), int(a.get("bonus", 0))) if isinstance(a, dict) else (a, 0)
        return resolve(self.ix, "armor", ref), bonus

    def _ac(self):
        armor, abonus = self._armor()
        shield = self.spec.get("shield")
        sbonus = int(shield.get("bonus", 0)) if isinstance(shield, dict) else 0
        candidates = []
        if armor is not None:
            d = armor.data
            if d["category"] == "shield":
                raise SpecError("the Shield goes in \"shield\": true, not \"armor\"")
            dex = {"none": 0, "capped": min(self.m["dex"], d["ac_dex_cap"] or 99), "full": self.m["dex"]}.get(d["ac_dex"], self.m["dex"])
            candidates.append((d["ac_base"] + dex + abonus, armor.title + (f" +{abonus}" if abonus else "")))
            if d["category"] not in self.prof["armor"]:
                self.W(f"no training with {d['category'].title()} armor: Disadvantage on Str/Dex d20 tests and no spellcasting")
        else:
            candidates.append((10 + self.m["dex"], "unarmored"))
            for i in sorted(self.effect_ids):
                eff = EFFECTS.get(i, {})
                if "unarmored_ac" in eff and (eff["shield_ok"] or not shield):
                    x, y = eff["unarmored_ac"]
                    candidates.append((10 + self.m[x] + self.m[y], self.label(i)))
            if self.spec.get("mage_armor"):
                candidates.append((13 + self.m["dex"], "Mage Armor"))
        base, how = max(candidates, key=lambda c: c[0])
        ac, parts = base, [f"{how} {base}"]
        if shield and "shields" not in self.prof["armor"]:
            self.W("no Shield training: a Shield gives no AC without it (not counted)")
        elif shield:
            ac += 2 + sbonus
            parts.append(f"Shield +{2 + sbonus}")
        for i in sorted(self.effect_ids):
            eff = EFFECTS.get(i, {})
            if eff.get("ac_in_armor") and armor is not None:
                ac += eff["ac_in_armor"]
                parts.append(f"{self.label(i)} +{eff['ac_in_armor']}")
            if eff.get("ac"):
                ac += eff["ac"]
                parts.append(f"{self.label(i)} +{eff['ac']}")
        if self.mods.get("ac"):
            ac += int(self.mods["ac"])
            parts.append(f"modifiers {core.signed(int(self.mods['ac']))}")
        out = {"value": ac, "breakdown": " + ".join(parts), "options": sorted({f"{h}: {v}" for v, h in candidates})}
        if armor is not None:
            if armor.data.get("stealth_disadvantage"):
                out["stealth_disadvantage"] = True
            req = armor.data.get("strength_requirement")
            if req and self.scores["str"] < req:
                out["strength_short"] = req
        return out

    def _hp(self):
        con = self.m["con"]
        rolls = list((self.spec.get("hp") or {}).get("rolls") or []) if isinstance(self.spec.get("hp"), dict) else []
        order = []                   # hit die per character level, the starting class first
        for i, (cls, lvl, _) in enumerate(self.classes):
            order += [_parse_hd(cls.data["core_traits"])] * lvl
        first = order[0]
        total, how = first + con, [f"level 1: d{first} max {first}"]
        later = order[1:]
        if rolls and len(rolls) != len(later):
            self.W(f"hp rolls: {len(rolls)} given for {len(later)} levels after the 1st; the rest use the average")
        gained, clamped = 0, 0
        for i, die in enumerate(later):
            r = rolls[i] if i < len(rolls) else None
            if r is not None and not 1 <= int(r) <= die:
                self.W(f"hp roll {r} is not possible on a d{die}")
            v = int(r) if r is not None else die // 2 + 1
            gained += v
            if v + con < 1:                  # PHB p43: each level adds roll + Con, minimum of 1
                clamped += 1 - (v + con)
        total = max(total, 1) + gained + con * len(later) + clamped
        if later:
            how.append(f"{len(later)} more levels: {gained} ({'rolled' if rolls else 'average'})")
        how.append(f"Con {core.signed(con)} × {self.level}")
        if clamped:
            how.append(f"minimum 1 per level +{clamped}")
        for i in sorted(self.effect_ids):
            eff = EFFECTS.get(i, {})
            n = 0
            if eff.get("hp_per_level"):
                n = eff["hp_per_level"] * self.level
            if eff.get("hp_per_class_level"):
                owner = self.ix.get(i).owner_class
                n = eff["hp_per_class_level"] * next(l for c, l, _ in self.classes if c.title.lower() == owner)
            if n:
                total += n
                how.append(f"{self.label(i)} +{n}")
        if self.mods.get("hp"):
            total += int(self.mods["hp"])
            how.append(f"modifiers {core.signed(int(self.mods['hp']))}")
        dice = {}
        for d in order:
            dice[f"d{d}"] = dice.get(f"d{d}", 0) + 1
        return {"max": max(total, 1), "breakdown": "; ".join(how)}, dice

    def _speed(self):
        base = speed_ft(self.species.data.get("speed")) if self.species is not None else 30
        armor, _ = self._armor()
        heavy = armor is not None and armor.data["category"] == "heavy"
        sp, parts = base, [f"{self.species.title if self.species is not None else 'base'} {base} ft."]
        for i in sorted(self.effect_ids):
            eff = EFFECTS.get(i, {})
            if eff.get("speed_unless_heavy") and not heavy:
                sp += eff["speed_unless_heavy"]
                parts.append(f"{self.label(i)} +{eff['speed_unless_heavy']}")
            if eff.get("speed_column") and armor is None and not self.spec.get("shield"):
                owner = self.ix.get(i).owner_class
                for c, l, _ in self.classes:
                    if c.title.lower() == owner:
                        v = c.data["levels"][l - 1]["columns"].get(eff["speed_column"], "")
                        n = speed_ft(v) if re.search(r"\d", v) else 0
                        sp += n
                        parts.append(f"{self.label(i)} +{n}")
        req = armor.data.get("strength_requirement") if armor is not None else None
        if req and self.scores["str"] < req:
            sp -= 10
            parts.append(f"{armor.title} needs Str {req}: -10")
        if self.mods.get("speed"):
            sp += int(self.mods["speed"])
            parts.append(f"modifiers {core.signed(int(self.mods['speed']))}")
        return {"walk": sp, "breakdown": " ".join(parts)}

    def _size(self):
        if self.spec.get("size"):
            return self.spec["size"].title()
        s = self.species.data.get("size", "Medium") if self.species is not None else "Medium"
        if " or " in s:
            self.W(f"{self.species.title} can be {' or '.join(re.findall(r'(Tiny|Small|Medium|Large)', s))}; "
                   "add \"size\" (Medium assumed)")
        return re.match(r"\w+", s).group()

    def _carry(self, size):
        mult = tables.carrying()
        sizes = list(mult)
        key = next((k for k in sizes if size.lower() in k.lower()), None)
        if key is None:
            raise tables.TableMissing(f"carrying capacity for {size} is not in this data set")
        if any(EFFECTS.get(i, {}).get("size_up_for_carrying") for i in self.effect_ids):
            key = sizes[min(sizes.index(key) + 1, len(sizes) - 1)]
        carry, drag = mult[key]
        s = self.scores["str"]
        return {"carry_lb": s * carry, "drag_lift_push_lb": s * drag}

    # ---- offense
    def _attacks(self):
        out = []
        monk = next((l for c, l, _ in self.classes if c.slug == "monk"), 0)
        if monk and (self._armor()[0] is not None or self.spec.get("shield")):
            monk = 0                         # Martial Arts: no armor and no Shield (PHB p101)
            self.W("Martial Arts needs no armor and no Shield: monk weapon and Unarmed Strike benefits not counted")
        martial_die = None
        if monk:
            martial_die = self.ix.get("class:monk").data["levels"][monk - 1]["columns"].get("Martial Arts")
        archery = sum(EFFECTS[i].get("ranged_attack", 0) for i in self.effect_ids if i in EFFECTS)
        atk_mod, dmg_mod = int(self.mods.get("attack", 0)), int(self.mods.get("damage", 0))
        for w in self.spec.get("weapons") or []:
            ref, bonus = (w.get("id"), int(w.get("bonus", 0))) if isinstance(w, dict) else (w, 0)
            e = resolve(self.ix, "weapon", ref)
            d = e.data
            props = {p["name"].lower(): p for p in d.get("properties", [])}
            ranged = d["kind"] == "ranged"
            if ranged:
                a = "dex"
            elif "finesse" in props:
                a = max(("str", "dex"), key=lambda x: self.m[x])
            else:
                a = "str"
            die = d["damage"]
            monk_weapon = monk and not ranged and (d["category"] == "simple" or "light" in props)
            if monk_weapon:
                a = max(("str", "dex"), key=lambda x: self.m[x])
                if martial_die and core_die(martial_die) > core_die(die):
                    die = martial_die
            prof = weapon_proficient(self.prof["weapons"], e, self.prof["weapon_ids"])
            hit = self.m[a] + (self.pb if prof else 0) + bonus + atk_mod + (archery if ranged else 0)
            dm = self.m[a] + bonus + dmg_mod
            row = {"weapon": e.sid, "name": e.title + (f" +{bonus}" if bonus else ""), "ability": a,
                   "attack": hit, "damage": f"{die}{fmt_mod(dm)} {d['damage_type']}", "proficient": prof,
                   "properties": d.get("properties_raw"), "mastery": d.get("mastery")}
            if "versatile" in props and props["versatile"].get("damage"):
                row["two_handed"] = f"{props['versatile']['damage']}{fmt_mod(dm)} {d['damage_type']}"
            if not prof:
                self.W(f"not proficient with {e.title}: no Proficiency Bonus on its attack rolls")
            out.append(row)
        a = "str"
        die = "1"
        if monk:
            a = max(("str", "dex"), key=lambda x: self.m[x])
            die = martial_die or "1d6"
        dm = self.m[a] + dmg_mod
        unarmed = (f"{die}{fmt_mod(dm)} Bludgeoning" if die != "1" else f"{max(1 + dm, 1)} Bludgeoning")
        out.append({"weapon": "term:unarmed-strike", "name": "Unarmed Strike", "ability": a,
                    "attack": self.m[a] + self.pb + atk_mod, "damage": unarmed, "proficient": True,
                    "properties": None, "mastery": None})
        return out

    def _spellcasting(self):
        out = []
        for cls, lvl, sub in self.classes:
            prog = caster_progression(cls, sub, lvl)
            if not prog:
                continue
            src = cls.data["spellcasting"] if prog != "third" else sub.data["spellcasting"]
            slots, cantrips, prepared = own_slots(cls, lvl, sub)
            if prog == "pact":
                row = cls.data["levels"][lvl - 1]
                top = row["pact_slot_level"]
            else:
                top = max(slots) if slots else 0
            if prog == "third" and not slots:
                continue
            a = ability(src["ability"])
            spell_class = cls.slug
            if prog == "third":
                body = " ".join(b.get("text", "") for f in sub.children if f.title == "Spellcasting" for b in f.content)
                m = re.search(r"from the (\w+) spell list", body)
                spell_class = m.group(1).lower() if m else spell_class
            out.append({"class": cls.title, "via": sub.title if prog == "third" else None,
                        "ability": a, "spell_list": spell_class,
                        "save_dc": 8 + self.pb + self.m[a] + int(self.mods.get("spell_dc", 0)),
                        "attack": self.pb + self.m[a] + int(self.mods.get("spell_attack", 0)),
                        "cantrips": cantrips, "prepared": prepared, "max_spell_level": top,
                        "progression": prog})
        slots, pact, clevel = spell_slots(self.classes)
        if not out:
            return None
        return {"casters": out, "slots": {str(k): v for k, v in sorted(slots.items())}, "pact": pact,
                "caster_level": clevel, "multiclass_table": sum(1 for c in out if c["progression"] != "pact") > 1,
                "cantrip_dice": 1 + (self.level >= 5) + (self.level >= 11) + (self.level >= 17)}


    # ---- chosen spells
    def _spells(self, sc):
        """The spec's `spells`, resolved and checked: on a caster's list, castable, within the caster's
        cantrip and prepared counts. An entry with a `source` (a feat, species or feature that grants
        it) is not counted or list-checked; `"prepared": false` (a wizard's spellbook) is not counted."""
        casters = (sc or {}).get("casters") or []
        out, counts = [], {}
        for x in self.spec.get("spells") or []:
            x = x if isinstance(x, dict) else {"spell": x}
            e = resolve(self.ix, "spell", x.get("spell") or x.get("id") or "")
            d = e.data
            lists = {c.lower() for c in e.classes}
            src = x.get("source")
            caster = None
            if x.get("class"):
                want = data.slugify(str(x["class"]).split(":")[-1])
                caster = next((c for c in casters if data.slugify(c["class"]) == want), None)
                if caster is None:
                    self.W(f"{e.title}: the character has no {x['class']} spellcasting")
            elif not src:
                caster = next((c for c in casters if c["spell_list"] in lists), None)
                if caster is None:
                    self.W(f"{e.title} is not on the "
                           + (" or ".join(sorted({c['spell_list'].title() for c in casters})) or "character's")
                           + " spell list; add \"source\" when a feat, species or feature grants it")
            if caster and not src:
                if caster["spell_list"] not in lists:
                    self.W(f"{e.title} is not on the {caster['spell_list'].title()} spell list")
                if d["level"] > caster["max_spell_level"]:
                    self.W(f"{e.title} is level {d['level']}; {caster['class']} casts up to level {caster['max_spell_level']}")
                prepared = x.get("prepared", True)
                if d["level"] == 0 or prepared:
                    k = (caster["class"], "cantrips" if d["level"] == 0 else "prepared")
                    counts[k] = counts.get(k, 0) + 1
            out.append({"id": e.sid, "title": e.title, "level": d["level"], "school": d["school"],
                        "casting_time": d["casting_time"], "range": d["range"], "components": d["components"],
                        "duration": d["duration"], "concentration": d["concentration"], "ritual": d["ritual"],
                        "class": caster["class"] if caster else None, "source": src,
                        "prepared": bool(d["level"] == 0 or src or x.get("prepared", True)),
                        "book": e.book, "page": e.page})
        for c in casters:
            for kind in ("cantrips", "prepared"):
                n, cap = counts.get((c["class"], kind), 0), c[kind] or 0
                if n > cap:
                    self.W(f"{n} {c['class']} {'cantrips' if kind == 'cantrips' else 'prepared spells'} chosen; "
                           f"the class gives {cap}")
        out.sort(key=lambda s: (s["level"], s["title"]))
        return out


def core_die(d):
    m = re.match(r"(\d*)d(\d+)", d or "")
    return (int(m.group(1) or 1) * (int(m.group(2)) + 1) / 2) if m else 0


def fmt_mod(n):
    return f" + {n}" if n > 0 else f" - {-n}" if n < 0 else ""


# ---------------------------------------------------------------- level up
def level_up(spec, class_ref, subclass=None, ix=None):
    """-> {"before", "after", "class", "new_features", "changes"}: the sheet before and after gaining one
    level in `class_ref` (a new class is added at level 1, as a multiclass)."""
    import copy
    ix = ix or data.load()
    before = build(spec, ix)
    cls = resolve(ix, "class", class_ref)
    spec2 = copy.deepcopy(spec)
    entries = [c if isinstance(c, dict) else {"class": c, "level": 1} for c in spec2["classes"]]
    hit = next((c for c in entries if resolve(ix, "class", c["class"]) is cls), None)
    if hit is None:
        hit = {"class": cls.slug, "level": 0}
        entries.append(hit)
    hit["level"] = int(hit.get("level", 1)) + 1
    if subclass:
        hit["subclass"] = subclass
    spec2["classes"] = entries
    if isinstance(spec2.get("hp"), dict) and spec2["hp"].get("rolls"):
        # rolls run in class order (levels after the 1st); the new level takes the average, at its class's place
        at = sum(int(c.get("level", 1)) for c in entries[:entries.index(hit) + 1]) - 1 - 1
        spec2["hp"]["rolls"].insert(min(at, len(spec2["hp"]["rolls"])), None)
    after = build(spec2, ix)
    old = {(f["class"], f["level"], f["title"]) for f in before["features"]}
    new_features = [f for f in after["features"] if (f["class"], f["level"], f["title"]) not in old]
    changes = []

    def diff(label, a, b):
        if a != b:
            changes.append({"what": label, "from": a, "to": b})
    diff("level", before["level"], after["level"])
    diff("proficiency bonus", before["proficiency_bonus"], after["proficiency_bonus"])
    diff("hit points", before["hit_points"]["max"], after["hit_points"]["max"])
    diff("attacks per action", before["attacks_per_action"], after["attacks_per_action"])
    bs, as_ = before.get("spellcasting") or {}, after.get("spellcasting") or {}
    diff("spell slots", bs.get("slots"), as_.get("slots"))
    diff("pact slots", bs.get("pact"), as_.get("pact"))
    for c in as_.get("casters", []):
        o = next((x for x in bs.get("casters", []) if x["class"] == c["class"]), {})
        diff(f"{c['class']} cantrips", o.get("cantrips"), c["cantrips"])
        diff(f"{c['class']} prepared spells", o.get("prepared"), c["prepared"])
    for k, v in after["resources"].get(cls.title, {}).items():
        diff(f"{cls.title} {k}", before["resources"].get(cls.title, {}).get(k), v)
    if len(entries) > len(spec["classes"]):
        _, armor, first = multiclass_traits(ix, cls)
        changes.append({"what": "multiclass", "from": None, "to": first})
    return {"class": cls.sid, "new_level": hit["level"], "before": before, "after": after,
            "new_features": new_features, "changes": changes,
            "warnings": [w for w in after["warnings"] if w not in before["warnings"]]}
