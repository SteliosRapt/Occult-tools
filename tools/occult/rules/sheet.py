"""Plain-text renderings of engine results, for `./occult character|encounter` (Markdown-friendly)."""
from . import core
from .tables import ABILITIES, ABILITY_NAMES

s = core.signed


def _n(x):
    return int(x) if float(x).is_integer() else x


def character_md(sh):
    cls = " / ".join(f"{c['title']} {c['level']}" + (f" ({c['subclass_title']})" if c["subclass_title"] else "")
                     for c in sh["classes"])
    who = " · ".join(x.split(":")[1].replace("-", " ").title() for x in (sh["species"], sh["background"]) if x)
    L = [f"# {sh['name']}", f"Level {sh['level']} {cls}" + (f" · {who}" if who else "")
         + f" · Proficiency Bonus {s(sh['proficiency_bonus'])}", ""]
    ac, hp, sp, ini = sh["armor_class"], sh["hit_points"], sh["speed"], sh["initiative"]
    dice = " + ".join(f"{n}{d}" for d, n in sh["hit_dice"].items())
    L.append(f"AC {ac['value']} ({ac['breakdown']}) · HP {hp['max']} · Hit Dice {dice} · "
             f"Speed {sp['walk']} ft. · Initiative {s(ini['bonus'])}{' (Advantage)' if ini['advantage'] else ''} · "
             f"Passive Perception {sh['passive_perception']}")
    L.append("")
    L.append("| | " + " | ".join(a.upper() for a in ABILITIES) + " |")
    L.append("|---|" + "---|" * 6)
    ab = sh["abilities"]
    L.append("| Score | " + " | ".join(str(ab[a]["score"]) for a in ABILITIES) + " |")
    L.append("| Mod | " + " | ".join(s(ab[a]["mod"]) for a in ABILITIES) + " |")
    L.append("| Save | " + " | ".join(s(ab[a]["save"]) + ("*" if ab[a]["save_proficient"] else "") for a in ABILITIES) + " |")
    L.append("")
    sk = [f"{v['title']} {s(v['bonus'])}" + ("**" if v["expertise"] else "*" if v["proficient"] else "")
          for k, v in sh["skills"].items()]
    L.append("Skills: " + ", ".join(sk) + "  (* proficient, ** expertise)")
    L.append("")
    L.append(f"## Attacks ({sh['attacks_per_action']} per Attack action)")
    for a in sh["attacks"]:
        extra = []
        if a.get("two_handed"):
            extra.append(f"two-handed {a['two_handed']}")
        if a.get("properties"):
            extra.append(a["properties"])
        if a.get("mastery"):
            extra.append(f"Mastery: {a['mastery']}")
        if not a["proficient"]:
            extra.append("not proficient")
        L.append(f"- {a['name']}: {s(a['attack'])} to hit, {a['damage']}" + (f" ({'; '.join(extra)})" if extra else ""))
    sc = sh.get("spellcasting")
    if sc:
        L += ["", "## Spellcasting"]
        for c in sc["casters"]:
            via = f" via {c['via']}" if c["via"] else ""
            bits = [f"{ABILITY_NAMES[c['ability']]}", f"save DC {c['save_dc']}", f"attack {s(c['attack'])}"]
            if c["cantrips"]:
                bits.append(f"{c['cantrips']} cantrips")
            if c["prepared"]:
                bits.append(f"{c['prepared']} prepared")
            bits.append(f"spells up to level {c['max_spell_level']} ({c['spell_list'].title()} list)")
            L.append(f"- {c['class']}{via}: " + ", ".join(bits))
        if sc["slots"]:
            how = f" (Multiclass Spellcaster table, caster level {sc['caster_level']})" if sc["multiclass_table"] else ""
            L.append("- Slots: " + ", ".join(f"{k}: {v}" for k, v in sc["slots"].items()) + how)
        if sc["pact"]:
            L.append(f"- Pact Magic: {sc['pact']['slots']} slots of level {sc['pact']['level']}")
        L.append(f"- Cantrip damage dice: ×{sc['cantrip_dice']} (character level {sh['level']})")
    if sh.get("spells"):
        L += ["", "## Spells"]
        lv = None
        for x in sh["spells"]:
            if x["level"] != lv:
                lv = x["level"]
                L.append(f"{'Cantrips' if lv == 0 else f'Level {lv}'}:")
            tags = [t for t, on in (("C", x["concentration"]), ("R", x["ritual"])) if on]
            via = x["source"] or x["class"]
            L.append(f"- {x['title']} `{x['id']}`" + (f" ({', '.join(tags)})" if tags else "")
                     + (f" · {via}" if via else "") + ("" if x["prepared"] else " · not prepared"))
    if sh["resources"]:
        L += ["", "## Class resources"]
        for c, cols in sh["resources"].items():
            L.append(f"- {c}: " + ", ".join(f"{k} {v}" for k, v in cols.items()))
    L += ["", "## Features"]
    for f in sh["features"]:
        L.append(f"- {f['class']} {f['level']}: {f['title']}" + (f" `{f['id']}`" if f["id"] else ""))
    if sh["feats"]:
        L += ["", "## Feats"]
        L += [f"- {f['title']} `{f['id']}` ({f['source']})" for f in sh["feats"]]
    if sh.get("options"):
        L += ["", "## Options"]
        L += [f"- {o['title']} `{o['id']}`" + (f" ({o['of']})" if o["of"] else "") for o in sh["options"]]
    pr = sh["proficiencies"]
    cc = sh["carrying_capacity"]
    L += ["", f"Proficiencies: armor {', '.join(pr['armor']) or 'none'}; weapons {', '.join(pr['weapons']) or 'none'}"
          + (f"; tools {', '.join(pr['tools'])}" if pr.get("tools") else ""),
          f"HP: {hp['breakdown']}",
          f"Speed: {sp['breakdown']} · Size {sh['size']} · Carry {_n(cc['carry_lb'])} lb., drag/lift/push {_n(cc['drag_lift_push_lb'])} lb.",
          f"XP: {sh['xp']['this_level']:,} for this level" + (f", {sh['xp']['next_level']:,} for the next" if sh['xp']['next_level'] else "")]
    if sh.get("languages"):
        L.append("Languages: " + ", ".join(sh["languages"]))
    if sh.get("equipment") or sh.get("coins"):
        L.append("Equipment: " + ", ".join(sh.get("equipment") or [])
                 + ("; " if sh.get("equipment") and sh.get("coins") else "")
                 + " ".join(f"{v} {k.upper()}" for k, v in (sh.get("coins") or {}).items()))
    if ac.get("stealth_disadvantage"):
        L.append("Armor: Disadvantage on Dexterity (Stealth) checks")
    if sh.get("choices"):
        L.append("Choices: " + "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in sh["choices"].items()))
    for n in sh["notes"]:
        L.append(f"Note: {n}")
    for r in sh["applied_rules"]:
        L.append(f"Rule: {r['rule']} ({r['from']})")
    if sh["warnings"]:
        L += ["", "## Check"]
        L += [f"- {w}" for w in sh["warnings"]]
    return "\n".join(L)


def level_up_md(r):
    a = r["after"]
    c = next(x for x in a["classes"] if x["class"] == r["class"])
    L = [f"# {a['name']}: {c['title']} {r['new_level']} (character level {a['level']})", ""]
    if r["new_features"]:
        L.append("New features:")
        L += [f"- {f['title']}" + (f" `{f['id']}`" if f["id"] else "") for f in r["new_features"]]
    if r["changes"]:
        L.append("")
        L.append("Changes:")
        for ch in r["changes"]:
            if ch["what"] == "multiclass":
                L.append(f"- multiclass: {ch['to']}")
            else:
                L.append(f"- {ch['what']}: {fmt(ch['from'])} -> {fmt(ch['to'])}")
    if r["warnings"]:
        L += ["", "Check:"] + [f"- {w}" for w in r["warnings"]]
    return "\n".join(L)


def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, dict):
        if "slots" in v and "level" in v:
            return f"{v['slots']} × level {v['level']}"
        return ", ".join(f"{k}: {x}" for k, x in v.items()) or "-"
    return str(v)


def encounter_md(ev):
    lv = ev["party"]
    L = [f"Party: {len(lv)} character{'s' * (len(lv) != 1)}, levels {', '.join(map(str, lv))}",
         "Budget: " + ", ".join(f"{d.title()} {v:,}" for d, v in ev["budget"].items()) + f" XP ({ev['source']})", ""]
    for c in ev["creatures"]:
        L.append(f"- {c['count']} × {c['title']} `{c['id']}` (CR {c['cr']}, {c['xp_each']:,} XP each) = {c['xp']:,} XP")
    L.append("")
    L.append(f"Total: {ev['total_xp']:,} XP → {ev['rating'].title()}" + (" (lair XP)" if ev["lair"] else ""))
    for w in ev["warnings"]:
        L.append(f"Warning: {w}")
    return "\n".join(L)
