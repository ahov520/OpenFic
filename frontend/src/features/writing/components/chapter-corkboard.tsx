import { Box, Dialog, Flex, ScrollArea, Text, TextField } from "@radix-ui/themes";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { SYNOPSIS_MAX_LENGTH, WRITING_STATUSES, type WritingStatus } from "@/lib/chapter-plan";
import type { ChapterListItem, VolumeWithChapters } from "@/lib/chapter.types";
import type { PlotThread } from "@/lib/plot-thread";

import { useChapterPlanDraft } from "../hooks/use-chapter-plan-draft";
import { usePlotThreads } from "../hooks/use-plot-threads";
import { useVolumeTree } from "../hooks/use-volumes";
import {
  INITIAL_CORKBOARD_FILTER,
  visibleCorkboardVolumes,
  type CorkboardStatusFilter,
} from "../lib/corkboard-owing";
import { useWritingStore } from "../store/use-writing-store";
import { WritingStatusSelect } from "./chapter-plan-status";
import { ChapterWordTarget } from "./chapter-word-target";

import "./chapter-plan.css";

interface ChapterCorkboardProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
  isAgentLocked?: boolean;
}

const EMPTY_VOLUMES: VolumeWithChapters[] = [];
const EMPTY_THREADS: PlotThread[] = [];

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
          : null}
        <ChapterWordTarget
          chapterId={chapter.id}
          written={chapter.wordCount}
          target={chapter.wordCountTarget}
          disabled={isAgentLocked}
        />
      </div>
    </article>
  );
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
  const plotThreads = usePlotThreads(open ? projectId : null);
  const currentChapterId = useWritingStore((state) => state.currentChapterId);
  const [statusFilter, setStatusFilter] = useState<CorkboardStatusFilter>(
    INITIAL_CORKBOARD_FILTER.status,
  );
  const [owingOnly, setOwingOnly] = useState(INITIAL_CORKBOARD_FILTER.owingOnly);
  const [query, setQuery] = useState(INITIAL_CORKBOARD_FILTER.query);
  const threads = plotThreads.data?.threads ?? EMPTY_THREADS;
  const owingApplied = owingOnly && plotThreads.isSuccess;
  const owingPending = owingOnly && plotThreads.isLoading;
  const volumes = data?.volumes ?? EMPTY_VOLUMES;
  const allChapters = useMemo(() => volumes.flatMap((volume) => volume.chapters), [volumes]);
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
  const owingCount = useMemo(() => {
    if (!plotThreads.isSuccess) return 0;
    return visibleCorkboardVolumes(
      volumes,
      { status: "all", owingOnly: true, query: "" },
      threads,
    ).reduce((sum, volume) => sum + volume.chapters.length, 0);
  }, [plotThreads.isSuccess, threads, volumes]);
  const shownVolumes = useMemo(
    () =>
      visibleCorkboardVolumes(
        volumes,
        { status: statusFilter, owingOnly: owingApplied, query },
        threads,
      ),
    [owingApplied, query, statusFilter, threads, volumes],
  );
  const currentChapterHidden = useMemo(() => {
    if (owingPending || !currentChapterId) return false;
    if (!allChapters.some((chapter) => chapter.id === currentChapterId)) return false;
    return !shownVolumes.some((volume) =>
      volume.chapters.some((chapter) => chapter.id === currentChapterId),
    );
  }, [allChapters, currentChapterId, owingPending, shownVolumes]);

  const showAll = () => {
    setStatusFilter(INITIAL_CORKBOARD_FILTER.status);
    setOwingOnly(INITIAL_CORKBOARD_FILTER.owingOnly);
    setQuery(INITIAL_CORKBOARD_FILTER.query);
  };

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
            <div className="chapter-corkboard-filters__status">
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
            <button
              type="button"
              className="chapter-corkboard-filter chapter-corkboard-owing"
              data-active={owingOnly ? "true" : "false"}
              aria-pressed={owingOnly}
              title={t("writing.chapterPlan.filterOwingHint")}
              onClick={() => setOwingOnly((current) => !current)}
            >
              {t("writing.chapterPlan.filterOwing", { count: owingCount })}
            </button>
          </div>
          {owingOnly ? (
            <p className="chapter-corkboard-owing-note">
              {t("writing.chapterPlan.owingActiveNote")}
            </p>
          ) : null}
          {plotThreads.isError && owingOnly ? (
            <p className="chapter-corkboard-owing-note">{t("writing.chapterPlan.owingFailed")}</p>
          ) : null}
          {currentChapterHidden ? (
            <div className="chapter-corkboard-return">
              <p className="chapter-corkboard-owing-note">
                {t("writing.chapterPlan.currentHidden")}
              </p>
              <button
                type="button"
                className="chapter-corkboard-filter"
                onClick={showAll}
              >
                {t("writing.chapterPlan.backToAll")}
              </button>
            </div>
          ) : null}
        </div>
        <ScrollArea className="chapter-corkboard-body">
          {isLoading || owingPending ? (
            <Text
              size="2"
              color="gray"
            >
              {owingPending ? t("writing.plotThreads.loading") : t("writing.chapterPlan.loading")}
            </Text>
          ) : owingApplied ? (
            volumes.length === 0 ? (
              <Text
                size="2"
                color="gray"
              >
                {t("writing.chapterPlan.empty")}
              </Text>
            ) : (
              shownVolumes.map((volume) => (
                <VolumeSection
                  key={volume.id}
                  volume={volume}
                  isAgentLocked={isAgentLocked}
                  onOpenChapter={onOpenChapter}
                />
              ))
            )
          ) : allChapters.length === 0 ? (
            <Text
              size="2"
              color="gray"
            >
              {t("writing.chapterPlan.empty")}
            </Text>
          ) : shownVolumes.length === 0 ? (
            <Text
              size="2"
              color="gray"
            >
              {t("writing.chapterPlan.emptyFilter")}
            </Text>
          ) : (
            shownVolumes.map((volume) => (
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
  volume: {
    id: string;
    title: string;
    chapters: ChapterListItem[];
    placeholder: "cards" | "empty-volume" | "empty-filter";
  };
  isAgentLocked: boolean;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <section
      className="chapter-corkboard-volume"
      data-placeholder={volume.placeholder}
    >
      <Text
        size="2"
        weight="medium"
        mb="2"
        as="p"
      >
        {volume.title}
      </Text>
      {volume.placeholder === "empty-volume" ? (
        <p className="chapter-corkboard-volume__empty">{t("volume.empty")}</p>
      ) : volume.placeholder === "empty-filter" ? (
        <p className="chapter-corkboard-volume__empty">
          {t("writing.chapterPlan.emptyVolumeFilter")}
        </p>
      ) : (
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
      )}
    </section>
  );
}
