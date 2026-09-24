import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  INITIAL_CORKBOARD_FILTER,
  chapterOwesOpenPlant,
  visibleCorkboardVolumes,
  type CorkboardChapterRef,
  type OwingThread,
} from "./corkboard-owing.ts";

function chapter(
  id: string,
  writingStatus: string,
  wordCount: number,
  title = id,
): CorkboardChapterRef {
  return { id, title, synopsis: "", writingStatus, wordCount };
}

function planted(
  chapterId: string,
  status = "active",
  extra: OwingThread["beats"][number][] = [],
): OwingThread {
  return {
    status,
    hasPayoff: extra.some((beat) => beat.kind === "payoff"),
    beats: [{ chapterId, kind: "plant" }, ...extra],
  };
}

describe("软木板还欠线", () => {
  const draft = chapter("draft", "drafting", 320, "灯还亮着");
  const revising = chapter("revise", "revising", 180, "再看一眼");
  const done = chapter("done", "done", 900, "已经写完");
  const idea = chapter("idea", "idea", 0, "还在想");

  it("默认不是还欠线，完成的章也留着", () => {
    assert.equal(INITIAL_CORKBOARD_FILTER.owingOnly, false);
    assert.equal(INITIAL_CORKBOARD_FILTER.status, "all");
    const shown = visibleCorkboardVolumes(
      [{ id: "v", title: "卷一", chapters: [draft, done] }],
      INITIAL_CORKBOARD_FILTER,
      [planted("draft"), planted("done")],
    );
    assert.deepEqual(
      shown[0]?.chapters.map((item) => item.id),
      ["draft", "done"],
    );
    assert.equal(shown[0]?.chapters[0], draft);
    assert.equal(shown[0]?.chapters[1]?.wordCount, 900);
  });

  it("草稿且本章埋下未回收的线会留下", () => {
    assert.equal(chapterOwesOpenPlant(draft, [planted("draft")]), true);
    const shown = visibleCorkboardVolumes(
      [{ id: "v", title: "卷一", chapters: [draft, done] }],
      { status: "all", owingOnly: true, query: "" },
      [planted("draft"), planted("done")],
    );
    assert.deepEqual(
      shown[0]?.chapters.map((item) => item.id),
      ["draft"],
    );
    assert.equal(shown[0]?.chapters[0], draft);
    assert.equal(shown[0]?.chapters[0]?.wordCount, 320);
  });

  it("修订章同样留下，构思不留下", () => {
    assert.equal(chapterOwesOpenPlant(revising, [planted("revise")]), true);
    assert.equal(chapterOwesOpenPlant(idea, [planted("idea")]), false);
  });

  it("该线有 payoff 后不再留下", () => {
    const paid: OwingThread = planted("draft", "active", [{ chapterId: "later", kind: "payoff" }]);
    assert.equal(paid.hasPayoff, true);
    assert.equal(chapterOwesOpenPlant(draft, [paid]), false);
  });

  it("只在别章埋下，或这一章只推进，都不留下", () => {
    assert.equal(chapterOwesOpenPlant(draft, [planted("other")]), false);
    const advanced: OwingThread = {
      status: "active",
      hasPayoff: false,
      beats: [{ chapterId: "draft", kind: "advance" }],
    };
    assert.equal(chapterOwesOpenPlant(draft, [advanced]), false);
  });

  it("完成状态不留下", () => {
    assert.equal(chapterOwesOpenPlant(done, [planted("done")]), false);
  });

  it("已放弃的线不留下", () => {
    assert.equal(chapterOwesOpenPlant(draft, [planted("draft", "abandoned")]), false);
  });

  it("还欠线留下卷名，空卷和筛空用不同说明，书序和字数不动", () => {
    const other = chapter("other", "drafting", 40, "另一章");
    const shown = visibleCorkboardVolumes(
      [
        { id: "empty", title: "空卷", chapters: [] },
        { id: "finished", title: "已完成", chapters: [done] },
        { id: "writing", title: "在写", chapters: [other, draft] },
      ],
      { status: "all", owingOnly: true, query: "" },
      [planted("draft"), planted("done")],
    );
    assert.deepEqual(
      shown.map((volume) => volume.title),
      ["空卷", "已完成", "在写"],
    );
    assert.equal(shown[0]?.placeholder, "empty-volume");
    assert.equal(shown[1]?.placeholder, "empty-filter");
    assert.equal(shown[2]?.placeholder, "cards");
    assert.equal(shown[2]?.chapters[0], draft);
    assert.equal(other.wordCount, 40);
    assert.equal(draft.wordCount, 320);
  });

  it("和状态筛选一起用，而不是互相换掉", () => {
    const shown = visibleCorkboardVolumes(
      [{ id: "v", title: "卷一", chapters: [draft, revising] }],
      { status: "revising", owingOnly: true, query: "" },
      [planted("draft"), planted("revise")],
    );
    assert.deepEqual(
      shown[0]?.chapters.map((item) => item.id),
      ["revise"],
    );
    assert.equal(shown[0]?.chapters[0]?.wordCount, 180);
  });
});
