import { useSyncExternalStore } from "react";

export interface MarginNoteFocus {
  chapterId: string;
  noteId: string;
  token: number;
}

let focus: MarginNoteFocus | null = null;
let consumedToken = 0;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): MarginNoteFocus | null {
  return focus;
}

export function requestMarginNoteFocus(chapterId: string, noteId: string): void {
  focus = {
    chapterId,
    noteId,
    token: (focus?.token ?? 0) + 1,
  };
  consumedToken = 0;
  for (const listener of listeners) listener();
}

export function consumeMarginNoteFocus(token: number): void {
  if (token > consumedToken) consumedToken = token;
}

export function useMarginNoteFocus(chapterId: string): MarginNoteFocus | null {
  const value = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  if (!value || value.chapterId !== chapterId || value.token <= consumedToken) return null;
  return value;
}
