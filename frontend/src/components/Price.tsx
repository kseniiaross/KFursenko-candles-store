import React from "react";

import "../styles/Price.css";

type Props = {
  /** The regular price, as the catalog stores it. */
  price: number | string | null | undefined;
  /** Set only when an offer applies. Null or equal to price means no sale. */
  discountPrice?: number | string | null;
  /** "sm" on catalog cards, "lg" on the product page. */
  size?: "sm" | "lg";
};

function toNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value: number): string {
  return `$${value.toFixed(2)}`;
}

/** One place that decides how a price looks, so a card and a product page
 *  cannot drift apart on rounding, ordering or colour. */
const Price: React.FC<Props> = ({ price, discountPrice, size = "sm" }) => {
  const regular = toNumber(price);
  const sale = toNumber(discountPrice);

  if (regular === null) return null;

  // A "discount" that is not actually lower is a data error upstream, not
  // something to draw a strikethrough for.
  const onSale = sale !== null && sale < regular;

  if (!onSale) {
    return <span className={`price price--${size}`}>{money(regular)}</span>;
  }

  return (
    <span className={`price price--${size} price--sale`}>
      <s className="price__was" aria-label={`Was ${money(regular)}`}>
        {money(regular)}
      </s>
      <span className="price__now">{money(sale)}</span>
    </span>
  );
};

export default Price;