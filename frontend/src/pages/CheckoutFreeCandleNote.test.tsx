/**
 * Which line says why it is at full price. When candles pay for a free one
 * in buy two, get three, those candles go without the sign-up discount: the
 * note sits on them, where the shopper sees full price and wonders why. The
 * free line only says "Free".
 *
 * The real Checkout page, store and router render; only the HTTP client is
 * replaced, answering the price preview the way the engine does
 * (orders/test_welcome_fallthrough.py checks the engine's side).
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../i18n";
import Checkout from "./Checkout";
import { store } from "../store";
import { logout, setCredentials } from "../store/authSlice";
import { setCart, type CartLine } from "../store/cartSlice";
import { clearAuthStorage, setAccessToken, setRefreshToken } from "../utils/token";

const NOTE = "Earns your free candle instead of New Shopper";

type Line = {
  variant_id: number;
  name: string;
  quantity: number;
  unit_price: string;
  discount_amount: string;
  discount_label: string;
  free_quantity: number;
  gave_up_label: string;
};

/** The preview the server answers with for the basket in the test. */
let preview: Line[] = [];

vi.mock("../api/axiosInstance", () => {
  const respond = async (url: string) => {
    if (url.startsWith("/orders/price-preview/")) {
      const lines = preview.map((line) => {
        const total = Number(line.unit_price) * line.quantity;
        const after = total - Number(line.discount_amount);
        return {
          ...line,
          line_total: total.toFixed(2),
          line_total_after_discount: after.toFixed(2),
        };
      });
      const sum = lines.reduce((acc, line) => acc + Number(line.line_total_after_discount), 0);
      return {
        data: { lines, subtotal: "0.00", discount: "0.00", items_total: sum.toFixed(2), label: "", unavailable: [] },
      };
    }
    if (url.startsWith("/accounts/profile/")) {
      return { data: { id: 1, first_name: "Nina", last_name: "New", email: "nina@example.test" } };
    }
    return { data: [] };
  };
  return {
    default: {
      get: vi.fn((url: string) => respond(url)),
      post: vi.fn((url: string) => respond(url)),
      patch: vi.fn((url: string) => respond(url)),
      delete: vi.fn((url: string) => respond(url)),
    },
  };
});

function checkoutWith(lines: Line[]) {
  preview = lines;
  setAccessToken("token-nina");
  setRefreshToken("token-nina");
  store.dispatch(setCredentials({ access: "token-nina", refresh: "token-nina" }));
  store.dispatch(
    setCart(
      lines.map(
        (line): CartLine => ({
          variant_id: line.variant_id,
          candle_id: line.variant_id,
          name: line.name,
          size: "",
          price: Number(line.unit_price),
          quantity: line.quantity,
        })
      )
    )
  );

  render(
    <Provider store={store}>
      <MemoryRouter initialEntries={["/checkout"]}>
        <Routes>
          <Route path="/checkout" element={<Checkout />} />
        </Routes>
      </MemoryRouter>
    </Provider>
  );
}

/** The order-summary line for a candle, once its price has arrived. */
async function lineFor(name: string): Promise<HTMLElement> {
  const heading = await screen.findByRole("heading", { name });
  const line = heading.closest("li") as HTMLElement;
  await waitFor(() => expect(line.querySelector(".linePrice")).not.toBeNull());
  return line;
}

beforeEach(() => {
  localStorage.clear();
  clearAuthStorage();
  store.dispatch(logout());
});

afterEach(() => {
  cleanup();
});

describe("checkout: the note on a basket with a free candle", () => {
  it("sits on each candle that paid for the free one, not on the free one", async () => {
    checkoutWith([
      { variant_id: 19, name: "Mango Island", quantity: 1, unit_price: "21.99", discount_amount: "0.00", discount_label: "", free_quantity: 0, gave_up_label: "New Shopper" },
      { variant_id: 22, name: "Tidal Bore", quantity: 1, unit_price: "21.99", discount_amount: "0.00", discount_label: "", free_quantity: 0, gave_up_label: "New Shopper" },
      { variant_id: 5, name: "Matcha Chill", quantity: 1, unit_price: "18.49", discount_amount: "18.49", discount_label: "Buy Two Get Three", free_quantity: 1, gave_up_label: "" },
    ]);

    for (const name of ["Mango Island", "Tidal Bore"]) {
      expect(within(await lineFor(name)).getByText(NOTE)).toBeTruthy();
    }

    const free = await lineFor("Matcha Chill");
    expect(within(free).getByText("Free")).toBeTruthy();
    expect(within(free).queryByText(NOTE)).toBeNull();
    expect(screen.getAllByText(NOTE)).toHaveLength(2);
  });

  it("three of one candle on one line, two paying and one free: that line carries both", async () => {
    checkoutWith([
      { variant_id: 7, name: "Mango Island", quantity: 3, unit_price: "18.49", discount_amount: "18.49", discount_label: "Spring", free_quantity: 1, gave_up_label: "New Shopper" },
    ]);

    const line = await lineFor("Mango Island");
    expect(within(line).getByText("1 free")).toBeTruthy();
    expect(within(line).getByText(NOTE)).toBeTruthy();
  });

  it("no note where nothing was given up: a line with the sign-up discount, or a campaign", async () => {
    checkoutWith([
      { variant_id: 19, name: "Mango Island", quantity: 1, unit_price: "21.99", discount_amount: "2.20", discount_label: "New Shopper", free_quantity: 0, gave_up_label: "" },
      { variant_id: 30, name: "Spice Delight", quantity: 1, unit_price: "18.85", discount_amount: "1.89", discount_label: "Spooky Season", free_quantity: 0, gave_up_label: "" },
    ]);

    expect(within(await lineFor("Mango Island")).getByText("New Shopper")).toBeTruthy();
    expect(within(await lineFor("Spice Delight")).getByText("Spooky Season")).toBeTruthy();
    expect(screen.queryByText(/Earns your free candle/)).toBeNull();
  });
});
