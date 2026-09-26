import assert from "node:assert/strict";
import test from "node:test";

import {
  goalProgress,
  todayUserWords,
  todayWordGoalRange,
} from "./daily-word-goal.ts";

test("今天范围是本地零点到明天零点，带时区名", () => {
  const now = new Date(2026, 8, 26, 15, 30, 45).getTime(); // 本地 2026-09-26 15:30:45
  const range = todayWordGoalRange(now);
  const start = new Date(range.startAt);
  const end = new Date(range.endAt);
  assert.equal(start.getHours(), 0);
  assert.equal(start.getMinutes(), 0);
  assert.equal(end.getDate(), start.getDate() + 1);
  assert.equal(end.getHours(), 0);
  assert.ok(range.timezone.length > 0);
  assert.match(range.startAt, /[+-]\d{2}:\d{2}$/);
});

test("今日字数只累计用户正向增量", () => {
  const words = todayUserWords([
    { userWordDelta: 1200 },
    { userWordDelta: -300 },
    { userWordDelta: 500 },
  ]);
  assert.equal(words, 1700);
});

test("目标进度：未设目标不产生进度", () => {
  assert.deepEqual(goalProgress(1000, 0), { percent: 0, done: false });
  assert.deepEqual(goalProgress(1000, 2000), { percent: 0.5, done: false });
  assert.deepEqual(goalProgress(2000, 2000), { percent: 1, done: true });
  assert.deepEqual(goalProgress(2500, 2000), { percent: 1, done: true });
  assert.deepEqual(goalProgress(-100, 2000), { percent: 0, done: false });
});
