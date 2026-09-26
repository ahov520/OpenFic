import assert from "node:assert/strict";
import test from "node:test";

import { NAME_KINDS, generateNames } from "./name-generator.ts";

/** 确定性伪随机：可复现，覆盖取模路径。 */
function seeded(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1103515245 + 12345) % 2147483648;
    return state / 2147483648;
  };
}

test("每种类型都能生成足量且不重复的名字", () => {
  for (const kind of NAME_KINDS) {
    const names = generateNames(kind, 24, seeded(kind.length + 7));
    assert.equal(names.length, 24, `${kind} 应生成 24 个`);
    assert.equal(new Set(names).size, 24, `${kind} 不应有重复`);
  }
});

test("生成的名字不含空白且非空", () => {
  for (const kind of NAME_KINDS) {
    for (const name of generateNames(kind, 24, seeded(kind.length + 1))) {
      assert.ok(name.length > 0, `${kind} 的名字不能为空`);
      assert.ok(!/\s/.test(name), `${kind} 的名字不应含空白: ${name}`);
    }
  }
});

test("同名随机种子得到相同结果，便于复现", () => {
  const a = generateNames("chineseMale", 10, seeded(42));
  const b = generateNames("chineseMale", 10, seeded(42));
  assert.deepEqual(a, b);
});

test("地名只由前缀加后缀组成，末字属于后缀集合", () => {
  const suffixes = new Set(["城", "镇", "谷", "岭", "湖", "泽", "脉", "市", "口", "关"]);
  for (const name of generateNames("place", 20, seeded(9))) {
    const last = [...name].pop() ?? "";
    assert.ok(suffixes.has(last), `地名「${name}」末字 ${last} 应为后缀`);
  }
});

test("西式名包含音译分隔符", () => {
  for (const name of generateNames("western", 10, seeded(3))) {
    assert.ok(name.includes("·"), `西式名「${name}」应包含 ·`);
  }
});
