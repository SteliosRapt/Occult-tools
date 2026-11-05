"""`./occult fetch images`: fill img/ (gitignored) with the files listed in data/<book>/images.json.

Each manifest is a JSON list of {"path", "bytes", "sha256"}; `path` is relative to the 5etools-img
root and to img/. Files come from a local 5etools-img checkout (hardlinked when possible, else
copied) or, with no checkout, from raw.githubusercontent.com at the book's pinned commit
(book.json `built_from.5etools_img_commit`). Every file is checked against its size and sha256.
Stdlib only.
"""
import hashlib
import json
import os
import shutil
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import data
from .images import IMG_ROOT

PROG = "./occult"
REPO = "5etools-mirror-3/5etools-img"
RAW = "https://raw.githubusercontent.com/" + REPO
ENV_SRC = "OCCULT_5ETOOLS_IMG"
WORKERS = 8
RETRIES = 3
MAX_LISTED = 20

HELP = f"""usage: {PROG} fetch images [--book B ...] [--from DIR] [--check] [--prune]
Copy the art the data refers to (data/<book>/images.json) into img/ (gitignored). Files already
present with the right size and sha256 are skipped; every new file is verified.
Source: --from DIR, else ${ENV_SRC}, else ../5etools-mirror-3/5etools-img next to the repo; with
no checkout, download from GitHub ({REPO}) at book.json's built_from.5etools_img_commit.
  --book B    only these books (repeat, or comma-separate: --book phb,dmg); default all
  --from DIR  a 5etools-img checkout
  --check     write nothing; exit 1 if a file is missing or wrong
  --prune     delete files under img/ that no manifest lists (with --check: only count them)
e.g. {PROG} fetch images · {PROG} fetch images --book dmg --check"""


class Usage(Exception):
    def __init__(self, msg, hints=(), label="valid"):
        super().__init__(msg)
        self.hints, self.label = list(hints), label


class Failed(Exception):
    pass


def err(msg, hints=(), label=""):
    print(f"error: {msg}", file=sys.stderr)
    if hints:
        print(f"{label}: " + ", ".join(hints), file=sys.stderr)


def note(msg):
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- arguments
def parse(argv):
    o = {"book": [], "from": None, "check": False, "prune": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        name, eq, val = a[2:].partition("=") if a.startswith("--") else ("", "", "")
        if a in ("-h", "--help"):
            print(HELP)
            raise SystemExit(0)
        if name in ("check", "prune") and not eq:
            o[name] = True
        elif name == "book":
            vals = [val] if eq else []
            while not eq and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                i += 1
                vals.append(argv[i])
            if not vals:
                raise Usage("--book needs a value", ["--book phb", "--book phb,dmg"], "e.g.")
            o["book"] += [b.strip().lower() for v in vals for b in v.split(",") if b.strip()]
        elif name == "from":
            if not eq:
                if i + 1 >= len(argv):
                    raise Usage("--from needs a directory")
                i += 1
                val = argv[i]
            o["from"] = val
        else:
            raise Usage(f"`fetch images` has no argument '{a}'",
                        ["--book B", "--from DIR", "--check", "--prune"], "valid flags")
        i += 1
    return o


# ---------------------------------------------------------------- manifests
def books_of(data_root):
    return {data.book_short(d.name): d for d in data.book_dirs(data_root)}


def valid_rel(rel):
    parts = rel.split("/")
    return bool(rel) and not rel.startswith("/") and "\\" not in rel and \
        all(p not in ("", ".", "..") for p in parts)


def read_manifest(path):
    """-> [(path, bytes, sha256)], or raise Failed with a one-line reason."""
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as x:
        raise Failed(f"{path}: cannot read ({x})") from None
    if not isinstance(rows, list):
        raise Failed(f"{path}: expected a JSON list")
    out = []
    for n, r in enumerate(rows):
        ok = isinstance(r, dict) and isinstance(r.get("path"), str) and valid_rel(r["path"]) and \
            isinstance(r.get("bytes"), int) and isinstance(r.get("sha256"), str) and len(r["sha256"]) == 64
        if not ok:
            raise Failed(f"{path}: entry {n} needs a relative path, bytes and a sha256")
        out.append((r["path"], r["bytes"], r["sha256"].lower()))
    return out


def img_commit(book_dir):
    try:
        meta = json.loads((book_dir / "book.json").read_text(encoding="utf-8"))
        return (meta.get("built_from") or {}).get("5etools_img_commit")
    except (OSError, ValueError, AttributeError):
        return None


# ---------------------------------------------------------------- sources
def main_repo(root):
    """The main checkout when `root` is a git worktree (its .git is a `gitdir:` file), else root."""
    g = root / ".git"
    try:
        line = g.read_text(encoding="utf-8").strip() if g.is_file() else ""
    except OSError:
        line = ""
    if line.startswith("gitdir:"):
        gitdir = Path(line[7:].strip())
        if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
            return gitdir.parent.parent.parent
    return root


def find_source(opt, env, root):
    """-> a checkout Path, or None (download). A named source that is not a directory is a usage error."""
    for given, what in ((opt, "--from"), (env.get(ENV_SRC), ENV_SRC)):
        if given:
            p = Path(given).expanduser()
            if not p.is_dir():
                raise Usage(f"{what} {given}: not a directory")
            return p.resolve()
    for r in dict.fromkeys((root, main_repo(root))):
        p = r.parent / "5etools-mirror-3" / "5etools-img"
        if p.is_dir():
            return p
    return None


def ssl_context(env):
    cafile = env.get("SSL_CERT_FILE") or env.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()


def raw_url(commit, rel):
    return f"{RAW}/{commit}/{urllib.parse.quote(rel)}"


# ---------------------------------------------------------------- files
def sha256_of(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def state(p, size, sha):
    """None when p is right, else why not."""
    try:
        st = p.stat()
    except OSError:
        return "absent"
    if not p.is_file():
        return "not a file"
    if st.st_size != size:
        return f"size {st.st_size}, expected {size}"
    if sha256_of(p) != sha:
        return "sha256 mismatch"
    return None


def temp_of(dest):
    return dest.with_name(f".{dest.name}.part-{os.getpid()}-{threading.get_ident()}")


def place(dest, write):
    """Write through a temp file next to dest, then rename over it."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = temp_of(dest)
    try:
        write(tmp)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def copy_in(src_root, dest, rel, size, sha):
    src = src_root / rel
    why = state(src, size, sha)
    if why == "absent":
        return "not in the checkout"
    if why:
        return f"checkout file differs ({why})"

    def write(tmp):
        try:
            os.link(src, tmp)
        except OSError:
            shutil.copy2(src, tmp)
            if sha256_of(tmp) != sha:
                raise OSError("sha256 mismatch after copy")
    try:
        place(dest, write)
    except OSError as x:
        return f"copy failed ({x})"
    return None


def download(opener, url, dest, size, sha):
    body, why = None, ""
    for attempt in range(RETRIES):
        if attempt:
            time.sleep(2 ** (attempt - 1))
        try:
            with opener.open(url, timeout=60) as r:
                body = r.read()
            break
        except urllib.error.HTTPError as x:
            why = f"HTTP {x.code}"
            if x.code in (403, 404, 410):
                break
        except (urllib.error.URLError, OSError) as x:
            why = str(getattr(x, "reason", x))
    if body is None:
        return f"download failed ({why})"
    if len(body) != size or hashlib.sha256(body).hexdigest() != sha:
        return f"downloaded file differs (size {len(body)}, expected {size}, or sha256)"
    try:
        place(dest, lambda tmp: tmp.write_bytes(body))
    except OSError as x:
        return f"write failed ({x})"
    return None


def prune(img_root, keep, dry):
    """Files under img_root not in keep (relative posix paths); deleted unless dry. -> count."""
    n = 0
    if not img_root.is_dir():
        return 0
    for d, _, files in os.walk(img_root, topdown=False):
        dp = Path(d)
        for f in files:
            p = dp / f
            if p.relative_to(img_root).as_posix() not in keep:
                n += 1
                if not dry:
                    p.unlink()
        if not dry and dp != img_root:
            try:
                dp.rmdir()                   # only succeeds when empty
            except OSError:
                pass
    return n


# ---------------------------------------------------------------- command
def run(o, data_root, img_root, root, env):
    books = books_of(data_root)
    for b in o["book"]:
        if b not in books:
            raise Usage(f"unknown book '{b}'", sorted(books), "books")
    chosen = [s for s in books if not o["book"] or s in o["book"]]

    keep, todo = set(), {}                   # todo: rel -> (size, sha, commit, book)
    have = []
    for short, d in books.items():
        mf = d / "images.json"
        if not mf.is_file():
            if short in chosen and o["book"]:
                note(f"warning: {short}: no images.json")
            continue
        rows = read_manifest(mf)
        keep.update(r[0] for r in rows)
        if short not in chosen:
            continue
        have.append(short)
        commit = img_commit(d)
        for rel, size, sha in rows:
            prev = todo.get(rel)
            if prev and (prev[0], prev[1]) != (size, sha):
                raise Failed(f"{rel}: listed by {prev[3]} and {short} with different contents")
            todo.setdefault(rel, (size, sha, commit, short))
    if not have:
        raise Failed("no data/<book>/images.json yet (the importer writes them)")

    check = o["check"]
    src = None if check else find_source(o["from"], env, root)
    opener = None
    if not check and src is None:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context(env)))
        for short in sorted({v[3] for v in todo.values() if not v[2]}):
            note(f"warning: {short}: book.json has no built_from.5etools_img_commit; downloading from main")

    def one(item):
        rel, (size, sha, commit, _) = item
        dest = img_root / rel
        why = state(dest, size, sha)
        if why is None:
            return rel, "ok", 0, None
        if check:
            return rel, "missing", 0, why
        if src is not None:
            why = copy_in(src, dest, rel, size, sha)
        else:
            why = download(opener, raw_url(commit or "main", rel), dest, size, sha)
        return rel, ("missing" if why else "fetched"), (0 if why else size), why

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(one, sorted(todo.items())))

    fetched = [r for r in results if r[1] == "fetched"]
    ok = sum(1 for r in results if r[1] == "ok")
    missing = [r for r in results if r[1] == "missing"]
    if fetched and not check:
        note(f"source: {src}" if src else f"source: GitHub {REPO}")
    mb = sum(r[2] for r in fetched) / 1e6
    parts = ([] if check else [f"fetched {len(fetched)} ({mb:.1f} MB)"]) + \
        [f"up to date {ok}", f"missing {len(missing)}"]
    if o["prune"]:
        n = prune(img_root, keep, dry=check)
        parts.append(f"{'would prune' if check else 'pruned'} {n}")
    print(", ".join(parts) + f"  ({', '.join(have)})")
    for rel, _, _, why in missing[:MAX_LISTED]:
        print(f"  missing  {rel}  ({why})")
    if len(missing) > MAX_LISTED:
        print(f"  +{len(missing) - MAX_LISTED} more")
    return 1 if missing else 0


def main(argv, data_root=None, img_root=None, root=None, env=None):
    if not argv or argv[0] in ("-h", "--help"):
        print(HELP)
        return 0 if argv else 2
    if argv[0] != "images":
        err(f"unknown fetch target '{argv[0]}'", ["images"], "targets")
        return 2
    try:
        return run(parse(argv[1:]), Path(data_root or data.DATA_ROOT), Path(img_root or IMG_ROOT),
                   Path(root or data.ROOT), os.environ if env is None else env)
    except Usage as x:
        err(str(x), x.hints, x.label)
        if not x.hints:
            note(f"usage: see `{PROG} fetch images --help`")
        return 2
    except Failed as x:
        err(str(x))
        return 1
    except KeyboardInterrupt:
        return 130
