"use client";
import { useEffect } from "react";

/** Every button springs when clicked (human request 2026-10-04): one document listener adds
 *  .is-pressed (globals.css keyframes) and removes it when the animation ends. Renders nothing. */
export function PressBounce() {
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const el = (e.target as Element | null)?.closest?.("button, [role=button]") as HTMLElement | null;
      if (!el) return;
      el.classList.remove("is-pressed");
      void el.offsetWidth; // restart the animation on a second click
      el.classList.add("is-pressed");
      el.addEventListener("animationend", () => el.classList.remove("is-pressed"), { once: true });
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);
  return null;
}
