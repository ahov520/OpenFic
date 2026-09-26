/**
 * Writing Sprint Store - 码字冲刺会话状态。
 *
 * 冲刺跨章节、跨编辑器挂载持续存在（内存态，不持久化）：
 * 字数按“各章历史最高水位”的正向增量累计，删改不会倒扣。
 */

import { create } from "zustand";

import {
  cancelSprint,
  finishSprint,
  pauseSprint,
  resumeSprint,
  startSprint,
  wordsDuringSprint,
  type SprintConfig,
  type SprintState,
} from "../lib/writing-sprint";

interface SprintStoreState {
  sprint: SprintState | null;
  /** 冲刺期间累计的正向字数增量。 */
  accumulatedWords: number;
  /** 各章字数水位：冲刺开始后首次见到某章记为基线，之后取最大值。 */
  wordWatermarks: Record<string, number>;
  halfTimeToasted: boolean;
  targetReachedToasted: boolean;
  summaryDismissed: boolean;
}

interface SprintStoreActions {
  start: (config: SprintConfig, now: number) => void;
  pause: (now: number) => void;
  resume: (now: number) => void;
  finish: (now: number) => void;
  cancel: (now: number) => void;
  /** 编辑器字数变化时上报；只在 running 状态计增量。 */
  recordProgress: (chapterId: string, wordCount: number) => void;
  markHalfTimeToasted: () => void;
  markTargetReachedToasted: () => void;
  dismissSummary: () => void;
}

type SprintStore = SprintStoreState & SprintStoreActions;

export const useSprintStore = create<SprintStore>((set, get) => ({
  sprint: null,
  accumulatedWords: 0,
  wordWatermarks: {},
  halfTimeToasted: false,
  targetReachedToasted: false,
  summaryDismissed: false,

  start: (config, now) =>
    set({
      sprint: startSprint(config, now),
      accumulatedWords: 0,
      wordWatermarks: {},
      halfTimeToasted: false,
      targetReachedToasted: false,
      summaryDismissed: false,
    }),

  pause: (now) => {
    const sprint = get().sprint;
    if (!sprint) return;
    set({ sprint: pauseSprint(sprint, now) });
  },

  resume: (now) => {
    const sprint = get().sprint;
    if (!sprint) return;
    set({ sprint: resumeSprint(sprint, now) });
  },

  finish: (now) => {
    const sprint = get().sprint;
    if (!sprint) return;
    set({ sprint: finishSprint(sprint, now) });
  },

  cancel: (now) => {
    const sprint = get().sprint;
    if (!sprint) return;
    set({ sprint: cancelSprint(sprint, now) });
  },

  recordProgress: (chapterId, wordCount) => {
    const state = get();
    const sprint = state.sprint;
    if (!sprint || sprint.status !== "running") return;
    const watermark = state.wordWatermarks[chapterId];
    if (watermark === undefined) {
      // 冲刺中途第一次见到这一章：记基线，不算增量。
      set({ wordWatermarks: { ...state.wordWatermarks, [chapterId]: wordCount } });
      return;
    }
    const delta = wordsDuringSprint(wordCount, watermark);
    if (delta <= 0) return;
    set({
      accumulatedWords: state.accumulatedWords + delta,
      wordWatermarks: { ...state.wordWatermarks, [chapterId]: Math.max(watermark, wordCount) },
    });
  },

  markHalfTimeToasted: () => set({ halfTimeToasted: true }),
  markTargetReachedToasted: () => set({ targetReachedToasted: true }),
  dismissSummary: () => set({ summaryDismissed: true }),
}));
