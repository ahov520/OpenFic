import assert from "node:assert/strict";
import test from "node:test";

import {
  filterSidebarVolumesByWritingStatus,
  replaceChapterWritingStatusInTree,
  volumeHasHiddenChapters,
} from "./sidebar-writing-status-filter.ts";

interface FixtureChapter {
  id: string;
  writingStatus: "idea" | "drafting" | "revising" | "done";
  order: number;
  wordCount: number;
}

interface FixtureVolume {
  id: string;
  title: string;
  chapterCount: number;
  chapters: FixtureChapter[];
}

function chapter(
  id: string,
  writingStatus: FixtureChapter["writingStatus"],
  order: number,
  wordCount: number,
): FixtureChapter {
  return { id, writingStatus, order, wordCount };
}

function fixture(): FixtureVolume[] {
  return [
    {
      id: "vol-main",
      title: "第一卷",
      chapterCount: 4,
      chapters: [
        chapter("ch-idea", "idea", 0, 10),
        chapter("ch-draft", "drafting", 1, 20),
        chapter("ch-revise", "revising", 2, 30),
        chapter("ch-done", "done", 3, 40),
      ],
    },
    {
      id: "vol-done",
      title: "终卷",
      chapterCount: 1,
      chapters: [chapter("ch-finale", "done", 0, 50)],
    },
  ];
}

function visibleIds(volumes: readonly { chapters: readonly { id: string }[] }[]): string[] {
  return volumes.flatMap((volume) => volume.chapters.map((chapter) => chapter.id));
}

test("default filter shows every chapter", () => {
  const volumes = fixture();
  const visible = filterSidebarVolumesByWritingStatus(volumes, "all");

  assert.equal(visible, volumes);
  assert.deepEqual(visibleIds(visible), [
    "ch-idea",
    "ch-draft",
    "ch-revise",
    "ch-done",
    "ch-finale",
  ]);
});

test("still-writing view omits finished chapters", () => {
  const visible = filterSidebarVolumesByWritingStatus(fixture(), "writing");

  assert.deepEqual(visibleIds(visible), ["ch-idea", "ch-draft", "ch-revise"]);
});

test("draft filter hides revising chapters and keeps order and word counts", () => {
  const volumes = fixture();
  const visible = filterSidebarVolumesByWritingStatus(volumes, "drafting");
  const draft = visible[0]?.chapters[0];

  assert.deepEqual(visibleIds(visible), ["ch-draft"]);
  assert.equal(draft, volumes[0]?.chapters[1]);
  assert.equal(draft?.wordCount, 20);
  assert.equal(draft?.order, 1);
  assert.equal(visible[0]?.chapterCount, 4);
});

test("marking a chapter done removes it from the still-writing view", () => {
  const volumes = fixture();
  const updated = replaceChapterWritingStatusInTree({ volumes }, "ch-draft", "done");
  const visible = filterSidebarVolumesByWritingStatus(updated.volumes, "writing");
  const marked = updated.volumes[0]?.chapters.find((chapter) => chapter.id === "ch-draft");

  assert.equal(volumes[0]?.chapters[1]?.writingStatus, "drafting");
  assert.equal(marked?.writingStatus, "done");
  assert.equal(marked?.wordCount, 20);
  assert.equal(visibleIds(visible).includes("ch-draft"), false);
  assert.deepEqual(visibleIds(visible), ["ch-idea", "ch-revise"]);
});

test("a volume with no visible chapters keeps its name", () => {
  const volumes = fixture();
  const visible = filterSidebarVolumesByWritingStatus(volumes, "writing");
  const finishedVolume = visible.find((volume) => volume.id === "vol-done");

  assert.deepEqual(
    visible.map((volume) => volume.id),
    ["vol-main", "vol-done"],
  );
  assert.equal(finishedVolume?.title, "终卷");
  assert.equal(finishedVolume?.chapterCount, 1);
  assert.equal(finishedVolume?.chapters.length, 0);
  assert.equal(volumeHasHiddenChapters(finishedVolume ?? { chapterCount: 0, chapters: [] }), true);
  assert.deepEqual(
    volumes[1]?.chapters.map((chapter) => chapter.id),
    ["ch-finale"],
  );
});
