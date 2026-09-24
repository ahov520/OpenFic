/**
 * 从空章、情节线空章或空标签离开后，回到刚才那一章。
 *
 * 上次真正写过的章节仍放在 IndexedDB 的 projectLastChapters。
 * 这里只决定何时读它、以及会话内这一步该回到哪一章。
 * 没有多级历史栈：再跳一次，就只记住刚离开的那一章。
 */

export interface ReturnChapter {
  id: string;
  title: string;
}

export interface WritingTabSnapshot {
  id: string;
  type: "chapter" | "note";
  refId: string | null;
}

export type WritingOpenDecision =
  | { action: "keep" }
  | { action: "restore"; chapterId: string }
  | { action: "stay-empty" };

const EMPTY_TAB_PREFIX = "__empty__";
const CHAPTER_TAB_PREFIX = "chapter:";
const NOTE_TAB_PREFIX = "note:";

/**
 * 现有保存把标签 id 写进了 chapterId：章节是 `chapter:<uuid>`，
 * 空标签是 `__empty__…`，笔记是 `note:<uuid>`。只认还能对上的章节。
 */
export function chapterIdFromStoredLastChapter(stored: string | null | undefined): string | null {
  if (typeof stored !== "string") return null;
  const value = stored.trim();
  if (!value) return null;
  if (value.startsWith(EMPTY_TAB_PREFIX) || value.startsWith(NOTE_TAB_PREFIX)) return null;
  if (value.startsWith(CHAPTER_TAB_PREFIX)) {
    const chapterId = value.slice(CHAPTER_TAB_PREFIX.length);
    return chapterId.length > 0 ? chapterId : null;
  }
  return value;
}

function isRealDocumentTab(tab: WritingTabSnapshot | null): boolean {
  return tab != null && tab.refId != null && !tab.id.startsWith(EMPTY_TAB_PREFIX);
}

/**
 * 打开写作页：
 * 当前标签已是章节或笔记则留下；
 * 没有有效章标签（空标签、创建新文件、一个标签都没有）且最近章节还在，就打开它；
 * 没有最近章节则保持空状态。
 */
export function decideWritingOpen(input: {
  tabs: readonly WritingTabSnapshot[];
  activeTabId: string | null;
  storedLastChapterId: string | null;
  chapterIds: readonly string[];
}): WritingOpenDecision {
  const active = input.tabs.find((tab) => tab.id === input.activeTabId) ?? null;
  if (isRealDocumentTab(active)) return { action: "keep" };

  const chapterId = chapterIdFromStoredLastChapter(input.storedLastChapterId);
  if (chapterId != null && input.chapterIds.includes(chapterId)) {
    return { action: "restore", chapterId };
  }
  return { action: "stay-empty" };
}

/**
 * 当前章变了就记下刚离开的那一章。回到它之后清掉，避免变成来回两级。
 * 同一章只是改了标题时，保持原来的返回目标。
 */
export function nextReturnTarget(
  previousChapter: ReturnChapter | null,
  currentChapter: ReturnChapter | null,
  existing: ReturnChapter | null,
): ReturnChapter | null {
  if (currentChapter && existing && currentChapter.id === existing.id) return null;
  if (previousChapter && currentChapter && previousChapter.id === currentChapter.id) {
    return existing;
  }
  if (previousChapter && (!currentChapter || previousChapter.id !== currentChapter.id)) {
    return previousChapter;
  }
  return existing;
}

/** 出发章还在项目里、并且现在没停在它上面时，才显示返回。 */
export function returnChapterToShow(
  target: ReturnChapter | null,
  currentChapterId: string | null,
  chapters: readonly ReturnChapter[],
): ReturnChapter | null {
  if (!target || target.id === currentChapterId) return null;
  const chapter = chapters.find((item) => item.id === target.id);
  if (!chapter) return null;
  return { id: chapter.id, title: chapter.title };
}
