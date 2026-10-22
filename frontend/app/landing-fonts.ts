import { Instrument_Serif } from "next/font/google";

/**
 * The one warm serif, for the landing page's big headings only. next/font downloads it at build
 * time and serves it from our own origin (no request to Google at runtime), as a single weight.
 * Everything else, including the whole app, stays on the system sans.
 */
export const display = Instrument_Serif({
  weight: "400",
  subsets: ["latin"],
  // "optional": the headline paints at once in a similar serif and never reflows when the font
  // arrives. On a first visit over a slow link that can mean the fallback serif; on every visit
  // after, and on most first visits (the font is preloaded), it is the real one.
  display: "optional",
  variable: "--font-display",
});
