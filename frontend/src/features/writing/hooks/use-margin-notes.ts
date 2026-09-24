import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import {
  createMarginNote,
  deleteMarginNote,
  fetchMarginNotes,
  fetchOpenMarginNotes,
  updateMarginNote,
} from "@/lib/api-client";
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
      queryClient.setQueryData<MarginNote[]>(["margin-notes", chapterId], (current) =>
        (current ?? []).map((item) => (item.id === note.id ? note : item)),
      );
      patchOpenMarginNotes(queryClient, note);
    },
  });
}

export function useDeleteMarginNote(chapterId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (noteId: string) => deleteMarginNote(chapterId, noteId),
    onSuccess: (_result, noteId) => {
      queryClient.setQueryData<MarginNote[]>(["margin-notes", chapterId], (current) =>
        (current ?? []).filter((item) => item.id !== noteId),
      );
      queryClient.setQueriesData<OpenMarginNote[]>(
        { queryKey: [OPEN_MARGIN_NOTES_KEY] },
        (current) => current?.filter((item) => item.id !== noteId),
      );
    },
  });
}
