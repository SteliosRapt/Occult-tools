"""Deck card view model (the Deck of Many More Things `card` children): tarot size, the face image
full-bleed (it carries its own gold frame), the card's name and effect in a panel over its foot.
Without a local face image the card falls back to the grimoire frame with the same text."""
from ._common import body_blocks, key, slug


def card(ix, e):
    deck = e.data.get("deck") or (e.parent.title if e.parent else "Deck")
    return {
        "kind": "deck_card", "size": "tarot", "key": key(e), "title": e.title, "page": e.page,
        "deck": deck, "body": body_blocks(e.content),
        "back": {"key": f"deck-{slug(deck)}", "kicker": "Magic Item", "title": deck, "icon": None},
    }
