/**
 * The catalogue's search. Typing matches words in the candles' names and
 * descriptions, which are English: a whole sentence, or a word in Russian,
 * Spanish or French, finds nothing. That used to end in "Nothing matches
 * this selection", under a placeholder inviting exactly such a sentence.
 * Now a typed miss offers Lumière's search, which reads the question in
 * any of the four languages; and what Lumière says about its picks is
 * shown, because without it an honest answer ("there's no pineapple
 * candle, here is the tropical one") looks like a wrong result.
 *
 * The real page, store and router render; only the HTTP client is
 * replaced, answering as the candles and Lumière endpoints do.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import Catalog from "./Catalog";
import { store } from "../store";

const candle = (id: number, slug: string, name: string) => ({
  id, slug, name, description: "", image: `https://example.test/${slug}.jpg`, images: [],
  price: "21.99", is_bestseller: false, badges: [],
  variants: [{ id: id * 10, size: "11.3 oz", price: "21.99", is_active: true, stock_qty: 5 }],
});

const CANDLES = [
  candle(1, "mango-island", "Mango Island"),
  candle(2, "mulled-wine", "Mulled Wine"),
  candle(3, "rich-smokey", "Rich Smokey"),
];

type Answer = { text: string; suggestions: { id: number; match_reason?: string }[] } | "fail";

/** What Lumière answers, by query. */
const lumiere: Record<string, Answer> = {};
const asked: { query: string; locale: string }[] = [];

vi.mock("../api/axiosInstance", () => ({
  default: {
    get: vi.fn(async (url: string, config?: { params?: Record<string, string> }) => {
      if (url.startsWith("/candles/categories/")) return { data: [] };
      if (url.startsWith("/candles/candles/")) {
        // The typed match: an English word in a name, or nothing.
        const search = config?.params?.search?.toLowerCase() ?? "";
        return { data: search ? CANDLES.filter((c) => c.name.toLowerCase().includes(search)) : CANDLES };
      }
      return { data: [] };
    }),
    post: vi.fn(async (url: string, body: { query: string; locale: string }) => {
      if (url.startsWith("/lumiere/search/")) {
        asked.push({ query: body.query, locale: body.locale });
        const answer = lumiere[body.query];
        if (!answer || answer === "fail") throw new Error("network");
        return {
          data: {
            query: body.query,
            text: answer.text,
            suggestions: answer.suggestions.map((s) => ({
              ...s, name: "", slug: "", price: "21.99", in_stock: true,
            })),
          },
        };
      }
      return { data: {} };
    }),
  },
}));

function showCatalog() {
  return render(
    <Provider store={store}>
      <MemoryRouter initialEntries={["/catalog"]}>
        <Catalog />
      </MemoryRouter>
    </Provider>
  );
}

async function type(text: string) {
  const field = await screen.findByRole("searchbox");
  fireEvent.change(field, { target: { value: text } });
}

const cardNames = () => [...document.querySelectorAll(".catalogCard__name")].map((el) => el.textContent);

beforeEach(async () => {
  for (const key of Object.keys(lumiere)) delete lumiere[key];
  asked.length = 0;
  await i18n.changeLanguage("en");
});

afterEach(() => {
  cleanup();
});

describe("Catalogue search", () => {
  it("a sentence the typed match can't find: Lumière is offered, not 'nothing matches'", async () => {
    lumiere["I want something cozy for reading at night"] = {
      text: "For a cozy reading night, these warm candles fit.",
      suggestions: [
        { id: 2, match_reason: "Warm, spiced and slow." },
        { id: 3, match_reason: "Deep and intimate for late evenings." },
      ],
    };
    showCatalog();
    await type("I want something cozy for reading at night");

    expect(await screen.findByText(i18n.t("catalog.askLumiere"), {}, { timeout: 2000 })).toBeTruthy();
    expect(screen.queryByText("Nothing matches this selection.")).toBeNull();

    fireEvent.click(screen.getAllByRole("button", { name: "Lumière AI Search" }).at(-1)!);

    expect(await screen.findByText("For a cozy reading night, these warm candles fit.")).toBeTruthy();
    expect(cardNames()).toEqual(["Mulled Wine", "Rich Smokey"]);
    expect(screen.getByText("Warm, spiced and slow.")).toBeTruthy();
    expect(screen.getByText("Deep and intimate for late evenings.")).toBeTruthy();
    expect(screen.queryByText(i18n.t("catalog.askLumiere"))).toBeNull();
  });

  it("an honest near-miss reads as one: the explanation sits above the picks", async () => {
    lumiere.pineapple = {
      text: "We don't have a pineapple candle, but Mango Island is the tropical one.",
      suggestions: [{ id: 1, match_reason: "Bright tropical fruit, close to pineapple." }],
    };
    showCatalog();
    await type("pineapple");
    fireEvent.submit(await screen.findByRole("search"));

    const answer = await screen.findByText("We don't have a pineapple candle, but Mango Island is the tropical one.");
    const grid = document.querySelector(".catalog__grid")!;
    expect(answer.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(cardNames()).toEqual(["Mango Island"]);
  });

  it("the same reason on every card says nothing per card, so the cards don't repeat it", async () => {
    lumiere.vanilla = {
      text: "Lumière is temporarily using catalog matching.",
      suggestions: [
        { id: 2, match_reason: "Matched by catalog fields." },
        { id: 3, match_reason: "Matched by catalog fields." },
      ],
    };
    showCatalog();
    await type("vanilla");
    fireEvent.submit(await screen.findByRole("search"));

    expect(await screen.findByText("Lumière is temporarily using catalog matching.")).toBeTruthy();
    expect(screen.queryByText("Matched by catalog fields.")).toBeNull();
  });

  it("a word the typed match does find: its results, no prompt", async () => {
    showCatalog();
    await type("mango");

    await waitFor(() => expect(cardNames()).toEqual(["Mango Island"]), { timeout: 2000 });
    expect(screen.queryByText(i18n.t("catalog.askLumiere"))).toBeNull();
  });

  it("Lumière with nothing to offer: its own words, not 'nothing matches'", async () => {
    lumiere.lilac = { text: "There's no lilac candle in the shop right now.", suggestions: [] };
    showCatalog();
    await type("lilac");
    fireEvent.submit(await screen.findByRole("search"));

    expect(await screen.findByText("There's no lilac candle in the shop right now.")).toBeTruthy();
    expect(screen.queryByText("Nothing matches this selection.")).toBeNull();
  });

  for (const [language, word] of [["ru", "ваниль"], ["es", "vainilla"], ["fr", "vanille"]]) {
    it(`${language}: a word in the shopper's language finds nothing typed, and Lumière is offered in that language`, async () => {
      await i18n.changeLanguage(language);
      lumiere[word] = { text: `(${language}) answer`, suggestions: [{ id: 2, match_reason: `(${language}) reason` }] };
      showCatalog();
      await type(word);

      expect(await screen.findByText(i18n.t("catalog.askLumiere"), {}, { timeout: 2000 })).toBeTruthy();
      fireEvent.click(screen.getAllByRole("button", { name: i18n.t("catalog.aiSearch") }).at(-1)!);

      expect(await screen.findByText(`(${language}) answer`)).toBeTruthy();
      expect(asked.at(-1)).toEqual({ query: word, locale: language });
    });

    it(`${language}: a failed search says so in the shopper's language`, async () => {
      await i18n.changeLanguage(language);
      lumiere.anything = "fail";
      showCatalog();
      await type("anything");
      fireEvent.submit(await screen.findByRole("search"));

      expect(await screen.findByText(i18n.t("catalog.aiError"))).toBeTruthy();
      expect(screen.queryByText(/could not complete/)).toBeNull();
    });
  }
});
