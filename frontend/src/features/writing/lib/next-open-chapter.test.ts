import { describe, expect, it } from "vitest";

import zhCN from "../../../i18n/locales/zh-CN.json";
import {
  nextOpenChapterId,
  visibleNextOpenChapterId,
  type ReadingOrderChapter,
  type ReadingOrderVolume,
} from "./next-open-chapter";

function chapter(
  id: string,
  order: number,
  writingStatus: ReadingOrderChapter["writingStatus"],
): ReadingOrderChapter {
  return { id, order, writingStatus };
}

function volume(order: number, chapters: ReadingOrderChapter[]): ReadingOrderVolume {
  return { order, chapters };
}

function markedAmong(
  volumes: readonly ReadingOrderVolume[],
  visibleIds: readonly string[],
  statusOverrides?: Readonly<Record<string, ReadingOrderChapter["writingStatus"]>>,
): string[] {
  const nextId = visibleNextOpenChapterId(volumes, new Set(visibleIds), statusOverrides);
  return visibleIds.filter((id) => id === nextId);
}

describe("软木板下一章", () => {
  it("第一章完成、第二章草稿时，只有第二章有标记", () => {
    const volumes = [
      volume(1, [
        chapter("ch-1", 1, "done"),
        chapter("ch-2", 2, "drafting"),
        chapter("ch-3", 3, "idea"),
      ]),
    ];

    expect(markedAmong(volumes, ["ch-1", "ch-2", "ch-3"])).toEqual(["ch-2"]);
  });

  it("构思、草稿、修订都算还没完成，完成的不标", () => {
    expect(nextOpenChapterId([volume(1, [chapter("idea", 1, "idea")])])).toBe("idea");
    expect(nextOpenChapterId([volume(1, [chapter("draft", 1, "drafting")])])).toBe("draft");
    expect(nextOpenChapterId([volume(1, [chapter("revise", 1, "revising")])])).toBe("revise");
    expect(
      nextOpenChapterId([volume(1, [chapter("done", 1, "done"), chapter("later", 2, "revising")])]),
    ).toBe("later");
  });

  it("全部完成时没有标记", () => {
    const volumes = [
      volume(1, [chapter("ch-1", 1, "done"), chapter("ch-2", 2, "done")]),
      volume(2, [chapter("ch-3", 1, "done")]),
    ];

    expect(nextOpenChapterId(volumes)).toBeNull();
    expect(markedAmong(volumes, ["ch-1", "ch-2", "ch-3"])).toEqual([]);
    expect(nextOpenChapterId([])).toBeNull();
    expect(nextOpenChapterId([volume(1, [])])).toBeNull();
  });

  it("跨卷时标在下一卷的第一张未完成", () => {
    const volumes = [
      volume(2, [chapter("vol-2-idea", 1, "idea"), chapter("vol-2-draft", 2, "drafting")]),
      volume(1, [chapter("vol-1-done", 1, "done"), chapter("vol-1-done-2", 2, "done")]),
    ];

    expect(nextOpenChapterId(volumes)).toBe("vol-2-idea");
    expect(
      markedAmong(volumes, ["vol-2-idea", "vol-2-draft", "vol-1-done", "vol-1-done-2"]),
    ).toEqual(["vol-2-idea"]);
  });

  it("改成完成后，标记移到阅读顺序上的下一张未完成", () => {
    const volumes = [
      volume(1, [chapter("ch-1", 1, "done"), chapter("ch-2", 2, "drafting")]),
      volume(2, [chapter("ch-3", 1, "revising"), chapter("ch-4", 2, "idea")]),
    ];
    const visible = ["ch-1", "ch-2", "ch-3", "ch-4"];

    expect(markedAmong(volumes, visible)).toEqual(["ch-2"]);
    expect(markedAmong(volumes, visible, { "ch-2": "done" })).toEqual(["ch-3"]);
    expect(markedAmong(volumes, visible, { "ch-2": "done", "ch-3": "done" })).toEqual(["ch-4"]);
    expect(
      markedAmong(volumes, visible, { "ch-2": "done", "ch-3": "done", "ch-4": "done" }),
    ).toEqual([]);

    const refreshed = [
      volume(1, [chapter("ch-1", 1, "done"), chapter("ch-2", 2, "done")]),
      volume(2, [chapter("ch-3", 1, "revising"), chapter("ch-4", 2, "idea")]),
    ];
    expect(nextOpenChapterId(refreshed)).toBe("ch-3");
  });

  it("按卷序和卷内章序，不用数组位置或数据库 id", () => {
    const volumes = [
      volume(2, [chapter("id-1", 1, "idea")]),
      volume(1, [chapter("id-9", 10, "drafting"), chapter("id-2", 2, "revising")]),
    ];

    expect(nextOpenChapterId(volumes)).toBe("id-2");
  });

  it("筛选把下一章藏起来时，不改标到可见列表的第一张", () => {
    const volumes = [
      volume(1, [
        chapter("ch-1", 1, "idea"),
        chapter("ch-2", 2, "drafting"),
        chapter("ch-3", 3, "drafting"),
      ]),
    ];
    const draftingOnly = ["ch-2", "ch-3"];

    expect(nextOpenChapterId(volumes)).toBe("ch-1");
    expect(visibleNextOpenChapterId(volumes, new Set(draftingOnly))).toBeNull();
    expect(markedAmong(volumes, draftingOnly)).toEqual([]);
    expect(markedAmong(volumes, ["ch-3"])).toEqual([]);
    expect(markedAmong(volumes, draftingOnly, { "ch-1": "done" })).toEqual(["ch-2"]);
  });

  it("卡片文案是下一章", () => {
    expect(zhCN.writing.chapterPlan.nextChapter).toBe("下一章");
  });
});
