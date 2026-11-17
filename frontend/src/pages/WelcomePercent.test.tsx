/**
 * Every page that advertises the sign-up discount names the figure the
 * running offer has, from the same place Register's terms come from
 * (/accounts/terms/). With no offer running they name no figure.
 *
 * The real pages and router render; only the HTTP client is replaced.
 */
import { act, cleanup, render, screen } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import LoginChoice from "./LoginChoice";
import NewShoppers from "./offers/NewShoppers";
import { store } from "../store";

/** The sign-up discount running now; null for none. */
let running: number | null = 15;
const termsLocales: string[] = [];

vi.mock("../api/axiosInstance", () => ({
  default: {
    get: vi.fn(async (url: string, config?: { params?: { locale?: string } }) => {
      if (url.startsWith("/accounts/terms/")) {
        termsLocales.push(config?.params?.locale ?? "");
        return {
          data: {
            terms:
              running === null
                ? null
                : { version: "v", locale: "en", text: `${running}% …`, percent: running },
          },
        };
      }
      return { data: [] };
    }),
  },
}));

function show(page: React.ReactElement) {
  return render(
    <Provider store={store}>
      <MemoryRouter>{page}</MemoryRouter>
    </Provider>
  );
}

beforeEach(async () => {
  running = 15;
  termsLocales.length = 0;
  await i18n.changeLanguage("en");
});

afterEach(() => {
  cleanup();
});

describe("The Welcome page", () => {
  it("names the running offer's figure, not a fixed one", async () => {
    show(<LoginChoice />);

    expect(await screen.findByText("Sign in, or create an account and start with 15% off.")).toBeTruthy();
    expect(screen.getByText("15% off your first order")).toBeTruthy();
    expect(screen.queryByText(/10%/)).toBeNull();
    expect(termsLocales).toEqual(["en"]);
  });

  it("in the shopper's language", async () => {
    await i18n.changeLanguage("ru");
    show(<LoginChoice />);

    expect(await screen.findByText("Войдите или создайте аккаунт — и начните со скидкой 15%.")).toBeTruthy();
    expect(screen.getByText("15% на первый заказ")).toBeTruthy();
    expect(termsLocales).toEqual(["ru"]);
  });

  it("no offer running: no figure and no discount perk", async () => {
    running = null;
    show(<LoginChoice />);
    await act(async () => {});

    expect(screen.getByText("Sign in, or create an account.")).toBeTruthy();
    expect(screen.queryByText(/%/)).toBeNull();
    // The other reason to sign up is still there.
    expect(screen.getByText("Faster checkout, every time")).toBeTruthy();
  });
});

describe("The New Shoppers page", () => {
  it("names the running offer's figure, not a fixed one", async () => {
    show(<NewShoppers />);

    expect(await screen.findByRole("heading", { name: "15% off your first order" })).toBeTruthy();
    expect(screen.getByText(/your first order comes with 15% off\./)).toBeTruthy();
    expect(screen.queryByText(/10%/)).toBeNull();
  });

  it("no offer running: no figure", async () => {
    running = null;
    show(<NewShoppers />);
    await act(async () => {});

    expect(screen.getByRole("heading", { name: "A welcome discount on your first order" })).toBeTruthy();
    expect(screen.queryByText(/%/)).toBeNull();
  });
});

describe("Every language takes the figure", () => {
  it("has no fixed figure left in the Welcome page or Register lines", () => {
    for (const language of ["en", "ru", "es", "fr"]) {
      const t = i18n.getFixedT(language);
      for (const key of ["loginChoice.subtitle", "loginChoice.perkDiscountTitle", "register.welcomePerk"]) {
        const line = t(key, { percent: 15 });
        expect(line, `${language} ${key}`).toContain("15%");
        expect(line, `${language} ${key}`).not.toContain("10%");
      }
      expect(t("loginChoice.subtitleNoFigure"), language).not.toMatch(/%/);
    }
  });
});
