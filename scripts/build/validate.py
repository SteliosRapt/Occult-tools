"""Check books in data/ against scripts/build/book-node.schema.json and against themselves.

    python3 scripts/build/validate.py [data/efa-2025 ...]    # default: every data/*/book.json

Beyond the schema: ids are unique within a book and start with the book id,
book.json's contents point at files and ids that exist, chapters start
in page order, and an `embed` block names a node of the book (a child of its
node, or the one node of an entity the book prints twice). Needs
jsonschema (not in requirements.txt; a build-time tool).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCHEMA = json.loads((HERE / "book-node.schema.json").read_text(encoding="utf-8"))


def walk(node, parent=None):
    yield node, parent
    for child in node["children"]:
        yield from walk(child, node)


def blocks(bs):
    """Blocks, with the blocks inside sidebars."""
    for b in bs:
        yield b
        if b["type"] == "sidebar":
            yield from blocks(b.get("content", []))


# Types whose `data` the schema checks when present. The 5e.tools generic converter writes none yet:
# such nodes are counted and reported (not an error) until the family converters fill them in.
TYPED = ("spell", "feature", "feat", "stat-block", "background", "species", "class", "magic-item")
NO_DATA = {}


def check_book(book_dir: Path) -> list[str]:
    errors = []
    book = json.loads((book_dir / "book.json").read_text(encoding="utf-8"))
    for key in ("id", "title", "edition", "publisher", "page_numbers", "built_from", "contents"):
        if key not in book:
            errors.append(f"{book_dir.name}/book.json: missing {key}")
    validator = jsonschema.Draft202012Validator(SCHEMA)
    ids: dict[str, str] = {}
    embeds = []
    last_page = 0
    for entry in book["contents"]:
        path = book_dir / entry["file"]
        if not path.exists():
            errors.append(f"{book_dir.name}: book.json names a missing file {entry['file']}")
            continue
        chapter = json.loads(path.read_text(encoding="utf-8"))
        for err in validator.iter_errors(chapter):
            where = "/".join(str(p) for p in err.absolute_path)
            errors.append(f"{entry['file']}: {where}: {err.message[:200]}")
        if chapter["id"] != entry["id"]:
            errors.append(f"{entry['file']}: id {chapter['id']} but book.json says {entry['id']}")
        for node, parent in walk(chapter):
            embeds += [(entry["file"], node["id"], b["id"]) for b in blocks(node["content"]) if b["type"] == "embed"]
            if node["type"] in TYPED and "data" not in node:
                NO_DATA[node["type"]] = NO_DATA.get(node["type"], 0) + 1
            if parent and not node["id"].startswith(parent["id"] + "/"):
                errors.append(f"{entry['file']}: id {node['id']} does not extend its parent {parent['id']}")
            if node["id"] in ids:
                errors.append(f"{entry['file']}: duplicate id {node['id']} (also in {ids[node['id']]})")
            if not node["id"].startswith(book["id"] + "/"):
                errors.append(f"{entry['file']}: id {node['id']} outside the book")
            ids[node["id"]] = entry["file"]
        if chapter.get("page") is not None:
            if chapter.get("page") < last_page:
                errors.append(f"{entry['file']}: starts on page {chapter['page']}, before the previous chapter")
            last_page = chapter.get("page")

    def toc_ids(entries):
        for e in entries:
            yield e["id"]
            yield from toc_ids(e.get("children", []))

    for i in toc_ids(book["contents"]):
        if i not in ids:
            errors.append(f"{book_dir.name}/book.json: contents names unknown id {i}")
    for f, nid, target in embeds:
        if target not in ids:
            errors.append(f"{f}: {nid}: embed names unknown id {target}")
    return errors


def main(argv: list[str]) -> int:
    books = [Path(a) for a in argv] or sorted(p.parent for p in (REPO / "data").glob("*/book.json"))
    errors = []
    for book_dir in books:
        errors += check_book(book_dir)
    for e in errors:
        print(e)
    if NO_DATA:
        print("typed nodes without data (not converted yet): " + ", ".join(f"{t} {n}" for t, n in sorted(NO_DATA.items())))
    print(f"{len(books)} book(s) checked, {len(errors)} problem(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
