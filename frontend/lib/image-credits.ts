import { readFileSync } from "node:fs";
import { join } from "node:path";

/** The photo credits from docs/IMAGE_CREDITS.md, or null when that file is not there. */
export function readImageCredits(): string | null {
  try {
    const text = readFileSync(join(process.cwd(), "..", "docs", "IMAGE_CREDITS.md"), "utf8")
      .replace(/^#.*$/gm, "")
      .trim();
    return text || null;
  } catch {
    return null;
  }
}
