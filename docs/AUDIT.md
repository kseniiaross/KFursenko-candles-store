# Audit — KFursenko Candles Store

**Date:** 2026-09-29
**Scope:** whole repository, working tree as of today (committed `main` at `5b91a43` plus the uncommitted and untracked changes listed below).
**Method:** read the code, ran the build and test commands, and ran small read-only experiments where a claim could be checked directly. No source file was changed. The only file written in the repo is this one.
**Limits:** I couldn't see Railway's or Vercel's environment variables, the production database, or the Stripe and Shippo dashboards. The local database has one test category and no offers, so category and collection slugs and the real offer rows couldn't be checked. Where a finding depends on production configuration, it says so.

---

## Repository state

| | |
|---|---|
| Branch | `main`, up to date with `candles/main` |
| Modified (unstaged) | `backend/orders/discounts.py`, `backend/orders/urls.py`, `backend/orders/views_stripe.py`, `frontend/src/App.tsx`, `frontend/src/pages/Catalog.tsx`, `frontend/src/pages/Header.tsx`, `frontend/src/styles/Catalog.css` |
| Deleted | `frontend/src/pages/PromoBuy2Get3.tsx` (moved to `pages/offers/`) |
| Untracked | `backend/orders/views_offers.py`, `frontend/src/components/{CartOfferHint,OfferModal,Price}.tsx`, `frontend/src/pages/offers/{PromoBuy2Get3,HolidayOffer,NewShoppers}.tsx`, `frontend/src/styles/{CartOfferHint,OfferModal,Price}.css`, `frontend/src/styles/offers/*.css`, `.claude/settings.json` |
| Staged | nothing |

### Where `docs/CHANGELOG.md` disagrees with the code

When they disagree, the code wins. The changelog's 2026-08-31 entry is wrong or out of date in these places:

1. **"Frontend build is still broken … `Shippingrates.tsx` imports `../styles/Checkout/ShippingRates.css`."** Fixed in the committed code. The file is `components/ShippingRates.tsx` (that exact case in git and on disk), it imports `../styles/ShippingRates.css`, and that file exists. `vite build` passes for both HEAD and the working tree.
2. **"The stock check was moved earlier … quoting first would mean holding that lock for the 2–3 seconds a live carrier call can take."** The lock is still held during the carrier call. `build_order` is `@transaction.atomic` (`orders/serializers.py:154`), takes `select_for_update()` at line 178 and calls Shippo at line 223. Row locks last until the transaction commits, so moving the check earlier changed nothing about locking. See W6.
3. **"The rate returned to the client is only an id — the server always re-reads the price from Shippo … so a tampered amount from the browser changes nothing."** True for the amount. But the server never checks that the rate id belongs to this order's address and parcel. See B3.
4. **"Only six files are actually modified in the working tree, plus two new untracked frontend files."** Out of date. The current set is listed in the table above.
5. The docstring at `orders/discounts.py:350` says *"build_order now uses compute_line_discounts"*. It doesn't. See B1.

---

## Command output (summary; full output is in the chat reply)

| Command | Result |
|---|---|
| `python manage.py check` | No issues |
| `python manage.py check --deploy` | 37 warnings with local `.env` (`DEBUG=True`). 31 are drf-spectacular schema warnings. The security ones are W004/W008/W012/W016/W018, which all follow from `DEBUG=True`, plus W009 (weak `SECRET_KEY`). With `DEBUG=False`, only **W009** and **W021** (HSTS preload) remain. |
| `makemigrations --check --dry-run` | No changes detected |
| `pytest -q` | 99 passed, **39 skipped**, 42 warnings. The skip reason is wrong (W1). |
| `npx tsc --noEmit` | Clean |
| `npx vite build` | **Passes** on the working tree (output sent to scratch, `frontend/dist` untouched). HEAD also passes from a clean `git archive`. |

### Import paths vs disk vs git (case-sensitive)

I checked every relative import in `frontend/src` against exact-case directory listings and against `git ls-files`. **No case mismatches.** No path in git differs from another only by case (`core.ignorecase=true` here, so this is worth re-running before each deploy).

There are **12 imports that resolve on disk but point at untracked files**. That's B2.

---

## BLOCKER

### B1. The price a shopper is shown is not the price they are charged. Campaign discounts and buy-two-get-three are never applied at checkout.

**Where:**
- The charge: `orders/serializers.py:10` imports `welcome_percent_for`, and lines 289–292 apply only that. `order.discount_label` (line 298) is only ever the welcome offer's title.
- The new engine: `orders/discounts.py:205` `compute_line_discounts()` handles B2G3, percentage campaigns and the welcome offer. **Nothing calls it** (repo-wide grep). Its own "backwards compatibility" helpers at `discounts.py:338–361` are the code that actually runs.
- The display: `candles/serializers.py:280–305` `get_discount_price()` applies the first active offer of *any* kind with a `discount_percent` or a `discounted_price`.
- The promises:
  - `pages/offers/PromoBuy2Get3.tsx:58`: "The lowest-priced of the three is free — the discount is applied automatically at checkout."
  - `components/OfferModal.tsx:237–242`: "One more and the third is free."
  - `pages/offers/HolidayOffer.tsx:18, 36`: "10% off … applied automatically at checkout."
  - `pages/offers/NewShoppers.tsx:58` and `HolidayOffer.tsx:51`: "whichever gives you the better price."

**What breaks:**
- **Any active `discount`, `holiday` or `loyalty` offer:** the product page shows the reduced price with the old one struck through, and Stripe charges the full price. `CatalogDetail.tsx:292` already shows `discount_price` in HEAD, so this is **live in production today** for any such offer. The uncommitted `Catalog.tsx` change adds the same struck-through price to every catalog card.
- **Buy two, get three:** the cart modal and the offer page promise a free candle. The order charges all three.
- **Fixed-price offers (`Offer.discounted_price`):** shown on the storefront, never charged anywhere.
- **New shopper buying a candle that carries any other offer:** `has_competing_offer` (`discounts.py:338`) counts every active offer, including B2G3 offers with no percentage. So a first-time customer buying one or two Spring (B2G3) candles gets **no discount at all**: no welcome 10%, and no free candle because they don't have three. The pages promise "whichever gives the better price".
- **Timing:** `HolidayOffer.tsx` advertises **1–31 October 2026**, which starts in two days. If that offer is switched on in the admin, every Halloween and single-wick candle will be displayed at 10% off and charged at full price.

**Fix:** have `build_order` call `compute_line_discounts` and store the per-line amounts. Make `get_discount_price` and the badges use the same resolution, so display and charge can't diverge. Settle "better of welcome vs campaign" in one place; neither implementation does it today. Add tests for the 2/3/4/6-candle baskets and for the new-shopper-plus-campaign case before switching. A day or two of work including tests. The engine exists; it's the wiring and the tests that are missing.

**About the engine itself** (it isn't live, but it's what you'll switch to):
- Grouping: sorted dearest first, and every third unit is free. For 2 candles, nothing. For 3 candles at 30/20/10, 10 is free. For 4 candles at 40/30/20/10, **20** is free (the cheapest of the three dearest, not the overall cheapest). For 6 candles at 60…10, 40 + 10 = 50 is free. That matches "lowest-priced of the three" and is the customer-friendly reading.
- Per-line split: the last line absorbs rounding, so per-line B2G3 discounts always add up to the saving exactly. Checked with 33.33×3 → 11.11×3, and 10.01/10.02/10.03 → 3.33 + 3.34 + 3.34 = 10.01.
- Percentages (campaign and welcome) are rounded **per line** in the new engine but **once per order** in today's `build_order`. Three lines at 10.05 with 10% off give 3.03 per line vs 3.02 per order. Pick one and use it in both display and charge.
- The storefront rounds with `quantize(Decimal("0.01"))` (banker's rounding) and checkout rounds `ROUND_HALF_UP`, so a shown price can be a cent off the charged one even once the logic agrees.

### B2. Committing only the tracked changes takes both production deploys down

**Where:** `backend/orders/urls.py:6` imports `views_offers`, which is untracked. `frontend/src/App.tsx:8, 40–42` and `pages/Catalog.tsx:14` import 12 untracked files.

**What breaks:** nothing yet, because HEAD builds and runs. But `git commit -a` (or committing from an editor's "modified files" view) leaves the untracked files out. I reproduced it: a tree made of only git-tracked files plus their working-tree contents fails `vite build` with `UNRESOLVED_IMPORT: Could not resolve './components/OfferModal' in src/App.tsx` (and three more). On Railway the same commit makes `orders.urls` raise `ImportError`, and the whole API returns 500.

**Fix:** stage the new files explicitly, and run a clean-checkout build before pushing. For example, `git stash -u && npx vite build`, or a CI job on push. A few minutes.

### B3. The shipping rate is not tied to the order's address or parcel. The charge and the label can both be for somewhere else.

**Where:** `shipping/services.py:137–139` (`verify_rate` re-reads only the price for an id). `orders/serializers.py:252–262` stores that `rate_id` on the `Shipment`. `services.py:172, 194–201` later buys the label from that same `rate_id`. `components/ShippingRates.tsx:120–175` keeps the previous selection while a new quote is debouncing (600 ms) and loading.

**What breaks:** a Shippo rate belongs to a Shippo shipment, which carries its own `address_to` and parcel.
- **Honest mistake:** a shopper fixes their ZIP or street and clicks "continue to payment" before the new quote comes back. The order stores the new address, but the charge uses the old rate. When staff buy the label, Shippo prints it **for the old address**, because the label comes from the rate's shipment, not from `Order.shipping_*`.
- **Deliberate:** anyone can quote one light candle to a nearby ZIP and submit that `rate_id` with a heavy order to Alaska. The server charges and buys the cheap rate for the wrong parcel.

**Fix:** at order creation, fetch the rate's shipment and compare its `address_to` and parcel against what the server builds from the order, or simply re-quote server-side and match on carrier and service level. Clear the selection in `ShippingRates` whenever the address or items change. Half a day.

---

## SERIOUS

### S1. The order confirmation email goes out with no order number, total, address or link

**Where:** `orders/emails.py:14–20` passes `order`, `user`, `items`, `frontend_url` and `support_email`. `templates/emails/orders/order_confirmation.txt` uses `order_number`, `first_name`, `order_total`, `shipping_name`, `shipping_address` and `order_url`, none of which are passed. There's no `.html` template, so the `try` at line 24 always falls back to text only.

**What breaks:** every paying customer gets "Order #", "Order total: ", "Shipping to: , ", a blank link and "Hi there". I rendered it with the exact context the code passes to confirm. The email also promises "We'll email you again when your order ships"; no shipping email exists. `shipping_confirmation.txt`, `delivered.txt`, `refund_initiated.txt` and `order_canceled.txt` are all unused.

**Fix:** pass the variables the template expects, or change the template to use `order.id` and friends. An hour. A shipping email on label purchase is a separate half day.

### S2. Every "continue to payment" click creates a new order. Stock goes down each time, never comes back, and the welcome discount is lost on the retry.

**Where:** `pages/Checkout.tsx:333–365` posts `/orders/` on every click. Stock is decremented at `orders/serializers.py:273`, the only stock write in the codebase; nothing ever increments it. `orders/discounts.py:123–127` disqualifies the welcome offer if **any** non-cancelled order exists, including PENDING. Failed payments now stay PENDING by design (`views_stripe.py:265–274`).

**What breaks:**
- **First-time shopper:** clicks, spots a typo, edits, clicks again. Order #2 has no 10% because order #1 is PENDING. The page they just read promised it.
- **Stock:** each click removes the items from stock permanently. Abandoned, declined, cancelled (staff can only cancel PENDING orders) and refunded orders never return stock. There's no expiry job.
- **Abuse:** any logged-in account can reserve up to 999 of every variant per order, at 10 orders a minute (`THROTTLE_ORDERS_CREATE`). That would show the whole catalog as out of stock with no payment.

**Fix:** reuse the open PENDING order for the same cart instead of creating a new one. Exclude unpaid orders from the welcome check. Restore stock on cancel and on expiry, with a periodic job that cancels PENDING orders older than N hours. One to two days.

### S3. A payment on a replaced PaymentIntent is taken but never recorded

**Where:** `views_stripe.py:147, 163–172` creates a new intent, and **overwrites** `order.stripe_payment_intent_id`, whenever the old one can't be retrieved (any `StripeError`, including a network blip) or is in a non-reusable state such as `processing`. The webhook matches on the current id only (`views_stripe.py:245`), and returns 200 whether or not an order matched.

**What breaks:** a shopper has the payment form open (old client secret). Something re-requests the intent: a second tab, a retry, a refresh. A transient Stripe error then produces a new intent. The shopper pays with the old one. Stripe charges them, the webhook finds no order, the order stays PENDING, no email goes out, and it's acknowledged with 200 so Stripe never retries. If both intents get paid, the shopper is charged twice.

The webhook also never compares `amount_received` and `currency` with `order.total_amount`. Today order totals never change after creation, so they can't drift, but nothing checks it.

**Fix:** keep a list of every intent id per order, or look orders up by `metadata.order_id` and verify the intent id against that history. Cancel the superseded intent when replacing it. Log loudly when a `succeeded` event matches no order. Half a day.

### S4. Refunds and cancellations are promised, but no code performs them, and the order status can't express them

**Where:** `pages/CustomerCare/Policy.tsx:25` (24-hour cancellation with full refund) and `:85`, `Payments.tsx:84–86` (refund to the original payment method), `PromoBuy2Get3.tsx` "Returns" term. `Order.ALLOWED_TRANSITIONS` (`orders/models.py:92–99`) doesn't allow `PAID → CANCELED`. There's no `stripe.Refund` call anywhere, and the webhook ignores `charge.refunded` and disputes.

**What breaks:** staff honouring the 24-hour cancellation have to refund in the Stripe dashboard by hand. The order either stays `PAID` or gets manually set to `REFUNDED`, which moves no money. Stock isn't restored, and the customer gets no email. The Stripe records and the order records drift apart.

**Fix:** a staff refund action that calls Stripe, sets `REFUNDED`, restores stock and sends `refund_initiated`. Handle `charge.refunded` in the webhook so dashboard refunds sync too. Allow `PAID → CANCELED` with a refund. One to two days.

### S5. Labels bought from production are test labels, so the tracking numbers shown to customers are fake

**Where:** Shippo is on a `shippo_test_` token (per the brief, and the local `.env` too). `shipping/services.py:216–224` stores the transaction's `tracking_number` and `tracking_url`. `OrderReadSerializer` exposes them to the customer (`orders/serializers.py:97–103`). `Delivery.tsx:84` promises "Your tracking number appears in your order details as soon as the label is printed."

**What breaks:** if staff use `POST /api/shipping/orders/<id>/label/`, the order moves to `SHIPPED` with a test label that no carrier will accept, and the customer sees a test tracking number. If staff instead buy labels elsewhere, the promise on the Delivery page is never met, because nothing records the real tracking number. `Shipment.is_test` is recorded but not shown anywhere a person would notice.

**Fix:** switch to a live token, and until then block label purchase when `client.is_test` and `DEBUG` is off. Alternatively, add an admin field for entering tracking by hand. An hour, plus the Shippo account work.

### S6. Order creation returns a 500 for an unsupported country or an unrecognised US state

**Where:** `orders/serializers.py:224` calls `payload_to_address()` **outside** the fallback in `resolve_shipping_cost`. `AddressError` is a `ValueError` (`shipping/normalize.py:45`), not a `ShippoError`, so `services.py:144` doesn't catch it either when `quote_rates` raises it (Shippo says undeliverable, or a variant has no weight). DRF turns an uncaught `ValueError` into a 500.

**What breaks:** the checkout country list (`Checkout.tsx:48–`) offers Canada, the UK, France, Germany, Italy and more. Anything missing from `normalize.COUNTRIES`, or a free-text state such as "N.Y." or "Calif", gives the shopper a generic error with no reason and no order. The rates endpoint turns the same error into a 400 with a message; only order creation doesn't.

**Fix:** catch `AddressError` in `build_order` and raise a `ValidationError({"shipping": …})`. An hour.

### S7. The shipping fallback overcharges quietly, and nobody is told

**Where:** `shipping/services.py:129–146`.

**Is it the only silent fallback?** In the shipping path, yes, it's the only one that changes money. Other silent fallbacks elsewhere: a new PaymentIntent when retrieval fails (S3), email falling back to the console backend in production (S10), a confirmation email failure (logged only), `SHIPPO_FALLBACK_PHONE`, and `item.candle.variants.first()` in `purchase_label`.

**When it triggers:** Shippo unreachable or timing out (30 s × up to 3 attempts, all while holding stock row locks; see W6), no token, no rates, **or the chosen `rate_id` has expired or is invalid** (`verify_rate` gets a 404 and a `ShippoError` follows). The last case is ordinary: a shopper leaves checkout open and comes back.

**What the shopper sees:** they picked "$8.40 USPS Ground". After they click, the summary swaps to $15.00 (`Checkout.tsx:305–310`). There's no explanation beyond the code comment, and the Delivery page promises "No markup. You pay the carrier rate we pay."

**What the owner sees:** one `WARNING` log line. No `Shipment` row, no flag on the order, nothing in the admin. At label time the order is re-quoted at the cheapest rate, so the shop keeps the difference, or loses it on a heavy parcel.

**Fix:** on an expired `rate_id`, re-quote and match the same carrier and service level before falling back. Mark fallback orders (`shipping_is_estimate=True` or similar) and show them in the admin. Half a day.

### S8. Five missing translation keys show as raw text on every product page

**Where:** `pages/CatalogDetail.tsx:253–256` (`catalogDetail.mood`, `.bestFor`, `.season`, `.details`) and `:386` (`catalogDetail.scent`). All five are missing in all four languages in `src/i18n.ts`, and none passes a default value.

**What breaks:** product pages show labels like "catalogDetail.scent". I checked all 186 static `t()` calls. These are the only misses, and all four languages have the same 368 keys.

**Fix:** add the keys. Fifteen minutes.

### S9. Customer-facing pages contradict each other and the backend

- **Damage claims:** `Delivery.tsx:108` says "within 7 days"; `Policy.tsx:53` says "within 48 hours". One of them is wrong, and that matters in a dispute.
- **"We ship within the United States only"** (`Delivery.tsx:78`): the checkout offers eight or more other countries, and the backend quotes and charges them.
- **"We ship … with USPS and UPS"** (`Delivery.tsx:43`): `SHIPPO_CARRIERS = []` (`config/settings.py`), so every carrier on the Shippo account is offered.
- **"No markup"** (`Delivery.tsx:25`): not true when the $15 fallback applies (S7).
- **Buy-two-get-three badge:** `candles/models.py:203` sets the default badge to **"Buy 1 get 2"** for the `b2g3` kind. That promises a different offer to anyone who leaves the badge blank in the admin.
- **"Change password"** on the Profile page (`Profile.tsx:734`) links to `/account/change-password`. That route doesn't exist, so the catch-all quietly redirects to the homepage. There's no password-change or reset flow at all (`password_reset.txt` is unused).
- **"see what is running now"** (`NewShoppers.tsx:113`) links to `/offers`, a "Coming soon" placeholder. The uncommitted Header change removed that link for this reason.

**Fix:** mostly copy, plus `SHIPPO_CARRIERS = ["usps", "ups"]`, restricting the checkout country list (or supporting it), and the badge default. A couple of hours. The password flow is its own piece of work.

### S10. Security: settings that are fine only if production is configured correctly

- **`SECRET_KEY` default** (`config/settings.py:18–21`) is a literal `django-insecure-…` string, and **the GitHub repository is public** (the API returns 200 without authentication). The key also signs JWTs (`SIMPLE_JWT["SIGNING_KEY"]`). If `SECRET_KEY` is ever unset on Railway, anyone can mint an access token for any user id, staff included. I can't see whether Railway sets it. `check --deploy` reports W009 for the **local** key, so at minimum the local one is weak. **Fix:** remove the default so a missing key fails loudly at startup, rotate the key, and confirm Railway's value. Fifteen minutes.
- **Local `.env` uses live Stripe keys (`pk_live…`, `sk_live…`) with `DEBUG=True`**, and `config/settings_test.py` inherits them via `from .settings import *`. Today no test reaches Stripe; the payment-intent view has no tests. Any local checkout, or any future test of that view without a mock, creates real PaymentIntents against real cards. **Fix:** use `sk_test_` keys locally, and in `settings_test.py` blank `STRIPE_SECRET_KEY` and set `SHIPPO_TOKEN=""`. Ten minutes.
- **Email silently disabled in production if SMTP credentials are missing** (`config/settings.py` Email section: `if not DEBUG and (not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD): EMAIL_BACKEND = console`). Emails get printed to the Railway log and nobody is told. Check Railway; consider failing at startup instead.

---

## WORTH FIXING

### W1. 39 tests are skipped for a reason that isn't true, and they include every money-path test

`orders/test_orders.py:10–16`, `cart/test_cart.py:6–13` and `orders/test_stripe.py:13` skip on the grounds that SQLite raises `NotSupportedError` for `select_for_update()`. I checked on the test database: `connection.features.has_select_for_update` is `False`, and a `select_for_update()` query inside `atomic()` runs without error. Django silently ignores it on SQLite. So order creation, cart mutation and webhook handling aren't being tested, and they could be today. There are **no tests at all** for `discounts.py`, `views_offers.py` or `CreatePaymentIntentView`. `pytest` also runs from the system Python (`/Library/Frameworks/.../bin/pytest`), not `.venv`. Fix: remove the skips, see what fails, add tests for B1/B3/S2/S3. A day.

### W2. Duplicate field declarations are still there

- `orders/models.py:37–43` and `45–51`: `discount_amount` and `discount_label` declared twice.
- `candles/models.py:136–139`: `priority` and `is_active` twice. `:146–147`: `apply_globally` twice.

The copies are identical, so the last one wins and migrations are clean. Harmless now, but a future edit to the first copy will be silently ignored. Also note the mis-indented comment at `orders/models.py:37`. Five minutes.

### W3. Dead code, and code labelled as dead that's actually live

- `orders/discounts.py`: `compute_line_discounts`, `_apply_buy_two_get_three`, `_free_units`, `campaign_offer_for` (used by `views_offers` only) and `get_active_offers` aren't on the charge path. `buy_two_get_three_progress` (`:293`) has **no callers**; `views_offers.py` reimplements it.
- `has_competing_offer` / `welcome_percent_for` (`:335–361`), labelled "kept for backwards compatibility", are **the live checkout path**. Their docstrings say the opposite.
- `frontend/src/components/CartOfferHint.tsx` (new, untracked): nothing imports it. `OfferModal` does the same job.
- `settings.USE_STRIPE`: read nowhere. `stripe_intent_anon` throttle scope: used nowhere (the intent view requires login).
- `Offer.new_shopper_only`: editable in the admin (`candles/admin.py:125`), read by no code. Ticking it does nothing.

### W4. Comments that describe code that no longer exists

- `orders/serializers.py:190–193`: "would hold the select_for_update lock … for the two or three seconds". The lock is held anyway (W6).
- `orders/discounts.py:350–351`: "build_order now uses compute_line_discounts". It doesn't.
- `shipping/models.py:31–32`: "treat a stale one as a reason to re-quote". `purchase_label` (`services.py:172–174`) only re-quotes when `rate_id` is **empty**. A stored but expired rate fails the label purchase, marks it `FAILED`, and every retry re-sends the same dead rate. Depending on how long Shippo keeps rates valid (I haven't confirmed the window), orders paid some days before labelling may be un-labellable through the API.
- `views_stripe.py:149–152`: "The shopper can go back and pick a different shipping rate after the intent exists." Going back creates a new order (S2), so an order's total never changes after its intent exists.
- `candles/models.py:381–386`: shipping comments and `help_text` in Russian. The `help_text` shows in the admin; fine if intended.

### W5. Query counts grow with catalog size, including on an anonymous endpoint

`offer_applies_to` (`discounts.py:42–62`) runs up to five queries per (offer, candle) pair and ignores the prefetches callers set up. `CandleSerializer` calls `_applicable_offers` twice per candle (badges and discount price), and each call runs `get_welcome_offer` (two more queries). A catalog page of 40 candles with 5 offers is roughly 2,000 queries. `POST /api/orders/offer-progress/` is `AllowAny` and walks **the whole catalog** (`views_offers.py:142–171`) with the same per-candle queries, on every cart change. Fix: resolve offer membership once per request as id sets. Half a day.

### W6. Stock rows stay locked during the Shippo call

`build_order` locks the variant rows and then calls Shippo inside the same transaction. The timeout is 30 s and `create_shipment` retries twice, so a slow carrier API can hold locks on the popular candles for more than a minute. Every other checkout and cart update touching them blocks. Fix: quote before `atomic()`, then lock, re-check stock and write. An hour or two.

### W7. CORS allows every `*.vercel.app` site

`config/settings.py:66–68`. Auth is a bearer token in a header, so another site can't borrow a shopper's session. The practical risk is low, but it's broader than the project's own previews. Narrow it to `^https://kfursenko-[a-z0-9-]+\.vercel\.app$` or similar.

### W8. `.env.example` lists only the Shippo variables

`backend/.env.example` has no `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `STRIPE_*`, `EMAIL_*` or `CLOUDINARY_*`. A fresh deployment copies it and silently gets the defaults, including the public `SECRET_KEY` (S10).

### W9. The order admin can bypass the status rules and edit money fields

`orders/admin.py:33` makes only `total_amount`, the intent id and timestamps read-only. `status`, `subtotal_amount`, `discount_amount` and `shipping_amount` are editable, so a staff member can set any status, skipping `ALLOWED_TRANSITIONS`, and leave the amounts inconsistent with the total.

### W10. Two stock numbers and a manual sold-out flag

`Candle.stock_qty` and `CandleVariant.stock_qty` both exist. Only the variant one is checked and decremented. `Candle.is_sold_out` is a manual checkbox that doesn't follow the variant stock, so a candle can show as available, fail at "Add to cart" with "Only 0 left", and still appear in the offer-progress suggestions.

### W11. Offer pages hard-code what the admin controls

`HolidayOffer.tsx` hard-codes "10%" and "1–31 October 2026". `PromoBuy2Get3.tsx:24` filters on the badge slug `"buy-2-get-3"`, which is derived from the offer's *title* in the admin. `HolidayOffer.tsx:67` links to `/catalog/collection/halloween`, and there's no local data to confirm that slug. Renaming the offer or changing its percentage in the admin silently breaks the page. Read these from the offer API instead.

### W12. `.local/` isn't gitignored

The brief says it is; `git check-ignore .local/x` says otherwise. I used the session scratch directory instead and wrote nothing under `.local/`.

---

## NOTED (deliberate gaps and approximations)

- **Variant weights and dimensions are defaults** (8 oz, 3×3×4 in, migration `candles/0028`), so live quotes are only as good as those numbers. I couldn't check production data.
- **`build_parcels` is naive packing** with two hard-coded boxes (`SHIPPO_BOXES`). It says so in its own docstring.
- **Shippo label URLs expire.** Mirroring to Cloudinary isn't implemented (`shipping/models.py:46–48`).
- **HSTS** is 3600 s by default with preload off (W021). Reasonable while the domain setup is settling.
- **31 drf-spectacular warnings** in `check --deploy` affect only the generated API schema, not behaviour.
- **One welcome discount per email, not per person.** `NewShoppers.tsx:66` says additional accounts don't qualify; nothing enforces that beyond the unique email.
- **Offer times are in UTC** (`TIME_ZONE="UTC"`). "11:59pm on 31 October" entered as 23:59 in the admin ends at 7:59pm New York time.
- **"Made to order, 3–5 business days"** sits alongside a finite `stock_qty` that blocks ordering at zero. Fine if stock means "materials on hand", but the two ideas should be reconciled in the copy.
- **Guests can't check out** (`Checkout.tsx` redirects to login), so "Ordering as a guest means paying full price" (`NewShoppers.tsx`) describes a path that doesn't exist.
- **Tax is always 0** (`tax_amount=0`, `stripe_tax_calculation_id` never set). Presumably deliberate for now; worth a decision before volume grows.

---

## Secrets check

- `backend/.env` and `frontend/.env` are ignored (`.gitignore:11`). `git log --all -- backend/.env frontend/.env .env` is empty; neither file has ever been committed. The only env-like file ever in history is `backend/.env.example`.
- I searched the working tree (tracked and untracked) and the full `git log -p` of every branch for `sk_live`, `pk_live`, `rk_live`, `shippo_live_`, `shippo_test_<hex>`, `whsec_`, `sk-`/`sk-proj-`, `cloudinary://…@` and 40+ character quoted literals. **No keys found.** The one history hit was `EMAIL_HOST_PASSWORD = config(...)`, a false positive. The only secret-like literal in source is the insecure `SECRET_KEY` default (S10).
- The local `.env` holds live Stripe keys and a test Shippo token (S10).

## Permissions check (every DRF view)

All correct for their purpose. Staff-only views (`StaffOrdersAPIView`, `OrderStatusUpdateAPIView`, `PurchaseLabelAPIView`) check `is_staff` explicitly. Order, cart and payment-intent views filter by `request.user`. Catalog viewsets use `IsStaffOrReadOnly`. `AllowAny` is used only where intended: register, newsletter subscribe, Lumière, offer progress. No view trusts a client-sent price, amount or percentage. The one client-sent value that isn't fully verified is the shipping `rate_id` (B3).

---

## Follow-up findings (2026-10-02)

Found while fixing the order lifecycle (order reuse, stock restoration, intent cancellation). Not fixed yet.

### F1. SERIOUS — the Stripe webhook marks any order PAID, whatever its status

**Status 2026-10-04: mostly fixed.** The webhook now moves only PENDING → PAID (through `Order.transition_to`) and ignores redeliveries on PAID, SHIPPED and COMPLETED. A payment on a CANCELED or REFUNDED order is refunded automatically and recorded as a `PaymentIncident`: it's shown in the admin and on the order, emailed to `SUPPORT_EMAIL` and logged at ERROR. **Still open:** item 3 below, comparing `amount_received` with the order total.

**Where:** `orders/views_stripe.py:237-263`, the `payment_intent.succeeded` branch:

```python
if order and order.status != Order.Status.PAID:
    order.status = Order.Status.PAID
    order.save(update_fields=["status", "updated_at"])
    order_to_email = order
```

The guard only excludes PAID. It writes the status directly, bypassing `Order.transition_to`, and so bypasses `ALLOWED_TRANSITIONS` and the stock accounting that now lives there. It also never compares the amount Stripe received with `order.total_amount`.

**What breaks, and when:**

- **Redelivered events roll a shipped order back.** Stripe delivers webhooks *at least once*. It retries for up to three days after a timeout or 5xx, and the dashboard can resend any event. A `succeeded` event that arrives again after the order has moved on turns SHIPPED or COMPLETED back into PAID. (Until 2026-10-04 it also sent a second, blank "Order confirmed" email; the webhook no longer sends any email.) Nothing stops the status rollback today; it only needs one redelivery.
- **A REFUNDED order becomes PAID again.** The same redelivery after a refund flips it back. Since 2026-10-02 a refund also returns stock, so the order would read as paid with its stock already back on the shelf.
- **A CANCELED order becomes PAID with its stock released.** Cancelling now closes the PaymentIntent before the order (`orders/payments.py`), which removes the ordinary path. What remains:
  - orders cancelled **before** that change, whose intents were never closed — an old payment form left open can still pay them;
  - an intent that succeeds in the moment between Stripe confirming the cancellation and the shopper's browser completing a payment it had already submitted (Stripe should refuse this, but the webhook would not notice if it didn't).

  In each case money is taken for an order that will never be fulfilled. Its stock is already back on sale, so the candle may be sold twice.
- **An amount mismatch would be recorded as paid.** Totals don't change after creation today, so this is latent. But nothing checks it, and Fix 4 just changed how totals are computed.

**What fixing it involves (about half a day with tests):**

1. **Only PENDING → PAID moves the order:** `order.transition_to(PAID)` when it's PENDING, and do nothing for PAID, SHIPPED and COMPLETED. That makes redeliveries harmless. If an automatic email is ever reinstated, send it only when that transition actually happens, so a redelivery can't repeat it.
2. **CANCELED or REFUNDED plus a `succeeded` event means money was taken for an order that won't ship.** It needs a decision, not a status write. Options:
   - refund automatically through Stripe and log it (simplest; the shopper is never out of pocket);
   - re-reserve the stock if it's still available and reinstate the order. This needs a new CANCELED → PAID transition, and the `stock_qty >= 0` constraint means it can fail if the candle has since sold.

   Recommended: an automatic refund plus a staff alert.
3. **Compare `amount_received` and `currency` with the order** before marking it paid. On a mismatch, leave it PENDING and alert.
4. **Tests:**
   - a redelivered event on PAID, SHIPPED and COMPLETED changes nothing;
   - `succeeded` on CANCELED takes the chosen action;
   - an amount mismatch is not marked paid.

   The webhook tests were previously skipped as "requires PostgreSQL". Since 2026-10-02 they run on SQLite, so these can sit alongside them.
