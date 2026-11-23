/**
 * The cart speaks the shopper's language in every state, including the
 * ones a shopper only meets when something goes wrong: a candle sold out or
 * switched off, prices that couldn't be fetched, a change the server
 * refused without saying why. All of it used to be English in every
 * language.
 *
 * The real page, store and router render; only the HTTP client is
 * replaced.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import Cart from "./Cart";
import { store } from "../store";
import { logout, setCredentials } from "../store/authSlice";
import { setCart, type CartLine } from "../store/cartSlice";
import { clearAuthStorage, setAccessToken, setRefreshToken } from "../utils/token";

/** Every fixed string the cart used to show in English. */
const ENGLISH = [
  "Shopping cart",
  "Review your selected candles before checkout",
  "Your cart is empty",
  "Continue Shopping",
  "Size:",
  "No longer available",
  "Sold out",
  "It's a gift",
  "Gift wrapping",
  "Remove",
  "Unit Price",
  "Total",
  "Items",
  "Prices couldn't be updated",
  "Shipping and tax are added at checkout.",
  "Check out",
  "We couldn't update your cart",
  "Candle #",
];

/** Gone (19), sold out (22), a gift (5), and one with no name (7). */
const LINES: CartLine[] = [
  { item_id: 1, variant_id: 19, candle_id: 19, name: "Mango Island", size: "11.3 oz", price: 21.99, quantity: 1, inStock: true },
  { item_id: 2, variant_id: 22, candle_id: 22, name: "Tidal Bore", size: "11.3 oz", price: 21.99, quantity: 1, inStock: false },
  { item_id: 3, variant_id: 5, candle_id: 5, name: "Matcha Chill", size: "8 oz", price: 18.49, quantity: 1, inStock: true, isGift: true },
  { item_id: 4, variant_id: 7, candle_id: 7, name: "", size: "", price: 18.49, quantity: 1, inStock: true },
];

const server = { pricesFail: false };

vi.mock("../api/axiosInstance", () => {
  const cart = {
    id: 1,
    created_at: "",
    updated_at: "",
    items: [
      { item_id: 1, variant_id: 19, candle_id: 19, name: "Mango Island", slug: "m", price: "21.99", size: "11.3 oz", quantity: 1, in_stock: true, is_gift: false },
    ],
  };
  const preview = (items: { variant_id: number; quantity: number }[]) => ({
    lines: items.map((item) => ({
      variant_id: item.variant_id, name: "", quantity: item.quantity, unit_price: "21.99",
      line_total: "21.99", discount_amount: "0.00", discount_label: "", free_quantity: 0,
      gave_up_label: "", line_total_after_discount: "21.99",
    })),
    subtotal: "0.00", discount: "0.00", items_total: "87.96", label: "", unavailable: [19],
  });
  return {
    default: {
      get: vi.fn(async () => ({ data: cart })),
      post: vi.fn(async (url: string, body: { items: { variant_id: number; quantity: number }[] }) => {
        if (url.startsWith("/orders/price-preview/")) {
          if (server.pricesFail) throw new Error("network");
          return { data: preview(body.items) };
        }
        return { data: {} };
      }),
      // The server refuses without a reason: the cart's own words are used.
      patch: vi.fn(async () => {
        throw Object.assign(new Error("500"), { isAxiosError: true, response: { status: 500, data: null } });
      }),
      delete: vi.fn(async () => ({ data: cart })),
    },
  };
});

function showCart(lines: CartLine[], signedIn = false) {
  if (signedIn) {
    setAccessToken("token-nina");
    setRefreshToken("token-nina");
    store.dispatch(setCredentials({ access: "token-nina", refresh: "token-nina" }));
  }
  store.dispatch(setCart(lines));
  return render(
    <Provider store={store}>
      <MemoryRouter>
        <Cart />
      </MemoryRouter>
    </Provider>
  );
}

/** Everything on the page a shopper can see or hear. */
function pageWords(): string {
  const labels = [...document.querySelectorAll("[aria-label],[alt],[placeholder],[title]")].map((el) =>
    ["aria-label", "alt", "placeholder", "title"].map((name) => el.getAttribute(name) ?? "").join(" ")
  );
  return `${document.body.textContent ?? ""} ${labels.join(" ")}`;
}

/** Words that really are the same in that language. */
const SAME_WORD: Record<string, string[]> = { ru: [], es: ["Total"], fr: ["Total"] };

function englishLeft(): string[] {
  const words = pageWords();
  const same = SAME_WORD[i18n.language] ?? [];
  return ENGLISH.filter((phrase) => !same.includes(phrase) && words.includes(phrase));
}

beforeEach(async () => {
  server.pricesFail = false;
  localStorage.clear();
  clearAuthStorage();
  store.dispatch(logout());
  await i18n.changeLanguage("en");
});

afterEach(() => {
  cleanup();
});

describe("The cart in every language", () => {
  it("in English, every state shows its English line (the check below has something to find)", async () => {
    showCart(LINES);

    expect(await screen.findByText("No longer available — remove it to check out.")).toBeTruthy();
    expect(screen.getByText("Sold out — remove it to check out.")).toBeTruthy();
    expect(screen.getByText("Gift wrapping: Free")).toBeTruthy();
    expect(screen.getByText("Candle #7")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Check out" })).toBeTruthy();
  });

  for (const [language, title, soldOut, checkOut] of [
    ["ru", "Корзина", "Товар распродан — удалите его, чтобы оформить заказ.", "Оформить заказ"],
    ["es", "Carrito", "Agotado: quítalo para finalizar la compra.", "Finalizar compra"],
    ["fr", "Panier", "Épuisé — retirez-le pour passer commande.", "Passer commande"],
  ]) {
    it(`${language}: a full cart, with a candle gone, one sold out, a gift and a nameless line, has no English`, async () => {
      await i18n.changeLanguage(language);
      showCart(LINES);

      expect(await screen.findByRole("heading", { name: title })).toBeTruthy();
      await waitFor(() => expect(document.querySelector(".cartItem__unavailable")).not.toBeNull());
      expect(screen.getByText(soldOut)).toBeTruthy();
      expect(screen.getByRole("button", { name: checkOut })).toBeTruthy();
      expect(englishLeft()).toEqual([]);
    });

    it(`${language}: prices that couldn't be fetched are explained in the same language`, async () => {
      server.pricesFail = true;
      await i18n.changeLanguage(language);
      showCart(LINES);

      await waitFor(() =>
        expect(document.querySelector(".cart__summaryNote")?.textContent).toBe(i18n.t("cart.pricesFailed"))
      );
      expect(englishLeft()).toEqual([]);
    });

    it(`${language}: a change the server refuses without a reason`, async () => {
      await i18n.changeLanguage(language);
      showCart([LINES[0]], true);

      fireEvent.click(await screen.findByRole("checkbox"));

      expect((await screen.findByRole("alert")).textContent).toBe(i18n.t("cart.updateFailed"));
      expect(englishLeft()).toEqual([]);
    });

    it(`${language}: an empty cart`, async () => {
      await i18n.changeLanguage(language);
      showCart([]);

      expect(screen.getByText(i18n.t("cart.empty"))).toBeTruthy();
      expect(screen.getByRole("link", { name: i18n.t("cart.continueShopping") })).toBeTruthy();
      expect(englishLeft()).toEqual([]);
    });
  }

  it("every cart string has its own wording in each language", () => {
    const en = i18n.getFixedT("en");
    const keys = Object.keys(i18n.getResourceBundle("en", "translation").cart);
    for (const language of ["ru", "es", "fr"]) {
      const local = i18n.getFixedT(language);
      for (const key of keys) {
        // The same word in that language: "Total", and "OK" in French.
        if (key === "total" && language !== "ru") continue;
        if (key === "noticeOk" && language === "fr") continue;
        const options = { count: 2, id: 7, size: "8 oz", label: "X", offer: "X", price: "$1" };
        expect(local(`cart.${key}`, options), `${language} cart.${key}`).not.toBe(en(`cart.${key}`, options));
      }
    }
  });
});
