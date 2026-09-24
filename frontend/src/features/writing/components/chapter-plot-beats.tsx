import axios from "axios";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import type { PlotBeatKind, PlotThread } from "@/lib/plot-thread";
import {
  PLOT_BEAT_KINDS,
  STALE_CHAPTER_GAP,
  quietGapBeforeChapter,
  readingChapterIds,
} from "@/lib/plot-thread";

import {
  useCreatePlotBeat,
  useDeletePlotBeat,
  usePlotThreads,
  useUpdatePlotBeat,
} from "../hooks/use-plot-threads";

import "./plot-thread.css";

const EMPTY_THREADS: PlotThread[] = [];

interface ChapterPlotBeatsProps {
  projectId: string;
  chapterId: string;
  disabled?: boolean;
  onOpenBoard?: () => void;
}

export function ChapterPlotBeats({
  projectId,
  chapterId,
  disabled = false,
  onOpenBoard,
}: ChapterPlotBeatsProps) {
  const { t } = useTranslation();
  const { data } = usePlotThreads(projectId);
  const createBeat = useCreatePlotBeat(projectId);
  const updateBeat = useUpdatePlotBeat(projectId);
  const deleteBeat = useDeletePlotBeat(projectId);
  const threads = data?.threads ?? EMPTY_THREADS;
  const readingOrder = useMemo(() => readingChapterIds(data?.chapters ?? []), [data?.chapters]);
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

  const availableKey = available.map((thread) => thread.id).join("\0");

  useEffect(() => {
    const ids = availableKey ? availableKey.split("\0") : [];
    if (!ids.includes(threadId)) setThreadId(ids[0] ?? "");
  }, [availableKey, threadId]);

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
            <li key={thread.id}>
              {t("writing.plotThreads.considerAdvance", {
                name: thread.name,
                order: gap.lastOrder,
                title: gap.lastTitle || t("writing.untitledChapter"),
                count: gap.chaptersSince,
              })}
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
