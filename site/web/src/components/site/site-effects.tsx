"use client";
import { useEffect } from "react";

/** Two document-level effects, no markup: every button springs on click (globals.css
 *  .is-pressed), and the backdrop tints follow the cursor (--mx, --my on the root element; human
 *  request 2026-10-04). Touch screens send no mousemove, so they keep the default position. */
export function SiteEffects() {
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const el = (e.target as Element | null)?.closest?.("button, [role=button]") as HTMLElement | null;
      if (!el) return;
      el.classList.remove("is-pressed");
      void el.offsetWidth; // restart the animation on a second click
      el.classList.add("is-pressed");
      el.addEventListener("animationend", () => el.classList.remove("is-pressed"), { once: true });
    };
    let frame = 0;
    const onMove = (e: MouseEvent) => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const root = document.documentElement.style;
        root.setProperty("--mx", `${((100 * e.clientX) / window.innerWidth).toFixed(1)}%`);
        root.setProperty("--my", `${((100 * e.clientY) / window.innerHeight).toFixed(1)}%`);
      });
    };
    document.addEventListener("click", onClick);
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => {
      document.removeEventListener("click", onClick);
      window.removeEventListener("mousemove", onMove);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);
  return null;
}
