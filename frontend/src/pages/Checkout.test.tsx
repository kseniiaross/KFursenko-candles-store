/**
 * The checkout address comes from the signed-in shopper's own account, and
 * nothing of a previous account survives sign-out.
 *
 * Checkout used to read the address from a sessionStorage copy that only
 * the Profile page wrote and sign-out never cleared: a shopper going
 * straight to checkout got an empty form, and the next person to sign in
 * on that tab got the previous shopper's name and address.
 *
 * The real pages, store and router render; only the HTTP client is
 * replaced, answering for whichever account's token is stored.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Checkout from "./Checkout";
import Profile from "./Profile";
import { store } from "../store";
import { logout, setCredentials } from "../store/authSlice";
import { setCart } from "../store/cartSlice";
import { clearAuthStorage, setAccessToken, setRefreshToken } from "../utils/token";

const PROFILES: Record<string, Record<string, string>> = {
  "token-alice": {
    first_name: "Alice", last_name: "Adams", email: "alice@example.test",
    address_line1: "12 Elm St", apartment: "3C", city: "Albany",
    state: "NY", postal_code: "12207", country: "United States",
  },
  // Name only: Bob never saved an address.
  "token-bob": {
    first_name: "Bob", last_name: "Brown", email: "bob@example.test",
    address_line1: "", apartment: "", city: "", state: "", postal_code: "", country: "",
  },
};

const CART = [
  { variant_id: 11, candle_id: 1, name: "Mango Island", size: "11.3 oz", price: 21.99, quantity: 1 },
];

/** Profile requests made, by token; a test can hold the next answer back. */
const profileRequests: string[] = [];
let holdProfile: Promise<void> | null = null;

vi.mock("../api/axiosInstance", () => {
  const token = () => localStorage.getItem("access") ?? "";
  const respond = async (url: string) => {
    if (url.startsWith("/accounts/profile/")) {
      profileRequests.push(token());
      if (holdProfile) await holdProfile;
      return { data: { id: 1, ...PROFILES[token()] } };
    }
    if (url.startsWith("/orders/price-preview/")) {
      return { data: { lines: [], subtotal: "0.00", discount: "0.00", items_total: "0.00", label: "", unavailable: [] } };
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

function signIn(token: string): void {
  setAccessToken(token);
  setRefreshToken(token);
  store.dispatch(setCredentials({ access: token, refresh: token }));
  store.dispatch(setCart(CART));
}

/** What the header's "Log out" does, and nothing more. */
function signOut(): void {
  clearAuthStorage();
  store.dispatch(logout());
}

function renderAt(path: string) {
  return render(
    <Provider store={store}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/login-choice" element={<p>Sign in to continue</p>} />
        </Routes>
      </MemoryRouter>
    </Provider>
  );
}

const field = (id: string) => document.getElementById(id) as HTMLInputElement;
const fieldValues = () =>
  [...document.querySelectorAll<HTMLInputElement>(".checkoutForm__input")].map((input) => input.value);

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  profileRequests.length = 0;
  holdProfile = null;
  signOut();
});

afterEach(() => {
  cleanup();
});

describe("checkout address", () => {
  it("is prefilled from the shopper's account on first arrival", async () => {
    signIn("token-alice");
    renderAt("/checkout");

    await waitFor(() => expect(field("checkout-full-name").value).toBe("Alice Adams"));
    expect(field("checkout-address-1").value).toBe("12 Elm St");
    expect(field("checkout-address-2").value).toBe("3C");
    expect(field("checkout-city").value).toBe("Albany");
    expect(field("checkout-state").value).toBe("NY");
    expect(field("checkout-postal-code").value).toBe("12207");
    expect(field("checkout-country").value).toBe("United States");
  });

  it("never shows a previous account's address after sign-out", async () => {
    // Alice opens her profile, then signs out.
    signIn("token-alice");
    const profilePage = renderAt("/profile");
    await waitFor(() => expect(screen.getByDisplayValue("12 Elm St")).toBeTruthy());
    profilePage.unmount();
    signOut();

    // Bob signs in on the same tab and goes to checkout. Nothing of
    // Alice's may show, neither before his account answers nor after.
    signIn("token-bob");
    renderAt("/checkout");
    await waitFor(() => expect(fieldValues().length).toBeGreaterThan(0));
    expect(fieldValues().join(" | ")).not.toMatch(/Alice|Adams|Elm|Albany|12207/);

    await waitFor(() => expect(field("checkout-full-name").value).toBe("Bob Brown"));
    expect(fieldValues().join(" | ")).not.toMatch(/Alice|Adams|Elm|Albany|12207/);
    expect(field("checkout-address-1").value).toBe("");
    expect(field("checkout-country").value).toBe("United States");
  });

  it("keeps what the shopper typed if they start before the account answers", async () => {
    let release = () => {};
    holdProfile = new Promise<void>((resolve) => {
      release = resolve;
    });

    signIn("token-alice");
    renderAt("/checkout");
    await waitFor(() => expect(profileRequests).toContain("token-alice"));

    // A gift going elsewhere: a different name and city, typed first.
    fireEvent.change(field("checkout-full-name"), { target: { value: "Carol Clark" } });
    fireEvent.change(field("checkout-city"), { target: { value: "Boston" } });

    await act(async () => {
      release();
    });

    await waitFor(() => expect(field("checkout-address-1").value).toBe("12 Elm St"));
    expect(field("checkout-full-name").value).toBe("Carol Clark");
    expect(field("checkout-city").value).toBe("Boston");
    expect(field("checkout-postal-code").value).toBe("12207");
  });

  it("leaves every prefilled field editable", async () => {
    signIn("token-alice");
    renderAt("/checkout");
    await waitFor(() => expect(field("checkout-full-name").value).toBe("Alice Adams"));

    for (const input of document.querySelectorAll<HTMLInputElement>(".checkoutForm__input")) {
      expect(input.readOnly).toBe(false);
      expect(input.disabled).toBe(false);
    }

    fireEvent.change(field("checkout-address-1"), { target: { value: "1 Gift Lane" } });
    expect(field("checkout-address-1").value).toBe("1 Gift Lane");
  });

  it("asks nothing about a guest, who is sent to sign in", async () => {
    renderAt("/checkout");

    await waitFor(() => expect(screen.getByText("Sign in to continue")).toBeTruthy());
    expect(profileRequests).toEqual([]);
  });
});
