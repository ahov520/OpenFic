/**
 * 敏感词检测链路的离线红线检查：
 * 新增第一方文件（前端扫描/面板 + 后端词库/提取）不得引入任何
 * 网络客户端或外部 AI SDK（httpx/aiohttp/requests/urllib/openai/anthropic）。
 * 命中即退出码 1，接入 pnpm lint 随 CI 执行。
 */

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const frontendRoot = path.resolve(import.meta.dirname, "..");
const repoRoot = path.resolve(frontendRoot, "..");

const watchedFiles = [
  // 前端：扫描纯函数 / 高亮 Extension / 面板与列表
  "frontend/src/features/writing/lib/sensitive-words.ts",
  "frontend/src/features/writing/lib/sensitive-highlight.ts",
  "frontend/src/features/writing/components/sensitive-words-panel.tsx",
  "frontend/src/features/writing/components/sensitive-hit-list.tsx",
  // 后端：词库服务 / 资源 / router / 文档提取
  "backend/app/core/sensitive_words.py",
  "backend/app/core/resources/sensitive_words/starting_words.json",
  "backend/app/api/routers/sensitive_words.py",
  "backend/app/api/schemas/sensitive_words.py",
  "backend/app/core/doc_extract.py",
];

const bannedPattern = /httpx|aiohttp|requests|urllib|openai|anthropic/i;

let failures = 0;
for (const relativePath of watchedFiles) {
  const absolutePath = path.resolve(repoRoot, relativePath);
  if (!existsSync(absolutePath)) {
    console.error(`[check-offline] 缺少应存在的第一方文件: ${relativePath}`);
    failures += 1;
    continue;
  }
  const content = readFileSync(absolutePath, "utf8");
  const match = content.match(bannedPattern);
  if (match) {
    console.error(`[check-offline] ${relativePath} 命中禁用网络标识: ${match[0]}`);
    failures += 1;
  }
}

if (failures > 0) {
  console.error(`[check-offline] 离线红线检查失败（${failures} 处）`);
  process.exit(1);
}
console.log("[check-offline] 敏感词链路离线红线检查通过");
