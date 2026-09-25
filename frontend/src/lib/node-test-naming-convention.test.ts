import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// vitest 以 frontend 项目根为 cwd（与 vite.config.ts 的 loadEnv(mode, process.cwd(), "") 一致）。
const srcDir = join(process.cwd(), "src");
// 与 package.json 的 test 脚本（node --test "src/**/*.node.test.ts"）和
// vite.config.ts 的 vitest exclude（"src/**/*.node.test.ts"）保持同一约定。
const nodeTestImport = /(?:from\s+|import\s+|require\(\s*)["']node:test["'](?:\s*\))?/;

function listTestFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true, recursive: true })
    .filter((entry) => entry.isFile() && /\.test\.tsx?$/.test(entry.name))
    .map((entry) => join(entry.parentPath ?? entry.path, entry.name));
}

describe("node:test 用例命名约定", () => {
  it("使用 node:test 的测试文件必须命名为 *.node.test.ts，否则两条 runner 都接不住", () => {
    const offenders = listTestFiles(srcDir).filter((file) => {
      if (/\.node\.test\.tsx?$/.test(file)) {
        return false;
      }
      return nodeTestImport.test(readFileSync(file, "utf8"));
    });

    expect(
      offenders,
      [
        "以下文件使用了 node:test，但文件名不是 *.node.test.ts：",
        ...offenders.map((file) => `  ${file}`),
        "",
        "node --test 只拾取 src/**/*.node.test.ts（package.json 的 test 脚本），",
        "vitest 只排除这一模式（vite.config.ts test.exclude）。",
        "命名不符的文件 node --test 不会拾取，vitest 误拾取后会报",
        'Cannot bundle Node.js built-in "node:test"——请按 *.node.test.ts 重命名。',
      ].join("\n"),
    ).toEqual([]);
  });
});
