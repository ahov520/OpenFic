/**
 * 旁注锚在选中的原文上。定位规则与后端 locate_anchor 一致。
 */

export const MARGIN_ANCHOR_MAX = 1000;
export const MARGIN_BODY_MAX = 800;
export const MARGIN_CONTEXT_MAX = 40;

export type MarginNoteStatus = "open" | "struck";
export type MarginAlignment = "aligned" | "misaligned";
export type MarginMark = "faint" | "weak";

/** 未划掉、且能对上的句子。只是阅读提示，不进入正文。 */
export const OPEN_MARGIN_MARK_CLASS = "margin-note-mark";
/** 已划掉但仍对得上：保留可点击的痕迹，不用未划掉那一档的底色。 */
export const STRUCK_MARGIN_MARK_CLASS = "margin-note-mark margin-note-mark--struck";

export interface MarginNote {
  id: string;
  chapterId: string;
  anchorText: string;
  contextBefore: string;
  contextAfter: string;
  body: string;
  status: MarginNoteStatus;
  alignment: MarginAlignment;
  mark: MarginMark | null;
  start: number | null;
  end: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface MarginNoteCreate {
  anchorText: string;
  contextBefore: string;
  contextAfter: string;
  body: string;
}

export interface MarginNoteUpdate {
  status?: MarginNoteStatus;
  body?: string;
  anchorText?: string;
  contextBefore?: string;
  contextAfter?: string;
}

/** 与后端 mark_kind 一致。划掉的对得上只给 weak，不用 faint。对不齐不标。 */
export function marginMarkKind(status: MarginNoteStatus, aligned: boolean): MarginMark | null {
  if (!aligned) return null;
  return status === "struck" ? "weak" : "faint";
}

export function marginMarkClass(kind: MarginMark): string {
  return kind === "weak" ? STRUCK_MARGIN_MARK_CLASS : OPEN_MARGIN_MARK_CLASS;
}

export interface OpenMarginNote {
  id: string;
  chapterId: string;
  chapterTitle: string;
  anchorText: string;
  body: string;
  createdAt: string;
}

export interface AnchorHit {
  aligned: boolean;
  start: number | null;
  end: number | null;
}

function contextMatches(
  content: string,
  anchor: string,
  before: string,
  after: string,
  index: number,
): boolean {
  if (before) {
    const actualBefore = content.slice(Math.max(0, index - before.length), index);
    if (actualBefore !== before) return false;
  }
  if (after) {
    const actualAfter = content.slice(index + anchor.length, index + anchor.length + after.length);
    if (actualAfter !== after) return false;
  }
  return true;
}

export function locateAnchor(content: string, anchor: string, before = "", after = ""): AnchorHit {
  if (!anchor) return { aligned: false, start: null, end: null };

  const starts: number[] = [];
  let searchFrom = 0;
  while (searchFrom <= content.length) {
    const found = content.indexOf(anchor, searchFrom);
    if (found < 0) break;
    starts.push(found);
    searchFrom = found + 1;
  }

  if (starts.length === 0) return { aligned: false, start: null, end: null };
  if (starts.length === 1) {
    const start = starts[0];
    return { aligned: true, start, end: start + anchor.length };
  }

  const confident = starts.filter((index) => contextMatches(content, anchor, before, after, index));
  if (confident.length !== 1) return { aligned: false, start: null, end: null };
  const start = confident[0];
  return { aligned: true, start, end: start + anchor.length };
}
