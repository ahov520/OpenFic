import assert from "node:assert/strict";
import test from "node:test";

import { computeStreak } from "./daily-word-goal.ts";

function series(days: Array<[string, number]>) {
  return days.map(([date, userWordDelta]) => ({ date, userWordDelta }));
}

test("今天达标：从今天连续往回数", () => {
  const streak = computeStreak(
    series([
      ["2026-09-26", 600],
      ["2026-09-25", 600],
      ["2026-09-24", 100],
      ["2026-09-23", 600],
    ]),
    500,
    "2026-09-26",
  );
  assert.equal(streak, 2);
});

test("今天还没写够：从昨天起算， streak 仍然活着", () => {
  const streak = computeStreak(
    series([
      ["2026-09-26", 100],
      ["2026-09-25", 600],
      ["2026-09-24", 600],
    ]),
    500,
    "2026-09-26",
  );
  assert.equal(streak, 2);
});

test("中间断一天即归零", () => {
  const streak = computeStreak(
    series([
      ["2026-09-26", 600],
      ["2026-09-25", 100],
      ["2026-09-24", 600],
    ]),
    500,
    "2026-09-26",
  );
  assert.equal(streak, 1);
});

test("无记录日视为未达标", () => {
  const streak = computeStreak(
    series([
      ["2026-09-26", 600],
      ["2026-09-24", 600],
    ]),
    500,
    "2026-09-26",
  );
  assert.equal(streak, 1);
});

test("目标为 0 或空序列返回 0", () => {
  assert.equal(computeStreak([], 500, "2026-09-26"), 0);
  assert.equal(
    computeStreak(series([["2026-09-26", 600]]), 0, "2026-09-26"),
    0,
  );
});
