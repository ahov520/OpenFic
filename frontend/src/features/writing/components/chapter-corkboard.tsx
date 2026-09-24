import { Box, Dialog, Flex, ScrollArea, Switch, Text, TextField } from "@radix-ui/themes";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { corkboardLengthLabel } from "@/lib/chapter-length";
import { SYNOPSIS_MAX_LENGTH, WRITING_STATUSES, corkboardMissingSynopsis } from "@/lib/chapter-plan";
import type { ChapterListItem, VolumeWithChapters } from "@/lib/chapter.types";
import {
  CORKBOARD_OPEN_PLANT_PREVIEW,
  corkboardOpenPlantNames,
  previewOpenPlantNames,
} from "@/lib/corkboard-open-threads";
import {
  arrangeCorkboardVolumes,
  corkboardDragReorderEnabled,
  type CorkboardChapterSort,
} from "@/lib/corkboard-sort";

import { useChapterPlanDraft } from "../hooks/use-chapter-plan-draft";
import { usePlotThreads } from "../hooks/use-plot-threads";
import { useVolumeTree } from "../hooks/use-volumes";
import { chapterOwesOpenPlant } from "../lib/corkboard-owing";
import {
  chapterMatchesMissingTarget,
  countChaptersMissingWordCountTarget,
} from "../lib/corkboard-missing-target";
import {
  type CorkboardStatusFilter,
  type CorkboardVolumeCards,
  corkboardVolumeCards,
  corkboardVolumeEmptyKind,
  countChaptersMatchingCorkboardStatus,
  isChapterOutsideCorkboardView,
} from "../lib/corkboard-status-filter";
import { WritingStatusSelect } from "./chapter-plan-status";
import { ChapterWordTarget } from "./chapter-word-target";
import { OpenMarginNoteCount } from "./open-margin-note-count";

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
const EMPTY_OPEN_PLANTS: Record<string, readonly string[]> = {};
const EMPTY_THREADS: readonly [] = [];

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
  dragReorderEnabled,
  isAgentLocked,
  onOpenChapter,
}: {
  chapter: ChapterListItem;
  openPlantsByChapter: Readonly<Record<string, readonly string[]>>;
  dragReorderEnabled: boolean;
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
  const synopsisId = `corkboard-synopsis-${chapter.id}`;
  const missingSynopsis = corkboardMissingSynopsis(draft.writingStatus, draft.synopsis);

  return (
    <article
      className="chapter-corkboard-card"
      data-chapter-id={chapter.id}
      data-status={draft.writingStatus}
      data-testid="corkboard-card"
      data-missing-synopsis={missingSynopsis ? "true" : "false"}
      draggable={dragReorderEnabled}
      onDragStart={(event) => {
        if (dragReorderEnabled) return;
        event.preventDefault();
      }}
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
      {missingSynopsis ? (
        <label
          htmlFor={synopsisId}
          className="chapter-corkboard-card__missing-synopsis"
          data-testid="corkboard-missing-synopsis"
        >
          {t("writing.chapterPlan.missingSynopsis")}
        </label>
      ) : null}
      <textarea
        id={synopsisId}
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
  const plotThreads = usePlotThreads(open ? projectId : null);
  const plotBoard = plotThreads.data;
  const openPlantsByChapter = plotBoard?.openPlantsByChapter ?? EMPTY_OPEN_PLANTS;
  const threads = plotBoard?.threads ?? EMPTY_THREADS;
  const [statusFilter, setStatusFilter] = useState<CorkboardStatusFilter>("all");
  const [missingTargetOnly, setMissingTargetOnly] = useState(false);
  const [owingOnly, setOwingOnly] = useState(false);
  const [chapterSort, setChapterSort] = useState<CorkboardChapterSort>("reading");
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const dragReorderEnabled = corkboardDragReorderEnabled(chapterSort);
  const volumes = data?.volumes ?? EMPTY_VOLUMES;
  const allChapters = useMemo(() => volumes.flatMap((volume) => volume.chapters), [volumes]);
  const writingCount = useMemo(
    () => countChaptersMatchingCorkboardStatus(allChapters, "writing"),
    [allChapters],
  );
  const statusCounts = useMemo(() => {
    return {
      idea: countChaptersMatchingCorkboardStatus(allChapters, "idea"),
      drafting: countChaptersMatchingCorkboardStatus(allChapters, "drafting"),
      revising: countChaptersMatchingCorkboardStatus(allChapters, "revising"),
      done: countChaptersMatchingCorkboardStatus(allChapters, "done"),
    };
  }, [allChapters]);
  useEffect(() => {
    setChapterSort("reading");
    setMissingTargetOnly(false);
    setOwingOnly(false);
  }, [projectId]);

  const missingTargetCount = useMemo(
    () => countChaptersMissingWordCountTarget(allChapters),
    [allChapters],
  );
  const owingApplied = owingOnly && plotThreads.isSuccess;
  const owingPending = owingOnly && plotThreads.isLoading;
  const owingCount = useMemo(() => {
    if (!plotThreads.isSuccess) return 0;
    return allChapters.filter((chapter) => chapterOwesOpenPlant(chapter, threads)).length;
  }, [allChapters, plotThreads.isSuccess, threads]);

  const visibleVolumes = useMemo(() => {
    const filtered = corkboardVolumeCards(volumes, statusFilter, normalizedQuery).map((volume) =>
      missingTargetOnly
        ? {
            ...volume,
            chapters: volume.chapters.filter((chapter) => chapterMatchesMissingTarget(chapter, true)),
          }
        : volume,
    );
    const owing = owingApplied
      ? filtered.map((volume) => ({
          ...volume,
          chapters: volume.chapters.filter((chapter) => chapterOwesOpenPlant(chapter, threads)),
        }))
      : filtered;
    return arrangeCorkboardVolumes(owing, chapterSort);
  }, [chapterSort, missingTargetOnly, normalizedQuery, owingApplied, statusFilter, threads, volumes]);
  const currentChapter = useMemo(
    () => allChapters.find((chapter) => chapter.id === currentChapterId) ?? null,
    [allChapters, currentChapterId],
  );
  const currentChapterHidden =
    !owingPending &&
    (isChapterOutsideCorkboardView(currentChapter, statusFilter, normalizedQuery) ||
      (missingTargetOnly &&
        currentChapter != null &&
        !chapterMatchesMissingTarget(currentChapter, true)) ||
      (owingApplied && currentChapter != null && !chapterOwesOpenPlant(currentChapter, threads)));

  const showAllChapters = () => {
    setStatusFilter("all");
    setMissingTargetOnly(false);
    setOwingOnly(false);
    setQuery("");
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
              data-filter="all"
              data-active={statusFilter === "all" ? "true" : "false"}
              onClick={() => setStatusFilter("all")}
            >
              {t("writing.chapterPlan.filterAll", { count: allChapters.length })}
            </button>
            <button
              type="button"
              className="chapter-corkboard-filter"
              data-filter="writing"
              data-active={statusFilter === "writing" ? "true" : "false"}
              onClick={() => setStatusFilter("writing")}
            >
              {t("writing.chapterPlan.filterWriting", { count: writingCount })}
            </button>
            {WRITING_STATUSES.map((status) => (
              <button
                key={status}
                type="button"
                className="chapter-corkboard-filter"
                data-filter={status}
                data-active={statusFilter === status ? "true" : "false"}
                onClick={() => setStatusFilter(status)}
              >
                {t("writing.chapterPlan.filterStatus", {
                  status: t(`writing.chapterPlan.statuses.${status}`),
                  count: statusCounts[status],
                })}
              </button>
            ))}
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
          {owingOnly ? (
            <p className="chapter-corkboard-owing-note">{t("writing.chapterPlan.owingActiveNote")}</p>
          ) : null}
          {plotThreads.isError && owingOnly ? (
            <p className="chapter-corkboard-owing-note">{t("writing.chapterPlan.owingFailed")}</p>
          ) : null}
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
          <div
            className="chapter-corkboard-filters"
            role="group"
            aria-label={t("writing.chapterPlan.sortLabel")}
          >
            <button
              type="button"
              className="chapter-corkboard-filter"
              data-active={chapterSort === "reading" ? "true" : "false"}
              data-testid="corkboard-sort-reading"
              aria-pressed={chapterSort === "reading"}
              onClick={() => setChapterSort("reading")}
            >
              {t("writing.chapterPlan.sortReading")}
            </button>
            <button
              type="button"
              className="chapter-corkboard-filter"
              data-active={chapterSort === "shortfall" ? "true" : "false"}
              data-testid="corkboard-sort-shortfall"
              aria-pressed={chapterSort === "shortfall"}
              onClick={() => setChapterSort("shortfall")}
            >
              {t("writing.chapterPlan.sortShortfall")}
            </button>
          </div>
          {chapterSort === "shortfall" ? (
            <Text
              size="1"
              color="gray"
              data-testid="corkboard-sort-hint"
            >
              {t("writing.chapterPlan.sortShortfallHint")}
            </Text>
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
                openPlantsByChapter={openPlantsByChapter}
                dragReorderEnabled={dragReorderEnabled}
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
  dragReorderEnabled,
  isAgentLocked,
  onOpenChapter,
}: {
  volume: CorkboardVolumeCards<ChapterListItem>;
  openPlantsByChapter: Readonly<Record<string, readonly string[]>>;
  dragReorderEnabled: boolean;
  isAgentLocked: boolean;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
}) {
  const { t } = useTranslation();
  const emptyKind = corkboardVolumeEmptyKind(volume);

  return (
    <section
      className="chapter-corkboard-volume"
      data-volume-id={volume.id}
    >
      <Text
        size="2"
        weight="medium"
        mb="2"
        as="p"
      >
        {volume.title}
      </Text>
      {emptyKind === "cards" ? (
        <div
          className="chapter-corkboard-grid"
          data-drag-reorder={dragReorderEnabled ? "enabled" : "disabled"}
          data-testid="corkboard-grid"
        >
          {volume.chapters.map((chapter) => (
            <ChapterCorkboardCard
              key={chapter.id}
              chapter={chapter}
              openPlantsByChapter={openPlantsByChapter}
              dragReorderEnabled={dragReorderEnabled}
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
