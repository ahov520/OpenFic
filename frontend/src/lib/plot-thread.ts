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

export interface PlotGapChapter {
  id: string;
  /** 后端按阅读顺序给出的章节称呼，与总览里的「序. 标题」一致。 */
  label: string;
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
  /** 到全书最后一章中间空了多少章。0 表示上一章刚出现过。没有空档时为 null。 */
  chaptersSinceLast: number | null;
  /** 空章，顺序只认后端。空 0、已回收、已放弃时为空。 */
  gapChapters: PlotGapChapter[];
  /** 超过 4 章时后端给出的首尾范围。为空则逐章列出 gapChapters。 */
  gapRange: string | null;
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

/**
 * 空 0 章表示上一章刚出现过，空 1、2 章多半是故意隔开，不打断写作。
 * 中间空到 3 章，读者已经连续经过三章没再遇见这条线，才提示考虑推进。
 * 写作界面和后端 Agent 上下文共用这个数（后端常量 STALE_CHAPTER_GAP）。
 */
export const STALE_CHAPTER_GAP = 3;

export type PlotBoardView = "issues" | "open" | "quiet" | "all";

export function readingChapterIds(chapters: readonly PlotChapterOption[]): string[] {
  return [...chapters]
    .sort((left, right) => left.globalOrder - right.globalOrder || left.id.localeCompare(right.id))
    .map((chapter) => chapter.id);
}

/** 按阅读顺序数两章中间空了几章。同一章或顺序颠倒时返回 null。紧挨着返回 0。 */
export function chaptersBetween(
  readingOrder: readonly string[],
  earlierId: string,
  laterId: string,
): number | null {
  const earlier = readingOrder.indexOf(earlierId);
  const later = readingOrder.indexOf(laterId);
  if (earlier < 0 || later < 0 || later <= earlier) return null;
  return later - earlier - 1;
}

export interface QuietGap {
  chaptersSince: number;
  lastOrder: number;
  lastTitle: string;
}

/**
 * 作者正在看的这一章：未回收的线，从最后一次已出现的节拍到这一章中间空了多少章。
 * 后文的节拍不参与，避免把还没写到的回收算进来。
 */
export function quietGapBeforeChapter(
  thread: PlotThread,
  readingOrder: readonly string[],
  chapterId: string,
): QuietGap | null {
  if (thread.status !== "active") return null;
  const currentIndex = readingOrder.indexOf(chapterId);
  if (currentIndex < 0) return null;
  const position = new Map(readingOrder.map((id, index) => [id, index]));
  const visible = thread.beats.filter((beat) => {
    const index = position.get(beat.chapterId);
    return index !== undefined && index <= currentIndex;
  });
  if (visible.length === 0 || visible.some((beat) => beat.kind === "payoff")) return null;
  const last = [...visible].sort((left, right) => {
    const order = (position.get(left.chapterId) ?? 0) - (position.get(right.chapterId) ?? 0);
    if (order !== 0) return order;
    return left.id.localeCompare(right.id);
  })[visible.length - 1];
  if (!last) return null;
  const chaptersSince = chaptersBetween(readingOrder, last.chapterId, chapterId);
  if (chaptersSince == null) return null;
  return {
    chaptersSince,
    lastOrder: last.globalOrder,
    lastTitle: last.chapterTitle,
  };
}

export function boardProblemRank(issues: readonly string[]): number {
  if (issues.includes("payoff_without_plant") || issues.includes("payoff_before_plant")) return 0;
  if (issues.includes("open")) return 1;
  if (issues.length > 0) return 2;
  return 3;
}

/**
 * 与后端 select_board_threads 同一套规则。
 * 默认 issues：有问题的线在前；只有「未回收」、隔了很久的线仍留在名单里。
 * quiet：按隔得最久排，已回收和已放弃不进来。
 */
export function selectPlotThreads(
  threads: readonly PlotThread[],
  view: PlotBoardView,
): PlotThread[] {
  const chosen = threads.filter((thread) => {
    if (view === "all") return true;
    if (view === "quiet") return thread.chaptersSinceLast != null;
    if (view === "open") return thread.issues.includes("open");
    return thread.issues.length > 0;
  });
  return [...chosen].sort((left, right) => {
    if (view !== "quiet") {
      const rank = boardProblemRank(left.issues) - boardProblemRank(right.issues);
      if (rank !== 0) return rank;
    }
    const leftGap = left.chaptersSinceLast ?? -1;
    const rightGap = right.chaptersSinceLast ?? -1;
    if (leftGap !== rightGap) return rightGap - leftGap;
    if (left.sortOrder !== right.sortOrder) return left.sortOrder - right.sortOrder;
    return left.name.localeCompare(right.name);
  });
}
