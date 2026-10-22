/** Class strings for links that look like the kit's buttons (a link that navigates must be a link). */
export const LINK_PRIMARY =
  "press inline-flex min-h-(--target-primary) w-full items-center justify-center rounded-[16px] " +
  "bg-zolo-brand px-6 type-body font-semibold text-zolo-on-brand shadow-zolo-primary touch-manipulation";

export const LINK_SECONDARY =
  "press inline-flex min-h-(--target-min) w-full items-center justify-center rounded-zolo-control border " +
  "border-zolo-separator bg-zolo-elevated px-6 type-body font-semibold text-zolo-text shadow-zolo-card touch-manipulation";

/** The one card every screen is built from (see .surface in globals.css). */
export const CARD = "surface";
/** A card with room inside it. */
export const CARD_PAD = "surface grid gap-4 p-5";
/** A row in a card list: icon tile, words, then whatever sits at the end. */
export const ROW =
  "flex min-h-(--target-primary) items-center gap-4 px-4 py-3.5 text-zolo-text touch-manipulation";
/** The same row when the whole row is a link. */
export const ROW_LINK = `${ROW} row-link press`;
