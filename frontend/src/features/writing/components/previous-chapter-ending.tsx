import { useTranslation } from "react-i18next";

import { usePreviousChapterEnding } from "../hooks/use-chapters";

import "./previous-chapter-ending.css";

interface PreviousChapterEndingProps {
  chapterId: string;
  onOpenChapter?: (chapterId: string, chapterTitle: string) => void;
}

export function PreviousChapterEnding({ chapterId, onOpenChapter }: PreviousChapterEndingProps) {
  const { t } = useTranslation();
  const { data } = usePreviousChapterEnding(chapterId);
  if (!data) return null;

  return (
    <section
      className="previous-ending"
      aria-label={t("writing.previousEnding.aria")}
    >
      <p className="previous-ending__label">{t("writing.previousEnding.label")}</p>
      <button
        type="button"
        className="previous-ending__excerpt"
        aria-label={t("writing.previousEnding.open", { title: data.title })}
        onClick={() => onOpenChapter?.(data.chapterId, data.title)}
      >
        {data.excerpt}
      </button>
      <p className="previous-ending__hint">
        {t("writing.previousEnding.hint", {
          title: data.title || t("writing.previousEnding.untitled"),
        })}
      </p>
    </section>
  );
}
