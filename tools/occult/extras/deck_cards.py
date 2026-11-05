"""Optional deck face cards."""

def register_cards(cards):
    from ..views import deck_card
    cards["card"] = deck_card.card


def card_types():
    return ['cards']


def register_types(types):
    types["card"] = dict(aliases=["cards"], sort=lambda e: e.order)
