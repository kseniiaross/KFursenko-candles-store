/**
 * The product page's last English: the button while a candle is being
 * added, and the photo preview's labels. Screen readers announce the
 * labels, so they are as much the page as its visible text.
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
import { logout, setCredentials } from "../store/authSlice";
import { clearAuthStorage, setAccessToken, setRefreshToken } from "../utils/token";

let release: () => void = () => {};

vi.mock("../api/axiosInstance", () => ({
  default: {
    get: vi.fn(async (url: string) => {
      if (/^\/candles\/candles\/[^/]+\/$/.test(url)) {
        return {
          data: {
            id: 1, slug: "mango-island", name: "Mango Island", description: "Ripe mango.",
            image: "https://example.test/mango.jpg", images: [],
            variants: [{ id: 5, size: "8 oz", price: "18.49", is_active: true, stock_qty: 3 }],
          },
        };
      }
      return { data: [] };
    }),
    // Adding waits for the server, so the button's in-between state shows.
    post: vi.fn(async () => {
      await new Promise<void>((resolve) => (release = resolve));
      return { data: { id: 1, items: [] } };
    }),
  },
}));

function showProduct() {
  setAccessToken("token-nina");
  setRefreshToken("token-nina");
  store.dispatch(setCredentials({ access: "token-nina", refresh: "token-nina" }));
  render(
    <Provider store={store}>
      <MemoryRouter initialEntries={["/catalog/item/mango-island"]}>
        <Routes>
          <Route path="/catalog/item/:slug" element={<CatalogDetail />} />
        </Routes>
      </MemoryRouter>
    </Provider>
  );
}

beforeEach(async () => {
  localStorage.clear();
  clearAuthStorage();
  store.dispatch(logout());
  await i18n.changeLanguage("en");
});

afterEach(() => {
  cleanup();
});

describe("The product page's button and photo preview", () => {
  for (const [language, adding, large, close] of [
    ["en", "Adding...", "Large image of Mango Island", "Close image preview"],
    ["ru", "Добавляем...", "Фото «Mango Island» крупным планом", "Закрыть просмотр фото"],
    ["es", "Añadiendo...", "Imagen grande de Mango Island", "Cerrar la vista previa de la imagen"],
    ["fr", "Ajout en cours...", "Grande image de Mango Island", "Fermer l'aperçu de l'image"],
  ]) {
    it(`${language}: the button says it is adding, in the shopper's language`, async () => {
      await i18n.changeLanguage(language);
      showProduct();

      fireEvent.click(await screen.findByRole("button", { name: i18n.t("catalogDetail.addToCart") }));

      expect(screen.getByRole("button", { name: adding })).toBeTruthy();
      await act(async () => release());
    });

    it(`${language}: the photo preview is named and closed in the shopper's language`, async () => {
      await i18n.changeLanguage(language);
      showProduct();

      fireEvent.click(await screen.findByRole("button", { name: `${i18n.t("catalogDetail.selectImage")}: Mango Island` }));

      expect(screen.getByRole("dialog", { name: large })).toBeTruthy();
      expect(screen.getAllByRole("button", { name: close })).toHaveLength(2);
    });
  }
});
