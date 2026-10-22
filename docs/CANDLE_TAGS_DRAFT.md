# Candle tags & Lumière notes — draft for review

Drafted 2026-10-22 from the live catalogue
(`GET /api/candles/candles/`, 15 rows, 11 names). **Nothing here is in the
database yet.** Every value comes from the candle's public description; where
the description says nothing, the field is left empty (`—`). `burn_time` is
left blank on every row for the owner to fill.

> **Before loading this:** these fields are not only for Lumière. The product
> page shows the structured fields *instead of* the "Scent / Mood / Perfect
> for" lines it currently reads out of the description, and adds a Season row
> when `season_tags` is set (`CatalogDetail.tsx:250-268`). Tag values are shown
> exactly as stored, so lower-case English keys would appear on the page as
> lower-case English in every language. See [Applying it](#applying-it).

## Fields per scent

Sizes of one scent share the same values; the **Rows** column lists the
catalogue ids each line applies to.

Markers in the note columns:

- **†** The description names a group in that tier ("citrus", "soft florals",
  "spice", "soft herbal notes"); the ingredients of that kind from its
  *Scent:* line were placed there.
- **‡** Named in the description's opens / moves into / settles into
  sentence but missing from its *Scent:* line. Included, so it is added to
  the product page.
- **◊** On the *Scent:* line, but the description doesn't say where in the
  scent it sits. Put in heart_notes by default so it stays on the product
  page — move it if you know better.

| Scent | Rows | fragrance_family | intensity | top_notes | heart_notes | base_notes | mood_tags | use_case_tags | ideal_spaces | season_tags |
|---|---|---|---|---|---|---|---|---|---|---|
| Mango Island | 5, 16 | — | — | mango, tropical fruit | coconut, citrus | vanilla | bright, tropical, uplifting, relaxing | relaxation, self-care, evenings | living room, bedroom, cozy spaces | summer |
| Matcha Chill | 6, 17 | — | — | bergamot, lemon†, orange† | green tea, black tea | sandalwood | calm, clean, balanced | evenings, self-care, relaxation | bedroom | — |
| Sweet Lemon Dew | 7, 18 | citrus | — | lemon, bergamot, orange | honey, cake‡, mint◊ | tonka bean | fresh, uplifting, light | daytime, energy boost | kitchen, living room | — |
| Tidal Bore | 8, 19 | coastal | — | ozone‡, citrus | jasmine†, violet†, sea salt◊ | cedar, musk | calm, fresh, grounding | evenings, relaxation | living room | — |
| Mulled Wine | 9 | spiced | — | orange peel, apple | cinnamon, clove, peppercorn | tonka bean, vanilla | warm, cozy, inviting | evenings, entertaining | living room, dining room | winter |
| Berry Grove | 10 | aromatic | — | ozone, citrus | red berries, pear | pine, juniper, sage†, camphor† | fresh, crisp, uplifting | evenings, relaxation | cozy spaces | winter |
| Rich Smokey | 11 | — | — | amaretto, honey | brandy | tobacco leaf, oak, benzoin | warm, intimate, luxurious | evenings, relaxation, cozy moments | — | — |
| Ginger Bliss | 12 | spiced | — | ginger, cinnamon† | brown sugar, butter, molasses◊ | vanilla, milk, clove | cozy, warm, uplifting | holidays, evenings, cozy moments | — | — |
| Spice Delight | 13 | — | — | pumpkin, brown sugar | cinnamon, clove, cream◊ | vanilla, butter, nutmeg | cozy, warm, comforting | evenings, relaxation | — | autumn |
| Woman Body | 14 | — | — | — | — | — | — | — | — | — |
| Woman Body Black | 15 | — | — | — | — | — | — | — | — | — |

Why some fields are empty:

- **intensity** — no description says how strongly a candle throws. Empty
  everywhere.
- **fragrance_family** — set only where the description names the kind of
  fragrance: "a vibrant citrus fragrance", "a fresh, coastal fragrance", "a
  rich, spiced fragrance", "a crisp, aromatic fragrance", "a cozy, spiced
  fragrance". Mango Island ("sunny exotic"), Matcha Chill ("spa-inspired …
  built around green tea and citrus"), Rich Smokey ("deep, refined") and Spice
  Delight ("rich, comforting") don't name one.
- **season_tags** — only where *Perfect for* names a season ("summer
  evenings", "winter evenings", "autumn"). Ginger Bliss says "holidays" and
  "festive" but no season; Sweet Lemon Dew is *inspired by* summer air but
  isn't recommended for a season.
- **Woman Body / Woman Body Black** — both descriptions are empty.

Left out on purpose: Mango Island's "light sweetness" (a quality, not a note)
and every "Details" line (wax, wick, sizes, burn time) — those are product
facts, not tags.

## assistant_notes

Only what nothing else carries: how a scent differs from the shop's other
scents, and who it suits better or worse than its neighbours. The model
already reads the public description and the tag fields, so the notes don't
repeat the scent progression, the tags, or the wax and wick details.

Every comparison is drawn from two descriptions side by side; nothing is
said that no description says. Two consequences:

- **No pairings.** No description suggests buying two scents together, so
  "what it pairs with" is left for the owner.
- **"The only …" goes stale.** Claims like "the only floral scent" are true
  of today's 11 names; a new scent can make one false. Re-check the notes
  when the catalogue changes.

Written once per scent, on the 8 oz row (the 4 oz row for Woman Body); the
other size reads it from there. No burn time — that stays in `burn_time`.

| Scent | Write on row | assistant_notes |
|---|---|---|
| Mango Island | 5 | The shop's only tropical, fruit-led scent: mango and coconut, where Sweet Lemon Dew, the other bright, sunny one, is led by lemon and mint. The only scent recommended for summer. |
| Matcha Chill | 6 | The only tea scent. It opens like Sweet Lemon Dew, on bergamot and citrus, but settles into tea and sandalwood: the calm choice where Sweet Lemon Dew is the energizing one. |
| Sweet Lemon Dew | 7 | The only scent described as energizing, and the only one recommended for daytime and the kitchen. Sweeter than Matcha Chill, which shares its bergamot-and-citrus opening: honey and tonka where Matcha Chill has tea and sandalwood. |
| Tidal Bore | 8 | The only coastal scent and the only floral one. It opens like Berry Grove, on ozone and citrus, then turns to sea salt and florals where Berry Grove turns to berries and pine. |
| Mulled Wine | 9 | Of the two winter scents, the warm, spiced one; Berry Grove is the cool, crisp one. The only scent recommended for entertaining and for dining rooms, and the only one described as filling the whole room. |
| Berry Grove | 10 | Of the two winter scents, the cool one: described as cooling, where Mulled Wine is warm and spiced, so someone after warmth on a winter evening is better served by Mulled Wine. The only one with pine, juniper and herbal notes. |
| Rich Smokey | 11 | The only smoky scent, built on brandy, tobacco and oak. The evening choice for someone who wants depth without the spice of Mulled Wine, Ginger Bliss or Spice Delight. |
| Ginger Bliss | 12 | The only scent recommended for the holidays, built on gingerbread. Close to Spice Delight — both have brown sugar, butter, vanilla, cinnamon and clove — but with ginger and molasses where Spice Delight has pumpkin and nutmeg. |
| Spice Delight | 13 | The only scent recommended for autumn, built on pumpkin. Close to Ginger Bliss — both have brown sugar, butter, vanilla, cinnamon and clove — but with pumpkin and nutmeg where Ginger Bliss has ginger and molasses. |
| Woman Body | 14 | — (no description; for the owner) |
| Woman Body Black | 15 | — (no description; for the owner) |

## Vocabulary

Lower case, English, singular where the description used a plural
("tobacco leaves" → tobacco leaf), adjectives dropped from notes ("soft musk"
→ musk, "creamy coconut" → coconut).

- **fragrance_family** — aromatic, citrus, coastal, spiced
- **intensity** — the model's choices: soft, medium, strong (none used)
- **notes** — amaretto, apple, benzoin, bergamot, black tea, brandy, brown
  sugar, butter, cake, camphor, cedar, cinnamon, citrus, clove, coconut,
  cream, ginger, green tea, honey, jasmine, juniper, lemon, mango, milk,
  mint, molasses, musk, nutmeg, oak, orange, orange peel, ozone, pear,
  peppercorn, pine, pumpkin, red berries, sage, sandalwood, sea salt, tobacco
  leaf, tonka bean, tropical fruit, vanilla, violet
- **mood_tags** — balanced, bright, calm, clean, comforting, cozy, crisp,
  fresh, grounding, intimate, inviting, light, luxurious, relaxing, tropical,
  uplifting, warm
- **use_case_tags** — cozy moments, daytime, energy boost, entertaining,
  evenings, holidays, relaxation, self-care
- **ideal_spaces** — bedroom, cozy spaces, dining room, kitchen, living room
- **season_tags** — autumn, summer, winter

Where different wordings were merged into one value:

| Description says | Stored as |
|---|---|
| Tonka, Tonka bean | tonka bean |
| black pepper (prose), Peppercorn (*Scent:* line) | peppercorn |
| Soft musk, light musk | musk |
| Living room, Living space, Living spaces, Living rooms | living room |
| dining spaces | dining room |
| Cozy spaces, warm cozy interiors | cozy spaces |
| Cozy moments, Comfort moments | cozy moments |
| Self-care, self-care rituals | self-care |
| Boosting energy | energy boost |
| Winter evenings, summer evenings | evenings + the season |

## Found while drafting

Not changed — for the owner:

1. **Woman Body Black is a different name from Woman Body.** Sizes and
   colors of one scent are linked only by an identical name, so these two
   don't appear as one candle in two colors, and a note written on one isn't
   shared with the other. If they're the same scent, the black one should be
   named "Woman Body" with color Black (the unique constraint is on name +
   size + color, so that's allowed).
2. **Five descriptions offer a size that isn't sold.** Mulled Wine, Berry
   Grove, Rich Smokey, Ginger Bliss and Spice Delight say "8 oz / 11.3 oz",
   but each exists only in 8 oz.
3. **Burn time is already in the descriptions:** "50+ hrs" for every scent
   except Mango Island, which states none. If that figure holds for both
   sizes, it's a ready source for `burn_time`.
4. **"Rich Smokey" vs "Rich Smoky":** the product name and the description
   spell it differently.
5. **Woman Body and Woman Body Black have no description at all**, so the
   product page and Lumière have nothing to say about them.

## Applying it

Not done — the order this needs:

1. **Labels in the frontend first.** Store the values above as keys and map
   each one to a label in `i18n.ts`, in all four languages. Around 90
   entries; a missing key falls back to the key itself. Until that ships,
   loading the data would put lower-case English on the product page in
   every language.
2. **Check the ◊ notes** (mint, sea salt, molasses, cream) — in heart_notes
   by default.
3. **Load it** with `python manage.py load_candle_tags`, which reads the two
   tables in this file. Without `--apply` it only prints, per candle, what
   would change and what it would overwrite. `--apply` refuses to run until
   every value has a label in all four languages in
   `frontend/src/locales/candle-tags.json` and `frontend/src/i18n.ts`
   imports that file. A `—` cell leaves that field as
   it is; `burn_time` is never touched.
