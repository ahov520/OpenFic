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

/** 序列点的最小形状（与 dashboard 时间轴点一致）。 */
export interface StreakSeriesPoint {
  date: string;
  userWordDelta: number;
}

/**
 * 连续达标天数：从今天往回数（今天未达标则从昨天起算），遇到未达标日即断。
 * 历史天数一律按当前目标判定（目标变更没有历史记录，这是可接受的近似）。
 */
export function computeStreak(
  timeSeries: StreakSeriesPoint[],
  target: number,
  todayLocalDate: string,
): number {
  if (target <= 0) return 0;
  const byDate = new Map<string, number>();
  for (const point of timeSeries) {
    byDate.set(point.date, Math.max(0, point.userWordDelta));
  }

  const reached = (date: Date): boolean => {
    const key = localDateKey(date);
    const words = byDate.get(key);
    // 序列覆盖范围内的无记录日视为未达标；范围外的日期不再往前数。
    return words !== undefined && words >= target;
  };

  const today = parseLocalDateKey(todayLocalDate);
  let streak = 0;
  let cursor = new Date(today);
  if (!reached(cursor)) {
    cursor.setDate(cursor.getDate() - 1);
  }
  const rangeStart = new Date(today);
  rangeStart.setDate(rangeStart.getDate() - MAX_STREAK_LOOKBACK_DAYS + 1);
  while (cursor >= rangeStart && reached(cursor)) {
    streak += 1;
    cursor.setDate(cursor.getDate() - 1);
  }
  return streak;
}

export const MAX_STREAK_LOOKBACK_DAYS = 120;

export function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function parseLocalDateKey(key: string): Date {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(year ?? 1970, (month ?? 1) - 1, day ?? 1);
}
