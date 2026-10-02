# Changelog

## 2026-08-31 — Live shipping rates via Shippo

Replaces the flat $15 shipping fee with real carrier quotes, and fixes a
Stripe error-handling bug found along the way. Covers everything in the
working tree as of this date: the already-committed `shipping` app and
model/migration changes, plus the still-uncommitted edits to orders and the
checkout page.

> **Note on scope vs. the brief:** the task description said the `shipping`
> app "may not be committed yet." It is — `shipping/*`, the `candles` weight/
> dimension fields (migration `0028`), and `orders.shipping_phone` (migration
> `0008`) are all already on `main`. Only six files are actually modified in
> the working tree, plus two new untracked frontend files. This changelog
> documents the whole feature (for context) but the diff itself is the small
> part: order creation, Stripe intent handling, and the checkout UI.

### Backend — shipping (new app, already committed)

- New `shipping` app: a small hand-rolled Shippo HTTP client
  (`shipping/client.py`, deliberately not the official SDK — four endpoints
  don't justify the dependency), address/state normalisation to the ISO and
  USPS codes Shippo requires (`shipping/normalize.py`), naive box-packing from
  variant weight/dimensions (`build_parcels`), rate quoting, and label
  purchase/refund (`shipping/services.py`).
- New `Shipment` model, one row per `Order` (OneToOne, so the status field can
  be used as a lock against double-purchasing a label).
- Two new endpoints: `POST /api/shipping/rates/` (quote, authenticated) and
  `POST /api/shipping/orders/<id>/label/` (staff-only label purchase).
- *Why:* a flat $15 fee was either overcharging light orders or undercharging
  heavy/far ones. Candles are dense (mostly glass) so weight-based pricing
  needed real per-variant weight and dimensions, which candles didn't carry
  before. The rate returned to the client is only an id — the server always
  re-reads the price from Shippo before charging, so a tampered amount from
  the browser changes nothing.
- The Shippo call can fail or be unreachable; `resolve_shipping_cost()` never
  lets that fail a checkout — it falls back to `SHIPPING_FALLBACK_RATE`
  (the old $15, now a safety net rather than the price) and returns no rate
  object, so nothing downstream believes it has a real quote.

### Backend — candles (already committed)

- `CandleVariant` gained `weight_oz`, `length_in`, `width_in`, `height_in`
  (migration `candles/0028`). Needed to build a Shippo parcel; previously
  nothing about physical size was tracked at all.

### Backend — orders (uncommitted changes in this diff)

- `Order.shipping_phone` (migration `orders/0008`, already committed) is now
  populated from checkout and read by `shipping.normalize.order_to_address`
  (Shippo transactions want a phone; falls back to `SHIPPO_FALLBACK_PHONE` if
  the shopper left it blank).
- `build_order()` (`orders/serializers.py`) now calls
  `resolve_shipping_cost()` instead of hardcoding the fee, and accepts an
  optional `shipping_rate_id` picked at checkout. If a rate came back, a
  `Shipment` row is created alongside the `Order` carrying that carrier,
  service level and price.
- The stock/availability check (`is_active`, `stock_qty`) was moved earlier in
  `build_order()`, before the Shippo quote call. *Why:* the check runs while
  holding `select_for_update()` on the variant rows; quoting first would mean
  holding that lock for the 2–3 seconds a live carrier call can take, for a
  cart that might turn out to be unfulfillable anyway.
- `OrderReadSerializer` now exposes `shipping_phone`, `carrier`,
  `service_level`, `tracking_number`, `tracking_url` (via `getattr` on the
  optional reverse `Shipment` relation, since no label exists until an order
  is paid and shipped).
- List/detail order views now `select_related("shipment")` and
  `prefetch_related("items__candle")` — added because the serializer change
  above would otherwise cost one extra query per order in a list.
- `OrderStatusUpdateAPIView` now also `select_related("shipment")`, and its
  docstring points staff at the new label-purchase endpoint (buying a label
  moves the order to `shipped` itself; the plain status endpoint no longer
  needs to be used for that transition).

### Backend — Stripe (uncommitted changes in this diff)

- Fixed `stripe.error.StripeError` / `stripe.error.SignatureVerificationError`
  → `stripe.StripeError` / `stripe.SignatureVerificationError`. The installed
  `stripe` SDK version puts these on the top-level module now; the old
  `stripe.error.*` path either no longer exists or silently stopped matching,
  so **Stripe errors were not being caught at all** before this fix.
- `CreatePaymentIntentView.post` had two near-duplicate success-response
  blocks with different field sets, and its `except Exception` handler
  referenced `intent`/`order` — which may not be bound yet if the failure
  happened before they were assigned, i.e. a code path that could itself
  raise `UnboundLocalError` while handling an error, and returned **HTTP 200
  with the same success shape as a real success**. Both are gone now: a
  single `_order_payload()` builds the body, and Stripe/generic failures
  return `{"error": "..."}` with `502`/`500` instead of `200`. *Why it
  mattered:* the frontend used this response's presence/shape to decide
  whether to mount the Stripe payment form — a 200 on failure showed the
  shopper a checkout form that could never complete.
- The webhook handler now reads `order_id`/`intent_id` once, up front, and
  returns `200` immediately if an event carries no `order_id` (acknowledges
  events that aren't ours instead of letting them fall through). It also
  no longer cancels the order on `payment_intent.payment_failed` — a declined
  card is not a cancelled order, and `CANCELED` is terminal under
  `Order.ALLOWED_TRANSITIONS`, so the old behaviour meant a shopper whose
  first card failed could never retry with a second one. The order is now
  left `PENDING` and logged instead.
- The confirmation email send was already outside the row-lock transaction;
  a comment now documents why (an SMTP timeout must not roll back a payment
  that has already been taken).

### Frontend (uncommitted changes in this diff, plus two new files)

- New `frontend/src/components/Shippingrates.tsx`: fetches
  `POST /api/shipping/rates/` (debounced 600ms after the address/cart
  stabilises), renders a radio list of carrier options, auto-preselects the
  cheapest, and guards against a slow response overwriting a newer one with a
  request-id ref.
- New `frontend/src/styles/Shippingrates.css` for that component.
- `Checkout.tsx`: removed the hardcoded `SHIPPING_AMOUNT = 15`; mounts
  `<ShippingRates>` above the submit button, tracks the shopper's selection,
  sends `shipping_rate_id` with order creation, and after the order comes
  back trusts the server's `shipping_amount` over the client-picked estimate
  (labelled in the UI: the picked rate is shown until the server number
  exists, then the server number wins — it may differ if the carrier API was
  down and the fallback rate applied).
- `CustomerCare/Delivery.tsx`: copy rewritten from "delivery is free" to
  describing weight-based pricing (~$8–14 domestic), ship-from location, and
  a few operational notes (heat sensitivity, damage policy). No shipped
  behaviour change, just user-facing copy now that the free-shipping claim
  is no longer true.

### Product page — sticky panel and page height (unrelated to shipping)

Two small fixes in `frontend/src/styles/CatalogDetail.css` that happened to be
sitting in this working tree alongside the shipping changes — not part of the
Shippo integration, called out on their own so this entry doesn't imply
otherwise. The buy panel's `position: sticky` offset was a flat `32px`, which
put it underneath the fixed site header as the page scrolled; it now clears
the header with `calc(var(--header-height) + 24px)`. And the page no longer
forces `min-height: 100vh`/`100dvh`, which was leaving a band of empty page
below short product listings — height now comes from content. Both are
intentional and correct; likely a leftover from the earlier "sticky buy
panel" product-page work (commit `0149976`) that never got committed at the
time.

### Configuration

New Shippo-related settings, all read via `django-environ`/`decouple`-style
`config()` in `config/settings.py`:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SHIPPO_TOKEN` | **Yes**, to get live rates | `""` | API key. Empty → every quote falls back to the flat rate (`ShippoNotConfigured`), so the site still works with none set. |
| `SHIPPING_FALLBACK_RATE` | No | `15.00` | The old flat fee, now only used when Shippo is unreachable/unconfigured or returns no rates. |
| `SHIP_FROM_STREET1`, `SHIP_FROM_CITY`, `SHIP_FROM_STATE`, `SHIP_FROM_ZIP` | **Yes**, for real quotes | `""` | Origin address for every rate/label. Currently set in this repo's `.env` (Brooklyn, NY) but blank in `.env.example` — must be filled in per deployment. |
| `SHIP_FROM_NAME` | No | `"KFursenko Candles"` | Origin name on the label. |
| `SHIP_FROM_COMPANY`, `SHIP_FROM_STREET2`, `SHIP_FROM_PHONE` | No | `""` | Optional origin address fields. |
| `SHIP_FROM_COUNTRY` | No | `"US"` | Origin country. |
| `SHIP_FROM_EMAIL` | No | `DEFAULT_FROM_EMAIL` | Origin email on the label. |
| `SHIPPO_FALLBACK_PHONE` | No, but see gap below | `""` | Used as the `address_to` phone when an order/checkout has none. Shippo transactions want a phone; without this *and* a shopper-entered one, label purchase can fail. |
| `SHIPPO_API_BASE` | No | `https://api.goshippo.com` | Override for testing against a different host. |
| `SHIPPO_API_VERSION` | No | `2018-02-08` | Shippo API version header. |
| `SHIPPO_TIMEOUT_SECONDS` | No | `30` | Per-request timeout. |
| `SHIPPO_LABEL_FILE_TYPE` | No | `PDF` | Label format requested from Shippo. |
| `SHIPPO_MAX_RATES_PER_CARRIER` | No | `2` | Rates kept per carrier after quoting, cheapest first. Added to `.env.example` in the 2026-08-31 follow-up pass (see below); previously only had a default buried in `shipping/services.py`. |
| `THROTTLE_SHIPPING_RATES` | No | `20/min` | DRF throttle scope for `POST /api/shipping/rates/`. |

`SHIPPO_CARRIERS` (carrier allow-list) is now declared in `config/settings.py`
as a plain Python constant, `SHIPPO_CARRIERS: list[str] = []` — not an env
var, so there is nothing to set in `.env`/`.env.example` for it. Empty means
every carrier enabled in the Shippo dashboard is offered; edit the list in
`settings.py` directly to narrow it (e.g. `["usps", "fedex"]`).
`shipping/services.py` still reads both settings via
`getattr(settings, ..., default)` rather than a direct attribute access —
left that way deliberately so the module stays importable in any test that
builds a settings object without this section.
`SHIPPO_BOXES` (box sizes for packing) is likewise hardcoded in
`settings.py`, not an env var — two boxes, `5×5×5` and `8×8×5`, no `.env`
override exists.

### Deployment steps beyond `migrate`

1. Set the config-table variables above per environment; `SHIPPO_TOKEN` and
   the `SHIP_FROM_*` block are the ones that actually change behaviour.
2. In the Shippo dashboard, **enable at least one carrier account** for the
   token's mode (test or live) — `quote_rates()` raises a `ShippoError` with
   an explicit message pointing back at this step if no carrier is active,
   which is by far the most likely first failure after deploy.
3. Get a **live** `SHIPPO_TOKEN` before going live with real charges — the
   client's `is_test` property is derived from the token prefix
   (`shippo_test_...`), and every `Shipment.is_test` flag downstream depends
   on it being correct. The current `.env` in this repo carries a
   `shippo_test_...` token.
4. **Still open — fix the broken CSS import in the new frontend component**
   before deploying the frontend. This follow-up pass was told to assume it
   was already fixed and skip it; it isn't. Re-verified today:
   `Shippingrates.tsx` still imports `../styles/Checkout/ShippingRates.css`,
   which does not exist, and `npx vite build` still fails with
   `UNRESOLVED_IMPORT` — see Known Gaps and Verification below.
5. No data backfill needed for shipping weight: existing `CandleVariant` rows
   got sane defaults from migration `0028` (8 oz, 3×3×4 in), so quoting works
   for old catalog data without an admin pass, but those defaults are
   guesses — see Known Gaps.
6. Run migrations `orders/0009_orderitem_variant` and
   `orders/0010_backfill_orderitem_variant` (added in the 2026-08-31
   follow-up pass, see below) — the second is a data migration that backfills
   `OrderItem.variant` on existing rows and runs automatically as part of
   `migrate`, no manual step beyond that.

### Known gaps

- **Frontend build is still broken.** Not fixed. The follow-up pass that
  closed findings 2, 3, 4 and 6 (below) was told to assume this one was
  already fixed and to skip it; re-verifying today shows it isn't —
  `Shippingrates.tsx` still imports `../styles/Checkout/ShippingRates.css`,
  which does not exist (the real file is `frontend/src/styles/Shippingrates.css`,
  no `Checkout/` subdirectory, different case), and `npx vite build` still
  fails with `UNRESOLVED_IMPORT` — see Verification below for today's output.
  `npx tsc --noEmit` still doesn't catch it either, for the same reason as
  before: TypeScript resolves CSS imports against a wildcard ambient module
  declaration and never checks the file exists. Unchanged from the original
  audit entry; flagging again here since a later pass assumed otherwise.
- **Default variant weight/dimensions are guesses, not measurements.** The
  `0028` migration defaults every existing `CandleVariant` to 8 oz / 3×3×4 in
  regardless of actual size. Nothing flags which rows still carry the default
  vs. a real measurement — every rate quoted against un-updated stock is
  quoted against a made-up weight. Worth an admin pass (or a "needs
  measurement" flag) before this is trusted for real charges.
- **No carrier allow-list is active.** `SHIPPO_CARRIERS` and
  `SHIPPO_MAX_RATES_PER_CARRIER` are now declared explicitly in
  `config/settings.py` (2026-08-31 follow-up — previously referenced only via
  `getattr` in `shipping/services.py` with no line in the settings file to
  find them), but `SHIPPO_CARRIERS` still defaults to `[]`. The gap itself is
  unchanged: whatever carriers are enabled on the Shippo account, all of them
  can surface at checkout, until someone fills the list in.
- **`SHIPPO_FALLBACK_PHONE` and shopper-entered phone are both optional.**
  `ShippingSerializer` doesn't require a phone, and if the account-level
  fallback is also blank, `order_to_address()` sends no phone at all.
  Whether Shippo/the carrier accepts that for a label purchase hasn't been
  verified against a live account.
- **`build_parcels`' bin-packing is intentionally naive** (its own docstring
  says so): sum weight/volume, pick the smallest box that fits by volume, or
  split evenly across N of the largest box on overflow. Fine for single
  candles of similar shape; explicitly not real bin-packing, and there are
  only two box sizes defined (`SHIPPO_BOXES`, hardcoded, not env-configurable)
  — a large or oddly-shaped order may quote a parcel that doesn't reflect how
  it actually gets packed.
- **No stock is ever restored.** This predates this change (the flat-rate
  code never restocked either), but it's now more visible: stock is
  decremented at order creation, `payment_intent.payment_failed` no longer
  cancels the order (see above — that's a deliberate, correct fix), and there
  is still no job that expires abandoned `PENDING` orders or returns their
  stock. Declined-card orders now accumulate as retryable `PENDING` rows
  indefinitely rather than dying as `CANCELED` — better for the shopper,
  but there is no cleanup path for either state.
- **Shippo label links rot.** `Shipment.label_url` has a code comment noting
  Shippo doesn't host labels forever and suggesting mirroring the PDF to
  Cloudinary — that mirroring isn't implemented; long-lived access to old
  labels isn't guaranteed.
- ~~**`purchase_label`'s re-quote path assumes one variant per candle.**~~
  **Fixed** (2026-08-31, follow-up pass) — see the new section below.

### Follow-up — audit findings closed (2026-08-31, same-day pass)

Closes four items from the initial audit of this diff — findings 2, 3, 4 and
6. Finding 5 (Stripe error handling) needed no further work. Finding 1 (the
broken CSS import) was *believed* fixed going into this pass and explicitly
out of scope for it, but re-verifying today shows it is not — see the
now-unstruck "Frontend build is still broken" item above and Verification
below. It was left alone here rather than fixed opportunistically, since it
wasn't one of the four findings this pass was asked to close and silently
folding it in would have hidden that the assumption was wrong.

- **Trailing newline.** `orders/views_stripe.py` was missing one at EOF —
  restored. Checked every other file this diff touches against its last
  committed (`HEAD`) version first: all of them (`orders/serializers.py`,
  `orders/views.py`, `Checkout.tsx`, `Delivery.tsx`, `CatalogDetail.css`)
  already had no trailing newline *before* this working tree's edits — that's
  this repo's existing convention for those files, not something this diff
  broke. Left them as they were rather than impose a convention the repo
  doesn't otherwise follow.
- **Undeclared Shippo settings.** `SHIPPO_CARRIERS` and
  `SHIPPO_MAX_RATES_PER_CARRIER` are now declared in the Shippo section of
  `config/settings.py` instead of existing only as `getattr` defaults inside
  `shipping/services.py`. Behaviour is unchanged — same defaults, same
  `getattr` reads — this only makes the knobs visible to anyone reading the
  settings file. `SHIPPO_MAX_RATES_PER_CARRIER` added to `.env.example`;
  `SHIPPO_CARRIERS` isn't `.env`-backed so has no line there.
- **Unrelated `CatalogDetail.css` changes** given their own heading above,
  separate from the shipping work — see "Product page — sticky panel and
  page height."
- **`OrderItem` now records which variant was ordered.** Added
  `OrderItem.variant` (nullable `FK` to `CandleVariant`, `on_delete=PROTECT`
  to match the existing `candle` FK — a variant that appears in an order must
  not vanish; nullable because historic rows have no way to know).
  `build_order()` sets it when creating each item.
  `purchase_label()`'s re-quote path (used when no rate survived checkout)
  now prefers `item.variant` and only falls back to `item.candle.variants.first()`
  for historic rows, raising `ShippoError` if a row has neither.
  *Why it mattered:* weight and dimensions live on the variant; before this,
  the re-quote path guessed at "whichever variant sorts first," which is
  silently wrong the day any candle gets a second size again — the shop would
  quietly underpay for postage on that order rather than erroring.
  - Migration `orders/0009_orderitem_variant` (schema, auto-generated) adds
    the column. Migration `orders/0010_backfill_orderitem_variant` (hand-written
    data migration) backfills existing rows with `CandleVariant.objects.filter(candle_id=...).order_by("id").first()` —
    deterministic rather than relying on the database's incidental row order —
    and is a no-op in reverse (clearing `variant` back to null loses no
    information the forward pass didn't derive from `candle` in the first
    place). Confirmed before writing it that the backfill has one unambiguous
    answer for every row today: zero candles in this database currently have
    more than one variant (`Candle.objects.annotate(n=Count('variants')).filter(n__gt=1).count()` → `0`).
  - New test `shipping/tests.py::test_relabel_uses_the_recorded_variant`:
    builds a candle with a heavy and a light variant, records the light one
    on the `OrderItem`, and asserts the re-quoted parcel reflects the light
    variant's weight — a test that would have failed under the old
    `.first()` code if `.first()` had picked the heavy one.

### Verification (original audit pass, `2026-08-31`)

```
$ python manage.py check
System check identified no issues (0 silenced).

$ python manage.py makemigrations --check --dry-run
No changes detected

$ pytest -q
....sssssssssssssssss.......sssssssss............................sssssss [ 52%]
......sssss....................s.................................       [100%]
98 passed, 39 skipped, 42 warnings in 1.22s
```

The 39 skips are pre-existing and unrelated to this change — SQLite (the test
DB) doesn't support `select_for_update()`, which `cart`, `orders`, and the
Postgres-only Stripe test all rely on. All 11 tests in the new
`shipping/tests.py` ran and passed; none were skipped.

```
$ npx tsc --noEmit
(no output — passes clean)

$ npx vite build --mode production      # not in the requested checklist,
                                         # run to confirm the tsc pass above
                                         # wasn't masking a real problem
✗ Build failed in 78ms
[UNRESOLVED_IMPORT] Could not resolve '../styles/Checkout/ShippingRates.css'
in src/components/Shippingrates.tsx
```

No migrations were generated by this pass — `makemigrations --check`
reported nothing missing, so the exception in the task brief didn't apply.

### Verification (follow-up pass, same day)

```
$ python manage.py makemigrations orders
Migrations for 'orders':
  orders/migrations/0009_orderitem_variant.py
    + Add field variant to orderitem

$ python manage.py migrate
Applying orders.0009_orderitem_variant... OK
Applying orders.0010_backfill_orderitem_variant... OK

$ python manage.py check
System check identified no issues (0 silenced).

$ python manage.py makemigrations orders --check --dry-run
No changes detected in app 'orders'

$ pytest -q
....sssssssssssssssss.......sssssssss............................sssssss [ 52%]
......sssss....................s..................................      [100%]
99 passed, 39 skipped, 42 warnings in 1.25s
```

99 passed (98 before + the new `test_relabel_uses_the_recorded_variant`), same
39 pre-existing skips as before. Confirmed the backfill actually ran: `5/5`
existing `OrderItem` rows now have `variant` set. Also confirmed the new test
is not a tautology — reverted `shipping/services.py` to the pre-fix
`.first()` code with `git stash`, reran just that test, watched it fail
(`AssertionError: assert Decimal('22.50') < Decimal('10')` — it had picked
the 20oz variant, not the 4oz one), then `git stash pop` to restore the fix
and reran the full suite green again.

```
$ npx tsc --noEmit
(no output — passes clean)

$ npx vite build --mode production
✗ Build failed in 81ms
[UNRESOLVED_IMPORT] Could not resolve '../styles/Checkout/ShippingRates.css'
in src/components/Shippingrates.tsx
```

Unchanged from the original pass — finding 1 was not part of this pass's
scope and remains broken. See "Frontend build is still broken" above.
