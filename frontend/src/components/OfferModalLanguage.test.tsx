/**
 * The offer pop-up opens straight after a candle is added, so it is on the
 * shopping path, and it speaks the shopper's language: title, explanation,
 * buttons and the screen-reader labels. Only the prices were translated
 * before.
 *
 * The real modal, store and router render; only the HTTP client is
 * replaced, answering /orders/offer-progress/ as the server does.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import OfferModal from "./OfferModal";
import { store } from "../store";
import { logout } from "../store/authSlice";
import { setCart } from "../store/cartSlice";
import { clearAuthStorage } from "../utils/token";

const ENGLISH = [
  "Add one of these and it's free",
  "One more and the third is free",
  "Your basket has earned a free candle",
  "candles from this offer in your basket",
  "Add another",
  "See all candles in this offer",
  "No thanks",
  "Close",
];

const SUGGESTIONS = [
  { candle_id: 5, variant_id: 5, name: "Matcha Chill", slug: "matcha-chill", size: "8 oz", price: "18.49", display_price: "18.49", image: "" },
  { candle_id: 9, variant_id: 9, name: "Tidal Bore", slug: "tidal-bore", size: "8 oz", price: "18.49", display_price: "18.49", image: "" },
];

/** Whether the offer gives its free candle from its own group. */
let rewardGroup = true;

vi.mock("../api/axiosInstance", () => ({
  default: {
    get: vi.fn(async () => ({ data: [] })),
    post: vi.fn(async (url: string) => {
      if (url.startsWith("/orders/offer-progress/")) {
        return {
          data: {
            promotions: [
              {
                offer_slug: "spring", offer_path: "/offers/buy-2-get-3", offer_title: "Spring",
                badge_text: "Spring", reward_group: rewardGroup, replaces_label: "",
                in_cart: 2, needed: 1, free_so_far: 0, suggestions: SUGGESTIONS,
              },
            ],
          },
        };
      }
      return { data: {} };
    }),
  },
}));

let basket = 0;

/** A new basket each time: the modal prompts once per basket. */
function openModal() {
  basket += 1;
  store.dispatch(
    setCart([
      { variant_id: 100 + basket, candle_id: 19, name: "Mango Island", size: "11.3 oz", price: 21.99, quantity: 2 },
      // Already in the basket: its button says "add another".
      { variant_id: 5, candle_id: 5, name: "Matcha Chill", size: "8 oz", price: 18.49, quantity: 1 },
    ])
  );
  render(
    <Provider store={store}>
      <MemoryRouter initialEntries={["/catalog"]}>
        <OfferModal />
      </MemoryRouter>
    </Provider>
  );
  return screen.findByRole("dialog", {}, { timeout: 3000 });
}

function englishLeft(dialog: HTMLElement): string[] {
  const labels = [...document.querySelectorAll("[aria-label]")].map((el) => el.getAttribute("aria-label"));
  const words = `${dialog.textContent} ${labels.join(" ")}`;
  return ENGLISH.filter((phrase) => words.includes(phrase));
}

beforeEach(async () => {
  rewardGroup = true;
  localStorage.clear();
  clearAuthStorage();
  store.dispatch(logout());
  await i18n.changeLanguage("en");
});

afterEach(() => {
  cleanup();
});

describe("The offer pop-up in every language", () => {
  it("in English: what the check below looks for is really there", async () => {
    const dialog = await openModal();

    expect(screen.getByRole("heading", { name: "Add one of these and it's free" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Add another/ })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Close" })).toHaveLength(2);
    expect(englishLeft(dialog).length).toBeGreaterThan(0);
  });

  for (const [language, title, addAnother, close] of [
    ["ru", "Добавьте одну из них — и она бесплатна", "Добавить ещё", "Закрыть"],
    ["es", "Añade una de estas y es gratis", "Añadir otra", "Cerrar"],
    ["fr", "Ajoutez-en une, elle est offerte", "En ajouter une autre", "Fermer"],
  ]) {
    it(`${language}: a free candle from the offer's own group`, async () => {
      await i18n.changeLanguage(language);
      const dialog = await openModal();

      expect(screen.getByRole("heading", { name: title })).toBeTruthy();
      expect(screen.getByRole("button", { name: new RegExp(addAnother) })).toBeTruthy();
      expect(screen.getAllByRole("button", { name: close })).toHaveLength(2);
      expect(screen.getByText(i18n.t("offerModal.seeAll"))).toBeTruthy();
      expect(screen.getByText(i18n.t("offerModal.noThanks"))).toBeTruthy();
      expect(englishLeft(dialog)).toEqual([]);
    });

    it(`${language}: one more and the third is free, with the count in the sentence`, async () => {
      rewardGroup = false;
      await i18n.changeLanguage(language);
      const dialog = await openModal();

      expect(screen.getByRole("heading", { name: i18n.t("offerModal.titlePlain") })).toBeTruthy();
      expect(dialog.textContent).toContain(i18n.t("offerModal.leadPlain", { count: 2 }));
      expect(englishLeft(dialog)).toEqual([]);
    });
  }

  it("Russian counts candles the Russian way", () => {
    const ru = i18n.getFixedT("ru");
    expect(ru("offerModal.leadPlain", { count: 1 })).toContain("1 свеча ");
    expect(ru("offerModal.leadPlain", { count: 2 })).toContain("2 свечи ");
    expect(ru("offerModal.leadPlain", { count: 5 })).toContain("5 свечей ");
  });
});
