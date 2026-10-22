/** Why a customer is shown a result screen; carried in the URL so the screen can say it. */
export const RESULT_REASONS = ["changed", "limit", "check"] as const;
export type ResultReason = (typeof RESULT_REASONS)[number];

export const parseReason = (v: string | undefined): ResultReason | null =>
  (RESULT_REASONS as readonly string[]).includes(v ?? "") ? (v as ResultReason) : null;

export const resultPath = (id: string, reason?: ResultReason) =>
  `/requests/${encodeURIComponent(id)}/result${reason ? `?r=${reason}` : ""}`;
