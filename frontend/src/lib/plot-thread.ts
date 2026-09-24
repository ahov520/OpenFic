export const PLOT_THREAD_STATUSES = ["active", "resolved", "abandoned"] as const;
export const PLOT_BEAT_KINDS = ["plant", "advance", "payoff"] as const;

export type PlotThreadStatus = (typeof PLOT_THREAD_STATUSES)[number];
export type PlotBeatKind = (typeof PLOT_BEAT_KINDS)[number];

export interface PlotChapterOption {
  id: string;
  title: string;
  globalOrder: number;
  volumeTitle: string;
}

export interface PlotBeat {
  id: string;
  threadId: string;
  chapterId: string;
  chapterTitle: string;
  volumeTitle: string;
  globalOrder: number;
  kind: PlotBeatKind;
  note: string;
}

export interface PlotThread {
  id: string;
  projectId: string;
  name: string;
  intent: string;
  status: PlotThreadStatus;
  sortOrder: number;
  issues: string[];
  hasPlant: boolean;
  hasPayoff: boolean;
  lastChapterId: string | null;
  lastChapterTitle: string | null;
  lastGlobalOrder: number | null;
  lastKind: PlotBeatKind | null;
  beats: PlotBeat[];
}

export interface PlotBoard {
  threads: PlotThread[];
  chapters: PlotChapterOption[];
}

export interface PlotThreadCreate {
  name: string;
  intent?: string;
  status?: PlotThreadStatus;
}

export interface PlotThreadUpdate {
  name?: string;
  intent?: string;
  status?: PlotThreadStatus;
}

export interface PlotBeatCreate {
  chapterId: string;
  kind: PlotBeatKind;
  note?: string;
}

export interface PlotBeatUpdate {
  chapterId?: string;
  kind?: PlotBeatKind;
  note?: string;
}

const THREAD_STATUSES = new Set<string>(PLOT_THREAD_STATUSES);
const BEAT_KINDS = new Set<string>(PLOT_BEAT_KINDS);

export function normalizePlotThreadStatus(value: unknown): PlotThreadStatus {
  return typeof value === "string" && THREAD_STATUSES.has(value)
    ? (value as PlotThreadStatus)
    : "active";
}

export function normalizePlotBeatKind(value: unknown): PlotBeatKind {
  return typeof value === "string" && BEAT_KINDS.has(value) ? (value as PlotBeatKind) : "plant";
}
