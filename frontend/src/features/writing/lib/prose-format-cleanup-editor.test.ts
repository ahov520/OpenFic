import { history, undo } from "@tiptap/pm/history";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import { Schema } from "@tiptap/pm/model";
import type { Transaction } from "@tiptap/pm/state";
import { EditorState } from "@tiptap/pm/state";
import { describe, expect, it } from "vitest";

import {
  DEFAULT_PROSE_FORMAT_CLEANUP_RULES,
  type ProseFormatCleanupRules,
} from "./prose-format-cleanup";
import { buildProseFormatCleanupTransaction } from "./prose-format-cleanup-editor";

const ALL_ON = DEFAULT_PROSE_FORMAT_CLEANUP_RULES;

function withRules(overrides: Partial<ProseFormatCleanupRules>): ProseFormatCleanupRules {
  return { ...ALL_ON, ...overrides };
}

// 与章节编辑器同构的最小 schema：doc > paragraph | codeBlock，纯文本无 mark
const testSchema = new Schema({
  nodes: {
    doc: { content: "block+" },
    paragraph: { group: "block", content: "text*" },
    codeBlock: { group: "block", content: "text*", code: true },
    text: { inline: true },
  },
});

function paragraph(text: string) {
  const content = text ? testSchema.text(text) : null;
  return testSchema.nodes.paragraph.create(null, content);
}

function codeBlock(text: string) {
  return testSchema.nodes.codeBlock.create(null, testSchema.text(text));
}

function createState(...blocks: ProseMirrorNode[]) {
  return EditorState.create({
    doc: testSchema.nodes.doc.create(null, blocks),
    plugins: [history()],
  });
}

function docLines(state: EditorState): string[] {
  const lines: string[] = [];
  state.doc.forEach((node) => lines.push(node.textContent));
  return lines;
}

function applyCleanup(state: EditorState, rules: ProseFormatCleanupRules) {
  const transaction = buildProseFormatCleanupTransaction(state, rules);
  return transaction ? state.apply(transaction) : null;
}

describe("buildProseFormatCleanupTransaction", () => {
  it("在同一笔事务内逐段变换段落文本（缩进/行尾空白/标点）", () => {
    const state = createState(paragraph("　　你好,世界. "), paragraph("OK"), paragraph("再见?"));
    const next = applyCleanup(state, ALL_ON);
    expect(next).not.toBeNull();
    expect(docLines(next as EditorState)).toEqual(["你好，世界。", "OK", "再见？"]);
  });

  it("空段落（空行）整节点删除，段落间不留空行（yaml:140/219）", () => {
    const state = createState(
      paragraph("第一段"),
      paragraph(""),
      paragraph("  "),
      paragraph("第二段"),
    );
    const next = applyCleanup(state, ALL_ON);
    expect(next).not.toBeNull();
    expect(docLines(next as EditorState)).toEqual(["第一段", "第二段"]);
  });

  it("章节标记相邻的空行最多保留一个（yaml:219 另算）", () => {
    const state = createState(
      paragraph("###1."),
      paragraph(""),
      paragraph(""),
      paragraph("第一段"),
      paragraph(""),
      paragraph("第二段"),
    );
    const next = applyCleanup(state, ALL_ON);
    expect(docLines(next as EditorState)).toEqual(["###1.", "", "第一段", "第二段"]);
  });

  it("按节点类型跳过 codeBlock 等非段落节点，仅变换段落文本", () => {
    const state = createState(
      paragraph("你好,世界"),
      codeBlock("  keep,  this: 1\n  indented ?"),
      paragraph("再见,世界"),
    );
    const next = applyCleanup(state, ALL_ON);
    expect(docLines(next as EditorState)).toEqual([
      "你好，世界",
      "  keep,  this: 1\n  indented ?",
      "再见，世界",
    ]);
  });

  it("粘贴的 ``` 围栏段落序列整段受保护：缩进、标点、围栏内空段落都不动", () => {
    const state = createState(
      paragraph("前文,你好:"),
      paragraph("```text"),
      paragraph("  print,  hi: 1"),
      paragraph(""),
      paragraph("```"),
      paragraph("后文,你好?"),
    );
    const next = applyCleanup(state, ALL_ON);
    expect(docLines(next as EditorState)).toEqual([
      "前文，你好：",
      "```text",
      "  print,  hi: 1",
      "",
      "```",
      "后文，你好？",
    ]);
  });

  it("未闭合围栏之后的段落全部受保护，围栏前的空行仍按规则压缩", () => {
    const state = createState(
      paragraph("前文,你好:"),
      paragraph(""),
      paragraph("```python"),
      paragraph("  x, y = 1, 2"),
      paragraph("这段,也不动?"),
    );
    const next = applyCleanup(state, ALL_ON);
    expect(docLines(next as EditorState)).toEqual([
      "前文，你好：",
      "```python",
      "  x, y = 1, 2",
      "这段,也不动?",
    ]);
  });

  it("没有实际改动时返回 null（不派发事务）", () => {
    const state = createState(paragraph("你好，世界。"), paragraph("###1."));
    expect(buildProseFormatCleanupTransaction(state, ALL_ON)).toBeNull();
  });

  it("整章只有空段落时返回 null，不把文档清空", () => {
    const state = createState(paragraph(""), paragraph("  "));
    expect(buildProseFormatCleanupTransaction(state, ALL_ON)).toBeNull();
  });

  it("关闭段间压缩时保留空段落，文本变换仍然生效", () => {
    const state = createState(paragraph("你好,世界"), paragraph(""), paragraph("第二段"));
    const next = applyCleanup(state, withRules({ compactParagraphGaps: false }));
    expect(docLines(next as EditorState)).toEqual(["你好，世界", "", "第二段"]);
  });

  it("全部改动走一笔事务，配合 History 一步撤销还原整章", () => {
    const state = createState(
      paragraph("　　###1."),
      paragraph(""),
      paragraph(""),
      paragraph("　　她说,你好. "),
      paragraph("Keep"),
      codeBlock("x, y"),
    );
    const next = applyCleanup(state, ALL_ON);
    expect(next).not.toBeNull();

    // 一步撤销后整章（含被删的空段落、变换过的段落）完全还原
    let undoTransaction: Transaction | undefined;
    const undoSucceeded = undo(next as EditorState, (tr) => {
      undoTransaction = tr;
    });
    expect(undoSucceeded).toBe(true);
    expect(undoTransaction).toBeDefined();
    const undone = (next as EditorState).apply(undoTransaction as Transaction);
    expect(undone.doc.toJSON()).toEqual(state.doc.toJSON());
  });
});
