import { Box, Button, Dialog, Flex, IconButton, Text, TextField } from "@radix-ui/themes";
import { Flag, Pause, Play, Timer } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";

import {
  formatClock,
  halfTimeReached,
  isTimeUp,
  remainingMs,
  wordProgress,
  type SprintConfig,
} from "../lib/writing-sprint";
import { useSprintStore } from "../store/use-sprint-store";
import "./writing-sprint.css";

const DURATION_PRESETS = [10, 15, 30, 45, 60];

interface WritingSprintProps {
  chapterId: string;
  chapterWordCount: number;
  disabled?: boolean;
}

/** 编辑器底栏的码字冲刺控件：配置弹窗、进行中的 HUD 和结算弹窗。 */
export function WritingSprint({ chapterId, chapterWordCount, disabled }: WritingSprintProps) {
  const { t } = useTranslation();
  const sprint = useSprintStore((state) => state.sprint);
  const accumulatedWords = useSprintStore((state) => state.accumulatedWords);
  const halfTimeToasted = useSprintStore((state) => state.halfTimeToasted);
  const targetReachedToasted = useSprintStore((state) => state.targetReachedToasted);
  const summaryDismissed = useSprintStore((state) => state.summaryDismissed);
  const start = useSprintStore((state) => state.start);
  const pause = useSprintStore((state) => state.pause);
  const resume = useSprintStore((state) => state.resume);
  const finish = useSprintStore((state) => state.finish);
  const recordProgress = useSprintStore((state) => state.recordProgress);
  const markHalfTimeToasted = useSprintStore((state) => state.markHalfTimeToasted);
  const markTargetReachedToasted = useSprintStore((state) => state.markTargetReachedToasted);
  const dismissSummary = useSprintStore((state) => state.dismissSummary);

  const [configOpen, setConfigOpen] = useState(false);
  const [minutes, setMinutes] = useState(30);
  const [targetWordsInput, setTargetWordsInput] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const recordProgressRef = useRef(recordProgress);
  recordProgressRef.current = recordProgress;

  // 冲刺期间把本章字数上报给 store（内部按水位取正向增量）。
  useEffect(() => {
    recordProgressRef.current(chapterId, chapterWordCount);
  }, [chapterId, chapterWordCount]);

  const targetWords = sprint?.targetWords ?? null;
  const sprintWords = accumulatedWords;

  // 每秒驱动一次时间显示，并在到点时自动结算。
  useEffect(() => {
    if (!sprint || sprint.status !== "running") return;
    const timer = window.setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (isTimeUp(sprint, current)) {
        finish(current);
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [finish, sprint]);

  useEffect(() => {
    if (!sprint || sprint.status !== "running") return;
    const current = Date.now();
    if (halfTimeReached(sprint, current) && !halfTimeToasted) {
      markHalfTimeToasted();
      toast.info(t("writing.sprint.halfTimeToast"));
    }
    if (
      targetWords !== null &&
      sprintWords >= targetWords &&
      !targetReachedToasted
    ) {
      markTargetReachedToasted();
      toast.success(t("writing.sprint.targetReachedToast"));
    }
  }, [
    halfTimeToasted,
    markHalfTimeToasted,
    markTargetReachedToasted,
    sprint,
    sprintWords,
    targetReachedToasted,
    targetWords,
    t,
  ]);

  const handleStart = useCallback(() => {
    const parsedTarget = Number.parseInt(targetWordsInput, 10);
    const config: SprintConfig = {
      durationMinutes: minutes,
      targetWords: Number.isFinite(parsedTarget) && parsedTarget > 0 ? parsedTarget : null,
    };
    start(config, Date.now());
    setConfigOpen(false);
    toast.success(t("writing.sprint.startedToast", { minutes }));
  }, [minutes, start, t, targetWordsInput]);

  const handleGiveUp = useCallback(() => {
    const current = Date.now();
    setNow(current);
    finish(current);
  }, [finish]);

  const handlePauseToggle = useCallback(() => {
    const current = Date.now();
    setNow(current);
    if (sprint?.status === "running") {
      pause(current);
    } else if (sprint?.status === "paused") {
      resume(current);
    }
  }, [pause, resume, sprint?.status]);

  const targetProgress =
    targetWords !== null ? wordProgress(sprintWords, targetWords) : null;
  const targetReached = targetProgress !== null && targetProgress >= 1;

  return (
    <>
      {!sprint || sprint.status === "finished" || sprint.status === "cancelled" ? (
        <IconButton
          size="1"
          variant="ghost"
          color="gray"
          highContrast
          aria-label={t("writing.sprint.title")}
          title={t("writing.sprint.title")}
          disabled={disabled}
          onClick={() => setConfigOpen(true)}
        >
          <Timer size={14} />
        </IconButton>
      ) : (
        <Flex
          align="center"
          gap="2"
          px="2"
          py="1"
          className={`writing-sprint-hud${sprint.status === "paused" ? " writing-sprint-hud--paused" : ""}`}
        >
          <Timer size={14} />
          <Text size="1" weight="medium">
            {formatClock(remainingMs(sprint, now))}
          </Text>
          <Text size="1" color={sprintWords > 0 ? undefined : "gray"}>
            +{sprintWords}
          </Text>
          {targetWords !== null && (
            <Text size="1" color={targetReached ? "grass" : "gray"}>
              {targetReached ? "✓" : `${Math.round((targetProgress ?? 0) * 100)}%`}
            </Text>
          )}
          <IconButton
            size="1"
            variant="ghost"
            color="gray"
            aria-label={sprint.status === "running" ? t("writing.sprint.pause") : t("writing.sprint.resume")}
            onClick={handlePauseToggle}
          >
            {sprint.status === "running" ? <Pause size={13} /> : <Play size={13} />}
          </IconButton>
          <IconButton
            size="1"
            variant="ghost"
            color="gray"
            aria-label={t("writing.sprint.finishEarly")}
            title={t("writing.sprint.finishEarly")}
            onClick={handleGiveUp}
          >
            <Flag size={13} />
          </IconButton>
        </Flex>
      )}

      {/* 配置弹窗 */}
      <Dialog.Root
        open={configOpen}
        onOpenChange={setConfigOpen}
      >
        <Dialog.Content maxWidth="380px">
          <Dialog.Title>{t("writing.sprint.title")}</Dialog.Title>
          <Dialog.Description
            size="2"
            color="gray"
          >
            {t("writing.sprint.configHint")}
          </Dialog.Description>
          <Flex
            direction="column"
            gap="3"
            mt="4"
          >
            <Box>
              <Text
                as="div"
                size="1"
                mb="1"
                color="gray"
              >
                {t("writing.sprint.duration")}
              </Text>
              <Flex gap="2" wrap="wrap">
                {DURATION_PRESETS.map((preset) => (
                  <Button
                    key={preset}
                    size="1"
                    variant={minutes === preset ? "solid" : "soft"}
                    color={minutes === preset ? undefined : "gray"}
                    onClick={() => setMinutes(preset)}
                  >
                    {t("writing.sprint.minutes", { count: preset })}
                  </Button>
                ))}
              </Flex>
            </Box>
            <label>
              <Text
                as="div"
                size="1"
                mb="1"
                color="gray"
              >
                {t("writing.sprint.targetWords")}
              </Text>
              <TextField.Root
                type="number"
                min={1}
                placeholder={t("writing.sprint.targetWordsPlaceholder")}
                value={targetWordsInput}
                onChange={(event) => setTargetWordsInput(event.target.value)}
              />
            </label>
            <Flex
              justify="end"
              gap="2"
            >
              <Dialog.Close>
                <Button
                  variant="soft"
                  color="gray"
                >
                  {t("common.cancel")}
                </Button>
              </Dialog.Close>
              <Button onClick={handleStart}>
                <Timer size={14} />
                {t("writing.sprint.start")}
              </Button>
            </Flex>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>

      {/* 结算弹窗 */}
      <Dialog.Root
        open={Boolean(sprint && sprint.status === "finished" && !summaryDismissed)}
        onOpenChange={(open) => {
          if (!open) dismissSummary();
        }}
      >
        <Dialog.Content maxWidth="380px">
          <Dialog.Title>{t("writing.sprint.summaryTitle")}</Dialog.Title>
          <Dialog.Description
            size="2"
            color="gray"
          >
            {sprintWords > 0
              ? t("writing.sprint.summaryCheer", { count: sprintWords })
              : t("writing.sprint.summaryCheerZero")}
          </Dialog.Description>
          <Flex
            direction="column"
            gap="2"
            mt="4"
          >
            <Text size="2">
              {t("writing.sprint.summaryWords", { count: sprintWords })}
            </Text>
            {targetWords !== null && (
              <Text size="2" color={targetReached ? "grass" : undefined}>
                {targetReached
                  ? t("writing.sprint.summaryTargetReached", { count: targetWords })
                  : t("writing.sprint.summaryTargetMissed", {
                      count: sprintWords,
                      target: targetWords,
                    })}
              </Text>
            )}
            <Flex
              justify="end"
              mt="2"
            >
              <Dialog.Close>
                <Button variant="soft">{t("common.close")}</Button>
              </Dialog.Close>
            </Flex>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>
    </>
  );
}
