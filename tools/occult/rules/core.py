"""Basic derived numbers: modifiers, proficiency, XP and levels, CR, ability score generation."""
from fractions import Fraction

from . import tables

POINT_BUY_BUDGET = 27        # PHB p38: "You have 27 points to spend"
MAX_LEVEL = 20


def mod(score):
    """Ability modifier: (score - 10) // 2. 1 -> -5, 10 -> 0, 15 -> +2, 30 -> +10."""
    return (int(score) - 10) // 2


def signed(n):
    return f"+{n}" if n >= 0 else f"{n}"


def proficiency_bonus(level):
    """Character level -> proficiency bonus (Character Advancement table)."""
    level = int(level)
    adv = tables.advancement()
    if level not in adv:
        raise ValueError(f"character level must be 1-{MAX_LEVEL}, not {level}")
    return adv[level][1]


def xp_for_level(level):
    return tables.advancement()[int(level)][0]


def level_for_xp(xp):
    """-> (level, XP needed for the next level or None at 20)."""
    if xp < 0:
        raise ValueError(f"XP can't be negative, not {xp}")
    adv = tables.advancement()
    level = max(lv for lv, (need, _) in adv.items() if xp >= need)
    nxt = adv.get(level + 1)
    return level, (nxt[0] if nxt else None)


def cr_value(cr):
    """'1/4' -> Fraction(1, 4). None for unrated (summons: 'None')."""
    if cr is None:
        return None
    try:
        return Fraction(str(cr).strip())
    except (ValueError, ZeroDivisionError):
        return None


def cr_xp(cr):
    xp = tables.cr_xp()
    key = tables.cr_key(cr) if cr_value(cr) is not None else None
    if key not in xp:
        raise ValueError(f"no challenge rating '{cr}'; one of {', '.join(xp)}")
    return xp[key]


def cr_pb(cr):
    v = cr_value(cr)
    for lo, hi, pb in tables.cr_pb():
        if lo <= v <= hi:
            return pb
    raise ValueError(f"no proficiency bonus for CR {cr}")


def point_buy_cost(scores):
    """Scores (before background bonuses) -> (total cost, problems). Each score must be 8-15."""
    costs = tables.point_costs()
    total, problems = 0, []
    for a, s in scores.items():
        if s not in costs:
            problems.append(f"{a.upper()} {s} can't be bought (point buy allows {min(costs)}-{max(costs)})")
        else:
            total += costs[s]
    if total > POINT_BUY_BUDGET:
        problems.append(f"point buy costs {total} points; the budget is {POINT_BUY_BUDGET}")
    return total, problems


def standard_array():
    """The six numbers of the Standard Array, highest first (from the Standard Array by Class table)."""
    row = next(iter(tables.standard_array().values()))
    return sorted(row.values(), reverse=True)


def is_standard_array(scores):
    return sorted(scores.values(), reverse=True) == standard_array()
