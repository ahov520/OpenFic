import { describe, expect, it } from "vitest";
import { wordsCount } from "words-count";

import zhCN from "../../../i18n/locales/zh-CN.json";
import { htmlToNewlines } from "../../../lib/html-utils";
import { isChapterNotStarted } from "./chapter-not-started";

const planned = {
  synopsis: "他在门口停下，决定要不要推门。",
  writingStatus: "drafting" as const,
  wordCount: 0,
};

describe("corkboard not-started mark", () => {
  it("shows the mark for a draft with a synopsis and zero saved words", () => {
    expect(isChapterNotStarted(planned)).toBe(true);
  });

  it("shows the mark for a revision with a synopsis and zero saved words", () => {
    expect(isChapterNotStarted({ ...planned, writingStatus: "revising" })).toBe(true);
  });

  it("hides the mark once the saved word count is above zero", () => {
    expect(isChapterNotStarted({ ...planned, wordCount: 1 })).toBe(false);
    expect(isChapterNotStarted({ ...planned, wordCount: 4 })).toBe(false);
  });

  it("does not use this mark when the synopsis is blank", () => {
    for (const synopsis of ["", "   ", "\n\n", "\t  \n", "\u3000", " \u00a0 "]) {
      expect(isChapterNotStarted({ ...planned, synopsis })).toBe(false);
    }
  });

  it("does not mark idea or done chapters", () => {
    expect(isChapterNotStarted({ ...planned, writingStatus: "idea" })).toBe(false);
    expect(isChapterNotStarted({ ...planned, writingStatus: "done" })).toBe(false);
  });

  it("keeps the visible label as 还没动笔", () => {
    expect(zhCN.writing.chapterPlan.notStarted).toBe("还没动笔");
  });
});

describe("saved word count treats an empty manuscript as zero", () => {
  it("counts empty html, empty paragraphs, and whitespace-only prose as 0", () => {
    const blanks = [
      "",
      "   ",
      "\n\n",
      "\t",
      "\u00a0",
      "\u3000",
      "<p></p>",
      "<p></p><p></p>",
      "<p><br></p>",
      "<p>   </p>",
      "<p> </p><p>\n</p>",
      "<p>\u3000</p><p> </p>",
    ];

    for (const sample of blanks) {
      const stored = sample.includes("<") ? htmlToNewlines(sample) : sample;
      expect(wordsCount(stored), JSON.stringify(sample)).toBe(0);
      expect(
        isChapterNotStarted({
          ...planned,
          wordCount: wordsCount(stored),
        }),
      ).toBe(true);
    }
  });

  it("counts a saved sentence as already started", () => {
    const wordCount = wordsCount(htmlToNewlines("<p>他推开门。</p>"));
    expect(wordCount).toBeGreaterThan(0);
    expect(isChapterNotStarted({ ...planned, wordCount })).toBe(false);
  });
});
