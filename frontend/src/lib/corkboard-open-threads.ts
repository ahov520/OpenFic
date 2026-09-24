import type { WritingStatus } from "./chapter-plan.ts";

/**
 * 软木板上还没写完的章，标出这一章埋下、全书还没回收的情节线。
 * Plottr 的线在章节列上能看见卡；这里只标草稿和修订，构思和完成不铺线名。
 * 名单来自情节线总览按章归类的结果，不在前端用章节顺序推断有没有回收。
 */
export const CORKBOARD_OPEN_PLANT_PREVIEW = 3;

const OPEN_PLANT_STATUSES = new Set<WritingStatus>(["drafting", "revising"]);

export function corkboardShowsOpenPlants(status: WritingStatus): boolean {
  return OPEN_PLANT_STATUSES.has(status);
}

/** 只在草稿或修订上取这一章的名单。构思和完成返回空，即使后端仍记着未回收的埋下。 */
export function corkboardOpenPlantNames(
  status: WritingStatus,
  namesByChapter: Readonly<Record<string, readonly string[]>> | undefined,
  chapterId: string,
): string[] {
  if (!corkboardShowsOpenPlants(status)) return [];
  const names = namesByChapter?.[chapterId];
  return names ? [...names] : [];
}

/** 超过 3 条先露出 3 个名字，其余交给「还有 N 条」。展开后全部可见。 */
export function previewOpenPlantNames(
  names: readonly string[],
  expanded: boolean,
): { shown: string[]; hiddenCount: number } {
  if (expanded || names.length <= CORKBOARD_OPEN_PLANT_PREVIEW) {
    return { shown: [...names], hiddenCount: 0 };
  }
  return {
    shown: names.slice(0, CORKBOARD_OPEN_PLANT_PREVIEW),
    hiddenCount: names.length - CORKBOARD_OPEN_PLANT_PREVIEW,
  };
}
