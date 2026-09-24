export const WRITING_STATUSES = ["idea", "drafting", "revising", "done"] as const;

export type WritingStatus = (typeof WRITING_STATUSES)[number];

export const SYNOPSIS_MAX_LENGTH = 2000;

export function isWritingStatus(value: unknown): value is WritingStatus {
  return typeof value === "string" && WRITING_STATUSES.some((status) => status === value);
}

export function normalizeWritingStatus(value: unknown): WritingStatus {
  return isWritingStatus(value) ? value : "idea";
}

export function normalizeSynopsis(value: unknown): string {
  if (typeof value !== "string") return "";
  return value.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

export function isSynopsisBlank(synopsis: string): boolean {
  return synopsis.trim().length === 0;
}

export function corkboardMissingSynopsis(status: WritingStatus, synopsis: string): boolean {
  return (status === "drafting" || status === "revising") && isSynopsisBlank(synopsis);
}
