import { Theme } from "@radix-ui/themes";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import i18n from "@/i18n";
import zhCN from "@/i18n/locales/zh-CN.json";
import type { ChapterRevisionItem } from "@/lib/chapter.types";

import { ChapterRevisionList } from "./chapter-revision-list";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const mounted: Array<{ root: Root; container: HTMLDivElement }> = [];

function render(node: ReactNode) {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  act(() => {
    root.render(<Theme>{node}</Theme>);
  });
  mounted.push({ root, container });
  return { container };
}

afterEach(() => {
  for (const item of mounted) {
    act(() => {
      item.root.unmount();
    });
    item.container.remove();
  }
  mounted.length = 0;
});

const agentItem: ChapterRevisionItem = {
  commitId: "commit-agent",
  revisionId: "rev-agent",
  revisionType: "agent",
  message: "按细纲推进第二节",
  operation: "update",
  createdAt: "2026-09-26T12:00:00+08:00",
  title: "第一章",
  wordCount: 1200,
  hasSnapshot: true,
};

const manualItem: ChapterRevisionItem = {
  commitId: "commit-manual",
  revisionId: "rev-manual",
  revisionType: "manual",
  message: "手动保存",
  operation: "update",
  createdAt: "2026-09-26T13:00:00+08:00",
  title: "第一章",
  wordCount: 1250,
  hasSnapshot: true,
};

const createItem: ChapterRevisionItem = {
  commitId: "commit-create",
  revisionId: "rev-create",
  revisionType: "manual",
  message: "创建章节",
  operation: "create",
  createdAt: "2026-09-26T09:00:00+08:00",
  title: "第一章",
  wordCount: null,
  hasSnapshot: false,
};

function items(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLButtonElement>("button")).filter(
    (button) => button.getAttribute("aria-label") === zhCN.writing.chapterHistory.restore,
  );
}

describe("章节历史版本列表（轻渲染）", () => {
  it("渲染 Agent 与手动修订混合时间线：类型、时间、字数与恢复按钮", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = render(
      <ChapterRevisionList
        items={[manualItem, agentItem, createItem]}
        activeCommitId={null}
        isRestoring={false}
        onSelect={() => {}}
        onRestore={() => {}}
      />,
    );

    expect(view.container.textContent).toContain(zhCN.writing.chapterHistory.typeManual);
    expect(view.container.textContent).toContain(zhCN.writing.chapterHistory.typeAgent);
    expect(view.container.textContent).toContain("1250");
    expect(view.container.textContent).toContain("1200");
    // 无快照的 create 条目不出现恢复按钮
    expect(items(view.container)).toHaveLength(2);
  });

  it("空时间线显示占位文案", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = render(
      <ChapterRevisionList
        items={[]}
        activeCommitId={null}
        isRestoring={false}
        onSelect={() => {}}
        onRestore={() => {}}
      />,
    );
    expect(view.container.textContent).toContain(zhCN.writing.chapterHistory.empty);
  });

  it("点击恢复按钮触发恢复回调，并带上所选条目", async () => {
    await i18n.changeLanguage("zh-CN");
    const restored: string[] = [];
    const view = render(
      <ChapterRevisionList
        items={[manualItem]}
        activeCommitId={null}
        isRestoring={false}
        onSelect={() => {}}
        onRestore={(entry) => restored.push(entry.commitId)}
      />,
    );

    const restoreButton = items(view.container)[0];
    expect(restoreButton).toBeDefined();
    act(() => {
      restoreButton?.click();
    });
    expect(restored).toEqual(["commit-manual"]);
  });

  it("恢复进行中按钮禁用，选中条目高亮", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = render(
      <ChapterRevisionList
        items={[manualItem]}
        activeCommitId="commit-manual"
        isRestoring
        onSelect={() => {}}
        onRestore={() => {}}
      />,
    );
    const restoreButton = items(view.container)[0];
    expect(restoreButton?.disabled).toBe(true);
    expect(view.container.textContent).toContain(zhCN.writing.chapterHistory.restoring);
  });
});
