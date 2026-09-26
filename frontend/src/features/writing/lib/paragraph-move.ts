/**
 * 段落重排的纯逻辑：把光标所在的顶层块上移或下移一位。
 *
 * 只依赖 prosemirror 的 state/tr，方便在 node 测试里以最小 schema 驱动。
 */

import { TextSelection, type Transaction } from "@tiptap/pm/state";

export type BlockMoveDirection = "up" | "down";

/**
 * 生成移动事务。光标所在顶层块与相邻块交换位置，光标跟随移动后的块。
 * 已处于边界（第一块上移 / 最后一块下移）时返回 null，不产生事务。
 */
export function createMoveTopLevelBlockTr(
  tr: Transaction,
  direction: BlockMoveDirection,
): Transaction | null {
  const doc = tr.doc;
  const { from } = tr.selection;
  const $from = doc.resolve(from);
  const index = $from.index(0);
  const count = doc.childCount;

  if (direction === "up" && index === 0) return null;
  if (direction === "down" && index >= count - 1) return null;

  const node = doc.child(index);
  const size = node.nodeSize;
  const startPos = $from.before(1);

  if (direction === "up") {
    const previousSize = doc.child(index - 1).nodeSize;
    tr.delete(startPos, startPos + size);
    tr.insert(startPos - previousSize, node);
    const $target = tr.doc.resolve(startPos - previousSize + 1);
    tr.setSelection(TextSelection.near($target, 1));
  } else {
    const nextSize = doc.child(index + 1).nodeSize;
    tr.delete(startPos, startPos + size);
    tr.insert(startPos + nextSize, node);
    const $target = tr.doc.resolve(startPos + nextSize + 1);
    tr.setSelection(TextSelection.near($target, 1));
  }
  return tr;
}
