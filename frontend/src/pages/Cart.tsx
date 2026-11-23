import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { deleteCartItem, getMyCart, patchCartItem, readCartError } from "../api/cart";
import CartNotices from "../components/CartNotices";
import LinePrice from "../components/LinePrice";
import { usePricePreview } from "../hooks/usePricePreview";
import { useAppDispatch, useAppSelector } from "../store/hooks";
import {
  MAX_LINE_QUANTITY,
  removeFromCart,
  setCart,
  setGiftOption,
  updateQty,
} from "../store/cartSlice";

import "../styles/Cart.css";

const money = (value: number): string =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);

const Cart: React.FC = () => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const { t } = useTranslation();

  const items = useAppSelector((state) => state.cart.items);
  const isLoggedIn = useAppSelector((state) => Boolean(state.auth.isLoggedIn));
  const userId = useAppSelector((state) => state.auth.user?.id ?? null);

  const [updatingId, setUpdatingId] = useState<number | null>(null);
  /** Why the server refused the last change to a line. */
  const [lineError, setLineError] = useState<{
    variantId: number;
    message: string;
  } | null>(null);

  /** Changes show at once and are then sent. When the server refuses one,
   *  say why on that line and put the cart back to what the server has, so
   *  the page never shows a number checkout won't accept. */
  const restoreFromServer = async (
    variantId: number,
    error: unknown
  ): Promise<void> => {
    console.error("The server refused a cart change:", error);
    setLineError({ variantId, message: readCartError(error) });

    try {
      dispatch(setCart(await getMyCart()));
    } catch (reloadError) {
      console.error("Could not reload the cart:", reloadError);
    }
  };

  const totalItems = useMemo(() => {
    return items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  }, [items]);

  /** Every amount on this page comes from the server, priced the way
   *  checkout will charge — never multiplied out here. */
  const basketLines = useMemo(
    () =>
      items.map((item) => ({
        variant_id: Number(item.variant_id),
        quantity: Math.max(1, Number(item.quantity) || 1),
      })),
    [items]
  );

  const pricing = usePricePreview(
    basketLines,
    isLoggedIn ? `user:${userId ?? "?"}` : "guest"
  );
  const preview = pricing.preview;
  const amount = (value: string | undefined): string =>
    value === undefined ? "—" : money(Number(value));

  const hasGiftItems = useMemo(() => {
    return items.some((item) => Boolean(item.isGift));
  }, [items]);

  const handleCheckout = (): void => {
    if (!items.length) return;

    // The guest copy stays until signing in has merged it into the
    // account's cart; clearing it here lost the cart on a reload.
    if (!isLoggedIn) {
      navigate("/login-choice?next=/checkout");
      return;
    }

    navigate("/checkout");
  };

  const handleRemove = async (
    variantId: number,
    itemId?: number
  ): Promise<void> => {
    setLineError(null);
    dispatch(removeFromCart({ variant_id: variantId, persistAsGuest: !isLoggedIn }));

    if (!isLoggedIn || !itemId) return;

    setUpdatingId(variantId);

    try {
      const serverItems = await deleteCartItem(itemId);

      dispatch(setCart(serverItems));
    } catch (error) {
      await restoreFromServer(variantId, error);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleQuantityChange = async (
    variantId: number,
    nextQuantity: number,
    itemId?: number
  ): Promise<void> => {
    const quantity = Math.min(
      MAX_LINE_QUANTITY,
      Math.max(1, Number(nextQuantity) || 1)
    );

    setLineError(null);
    dispatch(
      updateQty({
        variant_id: variantId,
        quantity,
        persistAsGuest: !isLoggedIn,
      })
    );

    if (!isLoggedIn || !itemId) return;

    setUpdatingId(variantId);

    try {
      const serverItems = await patchCartItem(itemId, {
        quantity,
      });

      dispatch(setCart(serverItems));
    } catch (error) {
      await restoreFromServer(variantId, error);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleGiftChange = async (
    variantId: number,
    isGift: boolean,
    itemId?: number
  ): Promise<void> => {
    setLineError(null);
    dispatch(
      setGiftOption({
        variant_id: variantId,
        isGift,
        persistAsGuest: !isLoggedIn,
      })
    );

    if (!isLoggedIn || !itemId) return;

    setUpdatingId(variantId);

    try {
      const serverItems = await patchCartItem(itemId, {
        is_gift: isGift,
      });

      dispatch(setCart(serverItems));
    } catch (error) {
      await restoreFromServer(variantId, error);
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <main className="cart">
      <div className="cart__inner">
        <header className="cart__header">
          <h1 className="cart__title">{t("cart.title")}</h1>

          <p className="cart__subtitle">{t("cart.subtitle")}</p>
        </header>

        <CartNotices />

        {items.length === 0 ? (
          <div className="cart__empty">
            <p>{t("cart.empty")}</p>

            <Link to="/catalog" className="cart__emptyLink">
              {t("cart.continueShopping")}
            </Link>
          </div>
        ) : (
          <>
            <ul className="cart__list">
              {items.map((item) => {
                const variantId = Number(item.variant_id);
                const itemId = item.item_id;
                const quantity = Math.max(1, Number(item.quantity) || 1);
                const name = item.name?.trim() || t("cart.unnamedCandle", { id: item.candle_id });
                const priced = pricing.line(variantId);
                const unavailable = Boolean(
                  preview?.unavailable.includes(variantId)
                );
                const isUpdating = updatingId === variantId;
                const soldOut = !unavailable && item.inStock === false;
                const error =
                  lineError?.variantId === variantId ? lineError.message : "";

                return (
                  <li
                    key={`${variantId}-${itemId ?? "local"}-${
                      item.size ?? "default"
                    }`}
                    className="cartItem"
                  >
                    <div className="cartItem__imageWrap">
                      {item.image ? (
                        <img
                          src={item.image}
                          alt={name}
                          className="cartItem__image"
                          width="180"
                          height="210"
                          loading="eager"
                          decoding="async"
                        />
                      ) : (
                        <div className="cartItem__image cartItem__image--empty" />
                      )}
                    </div>

                    <div className="cartItem__content">
                      <div className="cartItem__topRow">
                        <div className="cartItem__titleGroup">
                          <h2 className="cartItem__name">{name}</h2>

                          {item.size && (
                            <p className="cartItem__meta">
                              {t("cart.size", { size: item.size })}
                            </p>
                          )}

                          {unavailable && (
                            <p className="cartItem__unavailable" role="note">
                              {t("cart.noLongerAvailable")}
                            </p>
                          )}

                          {soldOut && (
                            <p className="cartItem__unavailable" role="note">
                              {t("cart.soldOut")}
                            </p>
                          )}

                          {error && (
                            <p className="cartItem__unavailable" role="alert">
                              {error}
                            </p>
                          )}

                          <label className="cartItem__giftOption">
                            <input
                              type="checkbox"
                              checked={Boolean(item.isGift)}
                              disabled={isUpdating}
                              onChange={(event) => {
                                void handleGiftChange(
                                  variantId,
                                  event.target.checked,
                                  itemId
                                );
                              }}
                            />

                            <span>{t("cart.giftOption")}</span>
                          </label>

                          {item.isGift && (
                            <p className="cartItem__meta">{t("cart.giftWrappingFree")}</p>
                          )}
                        </div>

                        <button
                          type="button"
                          className="cartItem__remove"
                          disabled={isUpdating}
                          onClick={() => {
                            void handleRemove(variantId, itemId);
                          }}
                        >
                          {t("cart.remove")}
                        </button>
                      </div>

                      <div className="cartItem__bottomRow">
                        <div className="cartItem__priceBlock">
                          <span className="cartItem__priceLabel">
                            {t("cart.unitPrice")}
                          </span>

                          <span className="cartItem__price">
                            {amount(priced?.unit_price)}
                          </span>
                        </div>

                        <div className="cartItem__qty">
                          <button
                            type="button"
                            className="cartItem__qtyButton"
                            disabled={isUpdating || quantity <= 1}
                            onClick={() => {
                              void handleQuantityChange(
                                variantId,
                                quantity - 1,
                                itemId
                              );
                            }}
                          >
                            −
                          </button>

                          <span className="cartItem__qtyValue">{quantity}</span>

                          <button
                            type="button"
                            className="cartItem__qtyButton"
                            disabled={
                              isUpdating || quantity >= MAX_LINE_QUANTITY
                            }
                            onClick={() => {
                              void handleQuantityChange(
                                variantId,
                                quantity + 1,
                                itemId
                              );
                            }}
                          >
                            +
                          </button>
                        </div>

                        <div className="cartItem__lineTotalBlock">
                          <span className="cartItem__priceLabel">{t("cart.total")}</span>

                          <span
                            className={`cartItem__lineTotal${
                              pricing.updating ? " is-updating" : ""
                            }`}
                          >
                            {priced ? (
                              <LinePrice
                                lineTotal={priced.line_total}
                                lineTotalAfter={priced.line_total_after_discount}
                                quantity={priced.quantity}
                                freeQuantity={priced.free_quantity}
                                discountLabel={priced.discount_label}
                                gaveUpLabel={priced.gave_up_label}
                              />
                            ) : (
                              "—"
                            )}
                          </span>
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>

            <section className="cart__footer">
              <div
                className={`cart__summary${pricing.updating ? " is-updating" : ""}`}
                aria-busy={pricing.updating}
              >
                <div className="cart__summaryRow">
                  <span className="cart__summaryLabel">{t("cart.items")}</span>
                  <span className="cart__summaryValue">{totalItems}</span>
                </div>

                {hasGiftItems && (
                  <div className="cart__summaryRow">
                    <span className="cart__summaryLabel">{t("cart.giftWrapping")}</span>
                    <span className="cart__summaryValue">{t("cart.giftWrappingValue")}</span>
                  </div>
                )}

                {/* No discount row: each line already says what it costs,
                    so the total is just their sum. */}
                <div className="cart__summaryRow cart__summaryRow--total">
                  <span className="cart__summaryLabel">{t("cart.total")}</span>
                  <span className="cart__summaryValue">
                    {amount(preview?.items_total)}
                  </span>
                </div>

                <p className="cart__summaryNote">
                  {pricing.failed
                    ? t("cart.pricesFailed")
                    : t("cart.shippingAtCheckout")}
                </p>
              </div>
        

              <button
                type="button"
                className="cart__checkout"
                disabled={!items.length}
                onClick={handleCheckout}
              >
                {t("cart.checkOut")}
              </button>
            </section>
          </>
        )}
      </div>
    </main>
  );
};

export default Cart;