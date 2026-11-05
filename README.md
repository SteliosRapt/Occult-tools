# occult-tools

Self-contained, unofficial fan tooling for the D&D 2024 rules in the **System Reference Document 5.2.1**. Search and read rules, build characters, rate encounters, print cards and books, and build an offline Spell Explorer. No commercial books, book illustrations or source-page numbers are included.

This repository is generated from occult-lore by its SRD builder. Make changes in occult-lore (`scripts/srd/overlay/` for these docs, examples and skills), then rebuild; edits to generated files will be overwritten. This project is not affiliated with or endorsed by Wizards of the Coast.

## Quick start

Reading and the rules engine need only Python 3.10+. Collections and HTML generation also need Jinja2:

```sh
pip install -r requirements.txt
./occult show spell:fireball term:grappled
./occult list spells --class wizard --level 0-3 --ritual
./occult find bat guano
./occult toc
./occult character characters/examples/rowan-fighter-1.json
./occult encounter --party 4x3 goblin-warrior x4
./occult calc slots wizard=5 cleric=3
./occult roll 4d6kh3 1d20+5
./occult make md --check
./occult make pwa
python3 -m http.server -d dist/pwa 8000
```

PDF output needs Node and Playwright Chromium. Configure `OCCULT_NODE`, `OCCULT_PLAYWRIGHT` (the Playwright module path) and `PLAYWRIGHT_BROWSERS_PATH` for your installation. Defaults are `/opt/node22/bin/node`, `/opt/node22/lib/node_modules/playwright` and `/opt/pw-browsers`. Install Playwright/Chromium separately; the tools never download a browser. Optional: poppler/pdftoppm for book `--png`, pypdf and a separately supplied official blank sheet for `character --form` (see forms/README.md).

```sh
./occult make cards spells --class wizard --level 1 --backs category
./occult make spellbook --class cleric
./occult make class --class fighter --level 3
./occult make class --class wizard --subclass evoker
./occult make equipment
./occult make quickref
./occult make glossary
./occult character characters/examples/sel-wizard-3.json --pdf
./occult encounter --party 4x3 goblin-warrior x4 --pdf
```

`./occult make --list` lists outputs and `./occult types` lists selectors. `find`, `show`, `list`, `toc` and `types` work without Jinja2. Each entity has a short id, such as `spell:arcane-hand`, `subclass:life-domain` or `term:prone`; pass it to `show` or `make cards`. Output goes to `dist/`. `OCCULT_DATA` can select another data root.

The SRD has 12 classes, one subclass per class, 9 species and 4 backgrounds. `table --list` shows the available roll tables. The three AI workflows in `.claude/skills/` use the same command surface.

## Validation and credits

```sh
pip install jsonschema
python3 scripts/build/validate.py
python3 -m unittest discover tools/tests
OCCULT_BROWSER_TESTS=1 python3 -m unittest discover tools/tests
```

Data was derived from corrected occult-lore node trees, originally imported from 5e.tools v2.38.0, filtered by the pinned checkout's `srd52` flags and renamed per SRD. See `data/srd-5.2/CHANGES.md` for provenance and the pinned commits. Art and page references were removed. Styling, fonts (with their OFL licenses), icons, templates, tools and skills come from occult-lore; their source notices remain with the files. The SRD license applies to SRD material and does not itself license unrelated code or third-party font assets.

This work includes material from the System Reference Document 5.2.1 (“SRD 5.2.1”) by Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2.1 is licensed under the Creative Commons Attribution 4.0 International License, available at https://creativecommons.org/licenses/by/4.0/legalcode.
