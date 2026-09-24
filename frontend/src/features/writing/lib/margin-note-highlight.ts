/**
 * 旁注在句上的阅读标记，以及点侧栏时的短暂高亮。
 * 两者都是 ProseMirror decoration，不进入文档，因此不会进正文、字数或导出。
 */

import { Extension, type Range } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { Editor } from "@tiptap/react";

import {
  MARGIN_CONTEXT_MAX,
  locateAnchor,
  marginMarkClass,
  marginMarkKind,
  type MarginNoteStatus,
} from "@/lib/margin-note";

const marginNoteHighlightKey = new PluginKey<Range | null>("marginNoteHighlight");
const marginNoteMarksKey = new PluginKey<MarginMarkNote[]>("marginNoteMarks");

export const MARGIN_NOTE_OPEN_EVENT = "openfic-margin-note";

export interface MarginMarkNote {
  id: string;
  anchorText: string;
  contextBefore: string;
  contextAfter: string;
  status: MarginNoteStatus;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    marginNoteHighlight: {
      setMarginNoteHighlight: (range: Range | null) => ReturnType;
      setMarginNoteMarks: (notes: MarginMarkNote[]) => ReturnType;
    };
  }
}

function plainText(doc: PMNode): string {
  return doc.textBetween(0, doc.content.size, "\n", "\n");
}

export function readMarginNoteOpenId(event: Event): string | null {
  if (!(event instanceof CustomEvent)) return null;
  const detail: unknown = event.detail;
  if (typeof detail !== "object" || detail === null || !("noteId" in detail)) return null;
  const noteId = (detail as { noteId: unknown }).noteId;
  return typeof noteId === "string" && noteId.length > 0 ? noteId : null;
}

function inlineDecorations(doc: PMNode, range: Range, attrs: Record<string, string>): Decoration[] {
  const decorations: Decoration[] = [];
  doc.nodesBetween(range.from, range.to, (node, pos) => {
    if (!node.isText) return;
    const start = Math.max(range.from, pos);
    const end = Math.min(range.to, pos + node.nodeSize);
    if (start < end) decorations.push(Decoration.inline(start, end, attrs));
  });
  return decorations;
}

export const MarginNoteHighlight = Extension.create({
  name: "marginNoteHighlight",

  addCommands() {
    return {
      setMarginNoteHighlight:
        (range) =>
        ({ tr, dispatch }) => {
          if (dispatch) {
            tr.setMeta(marginNoteHighlightKey, range);
            tr.setMeta("addToHistory", false);
          }
          return true;
        },
      setMarginNoteMarks:
        (notes) =>
        ({ tr, dispatch }) => {
          if (dispatch) {
            tr.setMeta(marginNoteMarksKey, notes);
            tr.setMeta("addToHistory", false);
          }
          return true;
        },
    };
  },

  addProseMirrorPlugins() {
    return [
      new Plugin<Range | null>({
        key: marginNoteHighlightKey,
        state: {
          init: (): Range | null => null,
          apply(tr, value): Range | null {
            const meta: unknown = tr.getMeta(marginNoteHighlightKey);
            if (meta !== undefined) return meta as Range | null;
            if (tr.docChanged) return null;
            return value;
          },
        },
        props: {
          decorations(state) {
            const range = marginNoteHighlightKey.getState(state);
            if (!range || range.from >= range.to || range.to > state.doc.content.size) {
              return DecorationSet.empty;
            }
            const decorations = inlineDecorations(state.doc, range, {
              class: "margin-note-anchor",
            });
            if (decorations.length === 0) return DecorationSet.empty;
            return DecorationSet.create(state.doc, decorations);
          },
        },
      }),
      new Plugin<MarginMarkNote[]>({
        key: marginNoteMarksKey,
        state: {
          init: (): MarginMarkNote[] => [],
          apply(tr, value): MarginMarkNote[] {
            const meta: unknown = tr.getMeta(marginNoteMarksKey);
            if (meta !== undefined) return meta as MarginMarkNote[];
            return value;
          },
        },
        props: {
          decorations(state) {
            const notes = marginNoteMarksKey.getState(state) ?? [];
            if (notes.length === 0) return DecorationSet.empty;
            const plain = plainText(state.doc);
            const decorations: Decoration[] = [];
            for (const note of notes) {
              const range = rangeForAnchor(
                state.doc,
                plain,
                note.anchorText,
                note.contextBefore,
                note.contextAfter,
              );
              if (!range) continue;
              const kind = marginMarkKind(note.status, true);
              if (!kind) continue;
              decorations.push(
                ...inlineDecorations(state.doc, range, {
                  class: marginMarkClass(kind),
                  "data-margin-note-id": note.id,
                  "data-margin-mark": kind,
                }),
              );
            }
            if (decorations.length === 0) return DecorationSet.empty;
            decorations.sort((left, right) => left.from - right.from || left.to - right.to);
            return DecorationSet.create(state.doc, decorations);
          },
          handleClick(view, pos) {
            const notes = marginNoteMarksKey.getState(view.state) ?? [];
            if (notes.length === 0) return false;
            const plain = plainText(view.state.doc);
            let match: MarginMarkNote | null = null;
            for (const note of notes) {
              const range = rangeForAnchor(
                view.state.doc,
                plain,
                note.anchorText,
                note.contextBefore,
                note.contextAfter,
              );
              if (!range || pos < range.from || pos > range.to) continue;
              if (!match || (match.status === "struck" && note.status !== "struck")) match = note;
            }
            if (!match) return false;
            view.dom.dispatchEvent(
              new CustomEvent(MARGIN_NOTE_OPEN_EVENT, {
                bubbles: true,
                detail: { noteId: match.id },
              }),
            );
            return false;
          },
        },
      }),
    ];
  },
});

export interface MarginSelection {
  anchorText: string;
  contextBefore: string;
  contextAfter: string;
}

export function readMarginSelection(editor: Editor): MarginSelection | null {
  const { from, to } = editor.state.selection;
  if (from === to) return null;
  const anchorText = editor.state.doc.textBetween(from, to, "\n", "\n");
  if (!anchorText.trim()) return null;
  const beforeText = editor.state.doc.textBetween(0, from, "\n", "\n");
  const afterText = editor.state.doc.textBetween(to, editor.state.doc.content.size, "\n", "\n");
  return {
    anchorText,
    contextBefore: beforeText.slice(-MARGIN_CONTEXT_MAX),
    contextAfter: afterText.slice(0, MARGIN_CONTEXT_MAX),
  };
}

/**
 * 把 textBetween(..., "\\n") 的纯文本偏移映回文档位置。
 * 段落之间的换行和 ProseMirror 的 textBetween 一致，空段也算一个换行。
 * 映射结果还要再和原句比对，对不上就不高亮。
 */
export function rangeForPlainSlice(doc: PMNode, start: number, end: number): Range | null {
  if (end <= start) return null;
  let plain = 0;
  let firstBlock = true;
  let from: number | null = null;
  let to: number | null = null;

  doc.nodesBetween(0, doc.content.size, (node, pos) => {
    if (to !== null) return false;
    if (node.isTextblock) {
      if (firstBlock) firstBlock = false;
      else plain += 1;
    }
    if (!node.isText) return true;
    const text = node.text ?? "";
    const textStart = plain;
    const textEnd = plain + text.length;
    if (from === null && start >= textStart && start < textEnd) {
      from = pos + (start - textStart);
    }
    if (from !== null && end <= textEnd && end > textStart) {
      to = pos + (end - textStart);
    }
    plain = textEnd;
    return false;
  });

  if (from === null || to === null) return null;
  return { from, to };
}

export function rangeForAnchor(
  doc: PMNode,
  plain: string,
  anchor: string,
  before: string,
  after: string,
): Range | null {
  const hit = locateAnchor(plain, anchor, before, after);
  if (!hit.aligned || hit.start == null || hit.end == null) return null;
  const range = rangeForPlainSlice(doc, hit.start, hit.end);
  if (!range) return null;
  if (doc.textBetween(range.from, range.to, "\n", "\n") !== anchor) return null;
  return range;
}

export function editorPlainText(editor: Editor): string {
  return plainText(editor.state.doc);
}
