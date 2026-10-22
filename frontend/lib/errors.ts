import type { useRouter } from "next/navigation";
import { isApiError, NetworkError } from "@/lib/api/client";
import type { MessageKey } from "@/lib/i18n";

/** If the API says nobody is signed in, go to the sign-in chooser. Returns true when it did. */
export function redirectIfSignedOut(e: unknown, router: ReturnType<typeof useRouter>): boolean {
  if (isApiError(e, "UNAUTHENTICATED")) {
    router.replace("/signin");
    return true;
  }
  return false;
}

/** The generic, honest sentence for an error nothing else handled. Always says nothing was sent. */
export function genericErrorKey(e: unknown): MessageKey {
  if (e instanceof NetworkError) return "errors.network";
  if (isApiError(e, "RATE_LIMITED")) return "errors.rateLimited";
  return "errors.generic";
}
