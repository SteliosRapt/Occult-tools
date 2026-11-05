# occult-tools — SRD 5.2.1

This public repository is generated from occult-lore: change the source or `scripts/srd/overlay/` there and rebuild. Read rules with `./occult`; do not read large chapter JSON files directly. There is one book: `srd` (`data/srd-5.2`). References print `srd` without page numbers. Never infer that a missing option is included in the SRD.

- `./occult find <text> [--type T]`: titles, then full text; every result has an id.
- `./occult show <id>... [--brief|--full] [--json]`: read entities. Default output is truncated with a hint.
- `./occult list <type> [filters] [--ids|--json]`: filter tables; `./occult types` lists types and filters. Selectors accept `--book srd`.
- `./occult toc [id]`: browse the tree. Ids: `spell:fireball`, `feature:wizard/spellcasting`, `subclass:evoker`, `term:grappled`; `condition:grappled` is an alias. Chapter ids are qualified, for example `chapter:srd/07`.
- Examples: `./occult show spell:arcane-hand term:grappled` · `./occult list spells --class wizard --level 0-3 --ritual` · `./occult show $(./occult list spells --class wizard --level 3 --ids) --brief` · `./occult list magic-items --rarity legendary --attunement` · `./occult list creatures --cr 1-3`.
- `./occult make md [--check]`: regenerate collections/*.md. Never edit collections by hand. Run after changes to data, tools or templates/md. `git config core.hooksPath .githooks` enables the check.
- `./occult make cards <selector> [--mode bw] [--paper letter] [--png] [--check-fit] [--backs category]`: card PDFs in dist/cards. Types include spells, weapons, armor, conditions, actions, creatures, terms, feats, options, magic-items and cards. Select with `list` filters or ids. SRD data has no illustrations. `./occult make --list` lists outputs; style lives in style/, markup in templates/.
- `./occult make spellbook|class --class C|all [--level N]`: spellbooks and class booklets. `--subclass S [--class-features N]` prints one subclass; `--add ID,ID` appends options. `spellbook --list-only` omits descriptions. Examples: `make spellbook --class wizard --mode bw`, `make class --class fighter --level 3`, `make class --class wizard --subclass evoker`.
- `./occult make equipment|quickref|glossary [--mode bw|white] [--paper letter] [--compact] [--png]`: books in dist/books.
- `./occult make pwa [--out DIR]`: offline Spell Explorer in dist/pwa. Preview with `python3 -m http.server -d dist/pwa 8000`. Sources: tools/occult/explorer.py, templates/pwa/, style/themes/grimoire/explorer.css.
- `./occult character <spec.json> [--json] [--level-up CLASS]`: derive AC, HP, saves, skills, attacks, slots, features and spells. Check warnings before calling a character complete. Specs: characters/README.md; examples: characters/examples/. `--pdf [PATH] [--mode bw] [--paper letter] [--png]` prints a character sheet in dist/characters; `--cards [PATH] [--backs category]` prints spell cards. `--form [PATH]` uses a separately supplied official blank PDF and pypdf (forms/README.md).
- `./occult encounter --party 4x3 goblin-warrior x4 [--pdf [PATH]] [--cards [PATH]]`: rate and print an encounter. `--suggest --difficulty high --type undead --seed 3 [--pick N]` suggests creatures. Without --party, prints stat blocks only.
- `./occult calc slots wizard=5 cleric=3` · `calc cr 1/4` · `calc point-buy 15 15 15 8 8 8` · `./occult roll 4d6kh3 1d20+5`.
- `./occult table --list`, `./occult table "Potion Miscibility" --seed 2`: available die tables. Some loot/NPC/settlement/tavern generators require tables absent from the SRD and return a clear missing-table error. Do not invent table results or add commercial tables.
- AI skills: character-builder, dm-helper, loot, npc-tavern and session-prep in .claude/skills/ use this command surface and respect SRD limits.
- Runtime: Python stdlib; make additionally needs Jinja2. PDF rendering needs Node + Playwright Chromium; see README. Tests: `python3 -m unittest discover tools/tests`; schema: `python3 scripts/build/validate.py` (jsonschema); browser tests: `OCCULT_BROWSER_TESTS=1`. No commercial-data goldens or importer are shipped.

See LICENSE-SRD.md and NOTICE for required attribution. This is unofficial fan tooling, not affiliated with Wizards of the Coast.
