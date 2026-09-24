import { Theme } from "@radix-ui/themes";
import { act, type ReactNode, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import i18n from "@/i18n";
import type { ChapterListItem as ChapterListItemData } from "@/lib/chapter.types";

import { ChapterListItem } from "./chapter-list-item";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

function sampleChapter(overrides: Partial<ChapterListItemData> = {}): ChapterListItemData {
  return {
    id: "c1",
    projectId: "p1",
    volumeId: "v1",
    title: "雨停之前",
    synopsis: "雨停的时候把门打开",
    writingStatus: "drafting",
    wordCount: 0,
    wordCountTarget: null,
    order: 2,
    createdAt: "2026-09-01T00:00:00Z",
    updatedAt: "2026-09-02T00:00:00Z",
    ...overrides,
  };
}

const mounted: Array<{ root: Root; container: HTMLDivElement }> = [];

function render(node: ReactNode) {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  act(() => {
    root.render(<Theme>{node}</Theme>);
  });
  mounted.push({ root, container });
  return {
    container,
    rerender(next: ReactNode) {
      act(() => {
        root.render(<Theme>{next}</Theme>);
      });
    },
  };
}

function row(
  chapter: ChapterListItemData,
  onSelectChapter: (chapterId: string) => void = () => {},
) {
  return (
    <ChapterListItem
      chapter={chapter}
      isActive={false}
      onSelectChapter={onSelectChapter}
    />
  );
}

function notStartedMark(container: HTMLElement) {
  return container.querySelector("[data-not-started]");
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

describe("sidebar chapter row not-started mark", () => {
  it("shows 还没动笔 for a draft with a synopsis and zero saved words", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = render(row(sampleChapter({ writingStatus: "drafting", wordCount: 0 })));
    const mark = notStartedMark(view.container);
    expect(mark?.textContent).toBe("还没动笔");
  });

  it("shows 还没动笔 for a revision with a synopsis and zero saved words", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = render(row(sampleChapter({ writingStatus: "revising", wordCount: 0 })));
    expect(notStartedMark(view.container)?.textContent).toBe("还没动笔");
  });

  it("hides the mark as soon as the saved word count is above zero", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = render(row(sampleChapter({ wordCount: 0 })));
    expect(notStartedMark(view.container)).not.toBeNull();
    view.rerender(row(sampleChapter({ wordCount: 6 })));
    expect(notStartedMark(view.container)).toBeNull();
  });

  it("does not mark a blank synopsis", async () => {
    await i18n.changeLanguage("zh-CN");
    for (const synopsis of ["", "   ", "\n\n"]) {
      const view = render(row(sampleChapter({ synopsis })));
      expect(notStartedMark(view.container)).toBeNull();
    }
  });

  it("does not mark idea or done chapters", async () => {
    await i18n.changeLanguage("zh-CN");
    const idea = render(row(sampleChapter({ writingStatus: "idea", wordCount: 0 })));
    const done = render(row(sampleChapter({ id: "c2", writingStatus: "done", wordCount: 0 })));
    expect(notStartedMark(idea.container)).toBeNull();
    expect(notStartedMark(done.container)).toBeNull();
  });

  it("still opens the chapter when the mark is clicked", async () => {
    await i18n.changeLanguage("zh-CN");
    const selected: string[] = [];
    const view = render(row(sampleChapter(), (chapterId) => selected.push(chapterId)));
    const mark = notStartedMark(view.container);
    expect(mark).not.toBeNull();
    act(() => {
      mark?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(selected).toEqual(["c1"]);
  });
});

function SavedWordCountRow() {
  const [chapter, setChapter] = useState(sampleChapter({ wordCount: 0 }));
  return (
    <>
      <ChapterListItem
        chapter={chapter}
        isActive={false}
        onSelectChapter={() => {}}
      />
      <button
        type="button"
        onClick={() => setChapter(sampleChapter({ wordCount: 4 }))}
      >
        写入已保存字数
      </button>
    </>
  );
}

describe("saved manuscript clears the sidebar mark", () => {
  it("removes 还没动笔 when the row receives a saved word count above zero", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = render(<SavedWordCountRow />);
    expect(notStartedMark(view.container)?.textContent).toBe("还没动笔");
    const button = view.container.querySelector("button");
    act(() => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(notStartedMark(view.container)).toBeNull();
  });
});
