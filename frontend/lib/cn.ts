import clsx, { type ClassValue } from "clsx";

/** Join class names, skipping anything falsy. */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
