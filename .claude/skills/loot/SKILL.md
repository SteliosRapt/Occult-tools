---
name: loot
description: Choose SRD treasure and magic items with explicit limits on unavailable random tables.
---

# Loot

Adapted from the occult-lore loot workflow for the public SRD repository.

Use SRD magic-item entries and their variants. Never roll on a commercial table from memory. Several random treasure/rarity tables are absent from this dataset, so `loot hoard`, `loot individual` and related operations may return a missing-table error. Report that limit, then offer a clearly labeled manual selection from available items. Do not present your selection as an official random-table result.

```sh
./occult list magic-items --rarity uncommon
./occult list magic-items --rarity rare --attunement
./occult show magic-item:bag-of-holding --full
./occult table --list
./occult table "Potion Miscibility" --seed 2
./occult make cards magic-item:bag-of-holding --backs category
```

Ask for party level, theme and desired power; look up candidate items, explain attunement, charges and restrictions, and cite ids. Resolve a variant by its displayed SRD title. Offer item cards after the selection. Coins or story rewards you invent must be labeled as your recommendation.
