import type { WritingStatus } from "@/lib/chapter-plan";

/**
 * 软木板上的「还没动笔」。
 * 梗概去掉空白后还有内容，且已保存字数是 0，才算这一章可以开工。
 * 字数用章节列表上的 word_count，不在这里重算正文。
 * 只标草稿和修订。构思、完成，以及空梗概，都不标。
 */
export function isChapterNotStarted(input: {
  synopsis: string;
  writingStatus: WritingStatus;
  wordCount: number;
}): boolean {
  if (input.writingStatus !== "drafting" && input.writingStatus !== "revising") {
    return false;
  }
  if (input.synopsis.trim().length === 0) {
    return false;
  }
  return input.wordCount === 0;
}
