import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_CORKBOARD_VIEW,
  corkboardVolumeCards,
  corkboardVolumeEmptyKind,
  countChaptersMissingWordCountTarget,
  isChapterOutsideCorkboardView,
  replaceChapterWordCountTargetInTree,
  type CorkboardView,
} from "./corkboard-missing-target.ts";

interface FixtureChapter {
  id: string;
  title: string;
  synopsis: string;
  writingStatus: "idea" | "drafting" | "revising" | "done";
  wordCountTarget: number | null;
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
  wordCountTarget: number | null,
  order: number,
  wordCount: number,
): FixtureChapter {
  return {
    id,
    title: id,
    synopsis: "",
    writingStatus,
    wordCountTarget,
    order,
    wordCount,
  };
}

function fixture(): FixtureVolume[] {
  return [
    {
      id: "vol-main",
      title: "第一卷",
      chapterCount: 6,
      chapters: [
        chapter("ch-idea", "idea", null, 0, 10),
        chapter("ch-draft", "drafting", null, 1, 20),
        chapter("ch-draft-set", "drafting", 3000, 2, 21),
        chapter("ch-revise", "revising", null, 3, 30),
        chapter("ch-revise-set", "revising", 1, 4, 31),
        chapter("ch-done", "done", null, 5, 40),
      ],
    },
    {
      id: "vol-done",
      title: "终卷",
      chapterCount: 1,
      chapters: [chapter("ch-finale", "done", 8000, 0, 50)],
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

function view(partial: Partial<CorkboardView> = {}): CorkboardView {
  return { ...DEFAULT_CORKBOARD_VIEW, ...partial };
}

test("开关默认关闭，打开项目时章节都不藏", () => {
  assert.equal(DEFAULT_CORKBOARD_VIEW.missingTargetOnly, false);
  assert.equal(DEFAULT_CORKBOARD_VIEW.statusFilter, "all");
  assert.equal(DEFAULT_CORKBOARD_VIEW.query, "");

  const volumes = fixture();
  const visible = corkboardVolumeCards(volumes, DEFAULT_CORKBOARD_VIEW);

  assert.deepEqual(visibleIds(visible), [
    "ch-idea",
    "ch-draft",
    "ch-draft-set",
    "ch-revise",
    "ch-revise-set",
    "ch-done",
    "ch-finale",
  ]);
  assert.equal(visible[0]?.chapters[1], volumes[0]?.chapters[1]);
});

test("草稿和修订里没设目标的章留下，设了目标的不留", () => {
  const volumes = fixture();
  const visible = corkboardVolumeCards(volumes, view({ missingTargetOnly: true }));
  const draft = visible[0]?.chapters.find((item) => item.id === "ch-draft");

  assert.deepEqual(visibleIds(visible), ["ch-draft", "ch-revise"]);
  assert.equal(draft, volumes[0]?.chapters[1]);
  assert.equal(draft?.wordCount, 20);
  assert.equal(draft?.order, 1);
  assert.equal(draft?.wordCountTarget, null);
  assert.equal(volumes[0]?.chapterCount, 6);
});

test("构思和完成即使没设目标也不留下", () => {
  const visible = corkboardVolumeCards(fixture(), view({ missingTargetOnly: true }));
  const ids = visibleIds(visible);

  assert.equal(ids.includes("ch-idea"), false);
  assert.equal(ids.includes("ch-done"), false);
  assert.equal(ids.includes("ch-finale"), false);
});

test("只看修订时再打开开关，只剩修订里没设目标的章", () => {
  const visible = corkboardVolumeCards(
    fixture(),
    view({ statusFilter: "revising", missingTargetOnly: true }),
  );

  assert.deepEqual(visibleIds(visible), ["ch-revise"]);
});

test("目标为 0 或空不算已设，合法目标才把卡片筛掉", () => {
  const volumes = fixture();
  const draft = volumes[0]?.chapters.find((item) => item.id === "ch-draft");
  const revising = volumes[0]?.chapters.find((item) => item.id === "ch-revise");
  assert.ok(draft);
  assert.ok(revising);
  draft.wordCountTarget = 0;
  revising.wordCountTarget = null;

  const visible = corkboardVolumeCards(volumes, view({ missingTargetOnly: true }));

  assert.deepEqual(visibleIds(visible), ["ch-draft", "ch-revise"]);
  assert.equal(
    countChaptersMissingWordCountTarget(volumes.flatMap((volume) => volume.chapters)),
    2,
  );
});

test("在卡片上设了目标后，开关开着时这张卡立刻离开", () => {
  const volumes = fixture();
  const tree = { volumes };
  const updated = replaceChapterWordCountTargetInTree(tree, "ch-draft", 2500);
  const visible = corkboardVolumeCards(updated.volumes, view({ missingTargetOnly: true }));
  const marked = updated.volumes[0]?.chapters.find((item) => item.id === "ch-draft");

  assert.equal(volumes[0]?.chapters[1]?.wordCountTarget, null);
  assert.equal(marked?.wordCountTarget, 2500);
  assert.equal(marked?.wordCount, 20);
  assert.equal(marked?.order, 1);
  assert.deepEqual(
    updated.volumes[0]?.chapters.map((item) => item.id),
    volumes[0]?.chapters.map((item) => item.id),
  );
  assert.equal(visibleIds(visible).includes("ch-draft"), false);
  assert.deepEqual(visibleIds(visible), ["ch-revise"]);
});

test("卷名留下；本来没有章和筛空的卷分开说明", () => {
  const volumes = fixture();
  const visible = corkboardVolumeCards(volumes, view({ missingTargetOnly: true }));
  const finished = visible.find((volume) => volume.id === "vol-done");
  const empty = visible.find((volume) => volume.id === "vol-empty");

  assert.deepEqual(
    visible.map((volume) => volume.title),
    ["第一卷", "终卷", "空卷"],
  );
  assert.equal(finished ? corkboardVolumeEmptyKind(finished) : "cards", "filter");
  assert.equal(empty ? corkboardVolumeEmptyKind(empty) : "cards", "source");
  assert.equal(volumes[1]?.chapterCount, 1);
  assert.deepEqual(
    volumes[1]?.chapters.map((item) => item.id),
    ["ch-finale"],
  );
});

test("当前章被筛掉后，回到全部会同时收回状态、开关和搜索", () => {
  const volumes = fixture();
  const openChapter = volumes[0]?.chapters.find((item) => item.id === "ch-draft-set");
  const filtered = view({
    statusFilter: "drafting",
    missingTargetOnly: true,
    query: "不会匹配",
  });

  assert.equal(isChapterOutsideCorkboardView(openChapter, filtered), true);
  assert.equal(isChapterOutsideCorkboardView(openChapter, DEFAULT_CORKBOARD_VIEW), false);

  const restored = corkboardVolumeCards(volumes, DEFAULT_CORKBOARD_VIEW);
  assert.equal(visibleIds(restored).includes("ch-draft-set"), true);
  assert.equal(visibleIds(restored).includes("ch-idea"), true);
});
