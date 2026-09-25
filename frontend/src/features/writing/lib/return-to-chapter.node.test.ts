import assert from "node:assert/strict";
import test from "node:test";

import {
  chapterIdFromStoredLastChapter,
  decideWritingOpen,
  nextReturnTarget,
  returnChapterToShow,
} from "./return-to-chapter.ts";

const chapters = [
  { id: "chapter-a", title: "夜航" },
  { id: "chapter-b", title: "空章" },
];

test("有最近章节且当前是空标签时恢复", () => {
  const decision = decideWritingOpen({
    tabs: [{ id: "__empty__1", type: "chapter", refId: null }],
    activeTabId: "__empty__1",
    storedLastChapterId: "chapter-a",
    chapterIds: ["chapter-a", "chapter-b"],
  });
  assert.deepEqual(decision, { action: "restore", chapterId: "chapter-a" });
});

test("一个标签都没有、且存的是 chapter: 前缀时也恢复", () => {
  assert.equal(chapterIdFromStoredLastChapter("chapter:chapter-a"), "chapter-a");
  const decision = decideWritingOpen({
    tabs: [],
    activeTabId: null,
    storedLastChapterId: "chapter:chapter-a",
    chapterIds: ["chapter-a", "chapter-b"],
  });
  assert.deepEqual(decision, { action: "restore", chapterId: "chapter-a" });
});

test("当前正在写某一章时不改去最近章节", () => {
  const decision = decideWritingOpen({
    tabs: [{ id: "chapter:chapter-b", type: "chapter", refId: "chapter-b" }],
    activeTabId: "chapter:chapter-b",
    storedLastChapterId: "chapter-a",
    chapterIds: ["chapter-a", "chapter-b"],
  });
  assert.deepEqual(decision, { action: "keep" });
});

test("全新项目没有最近章节时保持空状态", () => {
  const decision = decideWritingOpen({
    tabs: [],
    activeTabId: null,
    storedLastChapterId: null,
    chapterIds: [],
  });
  assert.deepEqual(decision, { action: "stay-empty" });
});

test("空标签 id 和已删除的章节都不能当成最近章节", () => {
  assert.equal(chapterIdFromStoredLastChapter("__empty__9"), null);
  assert.equal(chapterIdFromStoredLastChapter("note:note-1"), null);
  const decision = decideWritingOpen({
    tabs: [{ id: "__empty__1", type: "chapter", refId: null }],
    activeTabId: "__empty__1",
    storedLastChapterId: "__empty__9",
    chapterIds: ["chapter-a"],
  });
  assert.deepEqual(decision, { action: "stay-empty" });
  const missing = decideWritingOpen({
    tabs: [],
    activeTabId: null,
    storedLastChapterId: "deleted-chapter",
    chapterIds: ["chapter-a"],
  });
  assert.deepEqual(missing, { action: "stay-empty" });
});

test("从 A 跳到 B 后可以回到 A，回到之后不再显示", () => {
  const onA = nextReturnTarget(null, { id: "chapter-a", title: "夜航" }, null);
  assert.equal(onA, null);

  const onB = nextReturnTarget({ id: "chapter-a", title: "夜航" }, chapters[1], onA);
  assert.deepEqual(onB, { id: "chapter-a", title: "夜航" });
  assert.deepEqual(returnChapterToShow(onB, "chapter-b", chapters), {
    id: "chapter-a",
    title: "夜航",
  });

  const returned = nextReturnTarget(chapters[1], chapters[0], onB);
  assert.equal(returned, null);
  assert.equal(returnChapterToShow(returned, "chapter-a", chapters), null);
});

test("从正在写的章节离开到空标签时记下出发章", () => {
  const target = nextReturnTarget({ id: "chapter-a", title: "夜航" }, null, null);
  assert.deepEqual(target, { id: "chapter-a", title: "夜航" });
  assert.deepEqual(returnChapterToShow(target, null, chapters), {
    id: "chapter-a",
    title: "夜航",
  });
});

test("再跳一章只保留刚离开的那一章", () => {
  const afterB = nextReturnTarget({ id: "chapter-a", title: "夜航" }, chapters[1], null);
  const afterC = nextReturnTarget(chapters[1], { id: "chapter-c", title: "下一章" }, afterB);
  assert.deepEqual(afterC, { id: "chapter-b", title: "空章" });
});
