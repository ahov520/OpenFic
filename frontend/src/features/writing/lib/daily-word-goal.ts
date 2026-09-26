/**
 * 每日码字目标的纯逻辑：本地「今天」的时间范围与目标进度换算。
 */

export interface TodayWordGoalRange {
  startAt: string;
  endAt: string;
  timezone: string;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** 生成带本地时区偏移的 ISO 时间，后端按 offset 换算成 UTC。 */
function localOffsetISO(date: Date): string {
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMinutes);
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  );
}

/** 本地时区的「今天 0 点 → 明天 0 点」半开区间，附 IANA 时区名。 */
export function todayWordGoalRange(now: number): TodayWordGoalRange {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return {
    startAt: localOffsetISO(start),
    endAt: localOffsetISO(end),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  };
}

/** 只统计用户手打的正向增量（导入和 Agent 修改不计入目标）。 */
export function todayUserWords(
  timeSeries: Array<{ userWordDelta: number }>,
): number {
  return timeSeries.reduce((total, point) => total + Math.max(0, point.userWordDelta), 0);
}

export interface GoalProgress {
  percent: number;
  done: boolean;
}

export function goalProgress(todayWords: number, target: number): GoalProgress {
  if (target <= 0) {
    return { percent: 0, done: false };
  }
  return {
    percent: Math.min(1, Math.max(0, todayWords) / target),
    done: todayWords >= target,
  };
}
