import { Box, Dialog, Flex, ScrollArea, Text, TextField } from "@radix-ui/themes";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { corkboardLengthLabel } from "@/lib/chapter-length";
import { SYNOPSIS_MAX_LENGTH, WRITING_STATUSES, type WritingStatus } from "@/lib/chapter-plan";
import type { ChapterListItem, VolumeWithChapters } from "@/lib/chapter.types";
import {
  CORKBOARD_OPEN_PLANT_PREVIEW,
  corkboardOpenPlantNames,
  previewOpenPlantNames,
} from "@/lib/corkboard-open-threads";

import { useChapterPlanDraft } from "../hooks/use-chapter-plan-draft";
import { usePlotThreads } from "../hooks/use-plot-threads";
import { useVolumeTree } from "../hooks/use-volumes";
import { WritingStatusSelect } from "./chapter-plan-status";
import { ChapterWordTarget } from "./chapter-word-target";
import { OpenMarginNoteCount } from "./open-margin-note-count";

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
const EMPTY_OPEN_PLANTS: Record<string, readonly string[]> = {};

function CorkboardOpenPlants({ names }: { names: readonly string[] }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const { shown, hiddenCount } = previewOpenPlantNames(names, expanded);
  const canToggle = names.length > CORKBOARD_OPEN_PLANT_PREVIEW;

  return (
    <div
      className="chapter-corkboard-card__threads"
      data-testid="corkboard-open-threads"
    >
      <span className="chapter-corkboard-card__threads-label">
        {t("writing.chapterPlan.openThreadsLabel")}
      </span>
      {shown.map((name, index) => (
        <span
          key={`${index}-${name}`}
          className="chapter-corkboard-card__thread"
          data-testid="corkboard-open-thread"
          title={name}
        >
          {name}
        </span>
      ))}
      {canToggle ? (
        <button
          type="button"
          className="chapter-corkboard-card__threads-more"
          data-testid="corkboard-open-threads-more"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {hiddenCount > 0
            ? t("writing.chapterPlan.openThreadsMore", { count: hiddenCount })
            : t("writing.chapterPlan.openThreadsLess")}
        </button>
      ) : null}
    </div>
  );
}

function ChapterCorkboardLength({ written, target }: { written: number; target: number | null }) {
  const { t } = useTranslation();
  const label = corkboardLengthLabel(written, target, (key, options) =>
    options ? t(key, options) : t(key),
  );
  if (!label) return null;
  return (
    <p
      className="chapter-corkboard-card__gap"
      data-pace={label.pace}
      data-testid="corkboard-length-mark"
    >
      {label.text}
    </p>
  );
}

function ChapterCorkboardCard({
  chapter,
  openPlantsByChapter,
  isAgentLocked,
  onOpenChapter,
}: {
  chapter: ChapterListItem;
  openPlantsByChapter: Readonly<Record<string, readonly string[]>>;
  isAgentLocked: boolean;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
}) {
  const { t } = useTranslation();
  const draft = useChapterPlanDraft(chapter, isAgentLocked);
  const openPlantNames = corkboardOpenPlantNames(
    draft.writingStatus,
    openPlantsByChapter,
    chapter.id,
  );

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
        <OpenMarginNoteCount
          count={chapter.openMarginNoteCount}
          onOpen={() => onOpenChapter(chapter.id, chapter.title)}
        />
        <WritingStatusSelect
          value={draft.writingStatus}
          disabled={isAgentLocked}
          onChange={draft.setWritingStatus}
        />
      </Flex>
      <ChapterCorkboardLength
        written={chapter.wordCount}
        target={chapter.wordCountTarget}
      />
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
      {openPlantNames.length > 0 ? <CorkboardOpenPlants names={openPlantNames} /> : null}
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
  const { data: plotBoard } = usePlotThreads(open ? projectId : null);
  const openPlantsByChapter = plotBoard?.openPlantsByChapter ?? EMPTY_OPEN_PLANTS;
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
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
                openPlantsByChapter={openPlantsByChapter}
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
  openPlantsByChapter,
  isAgentLocked,
  onOpenChapter,
}: {
  volume: VolumeWithChapters;
  openPlantsByChapter: Readonly<Record<string, readonly string[]>>;
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
            openPlantsByChapter={openPlantsByChapter}
            isAgentLocked={isAgentLocked}
            onOpenChapter={onOpenChapter}
          />
        ))}
      </div>
    </section>
  );
}
