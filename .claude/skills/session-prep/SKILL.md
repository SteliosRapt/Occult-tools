---
name: session-prep
description: Prepare a complete session from SRD mechanics and original scene ideas.
---

# Session Prep

Adapted from the occult-lore session-prep workflow for the public SRD repository.

Build a runnable outline using SRD rules and original fiction. Ask for party levels, length, tone and starting situation if unknown. Separate original scene material and rulings from cited mechanics. Do not invent citations, page numbers or official table results.

```sh
./occult encounter --party 4x3 --suggest --difficulty moderate --seed 4
./occult encounter --party 4x3 goblin-warrior x4 --pdf
./occult show creature:goblin-warrior term:grappled --full
./occult list magic-items --rarity uncommon
./occult table --list
```

Provide an opening hook, three scenes, one flexible encounter and two ways it can end. Read selected creatures, spells, hazards and traps before using them. Rate combat and include the warnings. Invent NPC names, motives and locations; choose their mechanics from `list creatures` and read selected stat blocks with `show`. Pick rewards manually with `list magic-items --rarity uncommon` and read their rules with `show`, labeling those selections. Offer printable encounters, condition cards and character sheets when useful. Deliver a concise checklist of ids and generated artifact paths.
