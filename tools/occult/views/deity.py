"""Deity card view model: pantheon tag, epithet, the holy symbol (art, in a round medallion; a
Cinzel initial when the book prints none), rank / plane / worshipers / symbol strip, and a short text:
the first paragraph of the entry (FRHoF prints several pages per god; the card is a reminder)."""
from ._common import body_blocks, html, key, slug


def card(ix, e):
    d = e.data
    pantheon = d.get("pantheon") or "Deity"
    first = next((b for b in e.content if b["type"] == "paragraph" and not b.get("label")), None)
    stats = [(lab, v) for lab, v in (("Rank", (d.get("rank") or "").title()), ("Plane", d.get("plane")),
                                     ("Worshipers", d.get("worshipers")), ("Symbol", d.get("symbol"))) if v]
    return {
        "kind": "deity", "size": "poker", "key": key(e), "title": e.title, "page": e.page,
        "tag": f"{pantheon} Pantheon" if d.get("pantheon") else "Deity", "epithet": d.get("epithet"),
        "alt_names": d.get("alt_names") or [],
        # Rank and Plane share a row when both are printed; every other field is a full row
        "stats": [{"label": lab, "html": html(v, False), "wide": lab not in ("Rank", "Plane") or not (d.get("rank") and d.get("plane"))}
                  for lab, v in stats],
        "body": body_blocks([first]) if first else [],
        "back": {"key": f"pantheon-{slug(pantheon)}", "kicker": "Deity", "title": f"{pantheon} Pantheon"
                 if d.get("pantheon") else "Deity", "icon": None},
    }
