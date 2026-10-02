import React, { useState } from "react";
import { addToCart as addToCartApi } from "../api/cart";
import { useAppDispatch, useAppSelector } from "../store/hooks";
import { addToCart, setCart } from "../store/cartSlice";
import { closeSizeModal } from "../store/modalSlice";

import "../styles/SizeModal.css";

const SizeModal: React.FC = () => {
  const dispatch = useAppDispatch();

  const { candle, isOpen } = useAppSelector((state) => state.modal);
  const isLoggedIn = useAppSelector((state) => state.auth.isLoggedIn);

  const [addingVariantId, setAddingVariantId] = useState<number | null>(null);

  if (!isOpen || !candle) return null;

  const handleClose = (): void => {
    dispatch(closeSizeModal());
  };

  const handleAdd = async (variant: {
    id: number;
    size: string;
    price: string | number;
  }): Promise<void> => {
    try {
      setAddingVariantId(variant.id);

      if (!isLoggedIn) {
        dispatch(
          addToCart({
            variant_id: variant.id,
            candle_id: candle.id,
            name: candle.name,
            price: Number(variant.price) || 0,
            image: candle.image ?? undefined,
            size: variant.size,
            quantity: 1,
            isGift: false,
          })
        );

        dispatch(closeSizeModal());
        return;
      }

      const items = await addToCartApi({
        variant_id: variant.id,
        quantity: 1,
        is_gift: false,
      });

      dispatch(setCart(items));
      dispatch(closeSizeModal());
    } catch (error) {
      console.error("Failed to add item to cart from size modal:", error);
    } finally {
      setAddingVariantId(null);
    }
  };

  return (
    <div className="sizeModalOverlay" onClick={handleClose}>
      <div className="sizeModal" onClick={(event) => event.stopPropagation()}>
        <button
          type="button"
          className="sizeModal__close"
          onClick={handleClose}
          aria-label="Close modal"
        >
          ×
        </button>

        <div className="sizeModal__header">
          <h2 className="sizeModal__title">Select Size</h2>
          <p className="sizeModal__product">{candle.name}</p>
        </div>

        <div className="sizeModal__sizes">
          {candle.variants?.map((variant) => {
            const isAdding = addingVariantId === variant.id;

            return (
              <button
                key={variant.id}
                type="button"
                className="sizeModal__sizeButton"
                onClick={() => {
                  void handleAdd(variant);
                }}
                disabled={isAdding}
              >
                <span className="sizeModal__size">{variant.size}</span>

                <span className="sizeModal__price">
                  {isAdding ? "Adding..." : `$${variant.price}`}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default SizeModal;