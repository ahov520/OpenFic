/**
 * 软木板「还欠线」：这一章埋下了，线仍在进行，全书还没有回收节拍。
 * 已放弃、已标回收、只推进、构思和完成的章都不算。
 * 只决定卡片出不出现，不改章节数据、书序或字数。
 */

export interface OwingBeat {
  chapterId: string;
  kind: string;
}

export interface OwingThread {
  status: string;
  hasPayoff: boolean;
  beats: readonly OwingBeat[];
}

export interface CorkboardChapterRef {
  id: string;
  title: string;
  synopsis: string;
  writingStatus: string;
  wordCount: number;
}

export type CorkboardStatusFilter = "all" | "idea" | "drafting" | "revising" | "done";

export interface CorkboardFilterState {
  status: CorkboardStatusFilter;
  owingOnly: boolean;
  query: string;
}

/** 打开软木板时的筛选。还欠线默认关着，章都留在板上。 */
export const INITIAL_CORKBOARD_FILTER: CorkboardFilterState = {
  status: "all",
  owingOnly: false,
  query: "",
};

export type CorkboardVolumePlaceholder = "cards" | "empty-volume" | "empty-filter";

export interface VisibleCorkboardVolume<T extends CorkboardChapterRef> {
  id: string;
  title: string;
  chapters: T[];
  originalChapterCount: number;
  placeholder: CorkboardVolumePlaceholder;
}

const OWING_CHAPTER_STATUSES = new Set(["drafting", "revising"]);

export function chapterOwesOpenPlant(
  chapter: { id: string; writingStatus: string },
  threads: readonly OwingThread[],
): boolean {
  if (!OWING_CHAPTER_STATUSES.has(chapter.writingStatus)) return false;
  return threads.some((thread) => openPlantOnChapter(thread, chapter.id));
}

function openPlantOnChapter(thread: OwingThread, chapterId: string): boolean {
  if (thread.status !== "active") return false;
  if (thread.hasPayoff || thread.beats.some((beat) => beat.kind === "payoff")) return false;
  return thread.beats.some((beat) => beat.chapterId === chapterId && beat.kind === "plant");
}

function matchesQuery(chapter: CorkboardChapterRef, query: string): boolean {
  if (!query) return true;
  const haystack = `${chapter.title}\n${chapter.synopsis}`.toLowerCase();
  return haystack.includes(query);
}

export function visibleCorkboardVolumes<T extends CorkboardChapterRef>(
  volumes: readonly { id: string; title: string; chapters: readonly T[] }[],
  filter: CorkboardFilterState,
  threads: readonly OwingThread[],
): VisibleCorkboardVolume<T>[] {
  const query = filter.query.trim().toLowerCase();
  const visible = volumes.map((volume) => {
    const chapters = volume.chapters.filter((chapter) => {
      if (filter.status !== "all" && chapter.writingStatus !== filter.status) return false;
      if (!matchesQuery(chapter, query)) return false;
      if (filter.owingOnly && !chapterOwesOpenPlant(chapter, threads)) return false;
      return true;
    });
    const placeholder: CorkboardVolumePlaceholder =
      chapters.length > 0
        ? "cards"
        : volume.chapters.length === 0
          ? "empty-volume"
          : "empty-filter";
    return {
      id: volume.id,
      title: volume.title,
      chapters,
      originalChapterCount: volume.chapters.length,
      placeholder,
    };
  });
  if (!filter.owingOnly) {
    return visible.filter((volume) => volume.chapters.length > 0);
  }
  return visible;
}
