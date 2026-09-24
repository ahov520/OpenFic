/**
 * 把旁注暂时高亮在编辑器里。高亮不是正文标记，文档一改就清掉。
 */

import { Extension, type Range } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { Editor } from "@tiptap/react";

import { MARGIN_CONTEXT_MAX } from "@/lib/margin-note";

const marginNoteHighlightKey = new PluginKey<Range | null>("marginNoteHighlight");

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    marginNoteHighlight: {
      setMarginNoteHighlight: (range: Range | null) => ReturnType;
    };
  }
}

export const MarginNoteHighlight = Extension.create({
  name: "marginNoteHighlight",

  addCommands() {
    return {
      setMarginNoteHighlight:
        (range) =>
        ({ tr, dispatch }) => {
          if (dispatch) tr.setMeta(marginNoteHighlightKey, range);
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
            const decorations: Decoration[] = [];
            state.doc.nodesBetween(range.from, range.to, (node, pos) => {
              if (!node.isText) return;
              const start = Math.max(range.from, pos);
              const end = Math.min(range.to, pos + node.nodeSize);
              if (start < end) {
                decorations.push(Decoration.inline(start, end, { class: "margin-note-anchor" }));
              }
            });
            if (decorations.length === 0) return DecorationSet.empty;
            return DecorationSet.create(state.doc, decorations);
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

export function editorPlainText(editor: Editor): string {
  return editor.state.doc.textBetween(0, editor.state.doc.content.size, "\n", "\n");
}
