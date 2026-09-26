import { Schema } from "@tiptap/pm/model";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { describe, expect, it, vi } from "vitest";

import {
  buildSensitiveDecorations,
  replaceSensitiveWord,
  SensitiveHighlight,
} from "./sensitive-highlight";
import type { SensitiveWordHit } from "./sensitive-words";

// 与章节编辑器同构的最小 schema（doc > paragraph > text），DOM-free
const testSchema = new Schema({
  nodes: {
    doc: { content: "block+" },
    paragraph: { group: "block", content: "text*" },
    text: { inline: true },
  },
});

function paragraph(text: string) {
  return testSchema.nodes.paragraph.create(null, text ? testSchema.text(text) : null);
}

function makeDoc(lines: string[]) {
  return testSchema.nodes.doc.create(null, lines.map(paragraph));
}

function makeEditorLike(doc) {
  // replaceSensitiveWord 只需要 state.tr/state.doc/view.dispatch 的轻量替身
  const dispatched: unknown[] = [];
  return {
    state: {
      doc,
      get tr() {
        let inserted = 0;
        return {
          insertText: vi.fn((text: string, from: number, to: number) => {
            inserted += 1;
            return undefined;
          }),
          get insertedCount() {
            return inserted;
          },
        };
      },
    },
    view: {
      dispatch: vi.fn((tr: unknown) => dispatched.push(tr)),
    },
  };
}

const HITS: SensitiveWordHit[] = [
  {
    word: "赌博",
    source: "通用类目示例",
    count: 2,
    positions: [
      { start: 0, end: 2 },
      { start: 12, end: 14 },
    ],
  },
];

describe("buildSensitiveDecorations（命中列表 → Decoration.inline 薄映射）", () => {
  it("把纯文本偏移映射为文档内联 decoration", () => {
    // doc: ["赌博开始\n中间\n赌博结束"] → textBetween 以 \n 连接段落
    const doc = makeDoc(["赌博开始", "中间", "赌博结束"]);
    const plain = doc.textBetween(0, doc.content.size, "\n", "\n");
    const hit: SensitiveWordHit = {
      word: "赌博",
      source: "",
      count: 2,
      positions: [
        { start: 0, end: 2 },
        { start: plain.indexOf("赌博", 2), end: plain.indexOf("赌博", 2) + 2 },
      ],
    };

    const decorations = buildSensitiveDecorations(doc, [hit]);
    expect(decorations).toHaveLength(2);
    const [first, second] = decorations as Decoration[];
    expect(first.from).toBe(1); // 段落内文本从 pos+1 开始
    expect(first.to).toBe(3);
    expect(second.from).toBeGreaterThan(first.to);
    const set = DecorationSet.create(doc, decorations);
    expect(set.find().length).toBe(2);
  });

  it("位置对不上原文时不产出 decoration（兜底）", () => {
    const doc = makeDoc(["干净正文"]);
    const decorations = buildSensitiveDecorations(doc, HITS);
    expect(decorations).toHaveLength(0);
  });

  it("Extension 已注册（名称与命令/插件挂载点）", () => {
    const extension = SensitiveHighlight;
    expect(extension.name).toBe("sensitiveHighlight");
    expect(extension.type).toBe("extension");
  });
});

describe("replaceSensitiveWord（复用 replaceAll 单事务多替换路径）", () => {
  it("重扫定位后倒序替换并派发单笔事务", () => {
    const doc = makeDoc(["赌博开始", "中间没有", "赌博结束"]);
    const editor = makeEditorLike(doc);
    const hit: SensitiveWordHit = {
      word: "赌博",
      source: "通用类目示例",
      count: 2,
      positions: [],
    };

    const replaced = replaceSensitiveWord(editor as never, hit, "＊＊");
    expect(replaced).toBe(2);
    expect(editor.view.dispatch).toHaveBeenCalledTimes(1);
    const tr = editor.view.dispatch.mock.calls[0][0] as { insertText: ReturnType<typeof vi.fn> };
    expect(tr.insertText).toHaveBeenCalledTimes(2);
  });

  it("无命中时不派发事务", () => {
    const doc = makeDoc(["干净正文"]);
    const editor = makeEditorLike(doc);
    const replaced = replaceSensitiveWord(
      editor as never,
      { word: "赌博", source: "", count: 0, positions: [] },
      "＊＊",
    );
    expect(replaced).toBe(0);
    expect(editor.view.dispatch).not.toHaveBeenCalled();
  });
});
