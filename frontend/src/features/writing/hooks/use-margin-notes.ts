import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import {
  createMarginNote,
  deleteMarginNote,
  fetchMarginNotes,
  fetchOpenMarginNotes,
  updateMarginNote,
} from "@/lib/api-client";
import type { VolumeTreeResponse } from "@/lib/chapter.types";
import type {
  MarginNote,
  MarginNoteCreate,
  MarginNoteUpdate,
  OpenMarginNote,
} from "@/lib/margin-note";

const OPEN_MARGIN_NOTES_KEY = "open-margin-notes";

export function useOpenMarginNotes(projectId: string | null | undefined) {
  return useQuery({
    queryKey: [OPEN_MARGIN_NOTES_KEY, projectId],
    queryFn: () => fetchOpenMarginNotes(projectId!),
    enabled: !!projectId,
  });
}

function patchOpenMarginNotes(queryClient: QueryClient, note: MarginNote): void {
  let missingOpenNote = false;
  queryClient.setQueriesData<OpenMarginNote[]>({ queryKey: [OPEN_MARGIN_NOTES_KEY] }, (current) => {
    if (!current) return current;
    const index = current.findIndex((item) => item.id === note.id);
    if (note.status !== "open") {
      return index < 0 ? current : current.filter((item) => item.id !== note.id);
    }
    if (index < 0) {
      missingOpenNote = true;
      return current;
    }
    const existing = current[index];
    if (existing.body === note.body && existing.anchorText === note.anchorText) return current;
    const next = current.slice();
    next[index] = { ...existing, body: note.body, anchorText: note.anchorText };
    return next;
  });
  if (missingOpenNote) {
    void queryClient.invalidateQueries({ queryKey: [OPEN_MARGIN_NOTES_KEY] });
  }
}

function adjustOpenMarginNoteCount(queryClient: QueryClient, chapterId: string, delta: number) {
  if (delta === 0) return;
  const entries = queryClient.getQueriesData<VolumeTreeResponse>({ queryKey: ["volume-tree"] });
  for (const [key, tree] of entries) {
    if (!tree) continue;
    let touched = false;
    const volumes = tree.volumes.map((volume) => {
      let volumeTouched = false;
      const chapters = volume.chapters.map((chapter) => {
        if (chapter.id !== chapterId) return chapter;
        volumeTouched = true;
        touched = true;
        return {
          ...chapter,
          openMarginNoteCount: Math.max(0, (chapter.openMarginNoteCount ?? 0) + delta),
        };
      });
      return volumeTouched ? { ...volume, chapters } : volume;
    });
    if (touched) {
      queryClient.setQueryData<VolumeTreeResponse>(key, { ...tree, volumes });
    }
  }
}

export function useMarginNotes(chapterId: string | null | undefined) {
  return useQuery({
    queryKey: ["margin-notes", chapterId],
    queryFn: () => fetchMarginNotes(chapterId!),
    enabled: !!chapterId,
  });
}

function useSyncMarginNotes(chapterId: string) {
  const queryClient = useQueryClient();
  return (notes: MarginNote[]) => {
    queryClient.setQueryData(["margin-notes", chapterId], notes);
  };
}

export function useCreateMarginNote(chapterId: string) {
  const queryClient = useQueryClient();
  const sync = useSyncMarginNotes(chapterId);
  return useMutation({
    mutationFn: (data: MarginNoteCreate) => createMarginNote(chapterId, data),
    onSuccess: (note) => {
      const current = queryClient.getQueryData<MarginNote[]>(["margin-notes", chapterId]) ?? [];
      sync([...current, note]);
      if (note.status === "open") {
        adjustOpenMarginNoteCount(queryClient, chapterId, 1);
      }
      void queryClient.invalidateQueries({ queryKey: [OPEN_MARGIN_NOTES_KEY] });
    },
  });
}

export function useUpdateMarginNote(chapterId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, data }: { noteId: string; data: MarginNoteUpdate }) =>
      updateMarginNote(chapterId, noteId, data),
    onSuccess: (note) => {
      let previousStatus: MarginNote["status"] | undefined;
      queryClient.setQueryData<MarginNote[]>(["margin-notes", chapterId], (current) => {
        previousStatus = (current ?? []).find((item) => item.id === note.id)?.status;
        return (current ?? []).map((item) => (item.id === note.id ? note : item));
      });
      if (previousStatus && previousStatus !== note.status) {
        adjustOpenMarginNoteCount(queryClient, chapterId, note.status === "open" ? 1 : -1);
      } else if (!previousStatus) {
        void queryClient.invalidateQueries({ queryKey: ["volume-tree"] });
      }
      patchOpenMarginNotes(queryClient, note);
    },
  });
}

export function useDeleteMarginNote(chapterId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (noteId: string) => deleteMarginNote(chapterId, noteId),
    onSuccess: (_result, noteId) => {
      let removedStatus: MarginNote["status"] | undefined;
      queryClient.setQueryData<MarginNote[]>(["margin-notes", chapterId], (current) => {
        removedStatus = (current ?? []).find((item) => item.id === noteId)?.status;
        return (current ?? []).filter((item) => item.id !== noteId);
      });
      if (removedStatus === "open") {
        adjustOpenMarginNoteCount(queryClient, chapterId, -1);
      } else if (!removedStatus) {
        void queryClient.invalidateQueries({ queryKey: ["volume-tree"] });
      }
      queryClient.setQueriesData<OpenMarginNote[]>(
        { queryKey: [OPEN_MARGIN_NOTES_KEY] },
        (current) => current?.filter((item) => item.id !== noteId),
      );
    },
  });
}
