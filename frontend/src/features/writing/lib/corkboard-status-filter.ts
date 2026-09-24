import type { WritingStatus } from "@/lib/chapter-plan";

/**
 * 软木板的写作状态筛选。
 *
 * 默认「全部」。`writing` 是还在写：构思、草稿、修订，不含完成。
 * 只决定卡片是否出现，不改章节对象、字数和原有顺序。卷始终留下。
 */
export const CORKBOARD_STATUS_FILTERS = [
  "all",
  "writing",
  "idea",
  "drafting",
  "revising",
  "done",
] as const;

export type CorkboardStatusFilter = (typeof CORKBOARD_STATUS_FILTERS)[number];

const IN_PROGRESS_STATUSES = new Set<WritingStatus>(["idea", "drafting", "revising"]);

export function chapterMatchesCorkboardStatus(
  status: WritingStatus,
  filter: CorkboardStatusFilter,
): boolean {
  if (filter === "all") return true;
  if (filter === "writing") return IN_PROGRESS_STATUSES.has(status);
  return status === filter;
}

export function chapterMatchesCorkboardQuery(
  chapter: { title: string; synopsis: string },
  normalizedQuery: string,
): boolean {
  if (!normalizedQuery) return true;
  return `${chapter.title}\n${chapter.synopsis}`.toLowerCase().includes(normalizedQuery);
}

export interface CorkboardVolumeCards<TChapter> {
  id: string;
  title: string;
  chapters: TChapter[];
  /** 筛选前这一卷的章节数。用来区分「本来没有章」和「被筛掉了」。 */
  sourceChapterCount: number;
}

export function corkboardVolumeCards<
  TVolume extends {
    id: string;
    title: string;
    chapters: readonly { title: string; synopsis: string; writingStatus: WritingStatus }[];
  },
>(
  volumes: readonly TVolume[],
  filter: CorkboardStatusFilter,
  normalizedQuery: string,
): CorkboardVolumeCards<TVolume["chapters"][number]>[] {
  return volumes.map((volume) => ({
    id: volume.id,
    title: volume.title,
    sourceChapterCount: volume.chapters.length,
    chapters: volume.chapters.filter(
      (chapter) =>
        chapterMatchesCorkboardStatus(chapter.writingStatus, filter) &&
        chapterMatchesCorkboardQuery(chapter, normalizedQuery),
    ),
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

export function countChaptersMatchingCorkboardStatus<
  TChapter extends { writingStatus: WritingStatus },
>(chapters: readonly TChapter[], filter: CorkboardStatusFilter): number {
  let count = 0;
  for (const chapter of chapters) {
    if (chapterMatchesCorkboardStatus(chapter.writingStatus, filter)) count += 1;
  }
  return count;
}

export function isChapterOutsideCorkboardView(
  chapter: { title: string; synopsis: string; writingStatus: WritingStatus } | null | undefined,
  filter: CorkboardStatusFilter,
  normalizedQuery: string,
): boolean {
  if (!chapter) return false;
  return (
    !chapterMatchesCorkboardStatus(chapter.writingStatus, filter) ||
    !chapterMatchesCorkboardQuery(chapter, normalizedQuery)
  );
}

/** 把某一章的写作状态写进已加载的卷树，其它字段保持原样。 */
export function replaceChapterWritingStatusInTree<
  TChapter extends { id: string; writingStatus: WritingStatus },
  TVolume extends { chapters: TChapter[] },
  TTree extends { volumes: TVolume[] },
>(tree: TTree, chapterId: string, writingStatus: WritingStatus): TTree {
  let changed = false;
  const volumes = tree.volumes.map((volume) => {
    const index = volume.chapters.findIndex((chapter) => chapter.id === chapterId);
    if (index < 0) return volume;
    const previous = volume.chapters[index];
    if (!previous || previous.writingStatus === writingStatus) return volume;
    changed = true;
    const chapters = volume.chapters.slice();
    chapters[index] = { ...previous, writingStatus };
    return { ...volume, chapters };
  });
  if (!changed) return tree;
  return { ...tree, volumes };
}
