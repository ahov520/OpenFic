import { describe, expect, it } from "vitest";

import zhCN from "@/i18n/locales/zh-CN.json";
import type { VolumeTreeResponse } from "@/lib/chapter.types";

import { applySavedWordCountToVolumeTree, showsNotStartedMark } from "./sidebar-not-started";

const planned = {
  synopsis: "他在门口停下，决定要不要推门。",
  writingStatus: "drafting" as const,
  wordCount: 0,
};

describe("showsNotStartedMark", () => {
  it("marks a draft with a synopsis and zero saved words", () => {
    expect(showsNotStartedMark(planned)).toBe(true);
  });

  it("marks a revision with a synopsis and zero saved words", () => {
    expect(showsNotStartedMark({ ...planned, writingStatus: "revising" })).toBe(true);
  });

  it("hides the mark once the saved word count is above zero", () => {
    expect(showsNotStartedMark({ ...planned, wordCount: 1 })).toBe(false);
    expect(showsNotStartedMark({ ...planned, wordCount: 12 })).toBe(false);
  });

  it("does not mark a blank synopsis", () => {
    for (const synopsis of ["", "   ", "\n\n", "\t  \n", "\u3000", " \u00a0 "]) {
      expect(showsNotStartedMark({ ...planned, synopsis })).toBe(false);
    }
  });

  it("does not mark idea or done chapters", () => {
    expect(showsNotStartedMark({ ...planned, writingStatus: "idea" })).toBe(false);
    expect(showsNotStartedMark({ ...planned, writingStatus: "done" })).toBe(false);
  });

  it("keeps the visible label as 还没动笔", () => {
    expect(zhCN.writing.notStarted).toBe("还没动笔");
  });
});

describe("applySavedWordCountToVolumeTree", () => {
  it("drops the mark as soon as the saved word count is written onto the sidebar row", () => {
    const tree = sampleTree(planned);
    const saved = applySavedWordCountToVolumeTree(tree, {
      id: "c1",
      wordCount: 4,
      updatedAt: "2026-09-24T00:00:01Z",
    });
    const chapter = saved.volumes[0]?.chapters[0];
    expect(chapter?.wordCount).toBe(4);
    expect(chapter && showsNotStartedMark(chapter)).toBe(false);
    expect(tree.volumes[0]?.chapters[0]?.wordCount).toBe(0);
  });
});

function sampleTree(chapter: {
  synopsis: string;
  writingStatus: "drafting";
  wordCount: number;
}): VolumeTreeResponse {
  return {
    totalChapters: 1,
    volumes: [
      {
        id: "v1",
        projectId: "p1",
        title: "卷一",
        description: null,
        order: 1,
        chapterCount: 1,
        createdAt: "2026-09-01T00:00:00Z",
        updatedAt: "2026-09-01T00:00:00Z",
        chapters: [
          {
            id: "c1",
            projectId: "p1",
            volumeId: "v1",
            title: "雨停之前",
            synopsis: chapter.synopsis,
            writingStatus: chapter.writingStatus,
            wordCount: chapter.wordCount,
            wordCountTarget: null,
            order: 0,
            createdAt: "2026-09-01T00:00:00Z",
            updatedAt: "2026-09-02T00:00:00Z",
          },
        ],
      },
    ],
  };
}
