"""The encounter handout's context: monsters (with counts), the engine's rating, and the texts they need (stdlib only).

    ctx = encounter.context(ix, [(goblin_boss, 1), (goblin_warrior, 6)], ev)   # templates/book/encounter.html.j2

Page 1 is the DM's summary: the party's budget and the rating (when a party is given), a roster with
AC, HP and initiative, and an HP tracker with one row per creature. Then the stat blocks in full, one
per kind of creature, then the conditions and spells those stat blocks name.
"""
import re

from .. import text
from ._common import art, page_ref
from .books import spell_entry, statblock, term_entry
from .creature import more_texts

TOKEN_BOX = (16, 16)             # mm: the token disc beside a stat block's name
MAX_TRACK = 40                   # HP tracker rows; more creatures than that get one row per kind


def _ref(e):
    p = page_ref(e)
    return f"p{p}" if isinstance(p, int) else p


def _plain(s):
    return text.inline(s or "", "plain")


def _hp_max(hp):
    m = re.match(r"\s*(\d+)", hp or "")
    return int(m.group(1)) if m else None


def _strings(d):
    """Every prose string of a stat block: its lines, trait and action texts and what follows them."""
    out = [v for v in d.values() if isinstance(v, str)]
    for k in ("traits", "actions", "bonus_actions", "reactions", "legendary_actions"):
        for x in d.get(k) or []:
            out += [x.get("name") or "", x.get("text") or ""] + more_texts(x.get("more"))
    return out


def refs(ix, e):
    """The conditions and spells e's stat block names (links and italic names), in order of mention."""
    out = []
    for s in _strings(e.data):
        hits = [ix.by_id.get(nid) for _, nid in text.links(s)]
        for name in text.italic_names(s):
            r = ix.ref_lookup(name, e)
            hits += [r] if r else [ix.ref_lookup(x, e) for x in name.split(", ")] if ", " in name else []
        for r in hits:
            if r is None or r is e or r in out:
                continue
            if r.type == "spell" or (r.type == "term" and (r.data.get("tag") or "").lower() == "condition"):
                out.append(r)
    return out


def block(ix, e, n, art_mode="auto"):
    """One stat block for the template's `monster` macro: books.statblock plus count, CR line and token."""
    d = e.data
    sb = statblock(e)
    rated = d.get("cr") not in (None, "None")
    cr = (f"{d['cr']} ({d.get('xp', 0):,} XP" + (f", or {d['xp_lair']:,} in lair" if d.get("xp_lair") else "")
          + f"; PB {d.get('proficiency_bonus')})") if rated else None
    token = None if art_mode == "off" else art(e.images, ("token",), TOKEN_BOX)[0]
    return {"sid": e.sid, "title": e.title, "count": n, "ref": _ref(e), "cr": cr, "token": token, **sb}


def roster(rows_in):
    return [{"title": e.title, "count": n, "cr": e.data.get("cr") or "—", "xp": e.data.get("xp") or 0,
             "ac": _plain(e.data.get("ac")) or "—", "hp": _plain(e.data.get("hp")) or "—",
             "init": _plain(e.data.get("initiative")) or "—", "speed": _plain(e.data.get("speed")), "ref": _ref(e)}
            for e, n in rows_in]


def tracker(rows_in):
    """[{label, ac, hp}] one per creature (`Goblin Warrior 3`), or one per kind past MAX_TRACK creatures."""
    total = sum(n for _, n in rows_in)
    out = []
    for e, n in rows_in:
        ac, hp = _plain(e.data.get("ac")).split(" ")[0] or "—", _hp_max(e.data.get("hp"))
        reps = 1 if total > MAX_TRACK else n
        for i in range(1, reps + 1):
            label = e.title + (f" {i}" if n > 1 and reps > 1 else f" ×{n}" if n > 1 else "")
            out.append({"label": label, "ac": ac, "hp": hp})
    return out


def title_of(monsters):
    return " + ".join((f"{n} × " if n > 1 else "") + e.title for e, n in monsters)


def context(ix, monsters, ev=None, title=None, art_mode="auto"):
    """monsters: [(creature entity, count)] in order; ev: rules.encounter.evaluate's result, or None
    (a list of stat blocks without a party)."""
    seen, kinds = {}, []
    for e, n in monsters:                         # the same creature twice: one stat block, counts added
        if e.sid in seen:
            kinds[seen[e.sid]] = (e, kinds[seen[e.sid]][1] + n)
        else:
            seen[e.sid] = len(kinds)
            kinds.append((e, n))
    rules = []
    for e, _ in kinds:
        rules += [r for r in refs(ix, e) if r not in rules]
    conds = sorted((r for r in rules if r.type == "term"), key=lambda r: r.title)
    spells = sorted((r for r in rules if r.type == "spell"), key=lambda r: (r.data["level"], r.title))
    name = title or title_of(kinds)
    summary = None
    if ev:
        lv = ev["party"]
        summary = {"party": f"{len(lv)} characters, level{'s' if len(set(lv)) > 1 else ''} "
                            + (", ".join(map(str, lv)) if len(set(lv)) > 1 else str(lv[0])),
                   "budget": [(d.title(), f"{v:,}", d == ev["rating"]) for d, v in ev["budget"].items()],
                   "total": f"{ev['total_xp']:,}", "rating": ev["rating"].title(), "lair": ev["lair"],
                   "source": ev["source"], "warnings": ev["warnings"],
                   "per_pc": f"{ev['total_xp'] // len(lv):,}"}
    count = sum(n for _, n in kinds)
    return {"title": f"{name}: Encounter", "kicker": "Encounter", "name": name,
            "footer": f"Encounter | {name}" if len(name) <= 60 else "Encounter",
            "summary": summary, "roster": roster(kinds), "tracker": tracker(kinds),
            "tracker_grouped": count > MAX_TRACK, "pcs": len(ev["party"]) if ev else 0,
            "blocks": [block(ix, e, n, art_mode) for e, n in kinds],
            "conditions": [term_entry(r) for r in conds], "spells": [spell_entry(r) for r in spells],
            "stats": f"{count} creature{'' if count == 1 else 's'} · {len(kinds)} stat block{'' if len(kinds) == 1 else 's'}"
                     + (f" · {len(conds)} condition{'' if len(conds) == 1 else 's'}" if conds else "")
                     + (f" · {len(spells)} spell{'' if len(spells) == 1 else 's'}" if spells else "")
                     + (f" · {summary['rating']}" if summary else "")}
