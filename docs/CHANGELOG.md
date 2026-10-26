# Changelog

Newest first. Entries from 2026-10-02 on correspond to commits in this
repository; the git history starts with the "first commit" of that day, so
earlier entries have no commit to point to.

## 2026-10-26 — Repository housekeeping

- Local Claude Code settings (`.claude/settings.json`, `.claude/RESUME.md`)
  are no longer tracked (`3c83191`).
- Removed files that didn't belong in git: `.DS_Store`,
  `backend/candles_data.json` and `backend/lumiere_error.html` (`202f506`).

## 2026-10-23 — Lint, and the overlay fixes merged

- The frontend lints clean: nine ESLint errors fixed in `Catalog.tsx`,
  `LumiereWidget.tsx`, `ThemeProvider.tsx` and `utils/token.ts` (`556cc48`).
  The README's ESLint row is back (`c62fda5`).
- Merged the 2026-10-14 overlay work (PR #2, `4c64639`): see "Free-candle
  modal price, and overlays above the header" below.

## 2026-10-22 — README, licence, Lumière and scent tags

- **README** rewritten for the whole project (`f06c1ff`), then corrected
  where it described things the code doesn't support (`1c36d19`).
- **MIT licence** added (`263ca1d`).
- **Runs from a clean clone:** test dependencies in `requirements.txt` and
  complete `.env.example` files for backend and frontend (`2b35fce`). The
  test settings no longer need a `.env` at all (`7441a5c`).
- **Lumière** quotes prices from the function checkout charges with,
  priced for a guest — campaigns apply, the welcome discount doesn't — as the
  catalogue shows a signed-out shopper (`54177a4`). Each candle can carry notes only Lumière sees, edited in the
  admin (migration `candles/0030`, `7148572`).
- **Scent tags:** a reviewed draft of tags and notes per scent
  (`docs/CANDLE_TAGS_DRAFT.md`) and a `load_candle_tags` command that
  dry-runs unless told otherwise (`13fbc73`). The product page shows tag
  labels in the shopper's language (`0277ebd`), and reads every labelled line
  of a description: descriptions saved from the admin end their lines with
  `\r\n`, which the parser didn't split on (`d50f2aa`).

## 2026-10-14 — Payments, offers, error statuses and the cart

Merged as PR #1 (`1a54e48`) and PR #2 (`4c64639`).

**Payments**
- **First matching payment wins** (`1791f05`). A payment on an intent the
  order had replaced is accepted when it's for this order and the amount and
  currency match: the order switches to the paid intent, becomes PAID, and
  the other intent is cancelled. A mismatch is still refunded and reported;
  a payment on the other intent afterwards is refunded as one the order
  can't count.

**Offers**
- The home banner's "Shop the offer" pointed at `/offers/halloween`, which
  isn't a route; it now goes to `/offers/holidays` (`4a4fae3`).
- Offer links in the offer modal and the cart hint come from a new
  `offer_path`, worked out from the offer's kind, instead of being built
  from the slug. The slug is made from the offer's title in the admin and is
  rarely a route, so most offers linked to the home page (`1df9368`).
- The sign-up modal reads the welcome offer's percent and length from a new
  public `GET /api/orders/welcome-offer/`, chosen the way checkout chooses
  it, and stays shut when no welcome offer is running (`a958bff`). Its
  visibility is worked out on render rather than set from an effect
  (`dfad1a9`).
- Offer pages and the home banner checked against the admin and corrected
  (`1e69532`): Spooky Season is 10% on the Halloween collection plus five
  named candles (the banner said 5% off the entire collection; the holiday
  page said single-wick candles), and ends at 11:59pm Eastern on
  31 October. Both pages claimed "whichever offer gives the better price
  applies"; checkout doesn't compare, by design, and the pages now say what
  it does.

**Error statuses** (`ba9c6a2`)
- Order creation with a state or country the shop can't read, or an address
  Shippo says can't be delivered to, was a 500. It's now a 400 that says
  what to change. A non-numeric `order_id` to `create-intent` was a 500;
  it's a 400. A JSON body that isn't an object is a 400 for every endpoint.
  Another shopper's order was already a 404 everywhere.
- No shopper-facing message names code or setup: the unknown-country
  message no longer names `shipping.normalize.COUNTRIES`, and the rates
  endpoint keeps Shippo's failure reason in the log. A candle with no
  shipping weight is shop data, not the shopper's address: orders charge the
  flat rate and log an error, and quoting answers 503.

**Cart** (`7a74775`, `b6a1ca4`, `1766de9`)
- A change the server refuses no longer stays on screen: the cart reloads
  from the server and says why on the line. One candle is capped at 999
  everywhere, matching order creation. Cart requests run in order, so a slow
  answer can't show a stale cart. A guest tab picks up another tab's
  changes; a signed-in tab reloads the cart when it comes back into view.
  A candle that sold out after it went in the cart is marked on the cart
  page, and checkout says to remove it or lower the quantity.
- **Signing in keeps the guest cart.** The merge refused the whole guest
  cart when any line couldn't be taken, and the storefront then deleted it
  without a word. It now merges what it can and lists the rest; the cart and
  checkout pages say what changed (e.g. "Berry Grove / 8 OZ has sold out —
  we've taken it out of your cart."), and the notice survives a reload until
  dismissed. The merge also only ran on the next page load after signing in;
  it now runs at sign-in, and the guest copy is kept until merged.

**Free-candle modal price, and overlays above the header** (PR #2)
- Cards under "Add one of these and it's free" showed the welcome price; they
  now show the regular price struck through with "Free" (`bc105a3`).
- The header's links drew on top of four open overlays — the free-candle
  modal, the size picker, the product image zoom and the delete-account
  confirmation — because they rendered inside a stacking context below the
  header. They now render into `<body>` (`18e34bc`), and restate the styles
  they used to inherit from the page (`f276204`).

## 2026-10-08 — Postgres tests, shipping quotes, webhook and refunds

- **The test suite runs on Postgres**, the database production uses, and a
  payment set-up query that Postgres refused (but SQLite ignored) is fixed
  (`2224e96`).
- **Every order's shipping is quoted afresh** for its own candles and
  address; the rate the storefront sends only says which service the shopper
  picked. Rate quotes are capped and validated (`1c2a3b5`). This closes the
  rate-not-tied-to-the-order finding (AUDIT.md B3).
- **Webhook: never drop a payment** (`4783029`). The order is found by the id
  in the intent's metadata, whichever of its intents was paid. A payment on a
  replaced intent was acknowledged and dropped; it was then refunded and
  raised as a `PaymentIncident` (replaced by "first matching payment wins"
  on 2026-10-14). A payment for a different amount or currency than the
  order's total no longer marks it paid: it's refunded and reported, and the
  order stays payable. A payment for an order that doesn't exist is logged as
  an error.
- **Refunds come from Stripe; the shop records them** (`13373f3`).
  `charge.refunded` updates the order and records `refunded_amount`; a full
  refund moves it to REFUNDED, returning stock only if it hadn't shipped. The
  staff endpoint no longer marks orders refunded. The admin shows refunds,
  with a link to the payment in Stripe and a "Return items to stock" action.
  Reports count only paid orders, net of refunds. `charge.dispute.created` is
  logged as an error and emailed to support.
- **Welcome discount falls through** to lines a campaign gave nothing
  (`b7bf257`).
- One `.gitignore`, at the root (`922f710`).

## 2026-10-04 — One pricing engine, order lifecycle, payment incidents

- **Order lifecycle** (`bb622bb`): checkout reuses the open unpaid order
  when the basket and address haven't changed, instead of reserving the
  stock a second time; cancelling and expiring restore stock; an `expire_pending_orders` command cancels unpaid orders
  older than a cut-off (two hours by default, `--dry-run` available).
- **Payments on orders that won't ship** (`8fac651`): a payment on a
  CANCELED or REFUNDED order is refunded automatically and recorded as a
  `PaymentIncident` (migration `orders/0012`), shown in the admin and emailed
  to support. The webhook only moves PENDING → PAID. Automatic order emails
  are off: the confirmation email rendered with none of its variables
  filled (AUDIT.md S1), and confirmations are sent by hand. The support
  address has one source.
- **One pricing engine for every basket** (`c09cf60`): checkout, the
  catalogue (`8fb7ac1`), a new basket price preview (`811e285`), the size
  picker and the product page (`14b32e7`) all price through the same
  function, so the price shown is the price charged (AUDIT.md B1).
- **Buy two, get three** discounts whole units on the lines that hold them
  (migration `orders/0013`, `3d71f0d`); free units show at $0.00 with no
  separate discount row (`a934bff`). An offer can reward a different group of
  candles from the ones that qualify (migration `candles/0029`, `ff263cd`).
  Equal offer priorities are broken by id (`701d442`). The offer modal lists
  candles already in the basket (`49f12a9`), with a simpler footnote
  (`f764245`, 2026-10-05).

## 2026-10-02 — First commit, and the first fixes from the audits

- The repository's history starts here (`1e26145`).
- Fixed the header offset that put the first content of every inner page
  under the fixed header (AUDIT_FRONTEND.md B1), the logged-in cart doubling
  after a reload (AUDIT_FRONTEND.md S1), and the discount calculation,
  with per-line discount fields on order items (`f36ecb8`).

## 2026-09-29 — Audits

- Whole-repository audit (`docs/AUDIT.md`) and frontend audit
  (`docs/AUDIT_FRONTEND.md`). The findings they list are dated to that day;
  later entries above say which have been fixed.
- By this date the broken frontend build recorded on 2026-08-31 had been
  fixed: the component is `components/ShippingRates.tsx`, it imports
  `../styles/ShippingRates.css`, and that file exists. `vite build` passed
  (AUDIT.md, "Where `docs/CHANGELOG.md` disagrees with the code").

## 2026-08-31 — Live shipping rates via Shippo

Replaces the flat $15 shipping fee with real carrier quotes, and fixes a
Stripe error-handling bug found along the way.

The `shipping` app, the `candles` weight/dimension fields (migration
`0028`) and `orders.shipping_phone` (migration `0008`) were committed before
the rest of this work; they're described here for context. The rest of this
entry is order creation, Stripe intent handling and the checkout UI.

### Backend — shipping (new app)

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

### Backend — candles

- `CandleVariant` gained `weight_oz`, `length_in`, `width_in`, `height_in`
  (migration `candles/0028`). Needed to build a Shippo parcel; previously
  nothing about physical size was tracked at all.

### Backend — orders

- `Order.shipping_phone` (migration `orders/0008`) is now
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

### Backend — Stripe

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

### Frontend

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

Two small fixes in `frontend/src/styles/CatalogDetail.css` made at the same
time as the shipping changes — not part of the Shippo integration, called
out on their own so this entry doesn't imply otherwise. The buy panel's
`position: sticky` offset was a flat `32px`, which put it underneath the
fixed site header as the page scrolled; it now clears the header with
`calc(var(--header-height) + 24px)`. And the page no longer forces
`min-height: 100vh`/`100dvh`, which was leaving a band of empty page below
short product listings — height now comes from content. Both are
intentional and correct; likely a leftover from the earlier "sticky buy
panel" product-page work (commit `0149976`, before this repository's
history) that never got committed at the time.

### Configuration

New Shippo-related settings, all read via `django-environ`/`decouple`-style
`config()` in `config/settings.py`:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SHIPPO_TOKEN` | **Yes**, to get live rates | `""` | API key. Empty → every quote falls back to the flat rate (`ShippoNotConfigured`), so the site still works with none set. |
| `SHIPPING_FALLBACK_RATE` | No | `15.00` | The old flat fee, now only used when Shippo is unreachable/unconfigured or returns no rates. |
| `SHIP_FROM_STREET1`, `SHIP_FROM_CITY`, `SHIP_FROM_STATE`, `SHIP_FROM_ZIP` | **Yes**, for real quotes | `""` | Origin address for every rate/label. Set in the local `.env` (Brooklyn, NY) at the time but blank in `.env.example` — must be filled in per deployment. |
| `SHIP_FROM_NAME` | No | `"KFursenko Candles"` | Origin name on the label. |
| `SHIP_FROM_COMPANY`, `SHIP_FROM_STREET2`, `SHIP_FROM_PHONE` | No | `""` | Optional origin address fields. |
| `SHIP_FROM_COUNTRY` | No | `"US"` | Origin country. |
| `SHIP_FROM_EMAIL` | No | `DEFAULT_FROM_EMAIL` | Origin email on the label. |
| `SHIPPO_FALLBACK_PHONE` | No, but see gap below | `""` | Used as the `address_to` phone when an order/checkout has none. Shippo transactions want a phone; without this *and* a shopper-entered one, label purchase can fail. |
| `SHIPPO_API_BASE` | No | `https://api.goshippo.com` | Override for testing against a different host. |
| `SHIPPO_API_VERSION` | No | `2018-02-08` | Shippo API version header. |
| `SHIPPO_TIMEOUT_SECONDS` | No | `30` | Per-request timeout. |
| `SHIPPO_LABEL_FILE_TYPE` | No | `PDF` | Label format requested from Shippo. |
| `SHIPPO_MAX_RATES_PER_CARRIER` | No | `2` | Rates kept per carrier after quoting, cheapest first. Added to `.env.example` in the same-day follow-up (see below); previously only had a default buried in `shipping/services.py`. |
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
   on it being correct. The local `.env` carried a `shippo_test_...` token
   at the time.
4. *(Resolved by 2026-09-29.)* The frontend didn't build:
   `Shippingrates.tsx` imported `../styles/Checkout/ShippingRates.css`,
   which didn't exist, and `npx vite build` failed with `UNRESOLVED_IMPORT`
   (see Known gaps and Verification below). Fixed by 2026-09-29: the
   component is `components/ShippingRates.tsx`, it imports
   `../styles/ShippingRates.css`, and the build passes (re-checked
   2026-10-26).
5. No data backfill needed for shipping weight: existing `CandleVariant` rows
   got sane defaults from migration `0028` (8 oz, 3×3×4 in), so quoting works
   for old catalog data without an admin pass, but those defaults are
   guesses — see Known Gaps.
6. Run migrations `orders/0009_orderitem_variant` and
   `orders/0010_backfill_orderitem_variant` (added in the same-day
   follow-up, see below) — the second is a data migration that backfills
   `OrderItem.variant` on existing rows and runs automatically as part of
   `migrate`, no manual step beyond that.

### Known gaps

As recorded on 2026-08-31; later status noted where it changed.

- ~~**Frontend build is broken.**~~ **Fixed by 2026-09-29.**
  `Shippingrates.tsx` imported `../styles/Checkout/ShippingRates.css`,
  which did not exist (the real file was `frontend/src/styles/Shippingrates.css`,
  no `Checkout/` subdirectory, different case), and `npx vite build` failed
  with `UNRESOLVED_IMPORT` — see Verification below for that day's output.
  The same-day follow-up assumed it was already fixed and left it alone;
  re-checking that day showed it wasn't. It was fixed before the 2026-09-29
  audit (see that entry). The lesson stands: `npx tsc --noEmit` doesn't catch
  a missing CSS import, because TypeScript resolves CSS imports against a
  wildcard ambient module declaration and never checks the file exists.
  Only `vite build` does.
- **Default variant weight/dimensions are guesses, not measurements.** The
  `0028` migration defaults every existing `CandleVariant` to 8 oz / 3×3×4 in
  regardless of actual size. Nothing flags which rows still carry the default
  vs. a real measurement — every rate quoted against un-updated stock is
  quoted against a made-up weight. Worth an admin pass (or a "needs
  measurement" flag) before this is trusted for real charges.
- **No carrier allow-list is active.** `SHIPPO_CARRIERS` and
  `SHIPPO_MAX_RATES_PER_CARRIER` are now declared explicitly in
  `config/settings.py` (same-day follow-up — previously referenced only via
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
- ~~**No stock is ever restored.**~~ **Fixed 2026-10-04** (`bb622bb`:
  cancelling and expiring restore stock, and `expire_pending_orders` cancels
  abandoned unpaid orders). As recorded: this predated the change (the
  flat-rate code never restocked either), but became more visible: stock was
  decremented at order creation, `payment_intent.payment_failed` no longer
  cancelled the order (see above — a deliberate, correct fix), and no job
  expired abandoned `PENDING` orders or returned their stock. Declined-card
  orders accumulated as retryable `PENDING` rows indefinitely rather than
  dying as `CANCELED` — better for the shopper, but with no cleanup path for
  either state.
- **Shippo label links rot.** `Shipment.label_url` has a code comment noting
  Shippo doesn't host labels forever and suggesting mirroring the PDF to
  Cloudinary — that mirroring isn't implemented; long-lived access to old
  labels isn't guaranteed.
- ~~**`purchase_label`'s re-quote path assumes one variant per candle.**~~
  **Fixed** (2026-08-31, same-day follow-up) — see the next section.

### Follow-up fixes (2026-08-31, same day)

Closes findings 2, 3, 4 and 6 from that day's review of this change.
Finding 5 (Stripe error handling) needed no further work. Finding 1, the
broken CSS import, was assumed fixed and left alone; re-checking showed it
wasn't (see Known gaps), and it stayed open until it was fixed before
2026-09-29.

- **Trailing newline.** `orders/views_stripe.py` was missing one at EOF —
  restored. Checked every other file this change touches against its last
  committed (`HEAD`) version first: all of them (`orders/serializers.py`,
  `orders/views.py`, `Checkout.tsx`, `Delivery.tsx`, `CatalogDetail.css`)
  already had no trailing newline *before* these edits — that's the repo's
  existing convention for those files, not something this change broke.
  Left them as they were rather than impose a convention the repo doesn't
  otherwise follow.
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
    answer for every row at the time: zero candles in the database then had
    more than one variant (`Candle.objects.annotate(n=Count('variants')).filter(n__gt=1).count()` → `0`).
  - New test `shipping/tests.py::test_relabel_uses_the_recorded_variant`:
    builds a candle with a heavy and a light variant, records the light one
    on the `OrderItem`, and asserts the re-quoted parcel reflects the light
    variant's weight — a test that would have failed under the old
    `.first()` code if `.first()` had picked the heavy one.

### Verification (2026-08-31, before the follow-up fixes)

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

The 39 skips were pre-existing and unrelated to this change — they were
skipped on the grounds that SQLite (the test DB then) doesn't support
`select_for_update()`, which `cart`, `orders`, and the Postgres-only Stripe
test all rely on. (AUDIT.md W1 later showed that reason was wrong; the suite
has run on Postgres since 2026-10-08.) All 11 tests in the new
`shipping/tests.py` ran and passed; none were skipped.

```
$ npx tsc --noEmit
(no output — passes clean)

$ npx vite build --mode production      # run to confirm the tsc pass above
                                         # wasn't masking a real problem
✗ Build failed in 78ms
[UNRESOLVED_IMPORT] Could not resolve '../styles/Checkout/ShippingRates.css'
in src/components/Shippingrates.tsx
```

No migrations were needed: `makemigrations --check` reported nothing
missing.

### Verification (2026-08-31, after the follow-up fixes)

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

Still failing that day: finding 1 was left open (see Known gaps). Fixed by
2026-09-29; `vite build` passes as of 2026-10-26.
