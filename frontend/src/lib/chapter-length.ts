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

type LengthTranslator = (key: string, options?: { count: number }) => string;

export interface CorkboardLengthLabel {
  pace: Exclude<ChapterPace, "none">;
  text: string;
}

/**
 * 软木板卡片上的字数差距。没有目标时不显示。
 * 刚好达到标「达标」，不写成还差 0。超出用超出，不用还差。
 */
export function corkboardLengthLabel(
  written: number,
  target: number | null,
  translate: LengthTranslator,
): CorkboardLengthLabel | null {
  const progress = chapterLengthProgress(written, target);
  if (progress.pace === "none") return null;
  if (progress.pace === "short") {
    return {
      pace: "short",
      text: translate("writing.chapterLength.remaining", { count: progress.remaining }),
    };
  }
  if (progress.pace === "over") {
    return {
      pace: "over",
      text: translate("writing.chapterLength.over", { count: progress.over }),
    };
  }
  return { pace: "met", text: translate("writing.chapterLength.onTarget") };
}
