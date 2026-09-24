/**
 * 旁注锚在选中的原文上。定位规则与后端 locate_anchor 一致。
 */

export const MARGIN_ANCHOR_MAX = 1000;
export const MARGIN_BODY_MAX = 800;
export const MARGIN_CONTEXT_MAX = 40;

export type MarginNoteStatus = "open" | "struck";
export type MarginAlignment = "aligned" | "misaligned";

export interface MarginNote {
  id: string;
  chapterId: string;
  anchorText: string;
  contextBefore: string;
  contextAfter: string;
  body: string;
  status: MarginNoteStatus;
  alignment: MarginAlignment;
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
