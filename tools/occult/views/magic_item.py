"""Magic-item card view model: category tag, the subtitle line as printed, rarity / attunement /
charges badges, then the entry's text (paragraphs, run-ins, lists, tables) like a spell body.

Long entries continue on the next card via the
fit contract (tools/render/fit.js); tables split by row there.
"""
from ._common import body_blocks, key, slug

RARITIES = ["Common", "Uncommon", "Rare", "Very Rare", "Legendary", "Artifact", "Varies"]


def rarity_id(r):
    return slug(r) if r in RARITIES else "unknown"


def attunement(a):
    """True -> `Attunement`; "by a Wizard" -> `Attunement by a Wizard`; False -> None."""
    if not a:
        return None
    return "Attunement" if a is True else f"Attunement {a}"


def charges(d):
    """`7 charges · regains 1d3 daily at dawn`; `recharges at dawn` for a use-per-dawn item."""
    n, r = d.get("charges"), d.get("recharge")
    bits = []
    if n not in (None, ""):
        bits.append(f"{n} charge{'' if str(n) == '1' else 's'}")
    if r:
        bits.append(("recharges at dawn" if not n else "regains at dawn") if r == "dawn" else
                    f"regains {r}" if n else f"recharges {r}")
    return " · ".join(bits) or None


def card(ix, e):
    d = e.data
    rarity = d.get("rarity") or "Varies"
    cat = d.get("category") or "Wondrous Item"
    return {
        "kind": "magic_item", "size": "poker", "key": key(e), "title": e.title, "page": e.page,
        "tag": cat, "category_id": slug(cat), "subtitle": d.get("subtitle") or f"{cat}, {rarity}",
        "rarity": "Rarity Varies" if rarity == "Varies" else rarity, "rarity_id": rarity_id(rarity),
        "attunement": attunement(d.get("attunement")), "charges": charges(d),
        "body": body_blocks(e.content),
        "back": {"key": f"rarity-{rarity_id(rarity)}", "kicker": "Magic Item",
                 "title": "Rarity Varies" if rarity == "Varies" else rarity, "icon": None},
    }
