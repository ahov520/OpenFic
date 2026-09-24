import { WRITING_STATUSES, type WritingStatus } from "@/lib/chapter-plan";

/**
 * 侧栏章节列表的写作状态筛选。
 *
 * 默认「全部」。`writing` 是还在写的章：构思、草稿、修订，不含完成。
 * 筛选只决定哪些章节出现在列表里，不改章节对象、字数和原有顺序。
 */
export const SIDEBAR_WRITING_STATUS_FILTERS = ["all", "writing", ...WRITING_STATUSES] as const;

export type SidebarWritingStatusFilter = (typeof SIDEBAR_WRITING_STATUS_FILTERS)[number];

const IN_PROGRESS_STATUSES = new Set<WritingStatus>(["idea", "drafting", "revising"]);

export function isSidebarWritingStatusFilter(value: string): value is SidebarWritingStatusFilter {
  return (SIDEBAR_WRITING_STATUS_FILTERS as readonly string[]).includes(value);
}

export function chapterMatchesSidebarWritingStatus(
  status: WritingStatus,
  filter: SidebarWritingStatusFilter,
): boolean {
  if (filter === "all") return true;
  if (filter === "writing") return IN_PROGRESS_STATUSES.has(status);
  return status === filter;
}

export function countChaptersForSidebarFilter<TChapter extends { writingStatus: WritingStatus }>(
  volumes: readonly { chapters: readonly TChapter[] }[],
  filter: SidebarWritingStatusFilter,
): number {
  let count = 0;
  for (const volume of volumes) {
    for (const chapter of volume.chapters) {
      if (chapterMatchesSidebarWritingStatus(chapter.writingStatus, filter)) count += 1;
    }
  }
  return count;
}

/**
 * 留下每一卷。筛完没有可见章时章节数组为空，卷名和 chapterCount 仍在，
 * 列表按现有卷结构显示卷名，不把卷删掉。
 */
export function filterSidebarVolumesByWritingStatus<
  TChapter extends { writingStatus: WritingStatus },
  TVolume extends { chapters: TChapter[] },
>(volumes: readonly TVolume[], filter: SidebarWritingStatusFilter): TVolume[] {
  if (filter === "all") return volumes as TVolume[];

  return volumes.map((volume) => {
    const chapters = volume.chapters.filter((chapter) =>
      chapterMatchesSidebarWritingStatus(chapter.writingStatus, filter),
    );
    if (chapters.length === volume.chapters.length) return volume;
    return { ...volume, chapters };
  });
}

/** 卷里本来有章，但当前筛选下一章都不显示。卷名仍然留下。 */
export function volumeHasHiddenChapters(volume: {
  chapterCount: number;
  chapters: readonly unknown[];
}): boolean {
  return volume.chapters.length === 0 && volume.chapterCount > 0;
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
