import type { PlotBeatKind } from "./plot-thread";
import { normalizePlotBeatKind } from "./plot-thread";

export type PlanCheckOrigin = "synopsis" | "beat";
export type PlanCheckBasis = "literal" | "model";
export type PlanCheckFreshness = "unchecked" | "current" | "stale";
export type PlanCheckSource = "model" | "literal" | "empty";
export type PlanCheckOutcome = "unchecked" | "no_plan" | "gaps" | "partial" | "clear";

export interface PlanCheckGap {
  ref: string;
  origin: PlanCheckOrigin;
  planText: string;
  basis: PlanCheckBasis;
  missing: string[];
  detail: string;
  beatKind: PlotBeatKind | null;
  threadName: string | null;
}

export interface PlanCheckLine {
  ref: string;
  origin: PlanCheckOrigin;
  planText: string;
  beatKind: PlotBeatKind | null;
  threadName: string | null;
}

export interface PlanCheck {
  chapterId: string;
  hasPlan: boolean;
  freshness: PlanCheckFreshness;
  source: PlanCheckSource | null;
  outcome: PlanCheckOutcome;
  gaps: PlanCheckGap[];
  unchecked: PlanCheckLine[];
  checkedAt: string | null;
}

const FRESHNESS = new Set<PlanCheckFreshness>(["unchecked", "current", "stale"]);
const SOURCES = new Set<PlanCheckSource>(["model", "literal", "empty"]);
const OUTCOMES = new Set<PlanCheckOutcome>(["unchecked", "no_plan", "gaps", "partial", "clear"]);

function readOrigin(value: unknown): PlanCheckOrigin {
  return value === "beat" ? "beat" : "synopsis";
}

function readBasis(value: unknown): PlanCheckBasis {
  return value === "model" ? "model" : "literal";
}

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

function readBeatKind(value: unknown): PlotBeatKind | null {
  if (typeof value !== "string") return null;
  return normalizePlotBeatKind(value);
}

export function transformPlanCheck(raw: Record<string, unknown>): PlanCheck {
  const gaps = Array.isArray(raw.gaps) ? raw.gaps : [];
  const unchecked = Array.isArray(raw.unchecked) ? raw.unchecked : [];
  const freshness = FRESHNESS.has(raw.freshness as PlanCheckFreshness)
    ? (raw.freshness as PlanCheckFreshness)
    : "unchecked";
  const source = SOURCES.has(raw.source as PlanCheckSource)
    ? (raw.source as PlanCheckSource)
    : null;
  const outcome = OUTCOMES.has(raw.outcome as PlanCheckOutcome)
    ? (raw.outcome as PlanCheckOutcome)
    : "unchecked";
  return {
    chapterId: typeof raw.chapter_id === "string" ? raw.chapter_id : "",
    hasPlan: raw.has_plan === true,
    freshness,
    source,
    outcome,
    gaps: gaps
      .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
      .map((item) => ({
        ref: typeof item.ref === "string" ? item.ref : "",
        origin: readOrigin(item.origin),
        planText: typeof item.plan_text === "string" ? item.plan_text : "",
        basis: readBasis(item.basis),
        missing: readStringList(item.missing),
        detail: typeof item.detail === "string" ? item.detail : "",
        beatKind: readBeatKind(item.beat_kind),
        threadName: typeof item.thread_name === "string" ? item.thread_name : null,
      })),
    unchecked: unchecked
      .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
      .map((item) => ({
        ref: typeof item.ref === "string" ? item.ref : "",
        origin: readOrigin(item.origin),
        planText: typeof item.plan_text === "string" ? item.plan_text : "",
        beatKind: readBeatKind(item.beat_kind),
        threadName: typeof item.thread_name === "string" ? item.thread_name : null,
      })),
    checkedAt: typeof raw.checked_at === "string" ? raw.checked_at : null,
  };
}
