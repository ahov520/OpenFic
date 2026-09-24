import { Box, Dialog, Flex, ScrollArea, Switch, Text, TextField } from "@radix-ui/themes";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { SYNOPSIS_MAX_LENGTH, WRITING_STATUSES } from "@/lib/chapter-plan";
import type { ChapterListItem, VolumeWithChapters } from "@/lib/chapter.types";

import { useChapterPlanDraft } from "../hooks/use-chapter-plan-draft";
import { useVolumeTree } from "../hooks/use-volumes";
import {
  DEFAULT_CORKBOARD_VIEW,
  type CorkboardStatusFilter,
  type CorkboardView,
  type CorkboardVolumeCards,
  corkboardVolumeCards,
  corkboardVolumeEmptyKind,
  countChaptersMissingWordCountTarget,
  isChapterOutsideCorkboardView,
} from "../lib/corkboard-missing-target";
import { WritingStatusSelect } from "./chapter-plan-status";
import { ChapterWordTarget } from "./chapter-word-target";

import "./chapter-plan.css";

interface ChapterCorkboardProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
  currentChapterId?: string | null;
  isAgentLocked?: boolean;
}

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
      data-chapter-id={chapter.id}
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
  currentChapterId = null,
  isAgentLocked = false,
}: ChapterCorkboardProps) {
  const { t } = useTranslation();
  const { data, isLoading } = useVolumeTree(projectId);
  const [statusFilter, setStatusFilter] = useState<CorkboardStatusFilter>(
    DEFAULT_CORKBOARD_VIEW.statusFilter,
  );
  const [missingTargetOnly, setMissingTargetOnly] = useState(
    DEFAULT_CORKBOARD_VIEW.missingTargetOnly,
  );
  const [query, setQuery] = useState(DEFAULT_CORKBOARD_VIEW.query);
  const normalizedQuery = query.trim().toLowerCase();
  const view = useMemo<CorkboardView>(
    () => ({ statusFilter, missingTargetOnly, query: normalizedQuery }),
    [missingTargetOnly, normalizedQuery, statusFilter],
  );
  const volumes = data?.volumes ?? EMPTY_VOLUMES;
  const allChapters = useMemo(() => volumes.flatMap((volume) => volume.chapters), [volumes]);
  const counts = useMemo(() => {
    const next = {
      idea: 0,
      drafting: 0,
      revising: 0,
      done: 0,
    };
    for (const chapter of allChapters) next[chapter.writingStatus] += 1;
    return next;
  }, [allChapters]);
  const missingTargetCount = useMemo(
    () => countChaptersMissingWordCountTarget(allChapters),
    [allChapters],
  );
  const visibleVolumes = useMemo(() => corkboardVolumeCards(volumes, view), [view, volumes]);
  const currentChapter = useMemo(
    () => allChapters.find((chapter) => chapter.id === currentChapterId) ?? null,
    [allChapters, currentChapterId],
  );
  const currentChapterHidden = isChapterOutsideCorkboardView(currentChapter, view);

  const showAllChapters = () => {
    setStatusFilter(DEFAULT_CORKBOARD_VIEW.statusFilter);
    setMissingTargetOnly(DEFAULT_CORKBOARD_VIEW.missingTargetOnly);
    setQuery(DEFAULT_CORKBOARD_VIEW.query);
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
            <div
              className="chapter-corkboard-missing-target"
              data-active={missingTargetOnly ? "true" : "false"}
            >
              <Switch
                id="corkboard-missing-target"
                size="1"
                checked={missingTargetOnly}
                aria-label={t("writing.chapterPlan.filterMissingTarget", {
                  count: missingTargetCount,
                })}
                onCheckedChange={setMissingTargetOnly}
              />
              <label htmlFor="corkboard-missing-target">
                {t("writing.chapterPlan.filterMissingTarget", { count: missingTargetCount })}
              </label>
            </div>
          </div>
          {currentChapterHidden && currentChapter ? (
            <div className="chapter-corkboard-outside">
              <Text
                size="2"
                color="gray"
              >
                {t("writing.chapterPlan.currentOutsideFilter", {
                  title: currentChapter.title || t("writing.untitledChapter"),
                })}
              </Text>
              <button
                type="button"
                className="chapter-corkboard-filter"
                onClick={showAllChapters}
              >
                {t("writing.chapterPlan.showAllChapters")}
              </button>
            </div>
          ) : null}
        </div>
        <ScrollArea className="chapter-corkboard-body">
          {isLoading ? (
            <Text
              size="2"
              color="gray"
            >
              {t("writing.chapterPlan.loading")}
            </Text>
          ) : volumes.length === 0 ? (
            <Text
              size="2"
              color="gray"
            >
              {t("writing.chapterPlan.empty")}
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
  volume: CorkboardVolumeCards<ChapterListItem>;
  isAgentLocked: boolean;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
}) {
  const { t } = useTranslation();
  const emptyKind = corkboardVolumeEmptyKind(volume);

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
      {emptyKind === "cards" ? (
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
      ) : (
        <Text
          size="1"
          color="gray"
          as="p"
        >
          {emptyKind === "source" ? t("volume.empty") : t("writing.chapterPlan.emptyVolumeFilter")}
        </Text>
      )}
    </section>
  );
}
