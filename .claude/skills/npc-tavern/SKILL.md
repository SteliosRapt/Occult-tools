---
name: npc-tavern
description: Prepare NPCs, settlements and taverns using SRD stat blocks and labeled original fiction.
---

# Npc Tavern

Adapted from the occult-lore npc-tavern workflow for the public SRD repository.

The SRD omits many random name, settlement, tavern and personality tables. The `npc`, `settlement` and `tavern` verbs may return a missing-table error. Never claim an invented result came from those tables. Use original names and descriptions, marked as your own fiction, and attach a real SRD stat block when mechanics are needed.

```sh
./occult list creatures --type humanoid --cr 0-3
./occult show creature:priest --full
./occult table --list
./occult encounter priest --pdf
```

Get the scene's purpose and tone. Give one memorable visual detail, motivation, secret and interaction hook. For a settlement or tavern add two locations and one immediate problem, keeping the outline brief enough to run. Read any referenced stat block through `show`; cite its id. Use the loot skill for items and dm-helper for encounter balance. Do not import named settings or commercial lore.
