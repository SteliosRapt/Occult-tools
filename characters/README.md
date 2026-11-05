# Characters

Character specs for the rules engine. A spec is a JSON file of the player's **choices**; `./occult character <file>`
derives everything else from the books (class tables, armor, weapons, feats, species, backgrounds):

```
./occult character characters/examples/rowan-fighter-1.json          # the sheet, as Markdown
./occult character characters/examples/rowan-fighter-1.json --json   # the sheet, as JSON
./occult character characters/examples/sel-wizard-3.json --level-up wizard   # what the next level changes
./occult character characters/examples/sel-wizard-3.json --pdf               # a printable PDF character sheet
./occult character characters/examples/sel-wizard-3.json --cards             # spell cards for its spells
```

`--pdf [PATH]` writes `dist/characters/<name>.a4.pdf` (or PATH): a front sheet with every number and checkboxes for
Hit Dice, death saves, class resources and spell slots, then every feature, trait, feat and option in full, then the
spells (list and descriptions). `--mode bw` for an ink-saver, `--paper letter` for US Letter, `--png` for page images.
Rule problems print as `check:` lines; the PDF is still written.

`--form [PATH]` prints the same numbers onto the official D&D 2024 character sheet (Wizards of the Coast's
two-page PDF, which you put in `forms/`: see [forms/README.md](../forms/README.md); needs pypdf):
`dist/characters/<name>.dnd-2024.pdf` (or PATH). Header, abilities, saves and skills with their proficiency
dots, AC, HP and Hit Dice maximums, weapons and damage cantrips, class features, species traits, feats, training,
spellcasting, slots, the spell list with C/R/M marks, alignment, languages, equipment and coins. Fields the spec
leaves out (appearance, personality, current HP, ...) stay blank for pencil. `--mode bw` prints the values in black.

`--cards [PATH]` writes the spec's `spells` as spell cards, 3×3 on a sheet with crop marks like `make cards spells`:
`dist/cards/<name>-spells.a4.pdf` (or PATH). Add `--backs category` for mirrored back sheets (duplex, long edge);
`--mode`, `--paper` and `--png` work as for `--pdf`, and both can be given at once.

`examples/` holds four complete, rule-clean characters (the tests build each one and expect no warnings):
a human fighter, a dwarf Life Domain cleric, an elf Evoker wizard and a halfling Thief rogue. Put real party members in `characters/<name>.json`.

## The spec

| Key | Required | Meaning |
|---|---|---|
| `name` | | Display name |
| `species` | | Id or slug: `dwarf`, `species:elf`, `halfling` |
| `size` | for species that offer two | `medium` or `small` |
| `background` | | Id or slug: `soldier`. Its skills and origin feat are added automatically |
| `abilities` | yes | The six scores **before** the background bonus: `{"str": 15, "dex": 13, ...}` |
| `method` | | `standard-array`, `point-buy`, `rolled` or `manual`; the first two are checked |
| `background_bonus` | with a background | +2/+1 or +1/+1/+1 among the background's three abilities: `{"str": 2, "con": 1}` |
| `classes` | yes | `[{"class": "fighter", "level": 5, "subclass": "champion"}]`; the **first** is the starting class (its saves, armor, weapons and level 1 hit points) |
| `hp` | | `"average"` (default) or `{"rolls": [7, 3, null]}`: one roll per level after the 1st, in class order; `null` takes the average |
| `feats` | | Chosen feats (not the background's): `"alert"`, or `{"feat": "ability-score-improvement", "increase": {"str": 2}}` for feats that raise abilities |
| `skills` | | Skill proficiencies chosen from class, species or feats (the background's are added) |
| `expertise` | | Skills with Expertise |
| `armor`, `shield` | | `"chain-mail"` or `{"id": "chain-mail", "bonus": 1}`; `"shield": true` or `{"bonus": 1}` |
| `weapons` | | `["longsword", {"id": "longbow", "bonus": 1}]` |
| `mage_armor` | | `true` while *Mage Armor* is up (13 + Dex when unarmored) |
| `proficiencies` | | Extra training from feats or species: `{"armor": ["medium"], "weapons": ["longbow"], "tools": ["Dice Set"]}`; a background that offers a tool choice ("one kind of Gaming Set") takes it from `tools` |
| `modifiers` | | Anything the engine does not model, such as magic items: `ac hp speed initiative saves save_<ability> attack damage spell_dc spell_attack` |
| `set_abilities` | | Items that set a score: `{"str": 21}` |
| `choices` | | Free-form notes echoed on the sheet: `{"elven_lineage": "High Elf"}` |
| `spells` | | Known and prepared spells: `["fire-bolt", {"spell": "detect-magic", "source": "High Elf"}, {"spell": "alarm", "prepared": false}, {"spell": "shield", "class": "sorcerer"}]`. Checked against the casters' lists, highest level and cantrip/prepared counts; `source` marks a spell a feat, species or feature grants (not counted), `"prepared": false` a spellbook spell, `class` picks the caster in a multiclass |
| `options` | | Invocations, Metamagic, maneuvers and other class options: `["agonizing-blast"]` (`./occult list options --class warlock`) |
| `languages` | | `["Common", "Elvish", "Draconic"]` |
| `equipment`, `coins` | | `["Backpack", "Rope (50 ft.)"]`, `{"gp": 15, "sp": 4}` |
| `details` | | For the PDF: `alignment player age deity campaign` (header) and `appearance personality ideals bonds flaws backstory allies notes` (printed in full) |

## What the engine checks

Every problem is a line under **Check** (`warnings` in JSON), never an error, so a draft can still be printed:
point-buy cost and score range, the Standard Array, background ability choices, multiclass prerequisites
(13 in the primary ability of every class), a missing subclass at its level, General and Fighting Style feats
against the feat slots the classes give, feat level prerequisites, feat ability choices and caps, duplicate skill
proficiencies, Expertise without proficiency, armor and Shield training, impossible hit point rolls, and
weapons without proficiency, a background tool choice left open, and chosen spells (off the list, too high, more cantrips or prepared spells than the class gives). A spec that cannot be built at all (unknown class, level over 20, a subclass of
another class) is an error with suggestions.

## What it derives

Ability scores and modifiers, saves, all 18 skills (Expertise, Jack of All Trades), passive Perception,
initiative (Alert, Remarkable Athlete), AC (armor, Dex caps, Unarmored Defense, Draconic Resilience, Mage Armor,
Shield, Defense), hit points (with Tough, Dwarven Toughness, Draconic Resilience) and the
Hit Dice pool, speed (Fast Movement, Unarmored Movement, heavy armor Strength), size and carrying capacity,
attacks (finesse, ranged, thrown, Archery, monk weapons and Martial Arts dice, Versatile, mastery) and attacks
per action, spellcasting per class (ability, save DC, attack, cantrips, prepared spells, highest spell level,
which list), spell slots (single-class tables, the Multiclass Spellcaster table, third casters, Pact Magic) and
cantrip dice, class resources (the class table's columns: Rages, Focus Points, Sneak Attack ...), every class
and subclass feature by level with its id, feats with their source, and XP thresholds.

The rules applied automatically by feature, feat or species are in `EFFECTS` in
[tools/occult/rules/character.py](../tools/occult/rules/character.py); anything else goes in `modifiers`.
