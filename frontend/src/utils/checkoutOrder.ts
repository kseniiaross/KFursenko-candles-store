/**
 * The order Checkout last created in this tab, and the request that made it.
 *
 * Kept in sessionStorage rather than component state so that going back to
 * the cart, or reloading, does not lose it: returning with the same basket
 * and address reuses the order instead of reserving the stock a second time.
 * Cleared once payment succeeds.
 */

const STORAGE_KEY = "checkout_order";

export type CheckoutOrderRef = {
  orderId: number;
  /** JSON of the POST /orders/ body that created it. */
  key: string;
};

export function loadCheckoutOrder(): CheckoutOrderRef | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as Partial<CheckoutOrderRef>;
    const orderId = Number(parsed.orderId);

    if (!orderId || typeof parsed.key !== "string") return null;

    return { orderId, key: parsed.key };
  } catch {
    return null;
  }
}

export function saveCheckoutOrder(ref: CheckoutOrderRef): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ref));
  } catch {
    // Storage blocked: the order still works, it just won't be reused.
  }
}

export function clearCheckoutOrder(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
}
