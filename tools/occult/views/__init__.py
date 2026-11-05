"""View models: entity -> plain dict for a template (stdlib only).

    views.for_(ix, e)                        # the card model for e (see CARDS)
    views.for_(ix, e, art="off")             # without art (`make cards --art off`)
    views.for_(ix, e, variant="Potion of Greater Healing")   # a named variant's art, when it has one
    views.supports(e)                        # whether a card view exists for e's type

Each model has `kind` (the template name: templates/cards/<kind>.j2), `size` (poker | tarot),
`key` (unique per deck; continuation cards share it), `title`, `page` and `back` (the category
back for `make cards --backs category`: {key, kicker, title, icon}). Card types in ART also get
`art` (views._common.art: a local image, or None), `art_wanted` (the data refers to an image) and
`art_missing` (it does, but the file is not in img/: run `./occult fetch images`);
creatures also get `token` (shown when there is no art, or when fit.js drops the art).
Book contexts are in books.py.
"""
from . import armor, creature, deck_card, deity, facility, feat, magic_item, option, spell, term, weapon
from ._common import ART_MODES, art as art_model, item_art, with_art
from .. import data

CARDS = {"spell": spell.card, "weapon": weapon.card, "armor": armor.card, "term": term.card,
         "creature": creature.card, "feat": feat.card, "option": option.card,
         "magic-item": magic_item.card, "deity": deity.card, "facility": facility.card, "card": deck_card.card}

# Card types that show art: the image roles they use, in order of preference.
ART = {"magic-item": ("art",), "weapon": ("art",), "armor": ("art",), "creature": ("art",),
       "deity": ("art",), "facility": ("art",), "card": ("art",)}
# The largest box (w, h in mm) each kind of image prints in, for its print copy (images.derived): an
# art panel grows to the card's width and --art-grow (160px) (style/base/cards.css), a deck card's face fills
# the tarot card, a token is a 30px disc.
ART_BOX = {"card": (72, 122)}
ART_BOX_CARD = (62, 43)
TOKEN_BOX = (10, 10)


def supports(e):
    return e.type in CARDS


def back(e, m):
    """The category back of a card model (feat, option, deity, facility and card models set their own)."""
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


def variant_refs(e, variant):
    """Image refs for a magic item named by one of its variants: that variant's first, then the entry's."""
    if not variant:
        return e.images
    v = next((v for v in e.data.get("variants") or [] if isinstance(v, dict)
              and variant.lower() in ((v.get("title") or "").lower(), (v.get("record") or "").lower())), None)
    return list((v or {}).get("images") or []) + list(e.images)


def for_(ix, e, art="auto", variant=None):
    """The card model of e. `art`: auto | on (art models included) or off (none); fit.js reads the
    mode from the deck (auto may drop art to fit text, on keeps it)."""
    if art not in ART_MODES:
        raise ValueError(f"art mode {art!r} (have: {', '.join(ART_MODES)})")
    m = CARDS[e.type](ix, e)
    m.setdefault("back", back(e, m))
    m.setdefault("book", data.book_abbr(e.book))   # the footer source label (PHB, DMG, FRHoF); `page` may be None
    if e.type in ART:
        with_art(m, variant_refs(e, variant) if e.type == "magic-item" else e.images, art, ART[e.type],
                 ART_BOX.get(e.type, ART_BOX_CARD))
        m["art_missing"] = m["art_wanted"] and not m["art"]
        if e.type in ("weapon", "armor"):
            item_art(m, e.type)
        if e.type == "creature":
            m["token"], wanted = (None, False) if art == "off" else art_model(e.images, ("token",), TOKEN_BOX)
            m["art_missing"] = m["art_missing"] or (wanted and not m["token"])
            m["art_wanted"] = m["art_wanted"] or wanted
    return m


def has_art(m):
    """Whether a card model shows an image (art, or a creature's token)."""
    return bool(m.get("art") or m.get("token"))
