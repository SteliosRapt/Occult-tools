"""Class views: the level progression and core traits, as Markdown (shared by `show class:*`
and the collections) and as table data for the class booklet (views/books.py)."""
from .. import text

ORD = {1: "1st", 2: "2nd", 3: "3rd"}


def progression(d):
    """The class level table from data.levels (not the scraped table): (columns, rows)."""
    lv = d["levels"]
    extra = list(dict.fromkeys(k for x in lv for k in (x.get("columns") or {})))
    cantrips = any(x.get("cantrips_known") is not None for x in lv)
    prepared = any(x.get("prepared_spells") is not None for x in lv)
    slots = max((int(k) for x in lv for k in (x.get("spell_slots") or {})), default=0)
    pact = any(x.get("pact_slots") for x in lv)
    cols = ["Lvl", "PB", *extra]
    cols += ["Cantrips"] * cantrips + ["Prepared"] * prepared
    cols += [ORD.get(i, f"{i}th") for i in range(1, slots + 1)] + ["Pact slots"] * pact + ["Features"]
    rows = []
    for x in lv:
        r = [x["level"], x["proficiency_bonus"], *[(x.get("columns") or {}).get(k, "-") for k in extra]]
        r += [x.get("cantrips_known")] * cantrips + [x.get("prepared_spells")] * prepared
        r += [(x.get("spell_slots") or {}).get(str(i)) or "-" for i in range(1, slots + 1)]
        if pact:
            r.append(f"{x['pact_slots']}×L{x['pact_slot_level']}" if x.get("pact_slots") else "-")
        r.append(", ".join(x["features"]) or "-")
        rows.append(["-" if c is None else c for c in r])
    return cols, rows


def progression_md(d):
    return "#### Level progression\n" + text.md_table(*progression(d))


def traits_md(ct):
    """Core traits not already in the brief lines (replaces the scraped key/value table)."""
    return "\n".join([f"Skills: {ct['skill_proficiencies']['text']}",
                      f"Weapons: {ct['weapon_proficiencies'] or '—'} · Armor: {ct['armor_training']['text'] or '—'}"
                      f" · Tools: {ct['tool_proficiencies'] or '—'}",
                      f"Starting equipment: {ct['starting_equipment']}"])
