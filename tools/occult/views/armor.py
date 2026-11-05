"""Armour card view model: AC hero, Strength/Stealth/don-doff grid, training rules."""
from ._common import html, key, short_units



def ac_line(d):
    if d["ac_is_bonus"]:
        return d["ac"], "bonus to AC"
    if d["ac_dex"] == "none":
        return str(d["ac_base"]), "no Dex modifier"
    if d["ac_dex_cap"]:
        return str(d["ac_base"]), f"+ Dex modifier (max {d['ac_dex_cap']})"
    return str(d["ac_base"]), "+ Dex modifier"


def card(ix, e):
    d = e.data
    cat = d["category"]
    ac, ac_note = ac_line(d)
    slug = "shield" if cat == "shield" else "light-medium-or-heavy-armor"
    training = next((x for x in ix.all("section") if x.slug == slug and
                     any(a.slug == "armor-training" for a in x.ancestors())), None)
    rules = ([{"label": "Training", "html": html(training.content[0]["text"])}]
             if training and training.content and training.content[0].get("text") else [])
    # the Strength and Stealth explanations live in labelled list items of the Armor section
    section = next((x for x in ix.all("section") if x.slug == "armor"), None)
    for b in section.content if section else []:
        for it in b.get("items", []) if b["type"] == "list" else []:
            lab = it.get("label") or ""
            if (lab == "Strength" and d["strength_requirement"]) or (lab == "Stealth" and d["stealth_disadvantage"]):
                rules.append({"label": lab, "html": html(it["text"])})
    don, doff = short_units(d["don"]), short_units(d["doff"])
    return {
        "kind": "armor", "size": "poker", "key": key(e), "title": e.title, "page": e.page,
        "type_line": "Shield" if cat == "shield" else f"{cat.title()} Armor",
        "ac": ac, "ac_note": ac_note,
        "str_req": f"Str {d['strength_requirement']}" if d["strength_requirement"] else "—",
        "stealth": "Disadvantage" if d["stealth_disadvantage"] else "—",
        "don_doff": don if don == doff else f"{don} · {doff}",
        "weight": d["weight"], "cost": d["cost"], "rules": rules,
    }
