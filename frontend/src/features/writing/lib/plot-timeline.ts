/**
 * 情节线时间轴的纯逻辑：把节拍映射到「线 × 章」网格。
 */

import type { PlotBeat, PlotChapterOption, PlotThread } from "@/lib/plot-thread";

export interface TimelineBeatCell {
  chapter: PlotChapterOption;
  beat: PlotBeat | null;
}

export interface TimelineRow {
  thread: PlotThread;
  cells: TimelineBeatCell[];
}

/** 一条线的节拍按章节 ID 索引（同章同线只有一条）。 */
export function beatsByChapter(beats: PlotBeat[]): Map<string, PlotBeat> {
  const map = new Map<string, PlotBeat>();
  for (const beat of beats) {
    map.set(beat.chapterId, beat);
  }
  return map;
}

/** 组装时间轴行：章节列保持阅读顺序，每格给出该章的节拍（或空）。 */
export function buildTimelineRows(
  threads: PlotThread[],
  chapters: PlotChapterOption[],
): TimelineRow[] {
  return threads.map((thread) => {
    const byChapter = beatsByChapter(thread.beats);
    return {
      thread,
      cells: chapters.map((chapter) => ({
        chapter,
        beat: byChapter.get(chapter.id) ?? null,
      })),
    };
  });
}
