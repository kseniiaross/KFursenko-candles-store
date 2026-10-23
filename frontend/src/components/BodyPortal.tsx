import type React from "react";
import { createPortal } from "react-dom";

/**
 * Renders a full-screen overlay straight into <body>.
 *
 * Page content sits in .appShell__body, which is its own stacking context
 * (position: relative; z-index: 1). Anything fixed inside it, whatever its
 * z-index, stays under the fixed header (z-index 220), so the header's links
 * drew on top of open modals. Out here, the overlay's own z-index decides.
 */
const BodyPortal: React.FC<{ children: React.ReactNode }> = ({ children }) =>
  createPortal(children, document.body);

export default BodyPortal;
