export interface CorkboardSortableChapter {
  wordCount: number;
  wordCountTarget: number | null;
}

/** 阅读顺序是书序。还差字数只改软木板卡片的视觉顺序。 */
export type CorkboardChapterSort = "reading" | "shortfall";

function hasWordTarget(
  chapter: CorkboardSortableChapter,
): chapter is CorkboardSortableChapter & { wordCountTarget: number } {
  return typeof chapter.wordCountTarget === "number";
}

/**
 * 同一卷内：有目标的章按「目标 - 已写」降序。
 * 还差为正的在前，刚好写完（0）其次，已经超出（负数）再往后。
 * 没设目标的不按 0 还差插进有目标的章中间，保持原来的阅读顺序排在最后。
 */
export function orderCorkboardChapters<T extends CorkboardSortableChapter>(
  chapters: readonly T[],
  sort: CorkboardChapterSort,
): T[] {
  if (sort === "reading") return [...chapters];

  const targeted: Array<{ chapter: T; index: number; shortfall: number }> = [];
  const untargeted: T[] = [];
  for (const [index, chapter] of chapters.entries()) {
    if (!hasWordTarget(chapter)) {
      untargeted.push(chapter);
      continue;
    }
    targeted.push({
      chapter,
      index,
      shortfall: chapter.wordCountTarget - chapter.wordCount,
    });
  }

  targeted.sort((left, right) => {
    if (left.shortfall !== right.shortfall) return right.shortfall - left.shortfall;
    return left.index - right.index;
  });

  return [...targeted.map((item) => item.chapter), ...untargeted];
}

export function arrangeCorkboardVolumes<
  TChapter extends CorkboardSortableChapter,
  TVolume extends { chapters: readonly TChapter[] },
>(
  volumes: readonly TVolume[],
  sort: CorkboardChapterSort,
): Array<Omit<TVolume, "chapters"> & { chapters: TChapter[] }> {
  return volumes.map((volume) => ({
    ...volume,
    chapters: orderCorkboardChapters(volume.chapters, sort),
  }));
}

/**
 * 还差字数是临时视图。若在这里拖拽并保存，会把视觉顺序写成卷内书序。
 * 更安全的做法是直接禁用拖拽，而不是先切回阅读顺序再允许拖拽。
 * 阅读顺序下软木板同样不保存拖拽；书序只在侧栏修改。
 */
export function corkboardDragReorderEnabled(sort: CorkboardChapterSort): boolean {
  switch (sort) {
    case "shortfall":
      return false;
    case "reading":
      return false;
  }
}
