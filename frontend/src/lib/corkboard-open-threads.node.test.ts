import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { corkboardOpenPlantNames, previewOpenPlantNames } from "./corkboard-open-threads.ts";

const here = dirname(fileURLToPath(import.meta.url));

test("草稿章有埋下且未回收时出现线名", () => {
  const names = corkboardOpenPlantNames("drafting", { c1: ["铜镜"] }, "c1");
  assert.deepEqual(names, ["铜镜"]);
});

test("修订章同样显示，构思和完成不显示", () => {
  const grouped = { c1: ["铜镜", "旧信"] };
  assert.deepEqual(corkboardOpenPlantNames("revising", grouped, "c1"), ["铜镜", "旧信"]);
  assert.deepEqual(corkboardOpenPlantNames("idea", grouped, "c1"), []);
  assert.deepEqual(corkboardOpenPlantNames("done", grouped, "c1"), []);
});

test("只在别章埋下的线不出现在这一章", () => {
  const names = corkboardOpenPlantNames("drafting", { c2: ["旧信"] }, "c1");
  assert.deepEqual(names, []);
});

test("超过三条时先显示三个名字，其余记成还有 N 条", () => {
  const names = ["铜镜", "旧信", "伤疤", "夜航", "灯"];
  const collapsed = previewOpenPlantNames(names, false);
  assert.deepEqual(collapsed.shown, ["铜镜", "旧信", "伤疤"]);
  assert.equal(collapsed.hiddenCount, 2);
  const expanded = previewOpenPlantNames(names, true);
  assert.deepEqual(expanded.shown, names);
  assert.equal(expanded.hiddenCount, 0);
});

test("软木板卡片消费按章归类的名单，并提供展开", () => {
  const source = readFileSync(
    join(here, "../features/writing/components/chapter-corkboard.tsx"),
    "utf8",
  );
  const zh = JSON.parse(readFileSync(join(here, "../i18n/locales/zh-CN.json"), "utf8")) as {
    writing: { chapterPlan: { openThreadsMore: string } };
  };
  assert.match(source, /corkboardOpenPlantNames/);
  assert.match(source, /previewOpenPlantNames/);
  assert.match(source, /data-testid="corkboard-open-threads"/);
  assert.match(source, /writing\.chapterPlan\.openThreadsMore/);
  assert.equal(zh.writing.chapterPlan.openThreadsMore, "还有 {{count}} 条");
});
