import type { VolumeTreeResponse } from "@/lib/chapter.types";

/**
 * 把编辑器刚保存的字数目标写进侧栏用的章节树。
 * 只改目标和更新时间，不动字数、顺序和正文。
 */
export function applyWordCountTargetToVolumeTree(
  tree: VolumeTreeResponse,
  update: { id: string; wordCountTarget: number | null; updatedAt: string },
): VolumeTreeResponse {
  let changed = false;
  const volumes = tree.volumes.map((volume) => {
    let chapterChanged = false;
    const chapters = volume.chapters.map((chapter) => {
      if (chapter.id !== update.id) return chapter;
      if (
        chapter.wordCountTarget === update.wordCountTarget &&
        chapter.updatedAt === update.updatedAt
      ) {
        return chapter;
      }
      chapterChanged = true;
      changed = true;
      return {
        ...chapter,
        wordCountTarget: update.wordCountTarget,
        updatedAt: update.updatedAt,
      };
    });
    if (!chapterChanged) return volume;
    return { ...volume, chapters };
  });
  if (!changed) return tree;
  return { ...tree, volumes };
}
