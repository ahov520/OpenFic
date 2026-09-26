import assert from "node:assert/strict";
import test from "node:test";

import {
  cancelSprint,
  elapsedMs,
  finishSprint,
  formatClock,
  halfTimeReached,
  isTimeUp,
  pauseSprint,
  remainingMs,
  resumeSprint,
  startSprint,
  timeProgress,
  wordProgress,
  wordsDuringSprint,
} from "./writing-sprint.ts";

test("冲刺从配置开始，进行中按时间戳累计", () => {
  const sprint = startSprint({ durationMinutes: 30, targetWords: 1000 }, 0);
  assert.equal(sprint.status, "running");
  assert.equal(sprint.durationMs, 30 * 60_000);
  assert.equal(elapsedMs(sprint, 60_000), 60_000);
  assert.equal(remainingMs(sprint, 60_000), 29 * 60_000);
  assert.ok(!isTimeUp(sprint, 60_000));
});

test("到点自动判定结束，时间进度封顶 1", () => {
  const sprint = startSprint({ durationMinutes: 30, targetWords: null }, 0);
  assert.ok(isTimeUp(sprint, 30 * 60_000));
  assert.equal(timeProgress(sprint, 45 * 60_000), 1);
});

test("暂停冻结计时，续跑接着算", () => {
  const now = 0;
  let sprint = startSprint({ durationMinutes: 10, targetWords: null }, now);
  sprint = pauseSprint(sprint, 4 * 60_000);
  assert.equal(sprint.status, "paused");
  // 暂停期间时间流逝不增加进度。
  assert.equal(elapsedMs(sprint, 9 * 60_000), 4 * 60_000);
  sprint = resumeSprint(sprint, 20 * 60_000);
  assert.equal(elapsedMs(sprint, 21 * 60_000), 5 * 60_000);
  assert.ok(!isTimeUp(sprint, 21 * 60_000));
  assert.ok(isTimeUp(sprint, 26 * 60_000));
});

test("提前结束：running 冻结当前进度，paused 保持暂停前值", () => {
  let sprint = startSprint({ durationMinutes: 10, targetWords: null }, 0);
  sprint = finishSprint(sprint, 3 * 60_000);
  assert.equal(sprint.status, "finished");
  assert.equal(elapsedMs(sprint, 99 * 60_000), 3 * 60_000);

  let paused = startSprint({ durationMinutes: 10, targetWords: null }, 0);
  paused = pauseSprint(paused, 2 * 60_000);
  paused = finishSprint(paused, 8 * 60_000);
  assert.equal(elapsedMs(paused, 8 * 60_000), 2 * 60_000);
});

test("取消与结束互不覆盖已终态", () => {
  let sprint = startSprint({ durationMinutes: 5, targetWords: null }, 0);
  sprint = finishSprint(sprint, 1000);
  assert.equal(cancelSprint(sprint, 2000).status, "finished");
  const cancelled = cancelSprint(
    startSprint({ durationMinutes: 5, targetWords: null }, 0),
    1000,
  );
  assert.equal(cancelled.status, "cancelled");
  assert.equal(finishSprint(cancelled, 2000).status, "cancelled");
});

test("冲刺字数只统计正向增量，删改不倒扣", () => {
  assert.equal(wordsDuringSprint(1500, 1000), 500);
  assert.equal(wordsDuringSprint(900, 1000), 0);
  assert.equal(wordsDuringSprint(1000, 1000), 0);
});

test("半程里程碑在时长过半后触发", () => {
  const sprint = startSprint({ durationMinutes: 10, targetWords: null }, 0);
  assert.ok(!halfTimeReached(sprint, 4 * 60_000));
  assert.ok(halfTimeReached(sprint, 5 * 60_000));
});

test("未设目标时字数进度为 null，设了目标封顶 1", () => {
  assert.equal(wordProgress(500, null), null);
  assert.equal(wordProgress(500, 1000), 0.5);
  assert.equal(wordProgress(2000, 1000), 1);
});

test("分钟秒表格式化", () => {
  assert.equal(formatClock(0), "00:00");
  assert.equal(formatClock(65_000), "01:05");
  assert.equal(formatClock(10 * 60_000), "10:00");
  assert.equal(formatClock(-1), "00:00");
});
