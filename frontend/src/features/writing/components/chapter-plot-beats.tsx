import { useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import { fetchPlotThreads } from "@/lib/api-client";
import type {
  PlotBeatKind,
  PlotChapterOption,
  PlotThread,
  PlotThroughGap,
  QuietGap,
} from "@/lib/plot-thread";
import {
  PLOT_BEAT_KINDS,
  STALE_CHAPTER_GAP,
  currentChapterBeatAction,
  quietGapBeforeChapter,
  readingChapterIds,
} from "@/lib/plot-thread";

import {
  useCreatePlotBeat,
  useDeletePlotBeat,
  usePlotGapsThroughChapter,
  usePlotThreads,
  useUpdatePlotBeat,
} from "../hooks/use-plot-threads";
import { GapChapterList } from "./plot-gap-chapters";

import "./plot-thread.css";

const EMPTY_THREADS: PlotThread[] = [];
const EMPTY_CHAPTERS: PlotChapterOption[] = [];
const NOTE_MAX_LENGTH = 200;

interface AdvanceFailure {
  message: string;
  tone: "error" | "notice";
}

interface ChapterPlotBeatsProps {
  projectId: string;
  chapterId: string;
  disabled?: boolean;
  onOpenBoard?: () => void;
  onOpenChapter?: (chapterId: string, chapterTitle: string) => void;
}

export function ChapterPlotBeats({
  projectId,
  chapterId,
  disabled = false,
  onOpenBoard,
  onOpenChapter,
}: ChapterPlotBeatsProps) {
  const { t } = useTranslation();
  const { data } = usePlotThreads(projectId);
  const { data: throughChapter } = usePlotGapsThroughChapter(projectId, chapterId);
  const createBeat = useCreatePlotBeat(projectId);
  const updateBeat = useUpdatePlotBeat(projectId);
  const deleteBeat = useDeletePlotBeat(projectId);
  const threads = data?.threads ?? EMPTY_THREADS;
  const chapters = data?.chapters ?? EMPTY_CHAPTERS;
  const readingOrder = useMemo(() => readingChapterIds(chapters), [chapters]);
  const throughById = useMemo(() => {
    const found = new Map<string, PlotThroughGap>();
    for (const item of throughChapter?.threads ?? []) found.set(item.id, item);
    return found;
  }, [throughChapter]);
  const stale = useMemo(
    () =>
      threads.flatMap((thread) => {
        const gap = quietGapBeforeChapter(thread, readingOrder, chapterId);
        if (gap == null || gap.chaptersSince < STALE_CHAPTER_GAP) return [];
        return [{ thread, gap }];
      }),
    [chapterId, readingOrder, threads],
  );
  const onChapter = useMemo(
    () =>
      threads.flatMap((thread) =>
        thread.beats
          .filter((beat) => beat.chapterId === chapterId)
          .map((beat) => ({ thread, beat })),
      ),
    [chapterId, threads],
  );
  const available = threads.filter(
    (thread) => !thread.beats.some((beat) => beat.chapterId === chapterId),
  );
  const [threadId, setThreadId] = useState("");
  const [advanceFailures, setAdvanceFailures] = useState<Record<string, AdvanceFailure>>({});

  const availableKey = available.map((thread) => thread.id).join("\0");

  useEffect(() => {
    const ids = availableKey ? availableKey.split("\0") : [];
    if (!ids.includes(threadId)) setThreadId(ids[0] ?? "");
  }, [availableKey, threadId]);

  useEffect(() => {
    setAdvanceFailures({});
  }, [chapterId]);

  const staleIds = new Set(stale.map(({ thread }) => thread.id));
  const leftoverFailures = Object.entries(advanceFailures).filter(([id]) => !staleIds.has(id));

  const report = (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 409) {
      toast.error(t("writing.plotThreads.duplicateBeat"));
      return;
    }
    toast.error(t("writing.plotThreads.saveFailed"));
  };

  return (
    <div className="chapter-plot-beats">
      <div className="plot-thread-card__title-row">
        <span className="plot-thread-quiet">{t("writing.plotThreads.chapterSection")}</span>
        {onOpenBoard && (
          <button
            type="button"
            className="plot-thread-text-button"
            onClick={onOpenBoard}
          >
            {t("writing.plotThreads.manage")}
          </button>
        )}
      </div>
      {stale.length > 0 && (
        <ul
          className="chapter-plot-stale"
          data-testid="plot-thread-consider"
        >
          {stale.map(({ thread, gap }) => (
            <ConsiderAdvanceItem
              key={thread.id}
              projectId={projectId}
              chapterId={chapterId}
              thread={thread}
              gap={gap}
              throughGap={throughById.get(thread.id) ?? null}
              chapters={chapters}
              disabled={disabled}
              onOpenChapter={onOpenChapter}
              onFailure={(threadIdToMark, failure) => {
                setAdvanceFailures((current) => {
                  if (!failure) {
                    if (!(threadIdToMark in current)) return current;
                    const next = { ...current };
                    delete next[threadIdToMark];
                    return next;
                  }
                  return { ...current, [threadIdToMark]: failure };
                });
              }}
            />
          ))}
        </ul>
      )}
      {leftoverFailures.length > 0 && (
        <ul
          className="chapter-plot-advance-errors"
          data-testid="plot-thread-advance-errors"
        >
          {leftoverFailures.map(([id, failure]) => (
            <li
              key={id}
              role={failure.tone === "error" ? "alert" : "status"}
              className={
                failure.tone === "error"
                  ? "chapter-plot-advance-errors__error"
                  : "chapter-plot-advance-errors__notice"
              }
            >
              {failure.message}
            </li>
          ))}
        </ul>
      )}
      {onChapter.length === 0 ? (
        <p className="plot-thread-quiet">{t("writing.plotThreads.noBeatsOnChapter")}</p>
      ) : (
        onChapter.map(({ thread, beat }) => (
          <div
            key={beat.id}
            className="chapter-plot-beats__row"
          >
            <span className="chapter-plot-beats__name">{thread.name}</span>
            <select
              className="writing-status-select"
              aria-label={t("writing.plotThreads.kind")}
              value={beat.kind}
              disabled={disabled}
              onChange={(event) => {
                void updateBeat
                  .mutateAsync({
                    beatId: beat.id,
                    data: { kind: event.target.value as PlotBeatKind },
                  })
                  .catch(report);
              }}
            >
              {PLOT_BEAT_KINDS.map((kind) => (
                <option
                  key={kind}
                  value={kind}
                >
                  {t(`writing.plotThreads.kinds.${kind}`)}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="plot-thread-delete"
              disabled={disabled}
              onClick={() => {
                void deleteBeat.mutateAsync(beat.id).catch(report);
              }}
            >
              {t("writing.plotThreads.deleteBeat")}
            </button>
          </div>
        ))
      )}
      {available.length > 0 && (
        <form
          className="chapter-plot-beats__row"
          onSubmit={(event) => {
            event.preventDefault();
            if (!threadId || disabled) return;
            const thread = available.find((item) => item.id === threadId);
            const kind: PlotBeatKind = thread?.hasPlant ? "advance" : "plant";
            void createBeat.mutateAsync({ threadId, data: { chapterId, kind } }).catch(report);
          }}
        >
          <select
            className="writing-status-select"
            aria-label={t("writing.plotThreads.attachExisting")}
            value={threadId}
            disabled={disabled}
            onChange={(event) => setThreadId(event.target.value)}
          >
            {available.map((thread) => (
              <option
                key={thread.id}
                value={thread.id}
              >
                {thread.name}
              </option>
            ))}
          </select>
          <button
            type="submit"
            className="plot-thread-text-button"
            disabled={disabled || !threadId || createBeat.isPending}
          >
            {t("writing.plotThreads.attach")}
          </button>
        </form>
      )}
    </div>
  );
}

function plotActionError(error: unknown, duplicate: string, fallback: string): string {
  if (!axios.isAxiosError(error)) return fallback;
  if (error.response?.status === 409) return duplicate;
  const data = error.response?.data;
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

function ConsiderAdvanceItem({
  projectId,
  chapterId,
  thread,
  gap,
  throughGap,
  chapters,
  disabled,
  onOpenChapter,
  onFailure,
}: {
  projectId: string;
  chapterId: string;
  thread: PlotThread;
  gap: QuietGap;
  throughGap: PlotThroughGap | null;
  chapters: readonly PlotChapterOption[];
  disabled: boolean;
  onOpenChapter?: (chapterId: string, chapterTitle: string) => void;
  onFailure: (threadId: string, failure: AdvanceFailure | null) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const createBeat = useCreatePlotBeat(projectId);
  const updateBeat = useUpdatePlotBeat(projectId);
  const action = currentChapterBeatAction(thread, chapterId);
  const existing = action.mode === "edit" ? action.beat : null;
  const [note, setNote] = useState(existing?.note ?? "");
  const [focused, setFocused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!focused && existing) setNote(existing.note);
  }, [existing, focused]);

  const explain = (failure: AdvanceFailure) => {
    if (mountedRef.current) setError(failure.message);
    onFailure(thread.id, failure);
  };

  const keepExistingBeat = async (trimmed: string) => {
    const duplicate = t("writing.plotThreads.duplicateBeat");
    const fallback = t("writing.plotThreads.saveFailed");
    try {
      const board = await queryClient.fetchQuery({
        queryKey: ["plot-threads", projectId],
        queryFn: () => fetchPlotThreads(projectId),
      });
      const beat = board.threads
        .find((item) => item.id === thread.id)
        ?.beats.find((item) => item.chapterId === chapterId);
      if (!beat) {
        if (mountedRef.current) setBlocked(true);
        explain({ message: duplicate, tone: "error" });
        return;
      }
      if (trimmed && trimmed !== beat.note) {
        await updateBeat.mutateAsync({ beatId: beat.id, data: { note: trimmed } });
        explain({
          message: t("writing.plotThreads.advanceNoteSaved", { name: thread.name }),
          tone: "notice",
        });
        return;
      }
      explain({
        message: t("writing.plotThreads.advanceKeptExisting", { name: thread.name }),
        tone: "notice",
      });
    } catch (caught) {
      if (mountedRef.current) setBlocked(true);
      explain({ message: plotActionError(caught, duplicate, fallback), tone: "error" });
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (disabled || blocked || savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    setError(null);
    onFailure(thread.id, null);
    const trimmed = note.trim();
    const duplicate = t("writing.plotThreads.duplicateBeat");
    const fallback = t("writing.plotThreads.saveFailed");
    try {
      if (existing) {
        await updateBeat.mutateAsync({ beatId: existing.id, data: { note: trimmed } });
        return;
      }
      await createBeat.mutateAsync({
        threadId: thread.id,
        data: { chapterId, kind: "advance", note: trimmed },
      });
    } catch (caught) {
      if (axios.isAxiosError(caught) && caught.response?.status === 409) {
        await keepExistingBeat(trimmed);
        return;
      }
      explain({ message: plotActionError(caught, duplicate, fallback), tone: "error" });
    } finally {
      savingRef.current = false;
      if (mountedRef.current) setSaving(false);
    }
  };

  let mode: "blocked" | "edit" | "create" = "create";
  if (blocked) mode = "blocked";
  else if (existing) mode = "edit";

  return (
    <li
      className="chapter-plot-stale__item"
      data-testid="plot-thread-consider-item"
    >
      <p className="chapter-plot-stale__text">
        {t("writing.plotThreads.considerAdvance", {
          name: thread.name,
          order: gap.lastOrder,
          title: gap.lastTitle || t("writing.untitledChapter"),
          count: gap.chaptersSince,
        })}
      </p>
      {throughGap && throughGap.gapChapters.length > 0 && (
        <GapChapterList
          chapters={throughGap.gapChapters}
          range={throughGap.gapRange}
          onOpen={(openedId) => {
            const chapter = chapters.find((item) => item.id === openedId);
            onOpenChapter?.(openedId, chapter?.title ?? "");
          }}
        />
      )}
      {existing || blocked ? (
        <p
          className="chapter-plot-stale__hint"
          data-testid="plot-thread-advance-existing"
        >
          {t("writing.plotThreads.alreadyOnChapter")}
        </p>
      ) : null}
      <form
        className="chapter-plot-stale__form"
        onSubmit={(event) => {
          void submit(event);
        }}
      >
        <input
          className="plot-thread-note"
          data-testid="plot-thread-advance-note"
          aria-label={t("writing.plotThreads.note")}
          placeholder={t("writing.plotThreads.notePlaceholder")}
          value={note}
          maxLength={NOTE_MAX_LENGTH}
          disabled={disabled || blocked}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onChange={(event) => setNote(event.target.value)}
        />
        <button
          type="submit"
          className="plot-thread-text-button"
          data-testid="plot-thread-record-advance"
          data-mode={mode}
          disabled={disabled || blocked || saving}
        >
          {existing
            ? t("writing.plotThreads.editBeatHere")
            : t("writing.plotThreads.recordAdvance")}
        </button>
      </form>
      {error ? (
        <p
          className="chapter-plot-stale__error"
          role="alert"
          data-testid="plot-thread-advance-error"
        >
          {error}
        </p>
      ) : null}
    </li>
  );
}
