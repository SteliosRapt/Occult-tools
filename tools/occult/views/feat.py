"""Feat card view model: category tag, prerequisite / ability / repeatable strip, benefits."""
from ._common import body_blocks, html, key

ABBR = {"Strength": "Str", "Dexterity": "Dex", "Constitution": "Con", "Intelligence": "Int",
        "Wisdom": "Wis", "Charisma": "Cha"}


def ability_short(ai):
    """{"abilities": [...], "amount": 1, "maximum": 20} -> `+1 Str or Dex (max 20)`."""
    if not ai:
        return None
    ab = " or ".join(ABBR.get(a, a) for a in ai["abilities"]) or "any"
    return f"+{ai['amount']} {ab}" + (f" (max {ai['maximum']})" if ai.get("maximum") else "")


def card(ix, e):
    d = e.data
    cat = d["category"]
    return {
        "kind": "feat", "size": "poker", "key": key(e), "title": e.title, "page": e.page,
        "tag": f"{cat} Feat", "category": cat, "category_id": cat.lower().replace(" ", "-"),
        "prerequisite": html(d["prerequisite"], False) if d.get("prerequisite") else None,
        "ability": ability_short(d.get("ability_increase")), "repeatable": bool(d.get("repeatable")),
        "body": body_blocks(e.content),
        "back": {"key": f"feat-{cat.lower().replace(' ', '-')}", "kicker": "Feat", "title": cat, "icon": None},
    }
