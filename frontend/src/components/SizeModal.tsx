/* FULL FILE REWRITE */

import React from "react"
import { useAppDispatch, useAppSelector } from "../store/hooks"
import { closeSizeModal } from "../store/modalSlice"
import { addToCart } from "../store/cartSlice"

import "../styles/SizeModal.css"

const SizeModal: React.FC = () => {

  const dispatch = useAppDispatch()

  const { candle, isOpen } = useAppSelector(state => state.modal)

  if (!isOpen || !candle) return null

  const handleAdd = (variant: any) => {

    dispatch(
      addToCart({
        variant_id: variant.id,
        candle_id: candle.id,
        name: candle.name,
        price: Number(variant.price),
        size: variant.size,
        image: candle.image ?? "",
        quantity: 1,
      })
    )

    dispatch(closeSizeModal())
  }

  return (

    <div
      className="sizeModalOverlay"
      onClick={() => dispatch(closeSizeModal())}
    >

      <div
        className="sizeModal"
        onClick={(e) => e.stopPropagation()}
      >

        <button
          className="sizeModal__close"
          onClick={() => dispatch(closeSizeModal())}
          aria-label="Close modal"
        >
          ×
        </button>

        <div className="sizeModal__header">

          <h2 className="sizeModal__title">
            Select Size
          </h2>

          <p className="sizeModal__product">
            {candle.name}
          </p>

        </div>

        <div className="sizeModal__sizes">

          {candle.variants?.map((variant) => (

            <button
              key={variant.id}
              className="sizeModal__sizeButton"
              onClick={() => handleAdd(variant)}
            >

              <span className="sizeModal__size">
                {variant.size}
              </span>

              <span className="sizeModal__price">
                ${variant.price}
              </span>

            </button>

          ))}

        </div>

      </div>

    </div>

  )

}

export default SizeModal