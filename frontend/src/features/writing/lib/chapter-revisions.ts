/**
 * Chapter Revisions（章节历史版本时间线）
 *
 * 纯函数层：把后端返回的 Agent/手动修订混合变更条目整理成展示用时间线，
 * 与取数、节点/编辑器逻辑分离（组件层只做轻渲染断言，参照
 * sidebar-not-started.test.ts 的既有测试模式）。
 */

export type RevisionTypeLabelKey =
  | "writing.chapterHistory.typeAgent"
  | "writing.chapterHistory.typeManual"
  | "writing.chapterHistory.typeRollback"
  | "writing.chapterHistory.typeUnknown";

const REVISION_TYPE_LABEL_KEYS: Record<string, RevisionTypeLabelKey> = {
  agent: "writing.chapterHistory.typeAgent",
  manual: "writing.chapterHistory.typeManual",
  rollback: "writing.chapterHistory.typeRollback",
};

/** 版本类型的展示文案 key；未知类型兜底展示原文 */
export function revisionTypeLabelKey(revisionType: string): RevisionTypeLabelKey {
  return REVISION_TYPE_LABEL_KEYS[revisionType] ?? "writing.chapterHistory.typeUnknown";
}

/**
 * 合并 Agent 与手动修订的变更条目并按变更时间倒序整理。
 * - 时间相同（或无法解析）时保持后端既有次序，保证排序纯函数可稳定断言；
 * - 按 commitId 去重（保留先出现的条目），分页拼接的重叠条目不会重复展示。
 */
export function buildRevisionTimeline<T extends { commitId: string; createdAt: string }>(
  items: readonly T[],
): T[] {
  const timeOf = (item: T): number => {
    const parsed = Date.parse(item.createdAt);
    return Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
  };

  // 按 commitId 去重（保留先出现的条目），分页拼接的重叠条目不会重复展示
  const seen = new Set<string>();
  const unique = items.filter((item) => {
    if (item.commitId.length === 0 || seen.has(item.commitId)) return false;
    seen.add(item.commitId);
    return true;
  });

  return unique
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const diff = timeOf(b.item) - timeOf(a.item);
      // 稳定排序：时间相同按原次序
      return diff !== 0 ? diff : a.index - b.index;
    })
    .map(({ item }) => item);
}

/** 是否可恢复：仅当该条目携带历史快照（create 型首条没有快照） */
export function isRestorableRevision(item: { hasSnapshot: boolean }): boolean {
  return item.hasSnapshot;
}
