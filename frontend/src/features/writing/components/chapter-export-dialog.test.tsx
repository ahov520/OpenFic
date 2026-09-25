import { Theme } from "@radix-ui/themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import zhCN from "@/i18n/locales/zh-CN.json";
import type { ChapterExport } from "@/lib/chapter-export.types";
import type { VolumeWithChapters } from "@/lib/chapter.types";

import { ChapterExportDialog } from "./chapter-export-dialog";

// Radix Dialog 挂载在 portal（document.body），断言统一从 body 查询
function dialogBody() {
  return document.body;
}

async function waitFor(predicate: () => boolean) {
  for (let round = 0; round < 200 && !predicate(); round += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5));
    });
  }
  expect(predicate()).toBe(true);
}

vi.mock("react-virtuoso", async () => {
  const { createElement, Fragment } = await import("react");
  return {
    // happy-dom 无虚拟滚动测量，测试用静态全量渲染
    Virtuoso: ({
      data,
      itemContent,
    }: {
      data: unknown[];
      itemContent: (index: number, item: unknown) => ReactNode;
    }) =>
      createElement(
        Fragment,
        null,
        data.map((item, index) => itemContent(index, item)),
      ),
  };
});

vi.mock("@/lib/api-client", () => ({
  cancelChapterExport: vi.fn(),
  createChapterExport: vi.fn(),
  fetchChapter: vi.fn(),
  fetchChapterExport: vi.fn(),
  fetchProject: vi.fn(),
}));

vi.mock("@/lib/background-socket", () => ({
  subscribeBackgroundEvents: () => ({ close: () => {} }),
}));

vi.mock("@/lib/socket-client", () => ({
  getSocketConnectionStatus: () => "connected",
  subscribeSocketConnectionStatus: () => () => {},
}));

import { createChapterExport, fetchProject } from "@/lib/api-client";

const mockedCreateChapterExport = vi.mocked(createChapterExport);
const mockedFetchProject = vi.mocked(fetchProject);

const volume: VolumeWithChapters = {
  id: "v1",
  projectId: "p1",
  title: "第一卷",
  description: null,
  order: 1,
  chapterCount: 2,
  createdAt: "2026-09-01T00:00:00Z",
  updatedAt: "2026-09-02T00:00:00Z",
  chapters: [
    {
      id: "c1",
      projectId: "p1",
      volumeId: "v1",
      title: "第一章",
      synopsis: "",
      writingStatus: "done",
      wordCount: 500,
      wordCountTarget: null,
      order: 1,
      createdAt: "2026-09-01T00:00:00Z",
      updatedAt: "2026-09-02T00:00:00Z",
      openMarginNoteCount: 0,
    },
    {
      id: "c2",
      projectId: "p1",
      volumeId: "v1",
      title: "第二章",
      synopsis: "",
      writingStatus: "done",
      wordCount: 600,
      wordCountTarget: null,
      order: 2,
      createdAt: "2026-09-01T00:00:00Z",
      updatedAt: "2026-09-02T00:00:00Z",
      openMarginNoteCount: 0,
    },
  ],
};

const pendingExport: ChapterExport = {
  id: "job-1",
  status: "pending",
  filename: "测试小说-全本-2026-09-26.epub",
  mode: "volumes",
  format: "epub",
  volumeCount: 1,
  chapterCount: 2,
  wordCount: 1100,
  chapterIds: ["c1", "c2"],
  current: 0,
  total: 2,
  stage: null,
  chapterTitle: null,
  expiresAt: null,
  downloadUrl: null,
  errorMessage: null,
};

const mounted: Array<{ root: Root; container: HTMLDivElement }> = [];

function renderDialog() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <Theme>
          <ChapterExportDialog
            open
            onOpenChange={() => {}}
            projectId="p1"
            volumes={[volume]}
          />
        </Theme>
      </QueryClientProvider>,
    );
  });
  mounted.push({ root, container });
  return { container, queryClient };
}

async function flush() {
  for (let round = 0; round < 10; round += 1) {
    await act(async () => {
      await Promise.resolve();
    });
  }
}

function buttonByLabel(container: HTMLElement, label: string) {
  return Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
    (button) => button.textContent?.trim() === label || button.getAttribute("aria-label") === label,
  );
}

beforeEach(() => {
  mockedCreateChapterExport.mockReset();
  mockedFetchProject.mockReset();
  mockedFetchProject.mockResolvedValue({
    id: "p1",
    title: "测试小说",
    description: null,
    coverPath: null,
    chapterCount: 2,
    wordCount: 1100,
    createdAt: "2026-09-01T00:00:00Z",
    updatedAt: "2026-09-02T00:00:00Z",
  });
  mockedCreateChapterExport.mockResolvedValue(pendingExport);
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

describe("导出对话框格式选择（轻渲染）", () => {
  it("默认 TXT 导出并透传格式参数", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = renderDialog();
    await flush();

    await waitFor(
      () =>
        dialogBody().querySelector(
          '[aria-label="' + zhCN.writing.chapterExport.selectProject + '"]',
        ) !== null,
    );
    const selectAll = dialogBody().querySelector(
      '[aria-label="' + zhCN.writing.chapterExport.selectProject + '"]',
    ) as HTMLButtonElement | null;
    act(() => {
      selectAll?.click();
    });
    await waitFor(
      () => buttonByLabel(dialogBody(), zhCN.writing.chapterExport.export)?.disabled === false,
    );

    const exportButton = buttonByLabel(dialogBody(), zhCN.writing.chapterExport.export);
    expect(exportButton).toBeDefined();
    await act(async () => {
      exportButton?.click();
      await Promise.resolve();
    });
    await flush();

    expect(mockedCreateChapterExport).toHaveBeenCalledTimes(1);
    expect(mockedCreateChapterExport.mock.calls[0]?.[1].format).toBe("txt");
  });

  it("切换为 EPUB 后导出调用携带 epub 格式", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = renderDialog();
    await flush();

    await waitFor(
      () =>
        dialogBody().querySelector(
          '[aria-label="' + zhCN.writing.chapterExport.selectProject + '"]',
        ) !== null,
    );
    const selectAll = dialogBody().querySelector(
      '[aria-label="' + zhCN.writing.chapterExport.selectProject + '"]',
    ) as HTMLButtonElement | null;
    act(() => {
      selectAll?.click();
    });

    // Radix SegmentedControl 的 label 内容渲染两遍（Active/Inactive），用 includes 匹配
    const epubOption = Array.from(
      dialogBody().querySelectorAll<HTMLElement>("[role='radio']"),
    ).find(
      (element) =>
        element.getAttribute("value") === "epub" || element.textContent?.includes("EPUB"),
    );
    expect(epubOption).toBeDefined();
    act(() => {
      epubOption?.click();
    });

    const exportButton = buttonByLabel(dialogBody(), zhCN.writing.chapterExport.export);
    await act(async () => {
      exportButton?.click();
      await Promise.resolve();
    });
    await flush();

    expect(mockedCreateChapterExport).toHaveBeenCalledTimes(1);
    expect(mockedCreateChapterExport.mock.calls[0]?.[1].format).toBe("epub");
  });
});
