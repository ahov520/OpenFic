import { Box, Dialog, Flex, ScrollArea, Text, TextField } from "@radix-ui/themes";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ChapterListItem, VolumeWithChapters } from "@/lib/chapter.types";
import { SYNOPSIS_MAX_LENGTH, WRITING_STATUSES, type WritingStatus } from "@/lib/chapter-plan";

import { useChapterPlanDraft } from "../hooks/use-chapter-plan-draft";
import { useVolumeTree } from "../hooks/use-volumes";
import { WritingStatusSelect } from "./chapter-plan-status";

import "./chapter-plan.css";

interface ChapterCorkboardProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
  isAgentLocked?: boolean;
}

type StatusFilter = "all" | WritingStatus;

const EMPTY_VOLUMES: VolumeWithChapters[] = [];

function ChapterCorkboardCard({
  chapter,
  isAgentLocked,
  onOpenChapter,
}: {
  chapter: ChapterListItem;
  isAgentLocked: boolean;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
}) {
  const { t } = useTranslation();
  const draft = useChapterPlanDraft(chapter, isAgentLocked);

  return (
    <article
      className="chapter-corkboard-card"
      data-status={draft.writingStatus}
    >
      <Flex
        align="center"
        gap="2"
      >
        <button
          type="button"
          className="chapter-corkboard-card__title"
          onClick={() => onOpenChapter(chapter.id, chapter.title)}
        >
          {chapter.title || t("writing.untitledChapter")}
        </button>
        <WritingStatusSelect
          value={draft.writingStatus}
          disabled={isAgentLocked}
          onChange={draft.setWritingStatus}
        />
      </Flex>
      <textarea
        className="chapter-corkboard-card__synopsis"
        value={draft.synopsis}
        disabled={isAgentLocked}
        maxLength={SYNOPSIS_MAX_LENGTH + 1}
        placeholder={t("writing.chapterPlan.cardPlaceholder")}
        aria-label={t("writing.chapterPlan.synopsis")}
        onChange={(event) => draft.setSynopsis(event.target.value)}
        onBlur={draft.flush}
      />
      <div className="chapter-corkboard-card__meta">
        {draft.synopsisTooLong
          ? t("writing.chapterPlan.synopsisTooLong", { max: SYNOPSIS_MAX_LENGTH })
          : t("writing.chapterPlan.cardMeta", { count: chapter.wordCount })}
      </div>
    </article>
  );
}

function matchesQuery(chapter: ChapterListItem, query: string): boolean {
  if (!query) return true;
  const haystack = `${chapter.title}\n${chapter.synopsis}`.toLowerCase();
  return haystack.includes(query);
}

export function ChapterCorkboard({
  projectId,
  open,
  onOpenChange,
  onOpenChapter,
  isAgentLocked = false,
}: ChapterCorkboardProps) {
  const { t } = useTranslation();
  const { data, isLoading } = useVolumeTree(projectId);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const volumes = data?.volumes ?? EMPTY_VOLUMES
  const allChapters = useMemo(
    () => volumes.flatMap((volume) => volume.chapters),
    [volumes],
  );
  const counts = useMemo(() => {
    const next: Record<WritingStatus, number> = {
      idea: 0,
      drafting: 0,
      revising: 0,
      done: 0,
    };
    for (const chapter of allChapters) next[chapter.writingStatus] += 1;
    return next;
  }, [allChapters]);
  const visibleVolumes = useMemo(() => {
    return volumes
      .map((volume) => ({
        ...volume,
        chapters: volume.chapters.filter(
          (chapter) =>
            (statusFilter === "all" || chapter.writingStatus === statusFilter) &&
            matchesQuery(chapter, normalizedQuery),
        ),
      }))
      .filter((volume) => volume.chapters.length > 0);
  }, [normalizedQuery, statusFilter, volumes]);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Dialog.Content
        className="chapter-corkboard-content"
        maxWidth="1120px"
        style={{ width: "min(1120px, calc(100vw - 32px))" }}
      >
        <Dialog.Title className="chapter-corkboard-visually-hidden">
          {t("writing.chapterPlan.corkboardTitle")}
        </Dialog.Title>
        <Dialog.Description className="chapter-corkboard-visually-hidden">
          {t("writing.chapterPlan.corkboardDescription")}
        </Dialog.Description>
        <div className="chapter-corkboard-header">
          <Flex
            align="center"
            justify="between"
            gap="3"
          >
            <Box>
              <Text
                size="4"
                weight="bold"
              >
                {t("writing.chapterPlan.corkboardTitle")}
              </Text>
              <Text
                as="p"
                size="1"
                color="gray"
                mt="1"
              >
                {t("writing.chapterPlan.corkboardDescription")}
              </Text>
            </Box>
            <TextField.Root
              value={query}
              placeholder={t("writing.chapterPlan.searchPlaceholder")}
              onChange={(event) => setQuery(event.target.value)}
              style={{ width: 220 }}
            />
          </Flex>
          <div className="chapter-corkboard-filters">
            <button
              type="button"
              className="chapter-corkboard-filter"
              data-active={statusFilter === "all" ? "true" : "false"}
              onClick={() => setStatusFilter("all")}
            >
              {t("writing.chapterPlan.filterAll", { count: allChapters.length })}
            </button>
            {WRITING_STATUSES.map((status) => (
              <button
                key={status}
                type="button"
                className="chapter-corkboard-filter"
                data-active={statusFilter === status ? "true" : "false"}
                onClick={() => setStatusFilter(status)}
              >
                {t("writing.chapterPlan.filterStatus", {
                  status: t(`writing.chapterPlan.statuses.${status}`),
                  count: counts[status],
                })}
              </button>
            ))}
          </div>
        </div>
        <ScrollArea className="chapter-corkboard-body">
          {isLoading ? (
            <Text
              size="2"
              color="gray"
            >
              {t("writing.chapterPlan.loading")}
            </Text>
          ) : allChapters.length === 0 ? (
            <Text
              size="2"
              color="gray"
            >
              {t("writing.chapterPlan.empty")}
            </Text>
          ) : visibleVolumes.length === 0 ? (
            <Text
              size="2"
              color="gray"
            >
              {t("writing.chapterPlan.emptyFilter")}
            </Text>
          ) : (
            visibleVolumes.map((volume) => (
              <VolumeSection
                key={volume.id}
                volume={volume}
                isAgentLocked={isAgentLocked}
                onOpenChapter={onOpenChapter}
              />
            ))
          )}
        </ScrollArea>
      </Dialog.Content>
    </Dialog.Root>
  );
}

function VolumeSection({
  volume,
  isAgentLocked,
  onOpenChapter,
}: {
  volume: VolumeWithChapters;
  isAgentLocked: boolean;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
}) {
  return (
    <section className="chapter-corkboard-volume">
      <Text
        size="2"
        weight="medium"
        mb="2"
        as="p"
      >
        {volume.title}
      </Text>
      <div className="chapter-corkboard-grid">
        {volume.chapters.map((chapter) => (
          <ChapterCorkboardCard
            key={chapter.id}
            chapter={chapter}
            isAgentLocked={isAgentLocked}
            onOpenChapter={onOpenChapter}
          />
        ))}
      </div>
    </section>
  );
}
