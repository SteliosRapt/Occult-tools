"""Class option card view model (Eldritch Invocations, Metamagic, Cunning Strike, ...).

The prerequisite and cost live in labelled paragraphs ("Prerequisite", "Cost"); they move
into the stat strip, the rest is the body.
"""
import re

from ._common import body_blocks, html, key

STATS = ("Prerequisite", "Cost")


def group(e):
    """`Eldritch Invocation Options` -> `Eldritch Invocation`; an option of a feature -> `<Feature> option`."""
    p = e.parent
    if p.type == "section":
        return re.sub(r" Options$", "", p.title)
    return f"{p.title} Option"


def card(ix, e):
    stats = {b["label"]: html(b["text"], False) for b in e.content if b["type"] == "paragraph" and b.get("label") in STATS}
    body = [b for b in e.content if not (b["type"] == "paragraph" and b.get("label") in STATS)]
    cls = e.owner_class
    sub = e.owner_subclass.title if e.owner_subclass else None
    g = group(e)
    return {
        "kind": "option", "size": "poker", "key": key(e), "title": e.title, "page": e.page,
        "tag": g, "class": cls.title() if cls else None, "class_id": cls, "subclass": sub,
        "prerequisite": stats.get("Prerequisite") or (html(e.data["prerequisite"], False) if e.data.get("prerequisite") else None),
        "cost": stats.get("Cost") or (html(e.data["cost"], False) if e.data.get("cost") else None),
        "body": body_blocks(body),
        "back": {"key": f"option-{cls}-{re.sub(r'[^a-z0-9]+', '-', g.lower())}", "kicker": sub or (cls or "").title(),
                 "title": g, "icon": f"class-{cls}" if cls else None},
    }
