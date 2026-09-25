import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  arrangeCorkboardVolumes,
  corkboardDragReorderEnabled,
  orderCorkboardChapters,
} from "./corkboard-sort.ts";

interface Card {
  id: string;
  wordCount: number;
  wordCountTarget: number | null;
}

function card(id: string, wordCount: number, wordCountTarget: number | null): Card {
  return { id, wordCount, wordCountTarget };
}

test("还差 80 在还差 10 前面，超出在还差为正的后面，无目标保持原顺序排最后", () => {
  const chapters = [
    card("plain-a", 4000, null),
    card("gap-10", 90, 100),
    card("plain-b", 0, null),
    card("over", 130, 100),
    card("gap-80", 20, 100),
    card("met", 100, 100),
  ];
  const snapshot = chapters.map((chapter) => chapter.id);

  assert.deepEqual(
    orderCorkboardChapters(chapters, "shortfall").map((chapter) => chapter.id),
    ["gap-80", "gap-10", "met", "over", "plain-a", "plain-b"],
  );
  assert.deepEqual(
    chapters.map((chapter) => chapter.id),
    snapshot,
  );
  assert.deepEqual(
    orderCorkboardChapters(chapters, "reading").map((chapter) => chapter.id),
    snapshot,
  );
});

test("还差相同的章保持阅读顺序", () => {
  const chapters = [card("earlier", 40, 50), card("later", 90, 100)];
  assert.deepEqual(
    orderCorkboardChapters(chapters, "shortfall").map((chapter) => chapter.id),
    ["earlier", "later"],
  );
});

test("各卷分开排，卷的顺序不变", () => {
  const volumes = [
    {
      id: "volume-1",
      chapters: [card("v1-none", 0, null), card("v1-gap", 20, 100)],
    },
    {
      id: "volume-2",
      chapters: [card("v2-small", 90, 100), card("v2-over", 150, 100), card("v2-none", 8, null)],
    },
  ];

  const arranged = arrangeCorkboardVolumes(volumes, "shortfall");

  assert.deepEqual(
    arranged.map((volume) => volume.id),
    ["volume-1", "volume-2"],
  );
  assert.deepEqual(
    arranged[0]?.chapters.map((chapter) => chapter.id),
    ["v1-gap", "v1-none"],
  );
  assert.deepEqual(
    arranged[1]?.chapters.map((chapter) => chapter.id),
    ["v2-small", "v2-over", "v2-none"],
  );
  assert.deepEqual(
    arrangeCorkboardVolumes(volumes, "reading").map((volume) =>
      volume.chapters.map((chapter) => chapter.id),
    ),
    volumes.map((volume) => volume.chapters.map((chapter) => chapter.id)),
  );
});

test("还差视图禁用拖拽，排序不调用保存章节顺序的 API", () => {
  assert.equal(corkboardDragReorderEnabled("shortfall"), false);
  assert.equal(corkboardDragReorderEnabled("reading"), false);

  const sortSource = readFileSync(new URL("./corkboard-sort.ts", import.meta.url), "utf8");
  const boardSource = readFileSync(
    new URL("../features/writing/components/chapter-corkboard.tsx", import.meta.url),
    "utf8",
  );
  const savesChapterOrder = /reorderChapters|moveChapterToVolume|\/chapters\/reorder/;
  assert.doesNotMatch(sortSource, savesChapterOrder);
  assert.doesNotMatch(boardSource, savesChapterOrder);
});
