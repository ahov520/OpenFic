import { Flex, Text } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import { CalendarCheck } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { fetchWritingDashboard } from "@/features/dashboard/lib/dashboard-api";
import { fetchSettings } from "@/features/settings/lib/settings-api";

import {
  goalProgress,
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

  const range = useMemo(() => todayWordGoalRange(Date.now()), []);
  const { data } = useQuery({
    queryKey: ["writing-today", range.startAt, range.timezone],
    queryFn: () =>
      fetchWritingDashboard({
        startAt: range.startAt,
        endAt: range.endAt,
        timezone: range.timezone,
      }),
    enabled: target > 0,
    staleTime: 30_000,
    refetchInterval: REFRESH_INTERVAL_MS,
  });

  if (target <= 0) return null;

  const words = todayUserWords(data?.timeSeries ?? []);
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
    </Flex>
  );
}
