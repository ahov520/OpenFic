/**
 * Prose Format Cleanup（「一键排版」编辑器集成层）
 *
 * 纯文本变换逻辑在 ./prose-format-cleanup，这里只负责节点遍历与事务组装：
 * - 按节点类型分流：仅变换段落（paragraph）文本，codeBlock 等非段落节点整块跳过；
 * - 章节编辑器没有代码块节点，粘贴的 ``` 围栏会经 createPlainTextPasteContent
 *   变成普通段落，因此这里跨顶层节点维护与纯文本层同一口径的围栏状态机：
 *   围栏行段落与其后直到配对围栏行的段落（含围栏内空段落）整段映射为受保护的
 *   code，不参与缩进/标点/空行清理；
 * - 空段落（空行）按段间压缩规则整节点删除，与纯函数层共用同一套空行去留计划；
 * - 只遍历实际有改动的段落，全部 replace/delete 放进同一笔 ProseMirror 事务、
 *   从文档末尾向前应用避免位置漂移；配合 History 扩展（editor-config.ts）实现
 *   Ctrl+Z 一步整体撤销；
 * - 没有实际改动时不派发事务。
 */

import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import type { EditorState, Transaction } from "@tiptap/pm/state";
import type { Editor } from "@tiptap/react";

import {
  cleanupProseLine,
  isChapterMarkerLine,
  isCodeFenceLine,
  planParagraphGapCompaction,
  type ProseFormatCleanupRules,
  type ProseFormatLineKind,
} from "./prose-format-cleanup";

interface ProseFormatNodeEntry {
  kind: ProseFormatLineKind;
  /** 节点起始位置（含开标签） */
  from: number;
  /** 节点结束位置（含闭标签） */
  to: number;
  text: string;
}

interface ProseFormatCleanupOp {
  from: number;
  to: number;
  /** null 表示删除整个空段落节点 */
  text: string | null;
}

/**
 * 顶层节点 → 排版角色。非段落节点（codeBlock 等）一律映射为受保护的 `code`：
 * 文本不变换，但在段间压缩里视作内容参与前后相邻判断。
 */
function classifyProseNode(node: ProseMirrorNode): ProseFormatLineKind {
  if (node.type.name !== "paragraph") return "code";
  if (!node.textContent.trim()) return "blank";
  return isChapterMarkerLine(node.textContent) ? "marker" : "content";
}

function collectProseNodeEntries(doc: ProseMirrorNode): ProseFormatNodeEntry[] {
  const entries: ProseFormatNodeEntry[] = [];
  doc.forEach((node, offset) => {
    entries.push({
      kind: classifyProseNode(node),
      from: offset,
      to: offset + node.nodeSize,
      text: node.textContent,
    });
  });
  return entries;
}

/**
 * ``` 围栏状态机：围栏行段落翻转状态，围栏内段落（含空段落）整段标记为受保护的
 * code。粘贴产生的围栏在纯文本编辑器里只是普通段落，必须在这里兜住，才能兑现
 * 「代码块内容不动」。codeBlock 等非段落节点自包含、已是 code，不参与围栏翻转。
 */
function applyCodeFenceKinds(entries: ProseFormatNodeEntry[]): void {
  let inCodeFence = false;
  for (const entry of entries) {
    if (entry.kind === "code") continue;
    if (isCodeFenceLine(entry.text)) {
      inCodeFence = !inCodeFence;
      entry.kind = "code";
      continue;
    }
    if (inCodeFence) entry.kind = "code";
  }
}

/**
 * 组装「一键排版」事务；没有需要改动的内容时返回 null（调用方不派发事务）。
 * 所有改动都在同一笔事务内，撤销时一步整体还原。
 */
export function buildProseFormatCleanupTransaction(
  state: EditorState,
  rules: ProseFormatCleanupRules,
): Transaction | null {
  const entries = collectProseNodeEntries(state.doc);
  if (!entries.length) return null;

  applyCodeFenceKinds(entries);

  const kinds = entries.map((entry) => entry.kind);
  const removeBlanks = planParagraphGapCompaction(kinds, rules.compactParagraphGaps);
  // 全文档都是空段落时不删节点，避免把文档清空到违反 schema（block+）
  const hasContent = entries.some((entry) => entry.kind !== "blank");

  const ops: ProseFormatCleanupOp[] = [];
  entries.forEach((entry, index) => {
    if (entry.kind === "blank") {
      if (hasContent && removeBlanks[index]) {
        ops.push({ from: entry.from, to: entry.to, text: null });
      }
      return;
    }
    // codeBlock 等非段落节点整块跳过
    if (entry.kind === "code") return;

    const cleaned = cleanupProseLine(entry.text, rules);
    if (cleaned === entry.text) return;
    // 段落内文本范围 = 节点范围去掉开/闭标签各一位
    ops.push({ from: entry.from + 1, to: entry.to - 1, text: cleaned });
  });

  if (!ops.length) return null;

  const { tr } = state;
  for (const op of [...ops].sort((a, b) => b.from - a.from)) {
    if (op.text === null || op.text === "") {
      tr.delete(op.from, op.to);
    } else {
      tr.replaceWith(op.from, op.to, state.schema.text(op.text));
    }
  }
  return tr;
}

/** 对编辑器执行「一键排版」：单笔事务派发，返回是否发生了改动 */
export function applyProseFormatCleanup(editor: Editor, rules: ProseFormatCleanupRules): boolean {
  const transaction = buildProseFormatCleanupTransaction(editor.state, rules);
  if (!transaction) return false;

  editor.view.dispatch(transaction);
  return true;
}
