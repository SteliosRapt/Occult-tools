---
name: dm-helper
description: Run SRD encounters, look up monsters and answer rules questions.
---

# Dm Helper

Adapted from the occult-lore dm-helper workflow for the public SRD repository.

Use the SRD data and rules engine for each number. Cite ids without page numbers. If the SRD does not cover a situation, say so; mark your ruling explicitly.

```sh
./occult encounter --party 4x3 goblin-warrior x4
./occult encounter --party 4x5 --suggest --difficulty high --type undead --seed 3
./occult encounter --party 4x3 goblin-warrior x4 --pdf --cards
./occult list creatures --cr 1-3 --type undead
./occult show creature:goblin-warrior --full
./occult show term:grappled term:cover term:concentration
./occult find difficulty class
./occult calc cr 7
./occult roll 1d20+5 --times 4
```

Get party size, levels, habitat and intended difficulty. Rate a proposed mix; pass on warnings about numbers, CR and complexity. Read every chosen stat block before summarizing tactics. Offer terrain and a clearly labeled ruling when necessary. Print a handout with --pdf and optional creature cards. Search traps, hazards and languages through `list`; never assume a commercial setting, deity, Bastion or monster is present. For treasure, use the loot skill. For session outlines use session-prep.
