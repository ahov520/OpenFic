import type { WritingStatus } from "@/lib/chapter-plan";
import type { VolumeTreeResponse } from "@/lib/chapter.types";

/**
 * 有梗概、正文还是空的，才是可以开工的章。
 * 侧栏只在同时满足时标「还没动笔」：写作状态是草稿或修订，梗概去掉首尾空白后还有内容，已保存字数是 0。
 * 构思和完成不标。梗概为空白（含纯空格、换行）不标。
 * 只读列表上已经保存的字段，不重算正文，也不改字数统计。
 */
export function showsNotStartedMark(chapter: {
  synopsis: string;
  writingStatus: WritingStatus;
  wordCount: number;
}): boolean {
  if (chapter.writingStatus !== "drafting" && chapter.writingStatus !== "revising") {
    return false;
  }
  if (chapter.synopsis.trim().length === 0) {
    return false;
  }
  return chapter.wordCount === 0;
}

/**
 * 把刚保存的字数写进侧栏章节树，正文一存完标记就能消失。
 * 只替换这一章的 wordCount 和 updatedAt。
 */
export function applySavedWordCountToVolumeTree(
  tree: VolumeTreeResponse,
  update: { id: string; wordCount: number; updatedAt: string },
): VolumeTreeResponse {
  let changed = false;
  const volumes = tree.volumes.map((volume) => {
    let chapterChanged = false;
    const chapters = volume.chapters.map((chapter) => {
      if (chapter.id !== update.id) return chapter;
      if (chapter.wordCount === update.wordCount && chapter.updatedAt === update.updatedAt) {
        return chapter;
      }
      chapterChanged = true;
      changed = true;
      return {
        ...chapter,
        wordCount: update.wordCount,
        updatedAt: update.updatedAt,
      };
    });
    if (!chapterChanged) return volume;
    return { ...volume, chapters };
  });
  if (!changed) return tree;
  return { ...tree, volumes };
}
