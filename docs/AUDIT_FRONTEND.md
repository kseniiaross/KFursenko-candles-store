# Frontend audit — layout, states, accessibility, weight, duplication

**Date:** 2026-09-29
**Scope:** `frontend/`, working tree as of today (HEAD `5b91a43` plus the uncommitted changes listed in `docs/AUDIT.md`).
**Companion to** `docs/AUDIT.md`. Nothing covered there is repeated here: build health, the money path, secrets, permissions, dead routes, i18n keys and promise-vs-behaviour.
**Method:** read every page, component and stylesheet. Ran `vite build` into a scratch directory, served it with `vite preview`, and measured it in Chrome at 1440×900, 800×1000 and 375×700, with no API running (so every fetch fails, which is how the error states got exercised). Ran ESLint and computed WCAG contrast ratios. No repo file was changed apart from this report.

### Corrections to the brief

- **`--header-height` is declared in `src/styles/variables.css`**, not `app.css`. The global stylesheet is `src/styles/App.css`.
- The app runs **React 19.2** (not 18), react-router **7**, and **Vite 8.0.0-beta.15**. The production bundle is built with a beta bundler (see N6).

---

## BLOCKER

### B1. Every inner page's first content sits under the fixed header, and on Catalog the search and filters can't be clicked

**Where:** `src/styles/App.css:62-66`

```css
/* The header is fixed, so its height is padding here — but the shell
   still counts it in the flex layout above. … */
margin-top: calc(var(--header-height) * -1);
padding-top: var(--header-height);
```

**What happens:** the comment's premise is wrong. `.header` is `position: fixed` (`Header.css:6`), so it takes **no** space in the `.appShell` flex column. The negative margin pulls `.appShell__body` up to y = −140 (measured), and the padding puts page content back at y = 0, **under** the header. The line came in with commit `ae1f418` (29 Aug), titled *"i18 fixing: adding eeng modal discount text"*. That commit also patched Login, LoginChoice and Register individually, which is why only those three pages clear the header. The CSS is unchanged in the working tree, so this is in HEAD and presumably live.

**Measured** (top of the first visible text element, in px; the header is 140 / 100 / 110 px tall):

| Route | 1440 | 800 | 375 |
|---|---|---|---|
| `/catalog` (h1 "Catalog") | **0** | **0** | **0** |
| `/cart` (h1) | **0** | **0** | **0** |
| `/contacts` | **0** | **0** | **0** |
| `/support`, `/custom-candles` | 16 | 16 | 16 |
| `/recommendation-quiz` | 14 | 14 | 4 |
| `/orders` | 28 | 16 | 16 |
| `/delivery`, `/payments`, `/policy`, `/collections` | 45 | 27 | 23 |
| `/offers/*` (all three) | 64 | 40 | 32 |
| `/payment/success`, `/payment/cancel` | 69 | 69 | 45 |
| `/story-mission` (h1) | 4 | 4 | 4 |
| `/login`, `/login-choice`, `/register` | 298 / 283 / 204 | 252–272 | 178–208 ✓ |

**What a visitor sees:** the header is transparent, so page titles, kickers and the first line of copy run underneath the navigation text. On **Catalog** it's worse than overlap. At 1440 px, `document.elementFromPoint` on the centre of the search input, the category `<select>` and the "Lumière AI Search" button returns `.header__inner` or a header nav button in every case. **A mouse user can't search or filter the catalog.** Keyboard Tab still reaches them. Screenshot taken during the audit: the title "CATALOG" and the search row are drawn over "MENU / GO TO MY ACCOUNT … LANGUAGE / SHOPPING CART".

**Fix:** delete the `margin-top` line so `.appShell__body` really reserves the header's height. Then remove the header term from Login/LoginChoice/Register (`calc(var(--header-height) + clamp(…))` → `clamp(…)`), or they'll be pushed down twice. Deal with the original "band of empty page" by fixing page heights (W1), not by moving the shell. About an hour, plus a visual check of every route at three widths.

---

## SERIOUS

### S1. A logged-in shopper's cart doubles after adding from a product page or the offer modal and then reloading

**Where:**
- `store/cartSlice.ts:116-129`: `addToCart` always calls `saveGuestCart(state.items)`, logged in or not.
- `pages/CatalogDetail.tsx:203` and `components/OfferModal.tsx:169-180` dispatch `addToCart` optimistically for logged-in users and **never** call `clearGuestCartStorage()`. `Cart.tsx` does, after every mutation.
- `hooks/useHydrateCart.ts:39-58`: on load, a logged-in session merges whatever is in guest storage into the server cart.
- Backend `MergeCartAPIView` **adds** quantities (`final_qty = qty + existing`).

**What a visitor sees:** they have 2 candles in their cart, add a third from the product page, and reload. Guest storage now holds all three lines, and the merge adds them again: the cart shows 4 + 2. Each "add from product page, then reload" cycle doubles the cart once. If a doubled line exceeds stock, the merge returns 400 and the guest copy is dropped instead.

**Fix:** make `addToCart` persist only for guests (pass a flag, or split `addGuestItem` and `addServerItem`), or clear guest storage in the two callers. Better still, share one add-to-cart helper (see W3). An hour.

### S2. Guest cart lost on sign-in and on a failed load

**Where:** `hooks/useHydrateCart.ts:18-23, 78-84`

- Hydration runs **once per page load**, and a ref blocks it from re-running when `isLoggedIn` flips. Login and Register don't merge the cart themselves. A guest who signs in without a reload keeps their items only in Redux. The next server-backed add (`setCart(serverItems)`) **replaces** them with the server's cart, and the guest's items disappear.
- On load, if the merge fails with anything other than 400 (network, 5xx, 401 during refresh) **and** `getMyCart` then fails, the `catch` runs `setCart([])` and `clearGuestCartStorage()`. The guest items are deleted from `localStorage` for good.
- In development under `<React.StrictMode>`, the first run is cancelled by the simulated unmount and the second is blocked by the ref, so **the cart never hydrates in dev**. Production is unaffected, but it hides the other two bugs locally.

**Fix:** key hydration on `isLoggedIn` (merge when it turns true), and don't clear guest storage unless the merge succeeded. Half a day with tests.

### S3. Checkout lets the address be edited after payment is ready, then charges the old order

**Where:** `pages/Checkout.tsx`, address inputs at roughly lines 570–705, all `disabled={loading}` only. `showPayment` stays true after `createOrderAndIntent` finishes.

**What a visitor sees:** after "Payment is ready", every field is editable again. A shopper who spots a typo and fixes it sees the corrected address on screen, and the mounted card form pays the **already created** order with the original address. This is a second stale-state bug, separate from the shipping rate one in `AUDIT.md`: the rate is stale before the order exists; this is the whole order after it exists.

**Fix:** lock the form once `clientSecret` is set and offer an explicit "Edit details" that discards the client secret. Or reset `clientSecret` and `orderId` in `onFieldChange`. An hour.

### S4. The product page is blank while loading, on error and for an unknown slug, and it shows the previous product during a size or colour switch

**Where:** `pages/CatalogDetail.tsx:224` `if (!item) return null;` and the load effect at `:89-137`.

- **Loading / error / not found:** all three render nothing. Measured for `/catalog/item/x` with the API down: no content at any width; the footer rises to y=444 (1440), y=251 (800) and **y=0 (375)**, so on a phone the page is a footer under the header.
- **Stale state:** the size and colour switchers navigate to a sibling slug without resetting `item` or `variant`. Until the new fetch lands, the old product stays on screen and "Add to cart" (`:195-222`) adds **the previous variant**. If the new fetch fails, the page goes blank (`setItem(null)`). `zoomImg` isn't reset on a slug change either.

**Fix:** add explicit `status: "loading" | "error" | "notFound" | "ready"` states, and reset `item` and `variant` when `slug` changes. A few hours.

### S5. Catalog shows nothing while loading, and a late AI response overwrites a newer choice

**Where:** `pages/Catalog.tsx:360-474`. There's an empty state and an error state, but nothing renders while `loading` (the grid is simply hidden). `runAiSearch` (`:299-346`) has no request guard.

**What a visitor sees:** below the (overlapped, see B1) search bar, the page is empty until the first response arrives. That can take several seconds on a cold Railway start, and it happens again after every debounced keystroke. If a shopper runs "Lumière AI Search" and picks a category while it's thinking, the category results load, and then the AI response lands and replaces them, with `aiMode` switched back on.

**Fix:** a skeleton grid, keeping the previous results visible while re-querying. Give `runAiSearch` a request id and drop stale responses. Half a day.

### S6. Cart changes that fail are silent, and the size picker offers inactive sizes

**Where:**
- `pages/Cart.tsx:61-150`: remove, quantity and gift updates are optimistic, and on failure only `console.error`.
- `components/SizeModal.tsx:57-58`: a logged-in add failure is logged; the modal stays open with no message.
- `components/SizeModal.tsx:82`: renders `candle.variants` unfiltered, so **inactive** variants are offered.
- `CatalogDetail.tsx:218` and `OfferModal.tsx:194`: failures are swallowed, and the optimistic line stays in Redux.

**What a visitor sees:** "+" past the available stock shows the new quantity with no complaint; the server kept the old one. At checkout, the order is built from Redux (`Checkout.tsx:233`), so it fails with "Only N left" long after the cause. Picking an inactive size in the modal either does nothing (logged in) or adds a line that checkout will reject (guest).

**Fix:** roll back on failure and show the server's message inline. Filter `is_active` (and stock) in SizeModal. Half a day, with W3.

### S7. Error messages can be raw HTML, and a payment failure blames the shopper

**Where:** `pages/Checkout.tsx:103-164` `getErrorMessage` and `components/ShippingRates.tsx:60-90` `readError`.

- Both **return the response body verbatim when it's a string**. Django's production 500, Railway's 502/503 page and a proxy timeout are HTML strings. The shopper sees markup such as `<!doctype html>…` or `<h1>Server Error (500)</h1>` as the error text.
- Neither reads the `{"error": "..."}` shape that `create-intent` returns. A Stripe outage (502 from the backend) therefore shows the generic fallback, "Could not prepare payment. Please check your information and try again", which tells the shopper their details are wrong.

**Fix:** one shared `apiErrorMessage(error, fallback)` that ignores non-JSON bodies, reads `detail`, `error`, field arrays and `non_field_errors`, and maps 5xx and network errors to "try again later". See W3. An hour or two.

### S8. The modals: SizeModal has none of the required behaviour, and none of them restores focus

| | Role/label | Focus moved in | Escape | Tab trapped | Body scroll locked | Focus restored |
|---|---|---|---|---|---|---|
| **SizeModal** (`components/SizeModal.tsx`) | **none**: plain `div`s | **no** | **no** | **no** | **no** | **no** |
| **DiscountModal** | `role=dialog`, `aria-modal`, labelled | yes (close button, measured) | yes (measured) | yes (measured) | yes (measured) | **no**: focus fell to `<body>` (measured) |
| **OfferModal** | `role=dialog`, `aria-modal`, labelled | yes (`:125`) | yes | yes | yes | **no** |
| Product image zoom (`CatalogDetail.tsx:437-470`) | `role=dialog`, `aria-modal` | **no** | yes | **no** | yes | **no** |
| Profile delete-account | yes | yes | yes | yes | no | yes |
| Lumière panel | yes | yes | yes | — | — | yes: the pattern to copy |

**What a visitor sees:** SizeModal opens on every "Add to cart" from Catalog and the offer pages. It's rendered after all page content (`App.tsx`), so a keyboard user's focus stays on the card they activated, and they have to Tab through the whole page behind the overlay to reach the size buttons. A screen reader isn't told a dialog opened. There's no Escape, and the page scrolls underneath. For the other modals, closing drops focus to the top of the document.

Also:
- The DiscountModal and OfferModal trap selectors (`"button:not([disabled]), a[href]"`) skip inputs.
- DiscountModal's backdrop is a second focusable "Close" button **outside** the dialog.
- Each modal sets `document.body.style.overflow = ""` on close without checking the others. DiscountModal (1.2 s after landing) and OfferModal (0.9 s after a cart change) can both be open on the same page, and closing one unlocks scrolling under the other.

**Fix:** one `useDialog` hook (focus in, trap, Escape, restore, counted scroll lock) used by all five. Half a day.

### S9. Contrast failures on labels, prices and shipping details

Ratios are composited on white, against WCAG AA (4.5:1 normal text, 3:1 large):

| Opacity | on `#111` | on `--app-text` (`rgba(17,17,17,.92)`) |
|---|---|---|
| 0.40 | 2.61 | 2.41 |
| 0.45 | 3.03 | 2.75 |
| 0.50 | 3.54 | 3.11 |
| 0.55 | 4.17 | 3.59 |
| 0.60 | 4.95 | 4.17 |
| 0.62 | 5.33 | 4.48 |
| **Sale red `#b73a3a`** | **5.71: passes AA** | |

Failing text, all small (0.62–0.95 rem), so the 4.5 threshold applies:

- **Form labels:** `login__label`, `register__label` at 0.5 opacity, 0.7rem (**3.54 / 3.11**). These are the only labels on the login and register forms.
- **Was-prices:** `price__was` (`Price.css:39`), `catalogDetail__priceWas`, `cartItem__oldPrice` at 0.45–0.5 opacity (**3.03–3.54**).
- **Checkout shipping choices:** `rates__carrier` 0.5 opacity at 0.66rem, `rates__title` 0.5, `rates__note` 0.55 (**3.1–4.2**), plus `offerModal__note` and `offerCard__meta`.
- **Product page:** `catalogDetail__label`, `__eyebrow` and `facts dt` at 0.5 (**3.1–3.5**). The field names "Scent", "Mood" and so on.
- **Every kicker and eyebrow:** offer pages, customer-care pages, the menu's department labels at 0.45 opacity, 0.65rem (**2.75**).

`--app-text-muted` (`variables.css:10`, 0.68) measures **6.58** and passes. Most failures are opacity hacks on top of `--app-text` instead of that token.

**Fix:** replace text `opacity` with `color: var(--app-text-muted)` (6.58). An hour or two of search-and-replace, then a visual pass.

### S10. The Story & Mission page downloads about 30 MB of photos

**Where:** `src/assets/images/story_mission/story_mission2–8.jpg`: **4.0–5.0 MB each** (4,762,738 / 4,962,354 / 4,300,278 / 4,298,116 / 4,173,857 / 4,594,695 / 4,555,460 bytes). They're bundled as-is (`dist/assets/story_mission*-*.jpg`) and rendered at `StoryMission.tsx:133` into frames 300–460 px tall (`StoryMission.css:174, 299, 352`), with `loading="lazy"` but no `width`, `height`, `srcset` or `sizes`.

**What a visitor sees:** on mobile data, scrolling the page pulls down about 30 MB. The other three photos in the same folder are 125–160 kB, so these seven were simply never exported for web.

**Fix:** re-export at about 1600 px as WebP/AVIF (roughly 150–300 kB each) or move them to Cloudinary. Add `width` and `height` to prevent layout shift. An hour.

### S11. "Delete account" always fails

**Where:** `pages/Profile.tsx:47` posts to `/accounts/delete-account/`. The backend's `accounts/urls.py` defines only `register/`, `login/`, `token/refresh/` and `profile/`.

**What a visitor sees:** they confirm deletion in the dialog and get an error every time. The account stays.

**Fix:** add the endpoint, or remove the button until it exists.

### S12. An expired session leaves the site showing "logged in" while every request fails

**Where:** `api/axiosInstance.ts:140-176`. When the refresh fails, `clearTokens()` runs, but Redux `auth.isLoggedIn` stays `true`, and nothing redirects. `PrivateRoute` only guards `/profile`; `/orders` and `/checkout` aren't guarded.

**What a visitor sees:** after 7 idle days (the refresh lifetime), the header still greets them by name. Orders says "We couldn't load your orders right now", Checkout's "prepare payment" fails generically, and cart syncs silently fail (S6). Nothing tells them to sign in again.

**Fix:** dispatch `logout()` and redirect to `/login?next=…` from the interceptor's failure branch. An hour.

---

## WORTH FIXING

### W1. Every place that compensates for the header or the viewport, and where they disagree

`--header-height` = **140 px** (default), **100 px** at ≤900 px, **110 px** at ≤600 px (`variables.css:2, 32, 38`).

| Where | Assumes | Value |
|---|---|---|
| `App.css:65-66` `.appShell__body` | the header is in flow (it isn't) | −H margin, +H padding → **net 0** |
| `App.css:69-71` `.appShell--home .appShell__body` | the home hero sits under the header on purpose | padding 0 → body at −H |
| `Header.css:10, 103, 255, 282, 507, 532` | header, nav buttons, language box, cart link = H | H |
| `Header.css:159` account dropdown | opens just inside the header's bottom edge | `H − 10px` |
| `Header.css:654, 662` mobile dropdowns | fixed, flush below the header | H |
| `Login.css:50`, `LoginChoice.css:61`, `Register.css:55` | the body gives **no** offset, so the page adds it | `H + clamp(32px, 5vw, 64px)` |
| `CatalogDetail.css:63` sticky panel | viewport top is under the header (correct for a fixed header) | `H + 24px` (but see W2) |
| `offers/HolidayOffer.css:18`, `NewShoppers.css:21`, `PromoBuy2Get3.css:22` | the body **already** clears the header | `clamp(32px, 5vw, 64px)` only |
| `Orders.css:12`, `PaymentSuccess.css:12`, `PaymentCancel.css:11` | same | 28px |
| `Profile.css:9` 16px, `RecommendationQuiz.css:11` / `RecommendationResult.css:12` 14px, `Reviews.css:16` 8px, `StoryMission.css:34` 4px, `Gallery.css:2` 40px | same | fixed px |
| `Catalog.css:13`, `Cart.css:5`, `Checkout.css:6`, `Contacts.css:22`, `ComingSoon.css:4`, `CustomerCare/*.css:4`, `Support.css:10` | same | **0** |
| `Home.css:172, 319-333` logo `top: 5.5vh / 6vh / 7vh / 8vh` | a viewport fraction clears the header | vh, not H |
| `LumiereWidget.css:79` | panel height `min(620px, 100vh − 120px)` | 120 px stand-in |
| Page roots (`Cart.css:3`, `Catalog.css:12`, `Checkout.css:4`, `Orders.css:10`, `CustomerCare/*:2`, `Contacts.css:20`, …) | a page is at least one viewport tall | `min-height: 100vh / 100dvh` |

**Disagreements:**
- Login, LoginChoice and Register assume the body gives no offset; about 20 other pages assume it does. Only one group can be right at a time, and since `ae1f418` it's the first (B1).
- Where the body *does* pad by H, a page's own `min-height: 100vh` makes the column **H taller than the viewport**. That's the "extra band" that `ae1f418` was trying to remove. The fix belongs in the pages: `min-height: calc(100dvh - var(--header-height))`, or one `min-height` on `.appShell__body` and none on pages.
- Pages that render **nothing** (`CatalogDetail` returns `null`; `Gallery` returns a bare `<div>`) have no `min-height` at all. The footer climbs to y=0–444 (measured). That's the "column running short" case.

**Header height vs rendered height:** matches at every breakpoint. Measured box = 140 / 100 / 110, and the lowest visible header descendant ends exactly there. **The ordering is correct, not a bug.** Mobile is taller than tablet because the mobile layout shows a 104 px logo beside two 36 px nav rows (`Header.css:565, 583`), while the tablet logo is 82 px (`Header.css:492`).

### W2. The product page's sticky buy panel never sticks

**Where:** `CatalogDetail.css:15-19, 61-63`; markup `CatalogDetail.tsx:283-284`. `.catalogDetail__panel` is `position: sticky`, but it's the **only child** of `.catalogDetail__info`. Because the grid uses `align-items: start` (the comment credits this with *enabling* sticky), `.info` is exactly as tall as the panel, so the panel has no room to move inside its containing block. On a long gallery, the price and "Add to cart" scroll away with everything else.

I couldn't watch it in the browser, because the product page needs the API, so this comes from the CSS and the spec. **Fix:** put `position: sticky; top: …` on `.catalogDetail__info` itself, or give `.info` `align-self: stretch`. The sticky media on Login, LoginChoice and Register (`top: 0`) is fine: those images are meant to run under the transparent header.

### W3. Duplicated helpers that have already diverged

**Money formatting: seven implementations, three different outputs.**

| Where | Method | Output for 1234.5 |
|---|---|---|
| `Cart.tsx:16`, `Checkout.tsx:87` | `Intl.NumberFormat("en-US")` | `$1,234.50` |
| `Orders.tsx:75` | `Intl.NumberFormat(undefined, {currency})` | **browser locale**: `1 234,50 $US` in French, `1 234,50 $` in Russian |
| `Price.tsx:20`, `CatalogDetail.tsx:295-303`, `ShippingRates.tsx:247`, `OfferModal.tsx:273` | `"$" + toFixed(2)` | `$1234.50` (no separator) |
| `SizeModal.tsx:98` | `` `$${variant.price}` `` | the API's raw string |

A shopper sees `$1,234.50` in the cart and `$1234.50` on the product card. With the site in French, the same order shows in Orders as `24,00 $US` next to `$24.00` everywhere else.

**Cloudinary URLs: two identical copies, both misfiring.** `Catalog.tsx:33` and `PromoBuy2Get3.tsx:26` skip the rewrite if the URL contains `/upload/f_auto` or `/upload/q_auto`. The backend already transforms card images, and Cloudinary sorts parameters, so the URL is `/upload/c_limit,f_auto,h_1250,q_auto,w_1000/…` (checked by building one offline). The check never matches, so every card image becomes a **chained** transform (`/upload/f_auto,q_auto,w_480/c_limit,…,w_1000/…`). The "1200w" `srcset` candidate is really capped at 1000 px, and each width creates an extra derived asset.

**API error parsing: four parsers, all different.**
- `Checkout.getErrorMessage` reads `shipping.*`, `items`, `detail`.
- `ShippingRates.readError` reads `shipping`, `detail`.
- `Login.tsx:61` reads `detail`.
- `Register.tsx:67` reads field errors plus `non_field_errors`.

The first two have the raw-HTML and missing-`error` bugs (S7).

**Add to cart: four sequences, four behaviours.**

| Where | Order | On server failure | Guest storage when logged in |
|---|---|---|---|
| `CatalogDetail.tsx:195` | optimistic, then server | line kept, logged | **written, never cleared** (S1) |
| `OfferModal.tsx:164` | optimistic, then server | line kept, silent | **written, never cleared** (S1) |
| `SizeModal.tsx:23` | server first (logged in), local (guest) | nothing added, silent, modal stays open | untouched |
| `Cart.tsx` handlers | optimistic, then server | kept, logged | written, then cleared |

The divergence in the last column is the direct cause of S1.

**Fix:** `utils/money.ts`, `utils/cloudinary.ts` (detect any existing transformation), `api/errors.ts`, and one `useAddToCart()`. A day in total.

### W4. Image transforms are applied in only some places

- **Transformed:** catalog and B2G3 cards (double-transformed, W3), the product gallery, Gallery page items.
- **Originals:** the logged-in cart, and so the checkout thumbnails too. Backend `cart/serializers.py:13` calls `build_url(secure=True)` with no transform, so 110–160 px thumbnails load full uploads, with no WebP.
- **Originals:** OfferModal suggestion tiles (`views_offers._image_url` uses `candle.image.url`).
- Guest cart lines keep whatever URL was captured at add time: the transformed 1000 px one.
- **Fix:** transform in one place server-side (thumbnail and card sizes) and stop rewriting URLs in the frontend.

### W5. Request bursts

- **Catalog search:** debounced at 420 ms (`Catalog.tsx:22`), but every settled query runs **both** `listCategories()` and `listCandles()` (`:141-213`). The categories never change while typing. The anonymous throttle is 60/min across all endpoints, so a slow typist with frequent pauses can hit a 429 that renders as "Failed to load candles".
- **AI search:** fetches the **entire** catalog (`listCandles` with no filter, `:327`) just to map a handful of ids.
- **Debounced correctly:** `ShippingRates` (600 ms, request-id guard), `OfferModal` (900 ms, cancellation flag), `Profile` Nominatim (350 ms + `AbortController`).
- **Nominatim:** browsers silently drop the `User-Agent` header set at `Profile.tsx:108` (it's a forbidden header), so the comment claiming compliance is wrong. Nominatim's usage policy also prohibits autocomplete-style querying, and each query sends a customer's home address to a third party.

### W6. ESLint errors that are real bugs

`npx eslint src` reports 10 errors and no hidden dependency warnings. The three `eslint-disable` comments (`OfferModal.tsx:114`, `ShippingRates.tsx:168`, `CartOfferHint.tsx:71`) are deliberate trims, not false negatives. The real staleness bugs (the checkout rate, S3, S4) aren't dependency-array problems.
- `Catalog.tsx:208`: `return` inside `finally` (`no-unsafe-finally`). Harmless today, but it would swallow any future `throw` in that `try`.
- `LumiereWidget.tsx:52-53`: emoji in a character class without the `u` flag. The class matches lone surrogate halves and U+FE0F, so it strips half of unrelated emoji and turns every variation selector into ". ". Only the spoken (text-to-speech) version of replies is affected.

### W7. Styles defined in the wrong file, and lazily loaded CSS that collides

- `.catalogCard__priceWas` / `.catalogCard__priceNow` are defined in **`Checkout.css:16-26`**. They style catalog cards only after the Checkout chunk has loaded once.
- `.cc-page`, `.cc-hero*` are defined in **four** stylesheets (`ComingSoon.css`, `CustomerCare/Delivery.css`, `Payments.css`, `Policy.css`), and `.cc-card*` / `.cc-list*` / `.cc-panel*` in three. The copies have diverged. `ComingSoon.css` centres `.cc-hero__inner` (`text-align: center`) and centres the subtitle; `Delivery.css` doesn't. `Policy.css` uses `max-width: 75ch` where `Delivery.css` uses 65ch. Lazily loaded CSS stays in the document, and the last one loaded wins, so **Delivery's hero changes alignment depending on whether the visitor opened a "Coming soon" page first**. I didn't reproduce this visually.
- `.checkoutPay*` is defined in both `Checkout.css` and `CheckoutPaymentBlock.css`.
- **Fix:** one `customerCare.css` imported by all four pages; move card price styles into `Price.css` / `Catalog.css`.

### W8. Grids that won't shrink

`Checkout.css:339` (≤1200 px) switches to `1fr 1fr`, dropping both the `minmax(0, …)` and the 360 px minimum used on desktop. `Cart.css:81` `.cartItem` is `140px 1fr`. Only long unbreakable strings (an email address or URL in a name) overflow today, but these are the only non-`minmax(0)` tracks around text in the purchase flow. The two existing ellipses (`.catalogCard__name`, `.offerCard__name`) sit in `minmax(0, 1fr)` tracks and truncate correctly.

### W9. Smaller accessibility items

- **Home has no `<h1>`** (`Home.tsx`; the first heading is an `<h2>` in the promo). Every other page has exactly one `<h1>` and no skipped levels. The two `<h1>`s in `RecommendationResult` are alternative branches.
- **Profile address suggestions:** `role="listbox"` / `role="option"` without arrow-key support, and the only focus indicator is a 5% grey background (`Profile.css:255-258`, `outline: none`).
- **Product gallery:** every zoom button has the same label, "Select image: {name}".
- **Price:** `aria-label` on `<s>` (`Price.tsx:42`) is prohibited on a generic element, and most screen readers ignore it.
- Cart and Checkout thumbnails use `alt={name}` right next to the same name as a heading, so it's announced twice. `alt=""` would be better.
- Everything else checked out: all `<img>` have `alt`, decorative ones are `alt=""` or inside `aria-hidden`, there are no `onClick` handlers on non-interactive elements except the SizeModal overlay, and `outline: none` appears only where a `:focus-visible` replacement exists (Login, Register), apart from Profile's.

### W10. Unused dependencies

`@cloudinary/react` and `@cloudinary/url-gen` are in `package.json` and never imported. They add no bundle cost thanks to tree-shaking, but they're install weight and misleading.

---

## NOTED

- **N1. Bundle weight: nothing over 500 kB.** Actual `npx vite build` output: 226 modules. Largest JS chunks:
  - `index-BPLd1iqd.js` 275.76 kB (86.69 kB gzip)
  - `i18n-DKLW5P7V.js` 103.35 kB (31.79 kB gzip)
  - `axiosInstance` 37.94 kB, `Checkout` 26.13 kB, `redux-toolkit` 21.24 kB

  Total `dist` ≈ 35 MB, of which about 30 MB is the seven Story & Mission JPEGs (S10). Every page is lazy.
  - **`index`:** React 19, react-dom, react-router, react-redux, and the always-mounted Header, Footer, SizeModal, OfferModal, DiscountModal and LumiereWidget.
  - **`i18n`:** all four languages inline (`src/i18n.ts`, 1,936 lines), loaded eagerly from `main.tsx:12`. Loading only the active language would save about 75 kB raw. Reasonable to leave for now.
  - **Stripe** (`@stripe/stripe-js`, `react-stripe-js`) sits in the lazy Checkout chunk, and `js.stripe.com` is requested only when Checkout loads. Good.
- **N2.** The mobile header (110 px) being taller than the tablet one (100 px) is deliberate, and it matches the rendered content (W1).
- **N3.** Login, LoginChoice and Register media use `position: sticky; top: 0` under the transparent header on purpose (full-bleed photo).
- **N4.** Orders, the B2G3 page and ShippingRates handle loading, empty and error states properly. ShippingRates also guards against out-of-order responses. Gallery has all three states, but as unstyled bare `<div>`s (`Gallery.tsx:40-49`).
- **N5.** The `eslint-disable` comments on `OfferModal`'s and `ShippingRates`' dependency arrays are genuine, deliberate trims: they read current values through refs or a derived signature.
- **N6.** Production is built with **Vite 8.0.0-beta.15**. Nothing broke in this build, but a beta bundler in the production pipeline is worth pinning or upgrading deliberately.
- **N7.** The sale-price red (`#b73a3a`, 5.71:1) passes AA. Only the struck-through "was" price fails (S9).
- **N8.** Fixed media heights (`Gallery.css:37` 520/420 px, `StoryMission.css:174/299/352`, `Reviews.css:147-246`) use `object-fit: cover`, so they crop rather than stretch. I saw no clipped text at 375×700.
