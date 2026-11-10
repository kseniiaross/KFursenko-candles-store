import React, { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { clearServerCart } from "../api/cart";
import { clearCart } from "../store/cartSlice";
import { useAppDispatch } from "../store/hooks";
import { clearCheckoutOrder } from "../utils/checkoutOrder";

import "../styles/PaymentSuccess.css";

const PaymentSuccess: React.FC = () => {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();
  const [searchParams] = useSearchParams();

  const orderId = searchParams.get("order");

  useEffect(() => {
    let cancelled = false;

    async function clearAllCarts(): Promise<void> {
      dispatch(clearCart());
      // The paid order must never be reused or cancelled by a later checkout.
      clearCheckoutOrder();

      try {
        localStorage.removeItem("guest_cart_items");
        sessionStorage.removeItem("guest_cart_items");
      } catch {
        // Ignore storage errors.
      }

      try {
        await clearServerCart();

        if (!cancelled) {
          dispatch(clearCart());
        }
      } catch (error) {
        console.error("Failed to clear server cart after payment:", error);
      }
    }

    void clearAllCarts();

    return () => {
      cancelled = true;
    };
  }, [dispatch]);

  return (
    <main className="paymentSuccess">
      <div className="paymentSuccess__inner">
        <section className="paymentSuccess__card">
          <p className="paymentSuccess__kicker">{t("checkout.payment")}</p>

          <h1 className="paymentSuccess__title">{t("paymentSuccess.title")}</h1>

          <p className="paymentSuccess__description">
            {[
              t("paymentSuccess.subtitle"),
              orderId ? t("paymentSuccess.orderProcessing", { id: orderId }) : "",
              t("paymentSuccess.nextSteps"),
            ]
              .filter(Boolean)
              .join(" ")}
          </p>

          <div className="paymentSuccess__actions">
            <Link
              to="/orders"
              className="paymentSuccess__button paymentSuccess__button--primary"
            >
              {t("paymentSuccess.viewOrders")}
            </Link>

            <Link
              to="/catalog"
              className="paymentSuccess__button paymentSuccess__button--secondary"
            >
              {t("paymentSuccess.backToCatalog")}
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
};

export default PaymentSuccess;