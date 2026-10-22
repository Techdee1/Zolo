/**
 * Whether THIS phone has a Zolo passkey. The API has no "list my passkeys" call, and a passkey
 * lives on the device that made it, so this is remembered on the device (localStorage; not secret).
 * It is a hint for wording ("Set up" or "Replace"), never a gate: if it is wrong, approving still
 * works or the backend answers NO_PASSKEY and we send the person to set one up.
 */
import { useSyncExternalStore } from "react";

const KEY = "zolo.passkey";
const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function setPasskeyKnown(on: boolean): void {
  try {
    if (on) window.localStorage.setItem(KEY, "1");
    else window.localStorage.removeItem(KEY);
  } catch {
    // storage blocked: the hint is simply not remembered
  }
  listeners.forEach((l) => l());
}

/** true / false once on the device; `null` while rendering on the server, so nothing flashes. */
export function usePasskeyKnown(): boolean | null {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      window.addEventListener("storage", cb);
      return () => {
        listeners.delete(cb);
        window.removeEventListener("storage", cb);
      };
    },
    read,
    () => null,
  );
}
