import { useEffect, useRef } from "react";
import axios from "axios";

import { getMyCart, mergeCart } from "../api/cart";
import {
  GUEST_CART_KEY,
  clearGuestCartStorage,
  getGuestCartStorage,
  setCart,
  setGuestCart,
} from "../store/cartSlice";
import type { CartLine } from "../store/cartSlice";
import { useAppDispatch, useAppSelector } from "../store/hooks";
import { getAccessToken } from "../utils/token";

export function useHydrateCart(): void {
  const dispatch = useAppDispatch();
  const isLoggedIn = useAppSelector((state) => Boolean(state.auth?.isLoggedIn));
  const hasHydrated = useRef(false);

  useEffect(() => {
    if (hasHydrated.current) return;

    hasHydrated.current = true;

    let cancelled = false;

    async function hydrate(): Promise<void> {
      const token = getAccessToken();
      const guestItems = getGuestCartStorage();

      if (!isLoggedIn || !token) {
        if (!cancelled) {
          dispatch(setGuestCart(guestItems));
        }

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
            await mergeCart({
              items: validGuestItems.map((item) => ({
                variant_id: Number(item.variant_id),
                quantity: Number(item.quantity),
                is_gift: Boolean(item.isGift),
              })),
            });

            clearGuestCartStorage();
          } catch (mergeError: unknown) {
            console.error("Failed to merge guest cart:", mergeError);

            if (axios.isAxiosError(mergeError)) {
              const status = mergeError.response?.status;

              if (status === 400) {
                clearGuestCartStorage();
              }
            }
          }
        }

        const serverItems = await getMyCart();

        if (!cancelled) {
          dispatch(setCart(serverItems));
          clearGuestCartStorage();
        }
      } catch (error: unknown) {
        console.error("Failed to hydrate cart:", error);

        if (!cancelled) {
          dispatch(setCart([]));
          clearGuestCartStorage();
        }
      }
    }

    void hydrate();

    return () => {
      cancelled = true;
    };
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