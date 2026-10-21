"use client";

import { animate } from "motion";
import { useReducedMotion } from "motion/react";
import { useEffect, useId, useRef } from "react";
import { FADE_SECONDS, SPRING, toSpring } from "@/lib/motion";
import { Button } from "./Button";

/**
 * A bottom sheet on the native <dialog> element, so the browser provides what is hard to get right
 * by hand: a real focus trap, an inert page behind it, Escape to close, and focus returning to
 * whatever opened it. It slides up on a spring (damping 0.8, response 0.3) and leaves the way it
 * came; under reduced motion it only fades. It can be interrupted: opening it again mid-close
 * animates from where it is, not from the end.
 *
 * Every way out is a single tap: the Close button, Escape, or a tap on the scrim. No dragging is
 * needed (drag-to-dismiss would only ever be an extra).
 */
export type SheetProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  closeLabel: string;
  children?: React.ReactNode;
};

export function Sheet({ open, onClose, title, closeLabel, children }: SheetProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const onCloseRef = useRef(onClose);
  const reduce = useReducedMotion();
  const titleId = useId();

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open) {
      if (!dialog.open) {
        if (typeof dialog.showModal === "function") dialog.showModal();
        else dialog.setAttribute("open", ""); // environments without <dialog> modality (jsdom)
      }
      headingRef.current?.focus({ preventScroll: true });
      if (reduce) animate(dialog, { opacity: [0, 1] }, { duration: FADE_SECONDS });
      else animate(dialog, { y: ["100%", "0%"], opacity: 1 }, toSpring(SPRING.sheet));
      return;
    }

    if (!dialog.open) return;
    const finish = () => {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    };
    const controls = reduce
      ? animate(dialog, { opacity: 0 }, { duration: FADE_SECONDS })
      : animate(dialog, { y: "100%" }, toSpring(SPRING.sheet)); // back the way it came
    void controls.finished.then(finish, finish);
    return () => controls.stop();
  }, [open, reduce]);

  // Escape and a tap on the scrim ask the owner to close; the owner stays in charge of `open`.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const onCancel = (event: Event) => {
      event.preventDefault();
      onCloseRef.current();
    };
    const onScrimTap = (event: MouseEvent) => {
      if (event.target === dialog) onCloseRef.current();
    };
    dialog.addEventListener("cancel", onCancel);
    dialog.addEventListener("click", onScrimTap);
    return () => {
      dialog.removeEventListener("cancel", onCancel);
      dialog.removeEventListener("click", onScrimTap);
    };
  }, []);

  return (
    <dialog ref={dialogRef} className="sheet" aria-labelledby={titleId}>
      <div className="sheet-body">
        <h2 id={titleId} ref={headingRef} tabIndex={-1} className="type-headline">
          {title}
        </h2>
        {children}
        <Button variant="secondary" onClick={onClose}>
          {closeLabel}
        </Button>
      </div>
    </dialog>
  );
}
