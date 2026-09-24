import type { WritingStatus } from "@/lib/chapter-plan";

/** 阅读顺序上的一章。排序只用卷序和卷内章序，不用数据库 id。 */
export interface ReadingOrderChapter {
  id: string;
  order: number;
  writingStatus: WritingStatus;
}

export interface ReadingOrderVolume {
  order: number;
  chapters: readonly ReadingOrderChapter[];
}

function compareOrder(left: { order: number }, right: { order: number }): number {
  return left.order - right.order;
}

/**
 * 从全书第一章往后，返回第一张写作状态不是「完成」的章节。
 * 构思、草稿、修订都算还没完成。全部完成时返回 null。
 * 顺序是卷序，再是卷内章序；不看传入数组的先后，也不看 id。
 */
export function nextOpenChapterId(
  volumes: readonly ReadingOrderVolume[],
  statusOverrides?: Readonly<Record<string, WritingStatus>>,
): string | null {
  const volumesInReadingOrder = [...volumes].sort(compareOrder);
  for (const volume of volumesInReadingOrder) {
    const chaptersInReadingOrder = [...volume.chapters].sort(compareOrder);
    for (const chapter of chaptersInReadingOrder) {
      const status = statusOverrides?.[chapter.id] ?? chapter.writingStatus;
      if (status !== "done") return chapter.id;
    }
  }
  return null;
}

/**
 * 卡片上的「下一章」只出现在全书阅读顺序的那一张上。
 * 筛选或搜索把这张卡藏起来时返回 null，不改标到当前可见列表的第一张。
 */
export function visibleNextOpenChapterId(
  volumes: readonly ReadingOrderVolume[],
  visibleChapterIds: ReadonlySet<string>,
  statusOverrides?: Readonly<Record<string, WritingStatus>>,
): string | null {
  const nextId = nextOpenChapterId(volumes, statusOverrides);
  if (nextId == null || !visibleChapterIds.has(nextId)) return null;
  return nextId;
}
