import { useEffect, useRef } from "react";
import axios from "axios";

import { getMyCart, mergeCart } from "../api/cart";
import type { MergeAdjustment } from "../api/cart";
import {
  GUEST_CART_KEY,
  clearGuestCartStorage,
  getGuestCartStorage,
  setCart,
  setCartNotices,
  setGuestCart,
} from "../store/cartSlice";
import type { CartLine } from "../store/cartSlice";
import { useAppDispatch, useAppSelector } from "../store/hooks";
import { getAccessToken } from "../utils/token";

/** What the shopper is told about a guest line the merge changed. The
 *  name comes from the guest's own copy when the candle no longer exists. */
function describeAdjustment(
  adjustment: MergeAdjustment,
  guestItems: CartLine[]
): string {
  const guest = guestItems.find(
    (item) => Number(item.variant_id) === adjustment.variant_id
  );
  const name = adjustment.name || guest?.name || "A candle";
  const size = adjustment.size || guest?.size || "";
  const label = size ? `${name} / ${size}` : name;

  if (adjustment.reason === "sold_out") {
    return `${label} has sold out — we've taken it out of your cart.`;
  }

  if (adjustment.reason === "limited") {
    return `Only ${adjustment.quantity} left of ${label} — we've put ${adjustment.quantity} in your cart.`;
  }

  return `${label} is no longer available — we've taken it out of your cart.`;
}

export function useHydrateCart(): void {
  const dispatch = useAppDispatch();
  const isLoggedIn = useAppSelector((state) => Boolean(state.auth?.isLoggedIn));
  // The sign-in state the cart was last loaded for. Loading again when it
  // changes is what merges a guest cart at the moment of signing in, not
  // only on the next page load. A ref rather than effect cleanup, so
  // StrictMode's second run neither merges twice nor discards the answer.
  const loadedFor = useRef<boolean | null>(null);
  const generation = useRef(0);

  useEffect(() => {
    if (loadedFor.current === isLoggedIn) return;

    loadedFor.current = isLoggedIn;
    const current = ++generation.current;
    const isCurrent = (): boolean => current === generation.current;

    async function hydrate(): Promise<void> {
      const token = getAccessToken();
      const guestItems = getGuestCartStorage();

      if (!isLoggedIn || !token) {
        dispatch(setGuestCart(guestItems));
        return;
      }

      const validGuestItems: CartLine[] = guestItems.filter((item) => {
        return (
          Number(item.variant_id) > 0 &&
          Number(item.candle_id) > 0 &&
          Number(item.quantity) > 0
        );
      });

      try {
        if (validGuestItems.length > 0) {
          try {
            const { adjustments } = await mergeCart({
              items: validGuestItems.map((item) => ({
                variant_id: Number(item.variant_id),
                quantity: Number(item.quantity),
                is_gift: Boolean(item.isGift),
              })),
            });

            // Merged, so the guest copy must go: kept, it would be merged
            // again on the next load and every line counted twice.
            clearGuestCartStorage();

            if (adjustments.length > 0 && isCurrent()) {
              dispatch(
                setCartNotices(
                  adjustments.map((adjustment) =>
                    describeAdjustment(adjustment, validGuestItems)
                  )
                )
              );
            }
          } catch (mergeError: unknown) {
            // Only a malformed request is refused now; a candle that sold
            // out is an adjustment, not an error. Anything else (offline,
            // a 5xx) keeps the guest copy for the next try.
            console.error("Failed to merge guest cart:", mergeError);

            if (axios.isAxiosError(mergeError) && mergeError.response?.status === 400) {
              clearGuestCartStorage();
            }
          }
        }

        const serverItems = await getMyCart();

        if (isCurrent()) {
          dispatch(setCart(serverItems));
        }
      } catch (error: unknown) {
        console.error("Failed to hydrate cart:", error);

        if (isCurrent()) {
          dispatch(setCart([]));
        }
      }
    }

    void hydrate();
  }, [dispatch, isLoggedIn]);

  // Another tab changed the cart. Without this, a tab still showing the
  // old cart saves it over the other tab's changes, and the next reload
  // shows whichever tab wrote last. A guest's cart is in localStorage, so
  // the storage event brings the new copy; a signed-in cart is on the
  // server, so it is reloaded when this tab comes back into view.
  useEffect(() => {
    const onStorage = (event: StorageEvent): void => {
      if (isLoggedIn) return;
      if (event.key !== GUEST_CART_KEY && event.key !== null) return;

      dispatch(setCart(getGuestCartStorage()));
    };

    const onVisible = (): void => {
      if (!isLoggedIn || document.visibilityState !== "visible") return;

      getMyCart()
        .then((items) => dispatch(setCart(items)))
        .catch((error: unknown) => {
          console.error("Could not reload the cart:", error);
        });
    };

    window.addEventListener("storage", onStorage);
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      window.removeEventListener("storage", onStorage);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [dispatch, isLoggedIn]);
}