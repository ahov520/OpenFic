import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createPlotBeat,
  createPlotThread,
  deletePlotBeat,
  deletePlotThread,
  fetchPlotThreads,
  updatePlotBeat,
  updatePlotThread,
} from "@/lib/api-client";
import type {
  PlotBeatCreate,
  PlotBeatUpdate,
  PlotBoard,
  PlotThread,
  PlotThreadCreate,
  PlotThreadUpdate,
} from "@/lib/plot-thread";

export function usePlotThreads(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ["plot-threads", projectId],
    queryFn: () => fetchPlotThreads(projectId!),
    enabled: !!projectId,
  });
}

function useInvalidatePlotThreads(projectId: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["plot-threads", projectId] });
  };
}

function useSyncPlotThread(projectId: string) {
  const queryClient = useQueryClient();
  return (thread: PlotThread) => {
    queryClient.setQueryData<PlotBoard>(["plot-threads", projectId], (current) => {
      if (!current?.threads.some((item) => item.id === thread.id)) return current;
      return {
        ...current,
        threads: current.threads.map((item) => (item.id === thread.id ? thread : item)),
      };
    });
    void queryClient.invalidateQueries({ queryKey: ["plot-threads", projectId] });
  };
}

export function useCreatePlotThread(projectId: string) {
  const invalidate = useInvalidatePlotThreads(projectId);
  return useMutation({
    mutationFn: (data: PlotThreadCreate) => createPlotThread(projectId, data),
    onSuccess: invalidate,
  });
}

export function useUpdatePlotThread(projectId: string) {
  const invalidate = useInvalidatePlotThreads(projectId);
  return useMutation({
    mutationFn: ({ threadId, data }: { threadId: string; data: PlotThreadUpdate }) =>
      updatePlotThread(threadId, data),
    onSuccess: invalidate,
  });
}

export function useDeletePlotThread(projectId: string) {
  const invalidate = useInvalidatePlotThreads(projectId);
  return useMutation({
    mutationFn: (threadId: string) => deletePlotThread(threadId),
    onSuccess: invalidate,
  });
}

export function useCreatePlotBeat(projectId: string) {
  const sync = useSyncPlotThread(projectId);
  return useMutation({
    mutationFn: ({ threadId, data }: { threadId: string; data: PlotBeatCreate }) =>
      createPlotBeat(threadId, data),
    onSuccess: sync,
  });
}

export function useUpdatePlotBeat(projectId: string) {
  const sync = useSyncPlotThread(projectId);
  return useMutation({
    mutationFn: ({ beatId, data }: { beatId: string; data: PlotBeatUpdate }) =>
      updatePlotBeat(beatId, data),
    onSuccess: sync,
  });
}

export function useDeletePlotBeat(projectId: string) {
  const invalidate = useInvalidatePlotThreads(projectId);
  return useMutation({
    mutationFn: (beatId: string) => deletePlotBeat(beatId),
    onSuccess: invalidate,
  });
}
