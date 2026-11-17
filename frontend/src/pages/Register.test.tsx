/**
 * Every new account accepts the sign-up discount's terms on Register, and
 * the page can always get the shopper through: if the terms it showed are
 * no longer current, or it never got them, the server's answer carries the
 * current terms and the page asks again.
 *
 * The real page, store and router render; only the HTTP client is
 * replaced, answering as accounts/views.py does.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../i18n";
import DiscountModal from "../components/DiscountModal";
import Register from "./Register";
import { store } from "../store";
import { logout } from "../store/authSlice";
import { clearAuthStorage } from "../utils/token";

const CONSENT = "I understand how this discount works.";

const TERMS_V1 = {
  version: "v1",
  locale: "en",
  text: "Create an account and 10% comes off your first order automatically at checkout — no code needed.",
  percent: 10,
};
const TERMS_V2 = {
  version: "v2",
  locale: "en",
  text: "Create an account and 15% comes off your first order automatically at checkout — no code needed.",
  percent: 15,
};

/** What the server is running now; a test can change it under the page. */
const server: {
  terms: typeof TERMS_V1 | null;
  termsFails: boolean;
  registrations: Record<string, unknown>[];
} = { terms: TERMS_V1, termsFails: false, registrations: [] };

function conflict(code: string) {
  return Object.assign(new Error("409"), {
    isAxiosError: true,
    response: { status: 409, data: { code, terms: server.terms } },
  });
}

vi.mock("../api/axiosInstance", () => ({
  default: {
    get: vi.fn(async (url: string) => {
      if (url.startsWith("/accounts/terms/")) {
        if (server.termsFails) throw new Error("network");
        return { data: { terms: server.terms } };
      }
      if (url.startsWith("/accounts/profile/")) {
        return { data: { id: 7, email: "nina@example.test", first_name: "Nina", last_name: "New" } };
      }
      if (url.startsWith("/orders/welcome-offer/")) {
        return { data: { welcome_offer: { title: "New Shopper", discount_percent: 10, days_after_signup: 60 } } };
      }
      return { data: [] };
    }),
    post: vi.fn(async (url: string, body: Record<string, unknown>) => {
      if (url.startsWith("/accounts/register/")) {
        server.registrations.push(body);
        const sent = body.terms_version ?? "";
        if (server.terms && sent !== server.terms.version) {
          throw conflict(sent ? "terms_outdated" : "terms_required");
        }
        return { data: { id: 7, email: body.email } };
      }
      if (url.startsWith("/accounts/login/")) {
        return { data: { access: "token-nina", refresh: "token-nina" } };
      }
      return { data: {} };
    }),
  },
}));

function renderRegister() {
  return render(
    <Provider store={store}>
      <MemoryRouter initialEntries={["/register"]}>
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/" element={<p>Home page</p>} />
        </Routes>
      </MemoryRouter>
    </Provider>
  );
}

function fillForm(): void {
  const fields: [string, string][] = [
    ["First name", "Nina"],
    ["Last name", "New"],
    ["Phone number", "+1 555 0100"],
    ["Email", "nina@example.test"],
    ["Password", "testpass123"],
  ];
  for (const [label, value] of fields) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
}

function submit(): void {
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
}

beforeEach(() => {
  server.terms = TERMS_V1;
  server.termsFails = false;
  server.registrations = [];
  clearAuthStorage();
  localStorage.clear();
  store.dispatch(logout());
});

afterEach(() => {
  cleanup();
});

describe("Register: accepting the sign-up discount's terms", () => {
  it("names the checkbox with the consent line, and describes it with the terms", async () => {
    renderRegister();

    const box = await screen.findByRole("checkbox", { name: CONSENT });
    const description = (box.getAttribute("aria-describedby") ?? "")
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent)
      .join(" ");

    // The terms exactly as the server rendered them, as the description.
    expect(description).toBe(TERMS_V1.text);
    expect(screen.getByText(TERMS_V1.text)).toBeTruthy();
    expect(box).toHaveProperty("checked", false);

    fireEvent.click(screen.getByText(CONSENT));
    expect(box).toHaveProperty("checked", true);
  });

  it("the line above the form names the running offer's figure", async () => {
    server.terms = TERMS_V2;
    renderRegister();

    expect(await screen.findByText("15% off your first order — automatic, no code needed.")).toBeTruthy();
    expect(screen.queryByText(/^10% off your first order/)).toBeNull();
  });

  it("won't create the account until the box is ticked", async () => {
    renderRegister();
    await screen.findByRole("checkbox", { name: CONSENT });
    fillForm();

    submit();

    expect(await screen.findByText(/Please tick the box/)).toBeTruthy();
    expect(server.registrations).toHaveLength(0);
  });

  it("sends the version it showed and the shopper's language", async () => {
    renderRegister();
    fireEvent.click(await screen.findByRole("checkbox", { name: CONSENT }));
    fillForm();

    submit();

    expect(await screen.findByText("Home page")).toBeTruthy();
    expect(server.registrations).toHaveLength(1);
    expect(server.registrations[0]).toMatchObject({ terms_version: "v1", locale: "en" });
  });

  it("an old version: shows the current terms, asks again, then signs up", async () => {
    renderRegister();
    fireEvent.click(await screen.findByRole("checkbox", { name: CONSENT }));
    fillForm();

    // The offer changes while the page is open.
    server.terms = TERMS_V2;
    submit();

    expect(await screen.findByText(/The discount terms have changed/)).toBeTruthy();
    expect(screen.getByText(TERMS_V2.text)).toBeTruthy();
    expect(screen.queryByText(TERMS_V1.text)).toBeNull();
    // The line above the form follows the terms.
    expect(screen.getByText(/^15% off your first order/)).toBeTruthy();
    const box = screen.getByRole("checkbox", { name: CONSENT });
    expect(box).toHaveProperty("checked", false);
    expect(document.activeElement).toBe(box);
    // Nothing is stuck: the button still works.
    expect(screen.getByRole("button", { name: "Create account" })).toHaveProperty("disabled", false);

    fireEvent.click(box);
    submit();

    expect(await screen.findByText("Home page")).toBeTruthy();
    expect(server.registrations.map((body) => body.terms_version)).toEqual(["v1", "v2"]);
  });

  it("terms that never loaded: the server's answer brings them", async () => {
    server.termsFails = true;
    renderRegister();
    await act(async () => {});
    expect(screen.queryByRole("checkbox")).toBeNull();
    fillForm();

    submit();

    const box = await screen.findByRole("checkbox", { name: CONSENT });
    expect(screen.getByText(TERMS_V1.text)).toBeTruthy();
    expect(screen.getByText(/Please tick the box/)).toBeTruthy();

    fireEvent.click(box);
    submit();

    expect(await screen.findByText("Home page")).toBeTruthy();
    expect(server.registrations.at(-1)).toMatchObject({ terms_version: "v1" });
  });

  it("no sign-up discount running: nothing to accept", async () => {
    server.terms = null;
    renderRegister();
    await act(async () => {});
    fillForm();

    submit();

    expect(await screen.findByText("Home page")).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByText(/off your first order/)).toBeNull();
    expect(server.registrations[0].terms_version).toBeUndefined();
  });
});

describe("The sign-up modal sells the offer; it takes no consent", () => {
  it("shows the terms as text, with no box to tick, and goes to Register", async () => {
    render(
      <Provider store={store}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<DiscountModal />} />
            <Route path="/register" element={<p>Register page</p>} />
          </Routes>
        </MemoryRouter>
      </Provider>
    );

    const cta = await screen.findByRole("button", { name: /Create account/ }, { timeout: 3000 });
    expect(screen.getByText(/comes off your first order automatically/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();

    fireEvent.click(cta);

    await waitFor(() => expect(screen.getByText("Register page")).toBeTruthy());
  });
});
