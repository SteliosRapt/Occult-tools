"""`./occult character|encounter|calc|roll`: the rules engine on the command line (stdlib only).

Exit codes as the other verbs: 0 ok, 1 not found, 2 usage.
"""
import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

from .. import components, data
from . import character, core, dice, encounter, rolltables, sheet, tables

PROG = "./occult"

HELP = {
    "character": f"""usage: {PROG} character <spec.json|-> [--json] [--level-up CLASS [--subclass S]]
       {PROG} character <spec.json|-> --pdf [PATH] [--mode bw] [--paper letter] [--png] [--html]
       {PROG} character <spec.json|-> --cards [PATH] [--backs category] [--mode bw] [--paper letter] [--png]
       {PROG} character <spec.json|-> --form [PATH] [--form-template PDF] [--mode bw] [--png] [--html]
Every derived number of a character: abilities, saves, skills, AC, HP, speed, attacks, spell slots,
class resources and features, from a JSON spec (characters/README.md documents it; examples in
characters/examples/). Rule problems in the spec are listed under "Check".
  --json            the full sheet as JSON
  --level-up CLASS  what one more level in CLASS changes (a new class multiclasses)
  --subclass S      the subclass to take with --level-up
  --pdf [PATH]      a printable character sheet: the front sheet, then every feature, trait, feat and
                    option in full, then the spells (slot trackers, the list, the texts); default
                    dist/characters/<name>.<paper>[.bw].pdf. Rule problems print as `check:` lines
  --cards [PATH]    spell cards for the character's spells (the spec's `spells`), 3×3 poker cards as
                    `make cards`; default dist/cards/<name>-spells.<paper>[.bw].pdf
  --backs category  with --cards: a mirrored back sheet after each sheet (long-edge duplex)
  --form [PATH]     the values printed onto the official D&D 2024 character sheet (2 pages; needs
                    pypdf and the blank form, see forms/README.md); default
                    dist/characters/<name>.dnd-2024[.bw].pdf. Fields the spec leaves out stay blank
  --form-template PDF  the blank form (default $OCCULT_FORM_PDF or forms/dnd-2024-character-sheet.pdf)
  --mode bw         ink-saver PDF (default color)
  --paper letter    US Letter (default a4)
  --png             also write one PNG per page (needs pdftoppm)
  --html            also print the built HTML path
e.g. {PROG} character characters/examples/rowan-fighter-1.json · {PROG} character spec.json --level-up wizard
     {PROG} character characters/examples/sel-wizard-3.json --pdf --mode bw
     {PROG} character characters/examples/sel-wizard-3.json --cards --backs category
     {PROG} character characters/examples/sel-wizard-3.json --form""",
    "encounter": f"""usage: {PROG} encounter --party P [creature[xN]...] [--lair] [--json]
       {PROG} encounter --party P --suggest [--difficulty D] [creature filters] [--habitat H] [--group G] [--n N] [--seed S] [--strong]
       {PROG} encounter [--party P] creature[xN]... --pdf [PATH] [--cards [PATH]] [--title T] [--mode bw] [--paper letter]
       {PROG} encounter --party P --suggest ... --pdf [--pick N]
Rate a combat encounter by the XP budget, or suggest some, and print its stat blocks.
  --party P         character levels: 5,5,5,4 or 4x5 or 3x5,1x4
  creature[xN]      a creature id or name, times N: goblin-warrior x6 is also accepted (`goblin-warrior*6`)
  --lair            use lair XP for creatures that have it
  --suggest         propose encounters for --difficulty (low|moderate|high, default moderate)
  --type --cr --size{{book_filter}}   creature filters, as in `list creatures`
  --habitat H --group G       creature habitat (forest, underdark ...) or group (goblinoids ...)
  --n N --seed S    how many suggestions and the random seed (default 5, random)
  --strong          allow creatures above the party's level
  --pdf [PATH]      a DM handout: the rating and an HP and initiative tracker on page 1, then every
                    stat block in full, then the conditions and spells they name; default
                    dist/encounters/<creatures>.<paper>[.bw].pdf. Without --party: no rating
  --cards [PATH]    the stat blocks as tarot-size creature cards (`make cards creatures`), one per kind;
                    default dist/cards/<creatures>-cards.<paper>[.bw].pdf
  --pick N          with --suggest: which suggestion to print (default 1)
  --title T         the handout's title and file name (default: the creatures)
  --mode bw --paper letter --png --html{{extra_flags}}   as for `make`
e.g. {PROG} encounter --party 4x3 wolf x2 stirge x9 · {PROG} encounter --party 4x5 --suggest --type undead
     {PROG} encounter --party 4x5 goblin-boss goblin-warrior x6 --pdf --mode bw
     {PROG} encounter --party 4x5 --suggest --type undead --seed 3 --pick 2 --pdf --cards""",
    "calc": f"""usage: {PROG} calc <what> [args]
  mod SCORE...                 ability modifiers
  pb LEVEL                     proficiency bonus for a character level
  level XP                     character level for an XP total, and the next threshold
  cr CR                        XP and proficiency bonus for a challenge rating
  slots CLASS[:SUBCLASS]=LEVEL...   spell slots (single or multiclass), e.g. wizard=5 cleric=3 fighter:eldritch-knight=7
  point-buy S S S S S S        cost of six scores (STR..CHA order) against the 27-point budget
  budget PARTY                 XP budgets for a party (5,5,5,4 or 4x5)
e.g. {PROG} calc slots paladin=2 sorcerer=3 · {PROG} calc cr 1/4""",
    "roll": f"""usage: {PROG} roll <expr>... [--seed N] [--avg] [--times N]
Roll dice: 2d6+3, 1d20+5, 4d6kh3 (keep highest 3), 2d20kl1 (disadvantage), 8d6.
  --avg       print the expected value instead of rolling
  --times N   roll each expression N times
  --seed N    reproducible rolls
e.g. {PROG} roll 1d20+7 2d6+4 · {PROG} roll 4d6kh3 --times 6""",
    "table": f"""usage: {PROG} table <table> [--times N] [--n VALUE] [--seed S] [--json]
       {PROG} table --list [TEXT]
Roll on any of the {{table_count}} die tables in the loaded data. Pass a caption, a table id from
--list, or an entity holding one table (magic-item:bag-of-beans).
  --times N   roll N times
  --n VALUE   read the row for VALUE instead of rolling
  --list      list the tables (and ids) whose title or entity matches TEXT
e.g. {PROG} table "{{table_example}}" --seed 4 · {PROG} table --list""",
}


class Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Usage(message)

    def print_help(self, file=None):
        print(help_text(self.prog))


def help_text(cmd):
    value = HELP[cmd]
    if cmd == "encounter":
        value = value.replace("{book_filter}", " --book" if len(data.load().books) > 1 else "")
        value = value.replace("{extra_flags}", "".join(components.values("encounter_help")))
    if cmd == "table":
        tables = rolltables.all_tables()
        value = value.replace("{table_count}", str(len(tables))).replace("{table_example}", tables[0].title if tables else "TITLE")
    return components.transform("rules_help", value, cmd)


def parser(name):
    return _Parser(prog=name, add_help=True)


def err(msg):
    print(f"error: {msg}", file=sys.stderr)


def load_spec(path):
    """A spec file, `-` for stdin; a relative path is tried against the repo root too."""
    if path != "-" and not os.path.exists(path) and (data.ROOT / path).exists():
        path = str(data.ROOT / path)
    try:
        if path == "-":
            txt = sys.stdin.read()
        else:
            with open(path, encoding="utf-8") as fh:
                txt = fh.read()
    except OSError as x:
        raise Usage(f"can't read {path}: {x.strerror}") from None
    try:
        return json.loads(txt)
    except json.JSONDecodeError as x:
        raise Usage(f"{path} is not valid JSON: {x}") from None


def cmd_character(argv):
    p = parser("character")
    p.add_argument("spec")
    p.add_argument("--json", action="store_true")
    p.add_argument("--level-up")
    p.add_argument("--subclass")
    p.add_argument("--pdf", nargs="?", const="")
    p.add_argument("--mode", choices=("color", "bw"))
    p.add_argument("--paper", choices=("a4", "letter"))
    p.add_argument("--png", action="store_true")
    p.add_argument("--html", action="store_true")
    p.add_argument("--cards", nargs="?", const="")
    p.add_argument("--backs", choices=("none", "category"))
    p.add_argument("--form", nargs="?", const="")
    p.add_argument("--form-template")
    a = p.parse_args(argv)
    spec = load_spec(a.spec)
    printing = a.pdf is not None or a.cards is not None or a.form is not None
    if a.subclass and not a.level_up:
        raise Usage("--subclass goes with --level-up")
    if not printing and (a.mode or a.paper or a.png or a.html):
        raise Usage("--mode, --paper, --png and --html go with --pdf, --cards or --form")
    if a.backs and a.cards is None:
        raise Usage("--backs goes with --cards")
    if a.form_template and a.form is None:
        raise Usage("--form-template goes with --form")
    if a.paper and a.pdf is None and a.cards is None:
        raise Usage("--paper goes with --pdf or --cards (the form has its own page size)")
    if printing:
        if a.level_up or a.json:
            raise Usage("--pdf, --cards and --form print the sheet; leave out --level-up and --json")
        return pdf(spec, a)
    if a.level_up:
        r = character.level_up(spec, a.level_up, a.subclass)
        if a.json:
            print(json.dumps({k: v for k, v in r.items() if k != "before"}, indent=1, ensure_ascii=False))
        else:
            print(sheet.level_up_md(r))
        return 0
    sh = character.build(spec)
    print(json.dumps(sh, indent=1, ensure_ascii=False) if a.json else sheet.character_md(sh))
    return 0


def pdf(spec, a):
    from .. import pipeline
    ix = data.load()
    sh = character.build(spec, ix)
    for w in sh["warnings"]:
        print(f"check: {w}", file=sys.stderr)
    opts = {"mode": a.mode, "paper": a.paper, "png": a.png, "html": a.html}
    code = 0
    try:
        if a.pdf is not None:
            code = pipeline.run_character(ix, sh, dict(opts, pdf=a.pdf))
        if a.form is not None:
            stem = None if spec.get("name") or a.spec == "-" else pipeline.slug_stem(Path(a.spec).stem, "character")
            code = max(code, pipeline.run_form(ix, sh, dict(opts, pdf=a.form, template=a.form_template, stem=stem)))
        if a.cards is not None:
            ids = [x["id"] for x in sh.get("spells") or []]
            if not ids:
                raise Usage("--cards prints the spec's spells, and it has none (add them under `spells`)")
            stem = pipeline.slug_stem(sh["name"], "character") + "-spells"
            code = max(code, run_cards(pipeline, ix, ids, dict(opts, pdf=a.cards, stem=stem, backs=a.backs)))
    except pipeline.PipelineError as x:
        err(str(x))
        return 1
    return code


def run_cards(pipeline, ix, ids, opts):
    """Card sheets of these entity ids through `make cards` (outputs.CATALOGUE["cards"])."""
    from ..outputs import CATALOGUE
    return pipeline.run_cards(ix, CATALOGUE["cards"], list(dict.fromkeys(ids)), {},
                              {k: v for k, v in opts.items() if v not in (None, False)})


def parse_monsters(ix, terms):
    """['goblin-warrior', 'x6', 'bugbear-warrior*2'] -> [(entity, n)]."""
    out = []
    for t in terms:
        m = re.fullmatch(r"[x×*](\d+)", t)
        if m:
            if not out:
                raise Usage(f"'{t}' needs a creature before it")
            e, _ = out[-1]
            out[-1] = (e, int(m.group(1)))
            continue
        m = re.fullmatch(r"(.+?)(?:[x×*](\d+))?", t)
        ref, n = m.group(1), int(m.group(2) or 1)
        e = ix.resolve(ref if ":" in ref else f"creature:{ref}") or ix.resolve(ref)
        if not e or e.entity.type != "creature":
            sug = [x.sid for x in ix.suggest(ref, ix.all("creature"), 5)]
            raise LookupError(f"no creature '{ref}'" + (f"; did you mean: {', '.join(sug)}" if sug else ""))
        out.append((e.entity, n))
    return out


def cmd_encounter(argv):
    p = parser("encounter")
    p.add_argument("creatures", nargs="*")
    p.add_argument("--party")
    p.add_argument("--lair", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--suggest", action="store_true")
    p.add_argument("--difficulty", default="moderate")
    for f in ("type", "cr", "size", *( ("book",) if len(data.load().books) > 1 else () ), "habitat", "group"):
        p.add_argument(f"--{f}")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--seed", type=int)
    p.add_argument("--strong", action="store_true")
    p.add_argument("--pdf", nargs="?", const="")
    p.add_argument("--cards", nargs="?", const="")
    p.add_argument("--pick", type=int)
    p.add_argument("--title")
    p.add_argument("--mode", choices=("color", "bw"))
    p.add_argument("--paper", choices=("a4", "letter"))
    p.add_argument("--png", action="store_true")
    p.add_argument("--html", action="store_true")
    components.apply("encounter_flags", p)
    a = p.parse_args(argv)
    printing = a.pdf is not None or a.cards is not None
    if not printing and (a.title or a.mode or a.paper or a.png or a.html or components.values("encounter_options", a)):
        raise Usage(components.transform("encounter_usage", "--title, --mode, --paper, --png and --html go with --pdf or --cards"))
    if a.pick is not None and not (a.suggest and printing):
        raise Usage("--pick goes with --suggest and --pdf or --cards")
    if printing and a.json:
        raise Usage("--pdf and --cards print the stat blocks; leave out --json")
    ix = data.load()
    if not a.party:
        if a.suggest or not a.creatures or not printing:
            raise Usage("--party is needed, except to print a list of creatures with --pdf or --cards")
        return handout(ix, a, parse_monsters(ix, a.creatures), None)
    levels = encounter.party(a.party)
    if a.suggest:
        return suggest_encounters(ix, a, levels, printing)
    if not a.creatures:
        b = encounter.budget(levels)
        print(f"Party: {len(levels)} character{'s' * (len(levels) != 1)}, levels {', '.join(map(str, levels))}")
        print("Budget: " + ", ".join(f"{d.title()} {v:,}" for d, v in b.items()) + f" XP ({tables.cite('xp_budget')})")
        return 0
    mons = parse_monsters(ix, a.creatures)
    ev = encounter.evaluate(levels, mons, a.lair)
    print(json.dumps(ev, indent=1, ensure_ascii=False) if a.json else sheet.encounter_md(ev))
    return handout(ix, a, mons, ev) if printing else 0



def suggest_encounters(ix, a, levels, printing):
    if a.creatures:
        raise Usage("--suggest proposes creatures; leave the creature list out")
    filters = {k: getattr(a, k) for k in ("type", "cr", "size", "book") if getattr(a, k, None)}
    res = encounter.suggest(levels, a.difficulty.lower(), filters, a.habitat, a.group, a.n, a.seed, a.strong, ix)
    if a.json:
        print(json.dumps(res, indent=1, ensure_ascii=False))
    elif not res:
        print("no encounter fits that budget with these creatures; widen the filters or try --strong")
    else:
        b = encounter.budget(levels)
        print(f"Party: {len(levels)} character{'s' * (len(levels) != 1)}, levels {', '.join(map(str, levels))}; "
              f"{a.difficulty.title()} budget {b[a.difficulty.lower()]:,} XP ({tables.cite('xp_budget')})")
        for i, ev in enumerate(res, 1):
            parts = " + ".join(f"{c['count']} × {c['title']} `{c['id']}` (CR {c['cr']})" for c in ev["creatures"])
            print(f"{i}. {parts}: {ev['total_xp']:,} XP")
            for w in ev["warnings"]:
                print(f"   warning: {w}")
    if printing and res:
        k = a.pick or 1
        if not 1 <= k <= len(res):
            raise Usage(f"--pick {k}: there are {len(res)} suggestions")
        mons = [(ix.get(c["id"]), c["count"]) for c in res[k - 1]["creatures"]]
        print(f"printing suggestion {k}")
        return handout(ix, a, mons, encounter.evaluate(levels, mons, a.lair))
    return 0


def handout(ix, a, mons, ev):
    """--pdf: the stat block handout (pipeline.run_encounter); --cards: creature cards (`make cards`)."""
    from .. import pipeline
    opts = {"mode": a.mode, "paper": a.paper, "png": a.png, "html": a.html, **components.mapping("encounter_options_dict", a), "title": a.title}
    code = 0
    try:
        if a.pdf is not None:
            code = pipeline.run_encounter(ix, mons, ev, dict(opts, pdf=a.pdf))
        if a.cards is not None:
            stem = pipeline.encounter_stem(mons, a.title) + "-cards"
            code = max(code, run_cards(pipeline, ix, [e.sid for e, _ in mons],
                                       dict(opts, title=None, pdf=a.cards, stem=stem)))
    except pipeline.PipelineError as x:
        err(str(x))
        return 1
    return code


def cmd_calc(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(HELP["calc"])
        return 0 if argv else 2
    what, args = argv[0], argv[1:]
    s = core.signed
    if what == "mod":
        if not args:
            raise Usage("calc mod needs scores")
        for x in args:
            print(f"{x}: {s(core.mod(_int(x, 'an ability score')))}")
    elif what == "pb":
        lv = _int(_one(args, "a level"), "a level")
        print(f"level {lv}: proficiency bonus {s(core.proficiency_bonus(lv))}")
    elif what == "level":
        xp = _int(_one(args, "an XP total").replace(",", ""), "an XP total")
        lv, nxt = core.level_for_xp(xp)
        print(f"{xp:,} XP: level {lv}" + (f"; level {lv + 1} at {nxt:,} XP ({nxt - xp:,} to go)" if nxt else " (maximum)"))
    elif what == "cr":
        cr = _one(args, "a challenge rating")
        xp = core.cr_xp(cr)
        print(f"CR {tables.cr_key(cr)}: {xp:,} XP, proficiency bonus {s(core.cr_pb(cr))}")
    elif what == "slots":
        ix = data.load()
        entries = []
        for t in args:
            m = re.fullmatch(r"([\w-]+)(?::([\w-]+))?=(\d+)", t)
            if not m:
                raise Usage(f"'{t}': use CLASS=LEVEL or CLASS:SUBCLASS=LEVEL")
            cls = character.resolve(ix, "class", m.group(1))
            sub = character.resolve(ix, "subclass", m.group(2)) if m.group(2) else None
            if not 1 <= int(m.group(3)) <= core.MAX_LEVEL:
                raise Usage(f"'{t}': a class level is 1-{core.MAX_LEVEL}")
            entries.append((cls, int(m.group(3)), sub))
        if not entries:
            raise Usage("calc slots needs CLASS=LEVEL, e.g. wizard=5 cleric=3")
        slots, pact, clevel = character.spell_slots(entries)
        print("slots: " + (", ".join(f"level {k}: {v}" for k, v in sorted(slots.items())) or "none")
              + (f" (caster level {clevel})" if slots else ""))
        if pact:
            print(f"pact magic: {pact['slots']} slots of level {pact['level']}")
    elif what == "point-buy":
        if len(args) != 6:
            raise Usage("calc point-buy takes six scores, STR DEX CON INT WIS CHA")
        cost, problems = core.point_buy_cost(dict(zip(tables.ABILITIES, (_int(x, "a score") for x in args))))
        print(f"cost {cost} of {core.POINT_BUY_BUDGET}" + ("" if problems else f" ({core.POINT_BUY_BUDGET - cost} left)"))
        for x in problems:
            print(f"problem: {x}")
    elif what == "budget":
        levels = encounter.party(" ".join(args))
        b = encounter.budget(levels)
        print(", ".join(f"{d.title()} {v:,}" for d, v in b.items()) + f" XP ({tables.cite('xp_budget')})")
    else:
        raise Usage(f"unknown calc '{what}'; one of mod, pb, level, cr, slots, point-buy, budget")
    return 0


def _int(x, what):
    try:
        return int(x)
    except ValueError:
        raise Usage(f"'{x}' is not a number ({what})") from None


def _one(args, what):
    if len(args) != 1:
        raise Usage(f"needs {what}")
    return args[0]


def cmd_roll(argv):
    p = parser("roll")
    p.add_argument("expr", nargs="+")
    p.add_argument("--seed", type=int)
    p.add_argument("--avg", action="store_true")
    p.add_argument("--times", type=int, default=1)
    a = p.parse_args(argv)
    rng = random.Random(a.seed)
    for e in a.expr:
        if a.avg:
            print(f"{e}: average {round(dice.average(e), 2):g}")
            continue
        for _ in range(max(1, a.times)):
            r = dice.roll(e, rng)
            print(f"{e}: {r.total}  ({r.detail})")
    return 0














def cmd_table(argv):
    p = parser("table")
    p.add_argument("table", nargs="*")
    p.add_argument("--list", action="store_true")
    p.add_argument("--times", type=int, default=1)
    p.add_argument("--n", type=int)
    p.add_argument("--seed", type=int)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    ix = data.load()
    ref = " ".join(a.table)
    if a.list:
        low = ref.lower()
        ts = [t for t in rolltables.all_tables(ix)
              if not low or low in t.title.lower() or low in t.entity.title.lower() or low in t.id]
        for t in ts:
            print(f"{t.id}  {t.title}  {t.die}  {t.cite()}")
        print(f"\n{len(ts)} tables" + (f" matching '{ref}'" if ref else ""))
        return 0
    if not ref:
        raise Usage("name a table, or --list")
    t = rolltables.find(ref, ix)
    rng = random.Random(a.seed)
    res = [rolltables.roll(t, rng, a.n) for _ in range(1 if a.n is not None else max(1, a.times))]
    if any(r.row is None for r in res):
        raise Usage(f"{t.title} has no row for {a.n} ({t.die})")
    if a.json:
        print(json.dumps([{"table": t.id, "title": t.title, "die": t.die, "roll": r.n, "cells": r.cells} for r in res],
                         indent=1, ensure_ascii=False))
        return 0
    print(f"{t.title} `{t.id}` ({t.die}, {t.cite()})")
    for r in res:
        print(f"{r.n}: {r.text}")
    return 0


COMMANDS = {"character": cmd_character, "encounter": cmd_encounter, "calc": cmd_calc, "roll": cmd_roll,
            "table": cmd_table}

components.apply("register_rules", COMMANDS, HELP)


def main(cmd, argv):
    try:
        return COMMANDS[cmd](argv)
    except SystemExit as x:          # argparse --help
        return x.code or 0
    except Usage as x:
        err(str(x))
        print(f"usage: see `{PROG} {cmd} --help`", file=sys.stderr)
        return 2
    except (character.SpecError, encounter.EncounterError, ValueError, *components.values("errors")) as x:
        err(str(x))
        return 2
    except LookupError as x:
        err(x.args[0] if x.args else str(x))
        return 1
