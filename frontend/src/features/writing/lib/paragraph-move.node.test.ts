import { Schema } from "@tiptap/pm/model";
import { EditorState, TextSelection } from "@tiptap/pm/state";
import assert from "node:assert/strict";
import test from "node:test";

import { createMoveTopLevelBlockTr } from "./paragraph-move.ts";

const schema = new Schema({
  nodes: {
    doc: { content: "block+" },
    paragraph: { group: "block", content: "text*" },
    text: { inline: true },
  },
});

function buildState(lines: string[], caretParagraph: number): EditorState {
  const doc = schema.node(
    "doc",
    {},
    lines.map((line) => schema.node("paragraph", {}, line ? [schema.text(line)] : [])),
  );
  const paragraph = doc.child(caretParagraph);
  const offset = doc.children.forEach((child, childOffset, i) => {
    if (i >= caretParagraph) return true;
  });
  // 定位到目标段开头
  let position = 0;
  for (let i = 0; i < caretParagraph; i += 1) {
    position += doc.child(i).nodeSize;
  }
  position += 1; // 进入段内
  void paragraph;
  void offset;
  return EditorState.create({
    doc,
    selection: TextSelection.near(doc.resolve(position), 1),
  });
}

function paragraphTexts(state: EditorState): string[] {
  const texts: string[] = [];
  state.doc.forEach((node) => texts.push(node.textContent));
  return texts;
}

test("上移：光标所在段与上一段交换，光标跟随", () => {
  const state = buildState(["一", "二", "三"], 1);
  const tr = createMoveTopLevelBlockTr(state.tr, "up");
  assert.ok(tr);
  const nextState = state.apply(tr);
  assert.deepEqual(paragraphTexts(nextState), ["二", "一", "三"]);
  // 光标跟随被移动的块（原第二段）
  assert.equal(nextState.selection.$from.parent.textContent, "二");
});

test("下移：光标所在段与下一段交换，光标跟随", () => {
  const state = buildState(["一", "二", "三"], 1);
  const tr = createMoveTopLevelBlockTr(state.tr, "down");
  assert.ok(tr);
  const nextState = state.apply(tr);
  assert.deepEqual(paragraphTexts(nextState), ["一", "三", "二"]);
  assert.equal(nextState.selection.$from.parent.textContent, "二");
});

test("第一段上移、最后一段下移为边界，返回 null", () => {
  const first = buildState(["一", "二"], 0);
  assert.equal(createMoveTopLevelBlockTr(first.tr, "up"), null);
  const last = buildState(["一", "二"], 1);
  assert.equal(createMoveTopLevelBlockTr(last.tr, "down"), null);
});

test("空段落同样可以移动", () => {
  const state = buildState(["一", "", "三"], 1);
  const tr = createMoveTopLevelBlockTr(state.tr, "up");
  assert.ok(tr);
  const nextState = state.apply(tr);
  assert.deepEqual(paragraphTexts(nextState), ["", "一", "三"]);
});
