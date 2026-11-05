"""Deck face card models, with the deck title read from the data."""
from ._common import body_blocks, key, slug


def card(ix, e):
    deck = e.data.get("deck") or (e.parent.title if e.parent else "Deck")
    return {
        "kind": "deck_card", "size": "tarot", "key": key(e), "title": e.title, "page": e.page,
        "deck": deck, "body": body_blocks(e.content),
        "back": {"key": f"deck-{slug(deck)}", "kicker": "Magic Item", "title": deck, "icon": None},
    }
