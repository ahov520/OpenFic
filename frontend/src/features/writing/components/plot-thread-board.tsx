import { Box, Button, Dialog, Flex, ScrollArea, Text } from "@radix-ui/themes";
import axios from "axios";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import type {
  PlotBeat,
  PlotBeatKind,
  PlotBoardView,
  PlotChapterOption,
  PlotThread,
} from "@/lib/plot-thread";
import {
  PLOT_BEAT_KINDS,
  PLOT_THREAD_STATUSES,
  STALE_CHAPTER_GAP,
  selectPlotThreads,
} from "@/lib/plot-thread";

import {
  useCreatePlotBeat,
  useCreatePlotThread,
  useDeletePlotBeat,
  useDeletePlotThread,
  usePlotThreads,
  useUpdatePlotBeat,
  useUpdatePlotThread,
} from "../hooks/use-plot-threads";
import { GapChapterList } from "./plot-gap-chapters";
import { PlotTimeline } from "./plot-timeline";

import "./plot-thread.css";

interface PlotThreadBoardProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
  isAgentLocked?: boolean;
  currentChapterId?: string | null;
}

const EMPTY_THREADS: PlotThread[] = [];
const EMPTY_CHAPTERS: PlotChapterOption[] = [];

function chapterLabel(chapter: { globalOrder: number; title: string }, untitled: string): string {
  return `${chapter.globalOrder}. ${chapter.title || untitled}`;
}

function reportPlotError(error: unknown, fallback: string, duplicate: string): void {
  if (axios.isAxiosError(error) && error.response?.status === 409) {
    toast.error(duplicate);
    return;
  }
  toast.error(fallback);
}

export function PlotThreadBoard({
  projectId,
  open,
  onOpenChange,
  onOpenChapter,
  isAgentLocked = false,
  currentChapterId = null,
}: PlotThreadBoardProps) {
  const { t } = useTranslation();
  const { data, isLoading } = usePlotThreads(open ? projectId : null);
  const createThread = useCreatePlotThread(projectId);
  const [filter, setFilter] = useState<PlotBoardView>("issues");
  const [view, setView] = useState<"board" | "timeline">("board");
  const [name, setName] = useState("");
  const [intent, setIntent] = useState("");
  const threads = data?.threads ?? EMPTY_THREADS;
  const chapters = data?.chapters ?? EMPTY_CHAPTERS;
  const issueCount = threads.filter((thread) => thread.issues.length > 0).length;
  const openCount = threads.filter((thread) => thread.issues.includes("open")).length;
  const quietCount = threads.filter((thread) => thread.chaptersSinceLast != null).length;
  const visible = useMemo(() => selectPlotThreads(threads, filter), [filter, threads]);

  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed || isAgentLocked) return;
    try {
      await createThread.mutateAsync({ name: trimmed, intent: intent.trim() });
      setName("");
      setIntent("");
      setFilter("all");
    } catch (error) {
      reportPlotError(
        error,
        t("writing.plotThreads.saveFailed"),
        t("writing.plotThreads.duplicateBeat"),
      );
    }
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Dialog.Content
        className="plot-thread-content"
        maxWidth="920px"
        style={{ width: "min(920px, calc(100vw - 32px))" }}
      >
        <Dialog.Title className="chapter-corkboard-visually-hidden">
          {t("writing.plotThreads.title")}
        </Dialog.Title>
        <Dialog.Description className="chapter-corkboard-visually-hidden">
          {t("writing.plotThreads.description")}
        </Dialog.Description>
        <div className="plot-thread-header">
          <Box>
            <Text
              size="4"
              weight="bold"
            >
              {t("writing.plotThreads.title")}
            </Text>
            <Text
              as="p"
              size="1"
              color="gray"
              mt="1"
            >
              {t("writing.plotThreads.description")}
            </Text>
          </Box>
          <div className="chapter-corkboard-filters">
            <FilterButton
              active={view === "board"}
              label={t("writing.plotThreads.viewBoard")}
              onClick={() => setView("board")}
            />
            <FilterButton
              active={view === "timeline"}
              label={t("writing.plotThreads.viewTimeline")}
              onClick={() => setView("timeline")}
            />
            <FilterButton
              active={filter === "issues"}
              label={t("writing.plotThreads.filterIssues", { count: issueCount })}
              onClick={() => setFilter("issues")}
            />
            <FilterButton
              active={filter === "open"}
              label={t("writing.plotThreads.filterOpen", { count: openCount })}
              onClick={() => setFilter("open")}
            />
            <FilterButton
              active={filter === "quiet"}
              label={t("writing.plotThreads.filterQuiet", { count: quietCount })}
              onClick={() => setFilter("quiet")}
            />
            <FilterButton
              active={filter === "all"}
              label={t("writing.plotThreads.filterAll", { count: threads.length })}
              onClick={() => setFilter("all")}
            />
          </div>
        </div>
        <form
          className="plot-thread-create"
          onSubmit={(event) => {
            event.preventDefault();
            void create();
          }}
        >
          <div className="plot-thread-create__fields">
            <input
              className="plot-thread-input"
              aria-label={t("writing.plotThreads.name")}
              placeholder={t("writing.plotThreads.namePlaceholder")}
              value={name}
              disabled={isAgentLocked}
              maxLength={80}
              onChange={(event) => setName(event.target.value)}
            />
            <input
              className="plot-thread-input"
              aria-label={t("writing.plotThreads.intent")}
              placeholder={t("writing.plotThreads.intentPlaceholder")}
              value={intent}
              disabled={isAgentLocked}
              maxLength={200}
              onChange={(event) => setIntent(event.target.value)}
            />
            <Button
              type="submit"
              size="1"
              disabled={isAgentLocked || name.trim() === "" || createThread.isPending}
            >
              {t("writing.plotThreads.create")}
            </Button>
          </div>
        </form>
        <ScrollArea className="plot-thread-body">
          {isLoading ? (
            <p className="plot-thread-quiet">{t("writing.plotThreads.loading")}</p>
          ) : view === "timeline" && visible.length > 0 ? (
            <PlotTimeline
              projectId={projectId}
              threads={visible}
              chapters={chapters}
              disabled={isAgentLocked}
              currentChapterId={currentChapterId}
              onOpenChapter={onOpenChapter}
            />
          ) : visible.length === 0 ? (
            <p className="plot-thread-quiet">
              {filter === "open"
                ? t("writing.plotThreads.emptyOpen")
                : filter === "quiet"
                  ? t("writing.plotThreads.emptyQuiet")
                  : filter === "all"
                    ? t("writing.plotThreads.emptyAll")
                    : t("writing.plotThreads.emptyIssues")}
            </p>
          ) : (
            <div className="plot-thread-list">
              {visible.map((thread) => (
                <ThreadCard
                  key={thread.id}
                  projectId={projectId}
                  thread={thread}
                  chapters={chapters}
                  disabled={isAgentLocked}
                  onOpenChapter={onOpenChapter}
                />
              ))}
            </div>
          )}
        </ScrollArea>
      </Dialog.Content>
    </Dialog.Root>
  );
}

function FilterButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="chapter-corkboard-filter"
      data-active={active ? "true" : "false"}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function ThreadCard({
  projectId,
  thread,
  chapters,
  disabled,
  onOpenChapter,
}: {
  projectId: string;
  thread: PlotThread;
  chapters: PlotChapterOption[];
  disabled: boolean;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
}) {
  const { t } = useTranslation();
  const updateThread = useUpdatePlotThread(projectId);
  const deleteThread = useDeletePlotThread(projectId);
  const createBeat = useCreatePlotBeat(projectId);
  const [name, setName] = useState(thread.name);
  const [intent, setIntent] = useState(thread.intent);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [chapterId, setChapterId] = useState("");
  const [kind, setKind] = useState<PlotBeatKind>("plant");
  const [note, setNote] = useState("");
  const nameFocused = useRef(false);
  const intentFocused = useRef(false);
  const usedIds = new Set(thread.beats.map((beat) => beat.chapterId));
  const available = chapters.filter((chapter) => !usedIds.has(chapter.id));

  useEffect(() => {
    if (!nameFocused.current) setName(thread.name);
  }, [thread.name]);

  useEffect(() => {
    if (!intentFocused.current) setIntent(thread.intent);
  }, [thread.intent]);

  const availableKey = available.map((chapter) => chapter.id).join("\0");

  useEffect(() => {
    const ids = availableKey ? availableKey.split("\0") : [];
    if (!ids.includes(chapterId)) setChapterId(ids[0] ?? "");
  }, [availableKey, chapterId]);

  const saveThread = async (data: {
    name?: string;
    intent?: string;
    status?: PlotThread["status"];
  }) => {
    try {
      await updateThread.mutateAsync({ threadId: thread.id, data });
    } catch (error) {
      reportPlotError(
        error,
        t("writing.plotThreads.saveFailed"),
        t("writing.plotThreads.duplicateBeat"),
      );
    }
  };

  const attach = async () => {
    if (!chapterId || disabled) return;
    try {
      await createBeat.mutateAsync({
        threadId: thread.id,
        data: { chapterId, kind, note: note.trim() },
      });
      setNote("");
      setKind("plant");
    } catch (error) {
      reportPlotError(
        error,
        t("writing.plotThreads.saveFailed"),
        t("writing.plotThreads.duplicateBeat"),
      );
    }
  };

  return (
    <article
      className="plot-thread-card"
      data-status={thread.status}
      data-clean={thread.issues.length === 0 ? "true" : "false"}
      data-testid="plot-thread-card"
    >
      <div className="plot-thread-card__title-row">
        <input
          className="plot-thread-input plot-thread-card__name"
          aria-label={t("writing.plotThreads.name")}
          value={name}
          disabled={disabled}
          maxLength={80}
          onFocus={() => {
            nameFocused.current = true;
          }}
          onBlur={() => {
            nameFocused.current = false;
            const trimmed = name.trim();
            if (trimmed && trimmed !== thread.name) {
              void saveThread({ name: trimmed });
            } else {
              setName(thread.name);
            }
          }}
          onChange={(event) => setName(event.target.value)}
        />
        <select
          className="writing-status-select"
          aria-label={t("writing.plotThreads.status")}
          value={thread.status}
          disabled={disabled}
          onChange={(event) => {
            void saveThread({ status: event.target.value as PlotThread["status"] });
          }}
        >
          {PLOT_THREAD_STATUSES.map((status) => (
            <option
              key={status}
              value={status}
            >
              {t(`writing.plotThreads.statuses.${status}`)}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="plot-thread-delete"
          data-confirm={confirmDelete ? "true" : "false"}
          disabled={disabled || deleteThread.isPending}
          onClick={() => {
            if (!confirmDelete) {
              setConfirmDelete(true);
              return;
            }
            void deleteThread.mutateAsync(thread.id).catch((error: unknown) => {
              reportPlotError(
                error,
                t("writing.plotThreads.saveFailed"),
                t("writing.plotThreads.duplicateBeat"),
              );
            });
          }}
        >
          {confirmDelete
            ? t("writing.plotThreads.confirmDeleteThread")
            : t("writing.plotThreads.deleteThread")}
        </button>
      </div>
      <input
        className="plot-thread-input"
        aria-label={t("writing.plotThreads.intent")}
        placeholder={t("writing.plotThreads.intentPlaceholder")}
        value={intent}
        disabled={disabled}
        maxLength={200}
        onFocus={() => {
          intentFocused.current = true;
        }}
        onBlur={() => {
          intentFocused.current = false;
          const trimmed = intent.trim();
          if (trimmed !== thread.intent) {
            void saveThread({ intent: trimmed });
          }
        }}
        onChange={(event) => setIntent(event.target.value)}
      />
      {thread.issues.length > 0 && (
        <div
          className="plot-thread-issues"
          data-testid="plot-thread-issues"
        >
          {thread.issues.map((issue) => (
            <span
              key={issue}
              className="plot-thread-issue"
              data-issue={issue}
            >
              {t(`writing.plotThreads.issues.${issue}`, { defaultValue: issue })}
            </span>
          ))}
        </div>
      )}
      <p className="plot-thread-last">
        {thread.lastGlobalOrder == null || thread.lastKind == null
          ? t("writing.plotThreads.neverSeen")
          : t("writing.plotThreads.lastSeen", {
              order: thread.lastGlobalOrder,
              title: thread.lastChapterTitle || t("writing.untitledChapter"),
              kind: t(`writing.plotThreads.kinds.${thread.lastKind}`),
            })}
      </p>
      {thread.chaptersSinceLast != null && (
        <p
          className="plot-thread-gap"
          data-stale={thread.chaptersSinceLast >= STALE_CHAPTER_GAP ? "true" : "false"}
          data-testid="plot-thread-gap"
        >
          {thread.chaptersSinceLast === 0
            ? t("writing.plotThreads.gapToEndZero")
            : t("writing.plotThreads.gapToEnd", { count: thread.chaptersSinceLast })}
        </p>
      )}
      {thread.gapChapters.length > 0 && (
        <GapChapterList
          chapters={thread.gapChapters}
          range={thread.gapRange}
          onOpen={(chapterId) => {
            const chapter = chapters.find((item) => item.id === chapterId);
            onOpenChapter(chapterId, chapter?.title ?? "");
          }}
        />
      )}
      {thread.beats.length > 0 && (
        <div className="plot-thread-sequence">
          {thread.beats.map((beat) => (
            <button
              key={beat.id}
              type="button"
              className="plot-thread-chip"
              onClick={() => onOpenChapter(beat.chapterId, beat.chapterTitle)}
            >
              {chapterLabel(
                { globalOrder: beat.globalOrder, title: beat.chapterTitle },
                t("writing.untitledChapter"),
              )}{" "}
              · {t(`writing.plotThreads.kinds.${beat.kind}`)}
            </button>
          ))}
        </div>
      )}
      {thread.beats.map((beat) => (
        <BeatEditor
          key={beat.id}
          projectId={projectId}
          beat={beat}
          chapters={chapters}
          disabled={disabled}
        />
      ))}
      {chapters.length === 0 ? (
        <p className="plot-thread-quiet">{t("writing.plotThreads.noChapters")}</p>
      ) : available.length === 0 ? (
        <p className="plot-thread-quiet">{t("writing.plotThreads.allChaptersUsed")}</p>
      ) : (
        <form
          className="plot-thread-beat-row"
          onSubmit={(event) => {
            event.preventDefault();
            void attach();
          }}
        >
          <select
            className="writing-status-select"
            aria-label={t("writing.plotThreads.chapter")}
            value={chapterId}
            disabled={disabled}
            onChange={(event) => setChapterId(event.target.value)}
          >
            {available.map((chapter) => (
              <option
                key={chapter.id}
                value={chapter.id}
              >
                {chapterLabel(chapter, t("writing.untitledChapter"))}
              </option>
            ))}
          </select>
          <select
            className="writing-status-select"
            aria-label={t("writing.plotThreads.kind")}
            value={kind}
            disabled={disabled}
            onChange={(event) => setKind(event.target.value as PlotBeatKind)}
          >
            {PLOT_BEAT_KINDS.map((item) => (
              <option
                key={item}
                value={item}
              >
                {t(`writing.plotThreads.kinds.${item}`)}
              </option>
            ))}
          </select>
          <input
            className="plot-thread-note"
            aria-label={t("writing.plotThreads.note")}
            placeholder={t("writing.plotThreads.notePlaceholder")}
            value={note}
            disabled={disabled}
            maxLength={200}
            onChange={(event) => setNote(event.target.value)}
          />
          <Button
            type="submit"
            size="1"
            variant="soft"
            disabled={disabled || !chapterId || createBeat.isPending}
          >
            {t("writing.plotThreads.attach")}
          </Button>
        </form>
      )}
    </article>
  );
}

function BeatEditor({
  projectId,
  beat,
  chapters,
  disabled,
}: {
  projectId: string;
  beat: PlotBeat;
  chapters: PlotChapterOption[];
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const updateBeat = useUpdatePlotBeat(projectId);
  const deleteBeat = useDeletePlotBeat(projectId);
  const [note, setNote] = useState(beat.note);
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) setNote(beat.note);
  }, [beat.note]);

  const save = async (data: { chapterId?: string; kind?: PlotBeatKind; note?: string }) => {
    try {
      await updateBeat.mutateAsync({ beatId: beat.id, data });
    } catch (error) {
      reportPlotError(
        error,
        t("writing.plotThreads.saveFailed"),
        t("writing.plotThreads.duplicateBeat"),
      );
    }
  };

  return (
    <Flex
      align="center"
      gap="2"
    >
      <select
        className="writing-status-select"
        aria-label={t("writing.plotThreads.chapter")}
        value={beat.chapterId}
        disabled={disabled}
        onChange={(event) => {
          void save({ chapterId: event.target.value });
        }}
      >
        {chapters.map((chapter) => (
          <option
            key={chapter.id}
            value={chapter.id}
          >
            {chapterLabel(chapter, t("writing.untitledChapter"))}
          </option>
        ))}
      </select>
      <select
        className="writing-status-select"
        aria-label={t("writing.plotThreads.kind")}
        value={beat.kind}
        disabled={disabled}
        onChange={(event) => {
          void save({ kind: event.target.value as PlotBeatKind });
        }}
      >
        {PLOT_BEAT_KINDS.map((item) => (
          <option
            key={item}
            value={item}
          >
            {t(`writing.plotThreads.kinds.${item}`)}
          </option>
        ))}
      </select>
      <input
        className="plot-thread-note"
        aria-label={t("writing.plotThreads.note")}
        value={note}
        disabled={disabled}
        maxLength={200}
        onFocus={() => {
          focused.current = true;
        }}
        onBlur={() => {
          focused.current = false;
          if (note.trim() !== beat.note) void save({ note: note.trim() });
        }}
        onChange={(event) => setNote(event.target.value)}
      />
      <button
        type="button"
        className="plot-thread-delete"
        disabled={disabled || deleteBeat.isPending}
        onClick={() => {
          void deleteBeat.mutateAsync(beat.id).catch((error: unknown) => {
            reportPlotError(
              error,
              t("writing.plotThreads.saveFailed"),
              t("writing.plotThreads.duplicateBeat"),
            );
          });
        }}
      >
        {t("writing.plotThreads.deleteBeat")}
      </button>
    </Flex>
  );
}
