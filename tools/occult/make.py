"""`./occult make <output> [selector] [opts]` and `make --list`: the one generator entry point.

Each output is a row of outputs.CATALOGUE (its flags, whether it takes a selector, its runner);
pipeline.py builds it. Parsing stays stdlib-only; jinja2 is imported by the pipeline.
"""
import difflib
import sys

from . import data, query
from .outputs import CATALOGUE, Choices
from .types import resolve_type

PROG = "./occult"

HELP = f"""usage: {PROG} make <output> [selector] [opts]   |   {PROG} make --list
Run a generator. `{PROG} make <output> --help` for its options.
e.g. {PROG} make cards spells --class wizard --level 3 · {PROG} make md --check"""


class Usage(Exception):
    def __init__(self, msg, hints=(), label="valid flags"):
        super().__init__(msg)
        self.hints, self.label = list(hints), label


def err(msg, hints=(), label=""):
    print(f"error: {msg}", file=sys.stderr)
    if hints:
        print(f"{label}: " + ", ".join(hints), file=sys.stderr)


def listing():
    w = max(len(k) for k in CATALOGUE)
    u = max(len(o.usage) for o in CATALOGUE.values())
    return "\n".join(f"{k.ljust(w)}  {o.usage.ljust(u)}  {o.summary}  {o.priority}" for k, o in CATALOGUE.items())


def flag_usage(out):
    return " ".join(f"--{k}" + ("" if v is True else f" {'|'.join(v) if isinstance(v, (tuple, Choices)) else v}")
                    for k, v in out.flags.items())


def parse(out, argv):
    """-> (terms, opts, filters). Filters are flags of a type named in the selector."""
    terms, opts, filters = [], {}, {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(f"usage: {PROG} make {out.name} {out.usage}\n{out.help}")
            raise SystemExit(0)
        if not (a.startswith("--") and len(a) > 2):
            if not out.selector:
                raise Usage(f"`make {out.name}` takes no argument '{a}'", [flag_usage(out) or "(none)"])
            terms.append(a)
            i += 1
            continue
        name, eq, val = a[2:].partition("=")
        spec, target = out.flags.get(name), opts
        if spec is None and out.selector:
            f = next((query.filters_of(t)[name] for t in map(resolve_type, terms)
                      if t and name in query.filters_of(t)), None)
            if f is not None:
                spec, target = (True if f.op == "flag" else f.metavar), filters
        if spec is None:
            types = list(dict.fromkeys(t for t in map(resolve_type, terms) if t))
            filts = sorted({x for t in types for x in query.listed_filters(t)})
            close = difflib.get_close_matches(name, list(out.flags) + filts, 3, 0.5)
            if not out.selector:
                msg = f"`make {out.name}` has no flag --{name}"
            elif types:
                msg = f"`make {out.name}` has no flag --{name}, and {'/'.join(types)} has no filter --{name}"
            else:
                msg = f"`make {out.name}` has no flag --{name} (filters follow a type: make cards spells --class wizard)"
            hints = ["--" + x for x in close] or ([flag_usage(out) or "(none)"] + (["filters: " + " ".join(
                "--" + x for x in filts)] if filts else []))
            raise Usage(msg, hints, "did you mean" if close else "valid flags")
        if spec is True:
            if eq:
                raise Usage(f"--{name} takes no value")
            target[name] = True
            i += 1
            continue
        if not eq:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise Usage(f"--{name} needs a value", [f"--{name} {'|'.join(spec) if isinstance(spec, (tuple, Choices)) else spec}"], "usage")
            val, i = argv[i + 1], i + 1
        if isinstance(spec, (tuple, Choices)):
            hit = [c for c in spec if c.startswith(val.lower())]
            if len(hit) != 1:
                raise Usage(f"--{name} '{val}' is not one of {'|'.join(spec)}")
            val = hit[0]
        target[name] = val
        i += 1
    if out.variant and out.variant not in opts:
        raise Usage(f"`make {out.name}` needs --{out.variant}", [f"--{out.variant} {'|'.join(out.flags[out.variant])}"],
                    "usage")
    if out.selector and not terms:
        raise Usage(f"`make {out.name}` needs a selector", [f"make {out.name} spells --class wizard",
                                                           f"make {out.name} conditions actions",
                                                           f"make {out.name} spell:fireball creature:wolf"], "e.g.")
    return terms, opts, filters


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(HELP)
        return 0 if argv else 2
    if argv[0] == "--list":
        print(listing())
        return 0
    name = argv[0]
    out = CATALOGUE.get(name)
    if out is None:
        close = difflib.get_close_matches(name, CATALOGUE, 3, 0.5)
        err(f"no output '{name}'", close or list(CATALOGUE), "did you mean" if close else "outputs")
        return 2
    try:
        terms, opts, filters = parse(out, argv[1:])
    except Usage as x:
        err(str(x), x.hints, x.label)
        return 2
    from . import pipeline
    ix = data.load()
    try:
        return getattr(pipeline, "run_" + out.runner)(ix, out, terms, filters, opts)
    except query.QueryError as x:
        err(str(x), x.hints, x.label)
        return 2
    except data.NotFound as x:
        from .cli import candidates_msg
        err(candidates_msg(x.ref, x.lookup))
        return 1
    except pipeline.PipelineError as x:
        err(str(x))
        return 1
