/**
 * Writing Sprint - 码字冲刺纯逻辑。
 *
 * 时间状态只存时间戳，由调用方传入 now 计算，方便确定性测试。
 * 冲刺字数由 store 累计各章正向增量，这里只做展示层换算。
 */

export interface SprintConfig {
  durationMinutes: number;
  targetWords: number | null;
}

export type SprintStatus = "running" | "paused" | "finished" | "cancelled";

export interface SprintState {
  status: SprintStatus;
  /** 冲刺总时长（毫秒）。 */
  durationMs: number;
  targetWords: number | null;
  /** 当前运行段的起点时间戳；暂停时无意义。 */
  startedAt: number;
  /** 暂停前累计的已进行毫秒数。 */
  elapsedBeforePauseMs: number;
  finishedAt: number | null;
}

export function startSprint(config: SprintConfig, now: number): SprintState {
  const minutes = Math.max(1, Math.floor(config.durationMinutes));
  return {
    status: "running",
    durationMs: minutes * 60_000,
    targetWords:
      config.targetWords !== null && Number.isFinite(config.targetWords)
        ? Math.max(1, Math.floor(config.targetWords))
        : null,
    startedAt: now,
    elapsedBeforePauseMs: 0,
    finishedAt: null,
  };
}

export function pauseSprint(state: SprintState, now: number): SprintState {
  if (state.status !== "running") return state;
  return {
    ...state,
    status: "paused",
    elapsedBeforePauseMs: elapsedMs(state, now),
  };
}

export function resumeSprint(state: SprintState, now: number): SprintState {
  if (state.status !== "paused") return state;
  return {
    ...state,
    status: "running",
    startedAt: now,
  };
}

export function finishSprint(state: SprintState, now: number): SprintState {
  if (state.status === "finished" || state.status === "cancelled") return state;
  return {
    ...state,
    status: "finished",
    finishedAt: now,
    ...(state.status === "running" ? { elapsedBeforePauseMs: elapsedMs(state, now) } : {}),
  };
}

export function cancelSprint(state: SprintState, now: number): SprintState {
  if (state.status === "finished" || state.status === "cancelled") return state;
  return {
    ...finishSprint(state, now),
    status: "cancelled",
  };
}

export function elapsedMs(state: SprintState, now: number): number {
  if (state.status === "running") {
    return state.elapsedBeforePauseMs + Math.max(0, now - state.startedAt);
  }
  return state.elapsedBeforePauseMs;
}

export function remainingMs(state: SprintState, now: number): number {
  return Math.max(0, state.durationMs - elapsedMs(state, now));
}

/** 时间进度 0..1，封顶 1。 */
export function timeProgress(state: SprintState, now: number): number {
  if (state.durationMs <= 0) return 1;
  return Math.min(1, elapsedMs(state, now) / state.durationMs);
}

export function isTimeUp(state: SprintState, now: number): boolean {
  return state.status === "running" && elapsedMs(state, now) >= state.durationMs;
}

export function halfTimeReached(state: SprintState, now: number): boolean {
  return elapsedMs(state, now) >= state.durationMs / 2;
}

/** 冲刺期间的正向字数增量。 */
export function wordsDuringSprint(currentWords: number, baselineWords: number): number {
  return Math.max(0, Math.floor(currentWords) - Math.floor(baselineWords));
}

/** 字数目标进度 0..1；未设目标返回 null。 */
export function wordProgress(words: number, targetWords: number | null): number | null {
  if (targetWords === null || targetWords <= 0) return null;
  return Math.min(1, words / targetWords);
}

export function formatClock(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
