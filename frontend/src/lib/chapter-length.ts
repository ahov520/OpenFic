export const WORD_COUNT_TARGET_MAX = 100_000;

export type ChapterPace = "none" | "short" | "met" | "over";

export interface ChapterLengthProgress {
  pace: ChapterPace;
  written: number;
  target: number | null;
  remaining: number;
  over: number;
}

export function readWordCountTarget(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isInteger(value)) return null;
  if (value < 1 || value > WORD_COUNT_TARGET_MAX) return null;
  return value;
}

export function parseWordCountTarget(
  raw: string,
): { ok: true; value: number | null } | { ok: false } {
  const trimmed = raw.trim();
  if (trimmed === "") return { ok: true, value: null };
  if (!/^\d+$/.test(trimmed)) return { ok: false };
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value) || value < 1 || value > WORD_COUNT_TARGET_MAX) {
    return { ok: false };
  }
  return { ok: true, value };
}

export function chapterLengthProgress(
  written: number,
  target: number | null,
): ChapterLengthProgress {
  if (target == null) {
    return { pace: "none", written, target: null, remaining: 0, over: 0 };
  }
  if (written < target) {
    return { pace: "short", written, target, remaining: target - written, over: 0 };
  }
  if (written > target) {
    return { pace: "over", written, target, remaining: 0, over: written - target };
  }
  return { pace: "met", written, target, remaining: 0, over: 0 };
}
