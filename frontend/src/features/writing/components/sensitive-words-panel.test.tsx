import { Theme } from "@radix-ui/themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { Editor } from "@tiptap/react";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import zhCN from "@/i18n/locales/zh-CN.json";

import { SensitiveWordsPanel } from "./sensitive-words-panel";

vi.mock("@/lib/api-client", () => ({
  fetchSensitiveWords: vi.fn(),
  updateSensitiveWords: vi.fn(),
  importSensitiveWords: vi.fn(),
  exportSensitiveWords: vi.fn(),
}));

vi.mock("@/components", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

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

import {
  exportSensitiveWords,
  fetchSensitiveWords,
  importSensitiveWords,
  updateSensitiveWords,
} from "@/lib/api-client";

const mockedFetchSensitiveWords = vi.mocked(fetchSensitiveWords);
const mockedImportSensitiveWords = vi.mocked(importSensitiveWords);
const mockedExportSensitiveWords = vi.mocked(exportSensitiveWords);
const mockedUpdateSensitiveWords = vi.mocked(updateSensitiveWords);

const WORDS = [
  { word: "赌博", source: "通用类目示例" },
  { word: "枪支", source: "通用类目示例" },
];

const CHAPTER_TEXT = "他去赌博了，还摸了枪支。";

/**
 * 轻量编辑器替身（非 tiptap 实例）：只实现面板用到的表面——
 * 纯文本读取（textBetween）、命令对象与事件订阅。
 */
function makeFakeEditor(text: string) {
  return {
    on: vi.fn(),
    off: vi.fn(),
    commands: {
      setSensitiveHits: vi.fn(),
      setTextSelection: vi.fn(),
      scrollIntoView: vi.fn(),
    },
    state: {
      doc: {
        content: { size: text.length },
        textBetween: (_from: number, to: number) => text.slice(0, to),
      },
    },
  } as unknown as Editor;
}

const mounted: Array<{ root: Root; container: HTMLDivElement }> = [];

function renderPanel(editor: Editor, props: { onClose?: () => void } = {}) {
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
          <SensitiveWordsPanel
            editor={editor}
            isAgentLocked={false}
            onClose={props.onClose ?? (() => {})}
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

beforeEach(() => {
  mockedFetchSensitiveWords.mockReset();
  mockedImportSensitiveWords.mockReset();
  mockedExportSensitiveWords.mockReset();
  mockedUpdateSensitiveWords.mockReset();
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

describe("敏感词面板（轻渲染，mock api-client + 编辑器替身）", () => {
  it("打开即拉词库并整章扫描：命中行渲染且 setSensitiveHits 已联动", async () => {
    await i18n.changeLanguage("zh-CN");
    mockedFetchSensitiveWords.mockResolvedValue(WORDS);
    const editor = makeFakeEditor(CHAPTER_TEXT);

    const view = renderPanel(editor);
    await waitFor(() => view.container.textContent?.includes("赌博") ?? false);

    expect(mockedFetchSensitiveWords).toHaveBeenCalledTimes(1);
    // 扫描结果回写高亮 Extension
    const setHits = (editor.commands.setSensitiveHits as ReturnType<typeof vi.fn>).mock.calls.at(
      -1,
    )?.[0] as Array<{ word: string; count: number }>;
    expect(setHits).toEqual([
      { word: "赌博", source: "通用类目示例", count: 1, positions: [{ start: 2, end: 4 }] },
      { word: "枪支", source: "通用类目示例", count: 1, positions: [{ start: 9, end: 11 }] },
    ]);
    // 编辑事件订阅已挂载（防抖重扫）
    expect(editor.on).toHaveBeenCalledWith("update", expect.any(Function));
  });

  it("无命中时渲染空态文案", async () => {
    await i18n.changeLanguage("zh-CN");
    mockedFetchSensitiveWords.mockResolvedValue(WORDS);
    const editor = makeFakeEditor("完全干净的正文");

    const view = renderPanel(editor);
    await waitFor(
      () => view.container.textContent?.includes(zhCN.writing.sensitiveWords.empty) ?? false,
    );

    const setHits = (editor.commands.setSensitiveHits as ReturnType<typeof vi.fn>).mock.calls.at(
      -1,
    )?.[0] as unknown[];
    expect(setHits).toEqual([]);
  });

  it("词库加载失败渲染失败文案", async () => {
    await i18n.changeLanguage("zh-CN");
    mockedFetchSensitiveWords.mockRejectedValue(new Error("network down"));
    const editor = makeFakeEditor(CHAPTER_TEXT);

    const view = renderPanel(editor);
    await waitFor(
      () => view.container.textContent?.includes(zhCN.writing.sensitiveWords.loadFailed) ?? false,
    );

    expect(view.container.textContent).toContain(zhCN.writing.sensitiveWords.loadFailed);
  });

  it("词库维护区：导入按钮携带粘贴内容与格式调用导入端点", async () => {
    await i18n.changeLanguage("zh-CN");
    mockedFetchSensitiveWords.mockResolvedValue(WORDS);
    mockedImportSensitiveWords.mockResolvedValue({
      words: WORDS,
      count: 2,
      stats: { accepted: 1, duplicates: 0, invalid: 0 },
    });
    const editor = makeFakeEditor(CHAPTER_TEXT);

    const view = renderPanel(editor);
    await waitFor(() => view.container.textContent?.includes("赌博") ?? false);

    const textarea = document.body.querySelector<HTMLTextAreaElement>("textarea");
    expect(textarea).not.toBeNull();
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      setter?.call(textarea, "赌博|来源X");
      textarea!.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await waitFor(() =>
      Array.from(document.body.querySelectorAll("button")).some(
        (button) => button.textContent?.trim() === zhCN.writing.sensitiveWords.importButton,
      ),
    );

    const importButton = Array.from(document.body.querySelectorAll("button")).find(
      (button) => button.textContent?.trim() === zhCN.writing.sensitiveWords.importButton,
    );
    await act(async () => {
      importButton?.click();
      await Promise.resolve();
    });
    await waitFor(() => mockedImportSensitiveWords.mock.calls.length > 0);

    expect(mockedImportSensitiveWords).toHaveBeenCalledWith("赌博|来源X", "txt");
  });

  it("词库维护区：导出与清空按钮分别调用对应端点（清空需两次点击确认）", async () => {
    await i18n.changeLanguage("zh-CN");
    mockedFetchSensitiveWords.mockResolvedValue(WORDS);
    mockedExportSensitiveWords.mockResolvedValue({
      filename: "sensitive-words.txt",
      format: "txt",
      content: "赌博|通用类目示例",
    });
    mockedUpdateSensitiveWords.mockResolvedValue({
      words: [],
      count: 0,
      stats: { accepted: 0, duplicates: 0, invalid: 0 },
    });
    const editor = makeFakeEditor(CHAPTER_TEXT);

    renderPanel(editor);
    await waitFor(() => viewReady());

    function viewReady() {
      return Array.from(document.body.querySelectorAll("button")).some(
        (button) => button.textContent?.trim() === zhCN.writing.sensitiveWords.exportTxt,
      );
    }

    const findButton = (label: string) =>
      Array.from(document.body.querySelectorAll("button")).find(
        (button) => button.textContent?.trim() === label,
      );

    await act(async () => {
      findButton(zhCN.writing.sensitiveWords.exportTxt)?.click();
      await Promise.resolve();
    });
    await waitFor(() => mockedExportSensitiveWords.mock.calls.length > 0);
    expect(mockedExportSensitiveWords).toHaveBeenCalledWith("txt");

    // 清空：第一次点击只进入确认态，第二次才调用整表更新
    const clearButton = () =>
      findButton(zhCN.writing.sensitiveWords.clearButton) ??
      findButton(zhCN.writing.sensitiveWords.clearConfirm);
    await act(async () => {
      clearButton()?.click();
      await Promise.resolve();
    });
    expect(mockedUpdateSensitiveWords).not.toHaveBeenCalled();

    await act(async () => {
      clearButton()?.click();
      await Promise.resolve();
    });
    await waitFor(() => mockedUpdateSensitiveWords.mock.calls.length > 0);
    expect(mockedUpdateSensitiveWords).toHaveBeenCalledWith([]);
  });
});
