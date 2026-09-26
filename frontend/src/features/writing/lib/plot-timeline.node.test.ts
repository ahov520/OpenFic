import assert from "node:assert/strict";
import test from "node:test";

import type { PlotBeat, PlotChapterOption, PlotThread } from "@/lib/plot-thread";

import { beatsByChapter, buildTimelineRows } from "./plot-timeline.ts";

function chapter(id: string, globalOrder: number): PlotChapterOption {
  return { id, title: `第${globalOrder}章`, globalOrder, volumeTitle: "第一卷" };
}

function beat(id: string, threadId: string, chapterId: string, kind: "plant" | "advance" | "payoff"): PlotBeat {
  return { id, threadId, chapterId, chapterTitle: "", volumeTitle: "", globalOrder: 0, kind, note: `备注${id}` };
}

function thread(id: string, beats: PlotBeat[]): PlotThread {
  return {
    id,
    projectId: "p",
    name: `线${id}`,
    intent: "",
    status: "active",
    sortOrder: 0,
    issues: [],
    hasPlant: false,
    hasPayoff: false,
    lastChapterId: null,
    lastChapterTitle: null,
    lastGlobalOrder: null,
    lastKind: null,
    chaptersSinceLast: null,
    gapChapters: [],
    gapRange: null,
    beats,
  } as unknown as PlotThread;
}

test("同一章同一条线只取一个节拍（后端已去重，这里兜底）", () => {
  const map = beatsByChapter([beat("a", "t1", "c1", "plant"), beat("b", "t1", "c1", "payoff")]);
  assert.equal(map.get("c1")?.id, "b");
});

test("时间轴行按章节阅读顺序铺格子，无节拍处为空", () => {
  const chapters = [chapter("c1", 1), chapter("c2", 2), chapter("c3", 3)];
  const rows = buildTimelineRows(
    [thread("t1", [beat("a", "t1", "c3", "payoff")])],
    chapters,
  );
  assert.equal(rows.length, 1);
  const cells = rows[0].cells;
  assert.deepEqual(
    cells.map((cell) => cell.chapter.globalOrder),
    [1, 2, 3],
  );
  assert.equal(cells[0].beat, null);
  assert.equal(cells[2].beat?.kind, "payoff");
});

test("多条线各自独立映射", () => {
  const chapters = [chapter("c1", 1), chapter("c2", 2)];
  const rows = buildTimelineRows(
    [thread("t1", [beat("a", "t1", "c1", "plant")]), thread("t2", [beat("b", "t2", "c2", "payoff")])],
    chapters,
  );
  assert.equal(rows[0].cells[0].beat?.id, "a");
  assert.equal(rows[0].cells[1].beat, null);
  assert.equal(rows[1].cells[0].beat, null);
  assert.equal(rows[1].cells[1].beat?.id, "b");
});
