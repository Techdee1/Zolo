import type { z } from "zod";
import { API_BASE } from "@/lib/env";
import { problemSchema } from "./schemas";
import type { ErrorCode } from "./types";

/** The backend refused, with its RFC 9457 problem. `code` is the machine-readable part. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode;
  constructor(status: number, code: ErrorCode, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** The request never got an answer (offline, the proxy is down, aborted by the browser). */
export class NetworkError extends Error {
  constructor() {
    super("The network request failed");
    this.name = "NetworkError";
  }
}

/** The server answered 2xx with something that is not the shape the contract promises. */
export class ContractError extends Error {
  constructor(path: string) {
    super(`Unexpected response shape from ${path}`);
    this.name = "ContractError";
  }
}

export const isApiError = (e: unknown, code?: ErrorCode): e is ApiError =>
  e instanceof ApiError && (code === undefined || e.code === code);

type Init = {
  method?: "GET" | "POST";
  body?: unknown;
  headers?: Record<string, string>;
  query?: Record<string, string>;
  signal?: AbortSignal;
};

async function problemFrom(res: Response): Promise<ApiError> {
  const json: unknown = await res.json().catch(() => null);
  const parsed = problemSchema.safeParse(json);
  if (parsed.success) return new ApiError(res.status, parsed.data.code, parsed.data.title);
  // FastAPI's own 422 for a malformed body, or a proxy error page.
  const code: ErrorCode = res.status === 422 ? "VALIDATION_ERROR" : "INTERNAL_ERROR";
  return new ApiError(res.status, code, res.statusText || "Request failed");
}

/**
 * One call, validated both ways. Same-origin only: the browser sends the HttpOnly session cookie
 * itself and JavaScript never sees it. Nothing is cached, so a money screen cannot show an old state.
 */
export async function api<S extends z.ZodType>(
  path: string,
  schema: S,
  init: Init = {},
): Promise<z.infer<S>> {
  const qs = init.query ? `?${new URLSearchParams(init.query)}` : "";
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}${qs}`, {
      method: init.method ?? (init.body === undefined ? "GET" : "POST"),
      headers: {
        accept: "application/json",
        ...(init.body === undefined ? {} : { "content-type": "application/json" }),
        ...init.headers,
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      credentials: "same-origin",
      cache: "no-store",
      signal: init.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new NetworkError();
  }
  if (!res.ok) throw await problemFrom(res);
  const json: unknown = await res.json().catch(() => null);
  const parsed = schema.safeParse(json);
  if (!parsed.success) throw new ContractError(path);
  return parsed.data;
}
