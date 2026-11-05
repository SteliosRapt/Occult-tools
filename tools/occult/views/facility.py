"""Bastion facility card view model (DMG chapter 8 and later books): type and level tag, the
prerequisite / space / hirelings / orders strip, art when the book has some, then the entry's text
(order options as a list; long ones continue on the next card)."""
from ._common import body_blocks, html, key


def card(ix, e):
    d = e.data
    special = d.get("facility_type") == "special"
    level = d.get("level")
    kind = "Special Facility" if special else "Basic Facility"
    orders = d.get("orders") or []
    stats = []
    if d.get("prerequisite"):
        stats.append({"label": "Prerequisite", "html": html(d["prerequisite"], False), "wide": True})
    stats.append({"label": "Space", "html": html(", ".join(d.get("space") or []) or "—", False), "wide": False})
    stats.append({"label": "Hirelings", "html": html(str(d.get("hirelings") or "—"), False), "wide": False})
    if orders:
        stats.append({"label": "Order" if len(orders) == 1 else "Orders", "html": html(", ".join(orders), False),
                      "wide": True})
    back = f"Level {level}" if level else "Basic"
    return {
        "kind": "facility", "size": "poker", "key": key(e), "title": e.title, "page": e.page,
        "tag": kind, "level": level, "special": special,
        "type_line": (f"Level {level} " if level else "") + kind,
        "stats": stats, "body": body_blocks(e.content),
        "back": {"key": f"facility-{level or 'basic'}", "kicker": "Bastion", "title": f"{back} Facilities"
                 if level else "Basic Facilities", "icon": None},
    }
