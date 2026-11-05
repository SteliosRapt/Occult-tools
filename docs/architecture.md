# Architecture: occult-tools

This generated repository contains one book, `data/srd-5.2/`, titled System Reference Document 5.2.1. Its public rules are licensed CC-BY-4.0; see LICENSE-SRD.md. It is built from corrected occult-lore data by the SRD exporter in that source repository. The exporter and commercial books are not shipped here.

## Data and reading

`occult` adds tools/ to the Python path and calls `occult.cli`. Python stdlib covers reading and the rules engine. `tools/occult/data.py` loads the book chapters, builds parent/owner indexes and assigns short ids. `OCCULT_DATA` overrides the data root with a directory of books or a single book folder. The single book is named `srd`; entities use ids such as `spell:fireball` and `subclass:evoker`.

`book.json` records edition, license, attribution, contents and pinned provenance. Chapters contain trees of `{id, type, title, content, children, data?, origin?}`. IDs start with `srd-5.2/NN/`. Page numbers, book art and covers are absent; images.json is an empty array. Origin records retain only source, property and SRD name. Inline text uses Markdown emphasis and `[label](node-id)` links; every internal link resolves within this book. Containers have only public table blocks or public descendants, without unlicensed introductory prose. Flagged entities preserve source corrections; class taglines and species/background fluff are removed. PHB creature reprints are deduplicated against the monster entries.

`types.py` defines aliases, filters, brief output and table columns. `query.py` selects data for list and make. `text.py` converts stored markup to Markdown, HTML or plain text and resolves cross-references. Reading commands are `types`, `find`, `show`, `list` and `toc`; CLAUDE.md documents their options.

## Output pipeline

All outputs use selection → view model → Jinja template → HTML → Chromium → dist/. Markdown collections stop at the template stage. Jinja2 is the only required Python runtime dependency beyond stdlib and is loaded only by make. `tools/occult/outputs.py` is the output catalogue; `make.py` parses flags and `pipeline.py` drives generation.

View models in tools/occult/views/ create spell, equipment, creature and other cards, spellbooks, class booklets, equipment books, quick references, glossary books, character sheets and encounter handouts. `collections.py` creates collections/*.md with a hash of data and shaping code; `make md --check` detects stale output. Generated collections are never hand-edited.

Templates live in templates/; CSS, fonts, OFL notices, icons and ornaments live in style/. The book layouts use paged CSS. tools/render/render.mjs uses Node + Playwright Chromium to print; fit.js fits cards and handles continuation/duplex imposition, book.js waits for fonts and page readiness, and form.js handles optional official-form overlays. Node/Playwright/browser locations can be configured through OCCULT_NODE, OCCULT_PLAYWRIGHT and PLAYWRIGHT_BROWSERS_PATH. See README.md for installation and optional render dependencies. No illustrations are required.

`explorer.py`, templates/pwa/ and the explorer CSS produce the offline Spell Explorer with `make pwa`. It includes spells.json, the app shell, search/filter code, icons, fonts, a manifest and a service worker; it can be served by any static HTTP server.

## Rules engine and workflows

`tools/occult/rules/tables.py` finds rules tables by caption, preferring a named section before searching the whole index. Renumbering chapters does not change rules calculations. Missing tables raise TableMissing with a clear error. `core.py` computes modifiers, proficiency, point buy, advancement and slots; `dice.py` handles dice expressions. `character.py` derives a character sheet from a JSON spec and reports Check warnings; explicit EFFECTS model supported feature effects. Effects not modeled go in the spec's modifiers. `encounter.py` rates or suggests encounters using the public XP budget. `rolltables.py` finds die tables. `loot.py` and `generate.py` retain their command surface but require tables that may be absent from the SRD; they report that limitation instead of substituting commercial material.

Character specs and tested SRD examples live in characters/. Blank official form PDFs are supplied separately in forms/ and never distributed. AI skills in .claude/skills/ build characters, help with encounters, suggest items and prepare scenes from available SRD mechanics. Original fiction and rulings must be labeled explicitly.

## Checks and source changes

`python3 scripts/build/validate.py` checks schema and tree invariants (build-time jsonschema). `python3 -m unittest discover tools/tests` checks portable data behavior, image helpers, SRD counts, links, forbidden names, character examples, generated Markdown and PWA output. `OCCULT_BROWSER_TESTS=1` adds PDF render tests. CI runs browser-free checks. The pre-commit hook checks collections when shaping inputs change.

This repository is generated. Change tools, templates, styles or the SRD overlay in occult-lore, run its SRD builder and review the fresh public distribution. Membership, overrides and the audit report are maintained in the source repo; no importer or export scripts are needed to use occult-tools.
