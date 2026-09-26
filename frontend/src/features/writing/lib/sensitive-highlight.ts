/**
 * 敏感词命中高亮 Extension。
 *
 * 沿 margin-note-highlight.ts 的既有模式：命中列表经命令进入 Plugin 状态，
 * decorations 由外部状态派生（Decoration.inline，不进入文档，因此不进
 * 正文、字数或导出）；文档变化后清空，由面板防抖重扫刷新。
 * 「命中列表 → Decoration.inline」为薄映射，映射函数可脱离编辑器测试。
 *
 * 替换复用 search-and-replace.ts replaceAllMatches 的单事务多替换路径：
 * 按当前文档重扫定位后，倒序 insertText 到同一笔事务，Ctrl+Z 一步撤销。
 */

import { Extension, type Range } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { Editor } from "@tiptap/react";

import { editorPlainText, rangeForPlainSlice } from "./margin-note-highlight";
import {
  scanSensitiveWords,
  type SensitiveScanOptions,
  type SensitiveWordHit,
  type SensitiveWordEntry,
} from "./sensitive-words";

const sensitiveHighlightKey = new PluginKey<SensitiveWordHit[]>("sensitiveHighlight");

export const SENSITIVE_MARK_CLASS = "sensitive-word-mark";

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    sensitiveHighlight: {
      /** 设置敏感词命中列表（触发内联高亮；传空数组清除） */
      setSensitiveHits: (hits: SensitiveWordHit[]) => ReturnType;
    };
  }
}

/**
 * 「命中列表 → Decoration.inline」薄映射：
 * 把纯文本偏移经 rangeForPlainSlice 映射回文档位置，
 * 并与原文比对兜底（对不上就不高亮）。
 */
export function buildSensitiveDecorations(
  doc: PMNode,
  hits: readonly SensitiveWordHit[],
): Decoration[] {
  const plain = doc.textBetween(0, doc.content.size, "\n", "\n");
  const decorations: Decoration[] = [];

  for (const hit of hits) {
    for (const position of hit.positions) {
      const range = mapPlainRange(doc, plain, position.start, position.end, hit.word);
      if (!range) continue;
      decorations.push(
        Decoration.inline(range.from, range.to, {
          class: SENSITIVE_MARK_CLASS,
          "data-sensitive-word": hit.word,
        }),
      );
    }
  }
  decorations.sort((left, right) => left.from - right.from || left.to - right.to);
  return decorations;
}

export function mapPlainRange(
  doc: PMNode,
  plain: string,
  start: number,
  end: number,
  word: string,
): Range | null {
  const expected = plain.slice(start, end);
  if (expected !== word) return null;
  const range = rangeForPlainSlice(doc, start, end);
  if (!range) return null;
  if (doc.textBetween(range.from, range.to, "\n", "\n") !== word) return null;
  return range;
}

export const SensitiveHighlight = Extension.create({
  name: "sensitiveHighlight",

  addCommands() {
    return {
      setSensitiveHits:
        (hits) =>
        ({ tr, dispatch }) => {
          if (dispatch) {
            tr.setMeta(sensitiveHighlightKey, hits);
            tr.setMeta("addToHistory", false);
          }
          return true;
        },
    };
  },

  addProseMirrorPlugins() {
    return [
      new Plugin<SensitiveWordHit[]>({
        key: sensitiveHighlightKey,
        state: {
          init: (): SensitiveWordHit[] => [],
          apply(tr, value): SensitiveWordHit[] {
            const meta: unknown = tr.getMeta(sensitiveHighlightKey);
            if (meta !== undefined) return meta as SensitiveWordHit[];
            // 文档变化后命中位置失效，清空交给面板防抖重扫
            if (tr.docChanged) return [];
            return value;
          },
        },
        props: {
          decorations(state) {
            const hits = sensitiveHighlightKey.getState(state) ?? [];
            if (hits.length === 0) return DecorationSet.empty;
            const decorations = buildSensitiveDecorations(state.doc, hits);
            if (decorations.length === 0) return DecorationSet.empty;
            return DecorationSet.create(state.doc, decorations);
          },
        },
      }),
    ];
  },
});

/**
 * 一键替换：按同一扫描口径在当前文档重扫定位该词的全部命中，
 * 倒序 insertText 进同一笔事务（复用 search-and-replace replaceAllMatches
 * 的单事务多替换路径），返回替换次数；无命中时不派发事务。
 */
export function replaceSensitiveWord(
  editor: Editor,
  hit: SensitiveWordHit,
  replacement: string,
  options: SensitiveScanOptions = {},
): number {
  const entries: SensitiveWordEntry[] = [{ word: hit.word, source: hit.source }];
  const fresh = scanSensitiveWords(editorPlainText(editor), entries, options);
  const ranges: Range[] = [];
  const plain = editorPlainText(editor);
  for (const position of fresh.hits[0]?.positions ?? []) {
    const range = mapPlainRange(editor.state.doc, plain, position.start, position.end, hit.word);
    if (range) ranges.push(range);
  }
  if (ranges.length === 0) return 0;

  const { tr } = editor.state;
  for (const range of [...ranges].sort((left, right) => right.from - left.from)) {
    tr.insertText(replacement, range.from, range.to);
  }
  editor.view.dispatch(tr);
  return ranges.length;
}
