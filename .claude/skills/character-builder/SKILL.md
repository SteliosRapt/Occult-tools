---
name: character-builder
description: Build, check and level up SRD 5.2.1 characters.
---

# Character Builder

Adapted from the occult-lore character-builder workflow for the public SRD repository.

Use `./occult` for every rule, option and number. Start with characters/README.md and the four examples in characters/examples/. The SRD has 12 classes, one subclass per class, 9 species and 4 backgrounds; browse before selecting. Ask the player for missing choices when working interactively. Do not invent unavailable options.

```sh
./occult list classes
./occult list subclasses
./occult list species
./occult list backgrounds
./occult list feats
./occult show class:fighter subclass:champion background:soldier species:human
./occult list spells --class wizard --level 0-2
./occult character characters/examples/sel-wizard-3.json
./occult character characters/examples/sel-wizard-3.json --level-up wizard
./occult character characters/examples/sel-wizard-3.json --pdf
./occult character characters/examples/sel-wizard-3.json --cards
```

Record choices in a JSON spec: ability scores before background bonuses, species, background, class levels and subclass, feats, skills, equipment and spells. Use `modifiers` for effects the engine does not model, explaining them. Build the spec, read every Check warning, correct invalid choices, then build again. Do not report a draft as rule-clean. On level-up review the proposed changes and update the player's spec. Give the final numbers, ids and paths to any PDFs. Cite the SRD id; this dataset has no page numbers.
