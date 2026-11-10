import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  CardElement,
  useElements,
  useStripe,
} from "@stripe/react-stripe-js";

import "../styles/CheckoutPaymentBlock.css";

type CheckoutPaymentBlockProps = {
  orderId: number;
  clientSecret: string;
};

const CheckoutPaymentBlock: React.FC<CheckoutPaymentBlockProps> = ({
  orderId,
  clientSecret,
}) => {
  const { t } = useTranslation();
  const stripe = useStripe();
  const elements = useElements();

  const [paying, setPaying] = useState(false);
  const [paymentError, setPaymentError] = useState("");

  const isDisabled = !stripe || !elements || !clientSecret || paying;

  const onPay = async (): Promise<void> => {
    if (isDisabled) return;

    const cardElement = elements.getElement(CardElement);

    if (!cardElement) {
      setPaymentError(t("checkout.cardNotReady"));
      return;
    }

    setPaymentError("");
    setPaying(true);

    try {
      const result = await stripe.confirmCardPayment(clientSecret, {
        payment_method: {
          card: cardElement,
        },
        return_url: `${window.location.origin}/payment/success?order=${encodeURIComponent(
          String(orderId)
        )}`,
      });

      if (result.error) {
        setPaymentError(
          result.error.message ?? t("checkout.paymentFailed")
        );
        return;
      }

      if (result.paymentIntent?.status === "succeeded") {
        window.location.href = `/payment/success?order=${encodeURIComponent(
          String(orderId)
        )}`;
      }
    } catch (err) {
      console.error("Stripe error:", err);
      setPaymentError(t("checkout.unexpectedError"));
    } finally {
      setPaying(false);
    }
  };

  return (
    <div className={`checkoutPay ${paying ? "is-loading" : ""}`}>
      <div className="checkoutPay__elementWrap">
        <label className="checkoutPay__label">{t("checkout.cardDetails")}</label>

        <div className="checkoutPay__cardBox">
          <CardElement
            options={{
              hidePostalCode: true,
              style: {
                base: {
                  fontSize: "16px",
                  color: "#111111",
                  fontFamily: "Times New Roman, Times, serif",
                  "::placeholder": {
                    color: "#777777",
                  },
                },
                invalid: {
                  color: "#b73a3a",
                },
              },
            }}
          />
        </div>
      </div>

      <div
        className="checkout__statusArea"
        aria-live="polite"
        aria-atomic="true"
      >
        {paymentError && (
          <div className="checkout__state checkout__state--error" role="alert">
            {paymentError}
          </div>
        )}
      </div>

      <button
        type="button"
        className="checkout__button"
        onClick={onPay}
        disabled={isDisabled}
        // While paying the button holds only a spinner; this is what's read.
        aria-label={paying ? t("checkout.processing") : undefined}
      >
        {paying ? <span className="checkoutPay__spinner" /> : t("checkout.payNow")}
      </button>

      <p className="checkoutPay__note">
        {t("checkout.noCardStored")}
      </p>
    </div>
  );
};

export default CheckoutPaymentBlock;