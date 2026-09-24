import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { ChapterListItem, VolumeWithChapters } from "@/lib/chapter.types";

import {
  SIDEBAR_WRITING_STATUS_FILTERS,
  chapterMatchesSidebarWritingStatus,
  countChaptersForSidebarFilter,
  isSidebarWritingStatusFilter,
  type SidebarWritingStatusFilter,
} from "../lib/sidebar-writing-status-filter";

interface SidebarWritingStatusFilterBarProps {
  volumes: VolumeWithChapters[];
  value: SidebarWritingStatusFilter;
  currentChapter: ChapterListItem | null;
  onChange: (value: SidebarWritingStatusFilter) => void;
}

export function SidebarWritingStatusFilterBar({
  volumes,
  value,
  currentChapter,
  onChange,
}: SidebarWritingStatusFilterBarProps) {
  const { t } = useTranslation();
  const outsideFilter =
    currentChapter != null &&
    !chapterMatchesSidebarWritingStatus(currentChapter.writingStatus, value);
  const options = useMemo(
    () =>
      SIDEBAR_WRITING_STATUS_FILTERS.map((filter) => {
        const count = countChaptersForSidebarFilter(volumes, filter);
        const label =
          filter === "all"
            ? t("writing.chapterPlan.filterAll", { count })
            : filter === "writing"
              ? t("writing.chapterPlan.filterWriting", { count })
              : t("writing.chapterPlan.filterStatus", {
                  status: t(`writing.chapterPlan.statuses.${filter}`),
                  count,
                });
        return { filter, label };
      }),
    [t, volumes],
  );

  return (
    <div className="sidebar-writing-status-filter">
      <select
        className="writing-status-select sidebar-writing-status-filter__select"
        data-testid="sidebar-writing-status-filter"
        aria-label={t("writing.chapterPlan.status")}
        value={value}
        onChange={(event) => {
          const next = event.target.value;
          if (isSidebarWritingStatusFilter(next)) onChange(next);
        }}
      >
        {options.map((option) => (
          <option
            key={option.filter}
            value={option.filter}
          >
            {option.label}
          </option>
        ))}
      </select>
      {outsideFilter && currentChapter ? (
        <p
          className="sidebar-writing-status-current"
          data-testid="sidebar-current-outside-filter"
        >
          <span>
            {t("writing.chapterPlan.currentOutsideFilter", {
              title: currentChapter.title || t("writing.untitledChapter"),
            })}
          </span>
          <button
            type="button"
            onClick={() => onChange("all")}
          >
            {t("writing.chapterPlan.showAllChapters")}
          </button>
        </p>
      ) : null}
    </div>
  );
}
