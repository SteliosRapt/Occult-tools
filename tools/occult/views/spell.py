"""Spell card view model."""
import re

from ._common import body_blocks, caster_classes, html, key, short_units


def card(ix, e):
    d = e.data
    ct = d["casting_time"].replace(" or Ritual", "")
    trigger = None
    if ", which you take " in ct:
        ct, trigger = ct.split(", which you take ", 1)
        trigger = html(trigger.rstrip("."), False)
    dur = d["duration"]
    if d["concentration"]:
        dur = re.sub(r"^Concentration, up to ", "", dur)
    mat, level, school = d["material"], d["level"], d["school"]
    return {
        "kind": "spell", "size": "poker", "key": key(e), "title": e.title, "page": e.page,
        "level": level, "school": school, "school_id": school.lower(),
        "type_line": f"{school} Cantrip" if level == 0 else f"Level {level} {school}",
        "casting_time": short_units(ct), "trigger": trigger, "ritual": d["ritual"],
        "range": short_units(d["range"]), "duration": short_units(dur), "concentration": d["concentration"],
        "components": d["component_types"], "material": html(mat, False) if mat else None,
        "costly": bool(mat and "GP" in mat), "consumed": bool(mat and "consume" in mat),
        "classes": e.classes, "all_classes": caster_classes(ix),
        "body": body_blocks(e.content),
    }
