"""Card model registry. Optional components register card types and model extensions."""
from . import armor, creature, feat, magic_item, option, spell, term, weapon
from .. import components, data

CARDS = {"spell": spell.card, "weapon": weapon.card, "armor": armor.card, "term": term.card,
         "creature": creature.card, "feat": feat.card, "option": option.card,
         "magic-item": magic_item.card}

components.apply("register_cards", CARDS)

def supports(e):
    return e.type in CARDS


def back(e, m):
    """The category back of a card model (specialized models may set their own)."""
    if e.type == "spell":
        s = m["school"]
        return {"key": f"school-{m['school_id']}", "kicker": "Spell", "title": s, "icon": f"school-{m['school_id']}"}
    if e.type == "term":
        tag = m["tag"]
        return {"key": f"term-{tag.lower().replace(' ', '-')}", "kicker": "Rules Glossary", "title": tag, "icon": None}
    if e.type == "armor":
        return {"key": "armor", "kicker": "Equipment", "title": "Armor", "icon": "ui-shield"}
    if e.type == "weapon":
        return {"key": "weapon", "kicker": "Equipment", "title": "Weapon", "icon": None}
    return {"key": e.type, "kicker": "Bestiary", "title": "Creature", "icon": None}




def for_(ix, e, *args, **options):
    """Build the card model, then apply installed component model extensions."""
    args = components.transform("card_options", args, options)
    m = CARDS[e.type](ix, e)
    m.setdefault("back", back(e, m))
    m.setdefault("book", data.book_abbr(e.book))
    components.apply("card_model", m, ix, e, *args)
    return m
