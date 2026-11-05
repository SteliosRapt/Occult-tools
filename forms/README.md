# Forms

Blank official sheets that `./occult` prints a character onto. The PDFs are Wizards of the Coast's, so
they are not committed (`.gitignore`): put your copy here.

| File | What | Used by |
|---|---|---|
| `dnd-2024-character-sheet.pdf` | The D&D 2024 character sheet: 2 pages of 603 × 774 pt, product code `670D3898000001 EN` on page 2 (sha256 `f223ca7b…f54454`) | `./occult character <spec> --form` |

```
./occult character characters/changeling-warlock-1.json --form          # dist/characters/<name>.dnd-2024.pdf
./occult character <spec> --form out.pdf --form-template ~/Downloads/sheet.pdf --png
```

`--form-template PATH` or `$OCCULT_FORM_PDF` point at a copy elsewhere. The field positions in
`style/forms/dnd-2024.css` were measured on that edition (its rules, circles and diamonds), so another
printing may need them adjusted; `--form` warns when page 2 lacks the product code. Rendering needs
pypdf (`pip install pypdf`, optional like Pillow) besides the usual Node and Chromium.
