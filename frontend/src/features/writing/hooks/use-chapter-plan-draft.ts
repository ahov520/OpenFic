import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import { SYNOPSIS_MAX_LENGTH, normalizeSynopsis, type WritingStatus } from "@/lib/chapter-plan";

import { useUpdateChapter } from "./use-chapters";

interface ChapterPlanDraftSource {
  id: string;
  synopsis: string;
  writingStatus: WritingStatus;
}

const SAVE_DELAY_MS = 600;

export function useChapterPlanDraft(source: ChapterPlanDraftSource, isAgentLocked = false) {
  const { t } = useTranslation();
  const updateMutation = useUpdateChapter();
  const [synopsis, setSynopsisState] = useState(source.synopsis);
  const [writingStatus, setWritingStatusState] = useState(source.writingStatus);
  const savedRef = useRef({ synopsis: source.synopsis, writingStatus: source.writingStatus });
  const draftRef = useRef(savedRef.current);
  const dirtyRef = useRef(false);
  const chapterIdRef = useRef(source.id);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lockedRef = useRef(isAgentLocked);
  const updateMutationRef = useRef(updateMutation);
  const tRef = useRef(t);
  const sourceRef = useRef(source);
  updateMutationRef.current = updateMutation;
  tRef.current = t;
  sourceRef.current = source;

  useEffect(() => {
    lockedRef.current = isAgentLocked;
  }, [isAgentLocked]);

  const clearTimer = useCallback(() => {
    if (!timerRef.current) return;
    clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  const applySource = useCallback((next: ChapterPlanDraftSource) => {
    savedRef.current = { synopsis: next.synopsis, writingStatus: next.writingStatus };
    draftRef.current = savedRef.current;
    dirtyRef.current = false;
    setSynopsisState(next.synopsis);
    setWritingStatusState(next.writingStatus);
  }, []);

  useEffect(() => {
    const next = sourceRef.current;
    chapterIdRef.current = next.id;
    clearTimer();
    applySource(next);

    return () => {
      clearTimer();
      if (!dirtyRef.current || lockedRef.current) return;
      const chapterId = chapterIdRef.current;
      const draft = draftRef.current;
      const synopsisValue = normalizeSynopsis(draft.synopsis);
      if (synopsisValue.length > SYNOPSIS_MAX_LENGTH) return;
      if (
        synopsisValue === savedRef.current.synopsis &&
        draft.writingStatus === savedRef.current.writingStatus
      ) {
        return;
      }
      void updateMutationRef.current
        .mutateAsync({
          chapterId,
          data: { synopsis: synopsisValue, writingStatus: draft.writingStatus },
        })
        .catch(() => {
          toast.error(tRef.current("writing.chapterPlan.saveFailed"));
        });
    };
  }, [applySource, clearTimer, source.id]);

  const sourceId = source.id;
  const sourceSynopsis = source.synopsis;
  const sourceStatus = source.writingStatus;

  useEffect(() => {
    if (sourceId !== chapterIdRef.current || dirtyRef.current) return;
    if (
      sourceSynopsis === savedRef.current.synopsis &&
      sourceStatus === savedRef.current.writingStatus
    ) {
      return;
    }
    applySource({
      id: sourceId,
      synopsis: sourceSynopsis,
      writingStatus: sourceStatus,
    });
  }, [applySource, sourceId, sourceStatus, sourceSynopsis]);

  const persist = useCallback(async () => {
    if (lockedRef.current) return;
    const draft = draftRef.current;
    const synopsisValue = normalizeSynopsis(draft.synopsis);
    if (synopsisValue.length > SYNOPSIS_MAX_LENGTH) return;
    if (
      synopsisValue === savedRef.current.synopsis &&
      draft.writingStatus === savedRef.current.writingStatus
    ) {
      dirtyRef.current = false;
      return;
    }

    const chapterId = chapterIdRef.current;
    try {
      const updated = await updateMutation.mutateAsync({
        chapterId,
        data: { synopsis: synopsisValue, writingStatus: draft.writingStatus },
      });
      if (chapterIdRef.current !== chapterId) return;
      savedRef.current = {
        synopsis: updated.synopsis,
        writingStatus: updated.writingStatus,
      };
      if (
        normalizeSynopsis(draftRef.current.synopsis) === updated.synopsis &&
        draftRef.current.writingStatus === updated.writingStatus
      ) {
        dirtyRef.current = false;
      }
    } catch {
      dirtyRef.current = true;
      toast.error(t("writing.chapterPlan.saveFailed"));
    }
  }, [t, updateMutation]);

  const schedulePersist = useCallback(() => {
    clearTimer();
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      void persist();
    }, SAVE_DELAY_MS);
  }, [clearTimer, persist]);

  const flush = useCallback(() => {
    clearTimer();
    void persist();
  }, [clearTimer, persist]);

  const setSynopsis = useCallback(
    (value: string) => {
      if (lockedRef.current) return;
      dirtyRef.current = true;
      draftRef.current = { ...draftRef.current, synopsis: value };
      setSynopsisState(value);
      schedulePersist();
    },
    [schedulePersist],
  );

  const setWritingStatus = useCallback(
    (value: WritingStatus) => {
      if (lockedRef.current) return;
      dirtyRef.current = true;
      draftRef.current = { ...draftRef.current, writingStatus: value };
      setWritingStatusState(value);
      clearTimer();
      void persist();
    },
    [clearTimer, persist],
  );

  return {
    synopsis,
    writingStatus,
    setSynopsis,
    setWritingStatus,
    flush,
    synopsisTooLong: synopsis.length > SYNOPSIS_MAX_LENGTH,
  };
}
