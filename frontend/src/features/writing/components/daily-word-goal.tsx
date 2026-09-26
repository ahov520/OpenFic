import { Flex, Text } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, Flame } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { fetchWritingDashboard } from "@/features/dashboard/lib/dashboard-api";
import { fetchSettings } from "@/features/settings/lib/settings-api";

import {
  computeStreak,
  goalProgress,
  localDateKey,
  MAX_STREAK_LOOKBACK_DAYS,
  todayUserWords,
  todayWordGoalRange,
} from "../lib/daily-word-goal";
import "./daily-word-goal.css";

const REFRESH_INTERVAL_MS = 60_000;

/** 编辑器底栏的每日码字目标：展示今天的用户字数增量与目标进度。未设目标时不渲染。 */
export function DailyWordGoal() {
  const { t } = useTranslation();
  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
  });
  const target = settings?.dailyWordCountTarget ?? 0;

  const now = Date.now();
  const streakStart = useMemo(() => {
    const start = new Date(now);
    start.setDate(start.getDate() - MAX_STREAK_LOOKBACK_DAYS + 1);
    start.setHours(0, 0, 0, 0);
    return start;
  }, [now]);
  const streakRange = useMemo(() => {
    const startAt = todayWordGoalRange(streakStart.getTime());
    const endAt = todayWordGoalRange(now + 24 * 60 * 60 * 1000);
    return { startAt: startAt.startAt, endAt: endAt.endAt, timezone: endAt.timezone };
  }, [now, streakStart]);
  const { data } = useQuery({
    queryKey: ["writing-today", streakRange.startAt, streakRange.timezone],
    queryFn: () =>
      fetchWritingDashboard({
        startAt: streakRange.startAt,
        endAt: streakRange.endAt,
        timezone: streakRange.timezone,
      }),
    enabled: target > 0,
    staleTime: 30_000,
    refetchInterval: REFRESH_INTERVAL_MS,
  });

  if (target <= 0) return null;

  const series = data?.timeSeries ?? [];
  const words = todayUserWords(series);
  const streak = computeStreak(series, target, localDateKey(new Date(now)));
  const { percent, done } = goalProgress(words, target);

  return (
    <Flex
      align="center"
      gap="2"
      px="2"
      py="1"
      className={`daily-word-goal${done ? " daily-word-goal--done" : ""}`}
      title={t("writing.dailyGoal.title")}
    >
      <CalendarCheck size={14} />
      <Text size="1" weight={done ? "medium" : undefined}>
        {t("writing.dailyGoal.progress", { words, target })}
      </Text>
      <span className="daily-word-goal__track">
        <span
          className="daily-word-goal__fill"
          style={{ width: `${Math.round(percent * 100)}%` }}
        />
      </span>
      <Text size="1">
        {done ? "✓" : `${Math.round(percent * 100)}%`}
      </Text>
      {streak > 0 && (
        <Flex
          align="center"
          gap="1"
          title={t("writing.dailyGoal.streak", { count: streak })}
        >
          <Flame size={12} />
          <Text size="1">
            {t("writing.dailyGoal.streakShort", { count: streak })}
          </Text>
        </Flex>
      )}
    </Flex>
  );
}
