import { Flex, Text } from "@radix-ui/themes";
import { useTranslation } from "react-i18next";

import type { PlotChapterOption, PlotThread } from "@/lib/plot-thread";

import { buildTimelineRows } from "../lib/plot-timeline";
import "./plot-timeline.css";

interface PlotTimelineProps {
  threads: PlotThread[];
  chapters: PlotChapterOption[];
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
}

/** 情节线时间轴：行是情节线，列是按阅读顺序排列的章节，格子是节拍。 */
export function PlotTimeline({ threads, chapters, onOpenChapter }: PlotTimelineProps) {
  const { t } = useTranslation();
  const rows = buildTimelineRows(threads, chapters);

  return (
    <div className="plot-timeline-scroll">
      <div
        className="plot-timeline-grid"
        style={{ gridTemplateColumns: `var(--plot-timeline-name-width) repeat(${chapters.length}, var(--plot-timeline-cell-width))` }}
      >
        <div className="plot-timeline__corner">
          {t("writing.plotThreads.timelineCorner")}
        </div>
        {chapters.map((chapter) => (
          <button
            key={chapter.id}
            type="button"
            className="plot-timeline__chapter"
            title={t("writing.plotThreads.timelineChapterTitle", {
              order: chapter.globalOrder,
              title: chapter.title,
              volume: chapter.volumeTitle,
            })}
            onClick={() => onOpenChapter(chapter.id, chapter.title)}
          >
            {chapter.globalOrder}
          </button>
        ))}
        {rows.map((row) => (
          <TimelineRowCells
            key={row.thread.id}
            thread={row.thread}
            cells={row.cells}
            onOpenChapter={onOpenChapter}
          />
        ))}
      </div>
      {chapters.length === 0 && (
        <Text
          as="p"
          size="1"
          color="gray"
          mt="3"
        >
          {t("writing.plotThreads.noChapters")}
        </Text>
      )}
    </div>
  );
}

function TimelineRowCells({
  thread,
  cells,
  onOpenChapter,
}: {
  thread: PlotThread;
  cells: ReturnType<typeof buildTimelineRows>[number]["cells"];
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <Flex
        align="center"
        className="plot-timeline__name"
        title={thread.intent || thread.name}
      >
        <Text
          size="1"
          truncate
        >
          {thread.name}
        </Text>
      </Flex>
      {cells.map((cell) => {
        if (!cell.beat) {
          return (
            <div
              key={cell.chapter.id}
              className="plot-timeline__cell plot-timeline__cell--empty"
            />
          );
        }
        const kindLabel = t(`writing.plotThreads.kinds.${cell.beat.kind}`);
        return (
          <button
            key={cell.chapter.id}
            type="button"
            className={`plot-timeline__cell plot-timeline__cell--${cell.beat.kind}`}
            title={t("writing.plotThreads.timelineCellTitle", {
              chapter: cell.chapter.title,
              kind: kindLabel,
              note: cell.beat.note,
            })}
            onClick={() => onOpenChapter(cell.chapter.id, cell.chapter.title)}
          >
            {kindLabel.slice(0, 1)}
          </button>
        );
      })}
    </>
  );
}
