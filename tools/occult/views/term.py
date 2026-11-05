"""Rules-glossary card view model (conditions, actions and other terms)."""
from ._common import body_blocks, key


def card(ix, e):
    d = e.data
    return {"kind": "term", "size": "poker", "key": key(e), "title": e.title, "page": e.page,
            "tag": d.get("tag") or "Rule", "see_also": d.get("see_also") or [],
            "body": body_blocks(e.content)}
