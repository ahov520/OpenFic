import { Theme } from "@radix-ui/themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import zhCN from "@/i18n/locales/zh-CN.json";
import type { Chapter, ChapterRevisionItem } from "@/lib/chapter.types";

import { ChapterHistoryPanel } from "./chapter-history-panel";

// happy-dom 下 framer-motion 卸载会触碰不支持的 DOM API，测试用无动效直通替身
vi.mock("motion/react", async () => {
  const { createElement } = await import("react");
  return {
    motion: {
      div: ({ children, style }: { children?: ReactNode; style?: React.CSSProperties }) =>
        createElement("div", { style }, children),
    },
  };
});

vi.mock("@/lib/api-client", () => ({
  fetchChapterRevisions: vi.fn(),
  fetchChapterRevisionDetail: vi.fn(),
  restoreChapterRevision: vi.fn(),
}));

vi.mock("@/components", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "@/components";
import { fetchChapterRevisions, restoreChapterRevision } from "@/lib/api-client";

const mockedFetchChapterRevisions = vi.mocked(fetchChapterRevisions);
const mockedRestoreChapterRevision = vi.mocked(restoreChapterRevision);
const mockedToastError = vi.mocked(toast.error);

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

const restoredChapter: Chapter = {
  id: "c1",
  projectId: "p1",
  volumeId: "v1",
  title: "第一章",
  content: "恢复后的正文",
  synopsis: "",
  writingStatus: "drafting",
  wordCount: 350,
  wordCountTarget: null,
  order: 1,
  createdAt: "2026-09-01T00:00:00Z",
  updatedAt: "2026-09-26T14:00:00Z",
};

const mounted: Array<{ root: Root; container: HTMLDivElement }> = [];

function renderPanel(props: {
  onBeforeRestore?: () => Promise<void>;
  onRestored?: (chapter: Chapter) => void;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <Theme>
          <ChapterHistoryPanel
            chapterId="c1"
            isAgentLocked={false}
            onBeforeRestore={props.onBeforeRestore ?? (() => Promise.resolve())}
            onClose={() => {}}
            onRestored={props.onRestored ?? (() => {})}
          />
        </Theme>
      </QueryClientProvider>,
    );
  });
  mounted.push({ root, container });
  return { container, queryClient };
}

async function waitFor(predicate: () => boolean) {
  for (let round = 0; round < 200 && !predicate(); round += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5));
    });
  }
  expect(predicate()).toBe(true);
}

function restoreButton(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
    (button) => button.getAttribute("aria-label") === zhCN.writing.chapterHistory.restore,
  );
}

beforeEach(() => {
  mockedFetchChapterRevisions.mockReset();
  mockedRestoreChapterRevision.mockReset();
});

afterEach(() => {
  for (const item of mounted) {
    act(() => {
      item.root.unmount();
    });
    item.container.remove();
  }
  mounted.length = 0;
  document.body.innerHTML = "";
});

describe("章节历史版本面板（轻渲染，mock api-client）", () => {
  it("加载时间线并渲染恢复按钮；点击恢复先落盘再调恢复端点并回调 onRestored", async () => {
    await i18n.changeLanguage("zh-CN");
    const calls: string[] = [];
    const onBeforeRestore = vi.fn(async () => {
      calls.push("before");
    });
    const onRestored = vi.fn();
    mockedFetchChapterRevisions.mockResolvedValue([manualItem]);
    mockedRestoreChapterRevision.mockImplementation(async () => {
      calls.push("restore");
      return { revisionId: "rev-restored", chapter: restoredChapter };
    });

    const view = renderPanel({ onBeforeRestore, onRestored });
    await waitFor(() => restoreButton(view.container) !== undefined);

    expect(mockedFetchChapterRevisions).toHaveBeenCalledWith("c1", { offset: 0, limit: 50 });
    const button = restoreButton(view.container);
    expect(button).toBeDefined();

    await act(async () => {
      button?.click();
      await Promise.resolve();
    });
    await waitFor(() => onRestored.mock.calls.length > 0);

    expect(calls).toEqual(["before", "restore"]);
    expect(mockedRestoreChapterRevision).toHaveBeenCalledWith("c1", "commit-manual");
    expect(onRestored).toHaveBeenCalledWith(restoredChapter);
  });

  it("恢复前落盘失败时中止恢复（不调恢复端点）", async () => {
    await i18n.changeLanguage("zh-CN");
    const onBeforeRestore = vi.fn(async () => {
      throw new Error("保存未完成，已中止恢复");
    });
    const onRestored = vi.fn();
    mockedFetchChapterRevisions.mockResolvedValue([manualItem]);

    const view = renderPanel({ onBeforeRestore, onRestored });
    await waitFor(() => restoreButton(view.container) !== undefined);

    await act(async () => {
      restoreButton(view.container)?.click();
      await Promise.resolve();
    });
    // onError 分支：恢复失败 toast（onBeforeRestore 抛错导致）
    await waitFor(() => mockedToastError.mock.calls.length > 0);

    expect(mockedRestoreChapterRevision).not.toHaveBeenCalled();
    expect(onRestored).not.toHaveBeenCalled();
  });

  it("时间线加载失败渲染失败文案", async () => {
    await i18n.changeLanguage("zh-CN");
    mockedFetchChapterRevisions.mockRejectedValue(new Error("network down"));

    const view = renderPanel({});
    await waitFor(() =>
      view.container.textContent!.includes(zhCN.writing.chapterHistory.loadFailed),
    );

    expect(view.container.textContent).toContain(zhCN.writing.chapterHistory.loadFailed);
  });
});
