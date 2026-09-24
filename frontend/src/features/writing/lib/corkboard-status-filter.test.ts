import assert from "node:assert/strict";
import test from "node:test";

import {
  corkboardVolumeCards,
  corkboardVolumeEmptyKind,
  isChapterOutsideCorkboardView,
  replaceChapterWritingStatusInTree,
} from "./corkboard-status-filter.ts";

interface FixtureChapter {
  id: string;
  title: string;
  synopsis: string;
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
  return { id, title: id, synopsis: "", writingStatus, order, wordCount };
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
    {
      id: "vol-empty",
      title: "空卷",
      chapterCount: 0,
      chapters: [],
    },
  ];
}

function visibleIds(volumes: readonly { chapters: readonly { id: string }[] }[]): string[] {
  return volumes.flatMap((volume) => volume.chapters.map((item) => item.id));
}

test("default filter shows every chapter", () => {
  const volumes = fixture();
  const visible = corkboardVolumeCards(volumes, "all", "");

  assert.deepEqual(
    visible.map((volume) => volume.id),
    ["vol-main", "vol-done", "vol-empty"],
  );
  assert.deepEqual(visibleIds(visible), [
    "ch-idea",
    "ch-draft",
    "ch-revise",
    "ch-done",
    "ch-finale",
  ]);
  assert.equal(visible[0]?.chapters[1], volumes[0]?.chapters[1]);
});

test("still-writing view omits finished chapters", () => {
  const visible = corkboardVolumeCards(fixture(), "writing", "");

  assert.deepEqual(visibleIds(visible), ["ch-idea", "ch-draft", "ch-revise"]);
  assert.equal(visibleIds(visible).includes("ch-done"), false);
  assert.equal(visibleIds(visible).includes("ch-finale"), false);
});

test("draft filter hides revising chapters and keeps order and word counts", () => {
  const volumes = fixture();
  const visible = corkboardVolumeCards(volumes, "drafting", "");
  const draft = visible[0]?.chapters[0];

  assert.deepEqual(visibleIds(visible), ["ch-draft"]);
  assert.equal(
    visibleIds(visible).some((id) => id === "ch-revise"),
    false,
  );
  assert.equal(draft, volumes[0]?.chapters[1]);
  assert.equal(draft?.wordCount, 20);
  assert.equal(draft?.order, 1);
  assert.equal(volumes[0]?.chapterCount, 4);
});

test("marking a chapter done removes it from the still-writing view", () => {
  const volumes = fixture();
  const updated = replaceChapterWritingStatusInTree({ volumes }, "ch-draft", "done");
  const visible = corkboardVolumeCards(updated.volumes, "writing", "");
  const marked = updated.volumes[0]?.chapters.find((item) => item.id === "ch-draft");

  assert.equal(volumes[0]?.chapters[1]?.writingStatus, "drafting");
  assert.equal(marked?.writingStatus, "done");
  assert.equal(marked?.wordCount, 20);
  assert.equal(marked?.order, 1);
  assert.equal(visibleIds(visible).includes("ch-draft"), false);
  assert.deepEqual(visibleIds(visible), ["ch-idea", "ch-revise"]);
});

test("filtered and truly empty volumes both keep their names", () => {
  const volumes = fixture();
  const visible = corkboardVolumeCards(volumes, "writing", "");
  const finished = visible.find((volume) => volume.id === "vol-done");
  const empty = visible.find((volume) => volume.id === "vol-empty");

  assert.deepEqual(
    visible.map((volume) => volume.title),
    ["第一卷", "终卷", "空卷"],
  );
  assert.equal(finished?.chapters.length, 0);
  assert.equal(finished ? corkboardVolumeEmptyKind(finished) : "cards", "filter");
  assert.equal(empty ? corkboardVolumeEmptyKind(empty) : "cards", "source");
  assert.equal(volumes[1]?.chapterCount, 1);
  assert.deepEqual(
    volumes[1]?.chapters.map((item) => item.id),
    ["ch-finale"],
  );
});

test("the open chapter stays known when the filter hides it", () => {
  const volumes = fixture();
  const openChapter = volumes[0]?.chapters.find((item) => item.id === "ch-done");

  assert.equal(isChapterOutsideCorkboardView(openChapter, "writing", ""), true);
  assert.equal(isChapterOutsideCorkboardView(openChapter, "all", ""), false);

  const updated = replaceChapterWritingStatusInTree({ volumes }, "ch-draft", "done");
  const drafted = updated.volumes[0]?.chapters.find((item) => item.id === "ch-draft");
  assert.equal(isChapterOutsideCorkboardView(drafted, "writing", ""), true);
  assert.equal(isChapterOutsideCorkboardView(drafted, "all", ""), false);
});
