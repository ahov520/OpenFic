import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createMarginNote,
  deleteMarginNote,
  fetchMarginNotes,
  updateMarginNote,
} from "@/lib/api-client";
import type { MarginNote, MarginNoteCreate, MarginNoteUpdate } from "@/lib/margin-note";

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
    },
  });
}
