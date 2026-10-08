import React from "react";

import Price from "./Price";

import "../styles/LinePrice.css";

type Props = {
  /** The line at full price: unit price × quantity. */
  lineTotal: number | string;
  /** What the line costs after its offer — from the server, never worked
   *  out here. */
  lineTotalAfter: number | string;
  quantity: number;
  /** Units on this line that buy-two-get-three made free. */
  freeQuantity: number;
  /** The offer that applied to this line, if any. */
  discountLabel: string;
  /** On a free line: the welcome offer it replaced on the lines that paid
   *  for it. The total can go up when the free candle goes in, so the cart
   *  says why. */
  replacesLabel?: string;
};

/** One order line's price as a shop shows it: what this line costs, with
 *  the reason when it costs less. A line carries at most one promotion, so
 *  there is never more than one marker. Used by the cart, checkout and the
 *  order history, so all three describe a line the same way. */
const LinePrice: React.FC<Props> = ({
  lineTotal,
  lineTotalAfter,
  quantity,
  freeQuantity,
  discountLabel,
  replacesLabel = "",
}) => {
  const free = Math.max(0, freeQuantity);

  let marker = "";
  if (free > 0 && free >= quantity) marker = "Free";
  else if (free > 0) marker = `${free} free`;
  else if (Number(lineTotalAfter) < Number(lineTotal)) marker = discountLabel;

  return (
    <span className="linePrice">
      <Price price={lineTotal} discountPrice={lineTotalAfter} />
      {marker && (
        <span
          className={`linePrice__offer${free > 0 ? " linePrice__offer--free" : ""}`}
        >
          {marker}
        </span>
      )}
      {free > 0 && replacesLabel && (
        <span className="linePrice__note">
          Replaces your {replacesLabel} on the candles that earn it
        </span>
      )}
    </span>
  );
};

export default LinePrice;
