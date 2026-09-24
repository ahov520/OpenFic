import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { PlotGapChapter } from "@/lib/plot-thread";

/**
 * 总览和写作界面共用的空章展示。
 * chapters 的顺序只认后端阅读顺序，这里不排序、不改名。
 * range 有值时先收成首尾，展开后再按原顺序逐章列出。
 */
export function GapChapterList({
  chapters,
  range,
  onOpen,
}: {
  chapters: readonly PlotGapChapter[];
  range: string | null;
  onOpen: (chapterId: string) => void;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const collapsed = range != null && !expanded;

  return (
    <div
      className="plot-thread-gap-chapters"
      data-testid="plot-thread-gap-chapters"
      data-collapsed={collapsed ? "true" : "false"}
    >
      <span className="plot-thread-quiet">{t("writing.plotThreads.gapChapters")}</span>
      {collapsed ? (
        <span
          className="plot-thread-gap-range"
          data-testid="plot-thread-gap-range"
        >
          {range}
        </span>
      ) : (
        chapters.map((chapter) => (
          <button
            key={chapter.id}
            type="button"
            className="plot-thread-chip plot-thread-chip--gap"
            data-testid="plot-thread-gap-chapter"
            onClick={() => onOpen(chapter.id)}
          >
            {chapter.label}
          </button>
        ))
      )}
      {range != null && (
        <button
          type="button"
          className="plot-thread-text-button"
          data-testid="plot-thread-gap-toggle"
          onClick={() => setExpanded((value) => !value)}
        >
          {collapsed
            ? t("writing.plotThreads.expandGapChapters", { count: chapters.length })
            : t("writing.plotThreads.collapseGapChapters")}
        </button>
      )}
    </div>
  );
}
