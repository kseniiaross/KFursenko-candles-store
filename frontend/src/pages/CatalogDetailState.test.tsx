/**
 * The product page is never blank. While the candle loads it says so;
 * when the candle doesn't exist or the server doesn't answer, it says the
 * candle isn't available and links back to the catalogue. It used to render
 * nothing in all three cases, leaving the header and footer with nothing
 * between them, for good when the load failed.
 *
 * The real page, store and router render; only the HTTP client is replaced.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import CatalogDetail from "./CatalogDetail";
import { store } from "../store";

const UNAVAILABLE = "This candle isn't available.";

/** How the server answers for each slug; anything unlisted is a 404. */
const server: Record<string, "ok" | "fail" | "hold"> = {};
let release: () => void = () => {};

function httpError(status: number) {
  return Object.assign(new Error(String(status)), { isAxiosError: true, response: { status, data: {} } });
}

vi.mock("../api/axiosInstance", () => ({
  default: {
    get: vi.fn(async (url: string) => {
      const match = url.match(/^\/candles\/candles\/([^/]+)\/$/);
      if (match) {
        const slug = decodeURIComponent(match[1]);
        const answer = server[slug];
        if (answer === "hold") await new Promise<void>((resolve) => (release = resolve));
        if (answer === "fail") throw httpError(500);
        if (!answer) throw httpError(404);
        return {
          data: {
            id: 1, slug, name: "Mango Island", description: "Ripe mango.", image: null, images: [],
            variants: [{ id: 5, size: "8 oz", price: "18.49", is_active: true, stock_qty: 3 }],
          },
        };
      }
      return { data: [] };
    }),
    post: vi.fn(async () => ({ data: {} })),
  },
}));

function showProduct(slug: string) {
  return render(
    <Provider store={store}>
      <MemoryRouter initialEntries={[`/catalog/item/${slug}`]}>
        <Routes>
          <Route path="/catalog/item/:slug" element={<CatalogDetail />} />
          <Route path="/catalog" element={<p>Catalogue page</p>} />
        </Routes>
      </MemoryRouter>
    </Provider>
  );
}

beforeEach(async () => {
  for (const key of Object.keys(server)) delete server[key];
  await i18n.changeLanguage("en");
});

afterEach(() => {
  cleanup();
});

describe("The product page is never blank", () => {
  it("says it is loading while the candle is on its way", async () => {
    server["mango-island"] = "hold";
    showProduct("mango-island");

    expect(screen.getByRole("status").textContent).toBe("Loading product...");

    await act(async () => release());
    expect(await screen.findByRole("heading", { name: "Mango Island" })).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("a candle that doesn't exist: says so and links back to the catalogue", async () => {
    showProduct("no-such-candle");

    expect(await screen.findByRole("heading", { name: UNAVAILABLE })).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "Back to catalog" }));
    expect(await screen.findByText("Catalogue page")).toBeTruthy();
  });

  it("a server that fails: the same message, not a page that never resolves", async () => {
    server["mango-island"] = "fail";
    showProduct("mango-island");

    expect(await screen.findByRole("heading", { name: UNAVAILABLE })).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("in the shopper's language", async () => {
    await i18n.changeLanguage("es");
    showProduct("no-such-candle");

    expect(await screen.findByRole("heading", { name: "Esta vela no está disponible." })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Volver al catálogo" })).toBeTruthy();
  });
});
