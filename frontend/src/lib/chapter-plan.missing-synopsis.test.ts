import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { corkboardMissingSynopsis } from "./chapter-plan.ts";

const here = dirname(fileURLToPath(import.meta.url));

test("草稿且空梗概要标还没写梗概", () => {
  assert.equal(corkboardMissingSynopsis("drafting", ""), true);
});

test("修订且空梗概同样要标", () => {
  assert.equal(corkboardMissingSynopsis("revising", ""), true);
});

test("构思和完成不标", () => {
  assert.equal(corkboardMissingSynopsis("idea", ""), false);
  assert.equal(corkboardMissingSynopsis("done", ""), false);
});

test("已有梗概不标", () => {
  assert.equal(corkboardMissingSynopsis("drafting", "沈照推开门。"), false);
  assert.equal(corkboardMissingSynopsis("revising", "改掉门外那个人。"), false);
});

test("只含空白视为还没写", () => {
  assert.equal(corkboardMissingSynopsis("drafting", "   \n"), true);
  assert.equal(corkboardMissingSynopsis("revising", " \n\t "), true);
  assert.equal(corkboardMissingSynopsis("idea", "   "), false);
  assert.equal(corkboardMissingSynopsis("done", "\n"), false);
});

test("写下非空梗概后标记消失，清空后草稿和修订又出现", () => {
  assert.equal(corkboardMissingSynopsis("drafting", "门外是林晚棠。"), false);
  assert.equal(corkboardMissingSynopsis("drafting", ""), true);
  assert.equal(corkboardMissingSynopsis("revising", " "), true);
  assert.equal(corkboardMissingSynopsis("revising", "收回铜钥匙。"), false);
  assert.equal(corkboardMissingSynopsis("revising", ""), true);
  assert.equal(corkboardMissingSynopsis("done", ""), false);
  assert.equal(corkboardMissingSynopsis("idea", ""), false);
});

test("标记文案是还没写梗概，点标记聚焦现有梗概框", () => {
  const zh = JSON.parse(readFileSync(join(here, "../i18n/locales/zh-CN.json"), "utf8")) as {
    writing: { chapterPlan: { missingSynopsis: string } };
  };
  assert.equal(zh.writing.chapterPlan.missingSynopsis, "还没写梗概");

  const card = readFileSync(
    join(here, "../features/writing/components/chapter-corkboard.tsx"),
    "utf8",
  );
  assert.match(card, /corkboardMissingSynopsis\(draft\.writingStatus,\s*draft\.synopsis\)/);
  assert.match(card, /data-testid="corkboard-missing-synopsis"/);
  assert.match(card, /htmlFor=\{synopsisId\}/);
  assert.match(card, /id=\{synopsisId\}/);
  assert.match(card, /onChange=\{\(event\) => draft\.setSynopsis\(event\.target\.value\)\}/);
  assert.match(card, /onBlur=\{draft\.flush\}/);

  const css = readFileSync(join(here, "../features/writing/components/chapter-plan.css"), "utf8");
  const rule = css.slice(css.indexOf(".chapter-corkboard-card__missing-synopsis {"));
  assert.match(rule, /flex-shrink:\s*0/);
});
