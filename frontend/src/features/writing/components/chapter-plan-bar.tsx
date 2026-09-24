import { Text } from "@radix-ui/themes";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { Chapter } from "@/lib/chapter.types";
import { SYNOPSIS_MAX_LENGTH } from "@/lib/chapter-plan";

import { useChapterPlanDraft } from "../hooks/use-chapter-plan-draft";
import { useVolumeTree } from "../hooks/use-volumes";
import { WritingStatusSelect } from "./chapter-plan-status";

import "./chapter-plan.css";

interface ChapterPlanBarProps {
  chapter: Chapter;
  isAgentLocked?: boolean;
}

export function ChapterPlanBar({ chapter, isAgentLocked = false }: ChapterPlanBarProps) {
  const { t } = useTranslation();
  const { data: tree } = useVolumeTree(chapter.projectId);
  const listed = useMemo(
    () => tree?.volumes.flatMap((volume) => volume.chapters).find((item) => item.id === chapter.id),
    [chapter.id, tree],
  );
  const listedIsNewer =
    listed !== undefined && Date.parse(listed.updatedAt) >= Date.parse(chapter.updatedAt);
  const draft = useChapterPlanDraft(
    {
      id: chapter.id,
      synopsis: listedIsNewer ? listed.synopsis : chapter.synopsis,
      writingStatus: listedIsNewer ? listed.writingStatus : chapter.writingStatus,
    },
    isAgentLocked,
  );

  return (
    <section
      className="chapter-plan-bar"
      aria-label={t("writing.chapterPlan.synopsis")}
    >
      <div className="chapter-plan-bar__header">
        <Text
          size="1"
          weight="medium"
        >
          {t("writing.chapterPlan.synopsis")}
        </Text>
        <WritingStatusSelect
          value={draft.writingStatus}
          disabled={isAgentLocked}
          onChange={draft.setWritingStatus}
        />
      </div>
      <textarea
        className="chapter-plan-bar__synopsis"
        value={draft.synopsis}
        disabled={isAgentLocked}
        maxLength={SYNOPSIS_MAX_LENGTH + 1}
        placeholder={t("writing.chapterPlan.synopsisPlaceholder")}
        onChange={(event) => draft.setSynopsis(event.target.value)}
        onBlur={draft.flush}
      />
      {draft.synopsisTooLong ? (
        <p className="chapter-plan-bar__error">
          {t("writing.chapterPlan.synopsisTooLong", { max: SYNOPSIS_MAX_LENGTH })}
        </p>
      ) : (
        <p className="chapter-plan-bar__hint">{t("writing.chapterPlan.hint")}</p>
      )}
    </section>
  );
}
