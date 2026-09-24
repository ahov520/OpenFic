import { readWordCountTarget } from "@/lib/chapter-length";
import type { WritingStatus } from "@/lib/chapter-plan";

/**
 * 软木板「还没设目标」。
 *
 * 开关默认关闭。打开后只留下写作状态为草稿或修订、且没有字数目标的卡片。
 * 构思和完成即使没设目标也不留下。可以和「全部 / 构思 / 草稿 / 修订 / 完成」叠加。
 * 只决定卡片是否出现，不改目标、字数和书序。卷名始终留下。
 *
 * 目标为 null、空或读不出来才算没设。0 和超出 1–100000 的数后端不接受，
 * 读的时候同样视为未设置，不当成一种目标。
 */
export type CorkboardStatusFilter = "all" | WritingStatus;

export interface CorkboardView {
  statusFilter: CorkboardStatusFilter;
  missingTargetOnly: boolean;
  query: string;
}

export const DEFAULT_CORKBOARD_VIEW: CorkboardView = {
  statusFilter: "all",
  missingTargetOnly: false,
  query: "",
};

const MISSING_TARGET_STATUSES = new Set<WritingStatus>(["drafting", "revising"]);

export function chapterHasWordCountTarget(target: unknown): boolean {
  return readWordCountTarget(target) != null;
}

export function chapterMatchesCorkboardStatus(
  status: WritingStatus,
  filter: CorkboardStatusFilter,
): boolean {
  if (filter === "all") return true;
  return status === filter;
}

export function chapterMatchesMissingTarget(
  chapter: { writingStatus: WritingStatus; wordCountTarget: unknown },
  missingTargetOnly: boolean,
): boolean {
  if (!missingTargetOnly) return true;
  return (
    MISSING_TARGET_STATUSES.has(chapter.writingStatus) &&
    !chapterHasWordCountTarget(chapter.wordCountTarget)
  );
}

export function chapterMatchesCorkboardQuery(
  chapter: { title: string; synopsis: string },
  normalizedQuery: string,
): boolean {
  if (!normalizedQuery) return true;
  return `${chapter.title}\n${chapter.synopsis}`.toLowerCase().includes(normalizedQuery);
}

interface CorkboardChapter {
  title: string;
  synopsis: string;
  writingStatus: WritingStatus;
  wordCountTarget: unknown;
}

export function chapterVisibleOnCorkboard(chapter: CorkboardChapter, view: CorkboardView): boolean {
  const normalizedQuery = view.query.trim().toLowerCase();
  return (
    chapterMatchesCorkboardStatus(chapter.writingStatus, view.statusFilter) &&
    chapterMatchesMissingTarget(chapter, view.missingTargetOnly) &&
    chapterMatchesCorkboardQuery(chapter, normalizedQuery)
  );
}

export interface CorkboardVolumeCards<TChapter> {
  id: string;
  title: string;
  chapters: TChapter[];
  /** 筛选前这一卷的章节数。用来区分「本来没有章」和「被筛掉了」。 */
  sourceChapterCount: number;
}

export function corkboardVolumeCards<TChapter extends CorkboardChapter>(
  volumes: readonly {
    id: string;
    title: string;
    chapters: readonly TChapter[];
  }[],
  view: CorkboardView,
): CorkboardVolumeCards<TChapter>[] {
  return volumes.map((volume) => ({
    id: volume.id,
    title: volume.title,
    sourceChapterCount: volume.chapters.length,
    chapters: volume.chapters.filter((chapter) => chapterVisibleOnCorkboard(chapter, view)),
  }));
}

/** 卷名下该显示什么：有卡片、本来就没有章、或这一筛选下没有章。 */
export type CorkboardVolumeEmptyKind = "cards" | "source" | "filter";

export function corkboardVolumeEmptyKind(volume: {
  chapters: readonly unknown[];
  sourceChapterCount: number;
}): CorkboardVolumeEmptyKind {
  if (volume.chapters.length > 0) return "cards";
  if (volume.sourceChapterCount === 0) return "source";
  return "filter";
}

export function countChaptersMissingWordCountTarget<
  TChapter extends { writingStatus: WritingStatus; wordCountTarget: unknown },
>(chapters: readonly TChapter[]): number {
  let count = 0;
  for (const chapter of chapters) {
    if (chapterMatchesMissingTarget(chapter, true)) count += 1;
  }
  return count;
}

export function isChapterOutsideCorkboardView(
  chapter: CorkboardChapter | null | undefined,
  view: CorkboardView,
): boolean {
  if (!chapter) return false;
  return !chapterVisibleOnCorkboard(chapter, view);
}

/** 把某一章的字数目标写进已加载的卷树。其它字段、字数和顺序保持原样。 */
export function replaceChapterWordCountTargetInTree<
  TChapter extends { id: string; wordCountTarget: number | null },
  TVolume extends { chapters: TChapter[] },
  TTree extends { volumes: TVolume[] },
>(tree: TTree, chapterId: string, wordCountTarget: number | null): TTree {
  const nextTarget = readWordCountTarget(wordCountTarget);
  let changed = false;
  const volumes = tree.volumes.map((volume) => {
    const index = volume.chapters.findIndex((chapter) => chapter.id === chapterId);
    if (index < 0) return volume;
    const previous = volume.chapters[index];
    if (!previous || previous.wordCountTarget === nextTarget) return volume;
    changed = true;
    const chapters = volume.chapters.slice();
    chapters[index] = { ...previous, wordCountTarget: nextTarget };
    return { ...volume, chapters };
  });
  if (!changed) return tree;
  return { ...tree, volumes };
}
