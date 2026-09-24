import { Theme } from "@radix-ui/themes";
import { act, type ReactNode, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { showsMissingWordTargetMark } from "@/lib/chapter-length";
import type {
  ChapterListItem as ChapterListItemData,
  VolumeTreeResponse,
} from "@/lib/chapter.types";

import { applyWordCountTargetToVolumeTree } from "../lib/volume-tree-word-target";
import { ChapterListItem } from "./chapter-list-item";

function sampleChapter(overrides: Partial<ChapterListItemData> = {}): ChapterListItemData {
  return {
    id: "c1",
    projectId: "p1",
    volumeId: "v1",
    title: "雨停之前",
    synopsis: "雨停的时候把门打开",
    writingStatus: "drafting",
    wordCount: 480,
    wordCountTarget: null,
    order: 2,
    createdAt: "2026-09-01T00:00:00Z",
    updatedAt: "2026-09-02T00:00:00Z",
    openMarginNoteCount: 0,
    ...overrides,
  };
}

function sampleTree(chapter: ChapterListItemData): VolumeTreeResponse {
  return {
    totalChapters: 1,
    volumes: [
      {
        id: "v1",
        projectId: "p1",
        title: "卷一",
        description: null,
        order: 1,
        chapterCount: 1,
        createdAt: "2026-09-01T00:00:00Z",
        updatedAt: "2026-09-01T00:00:00Z",
        chapters: [chapter],
      },
    ],
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

function row(chapter: ChapterListItemData) {
  return (
    <ChapterListItem
      chapter={chapter}
      isActive={false}
      onSelectChapter={() => {}}
    />
  );
}

function missingMark(container: HTMLElement) {
  return container.querySelector("[data-missing-word-target]");
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

describe("showsMissingWordTargetMark", () => {
  it("treats null, blank, zero, and out-of-range values as unset for drafts and revisions", () => {
    for (const status of ["drafting", "revising"] as const) {
      expect(showsMissingWordTargetMark(status, null)).toBe(true);
      expect(showsMissingWordTargetMark(status, undefined)).toBe(true);
      expect(showsMissingWordTargetMark(status, "")).toBe(true);
      expect(showsMissingWordTargetMark(status, "  ")).toBe(true);
      expect(showsMissingWordTargetMark(status, 0)).toBe(true);
      expect(showsMissingWordTargetMark(status, 1.5)).toBe(true);
      expect(showsMissingWordTargetMark(status, 100_001)).toBe(true);
      expect(showsMissingWordTargetMark(status, -3)).toBe(true);
      expect(showsMissingWordTargetMark(status, 1)).toBe(false);
      expect(showsMissingWordTargetMark(status, 100_000)).toBe(false);
    }
    expect(showsMissingWordTargetMark("idea", null)).toBe(false);
    expect(showsMissingWordTargetMark("idea", 0)).toBe(false);
    expect(showsMissingWordTargetMark("done", null)).toBe(false);
    expect(showsMissingWordTargetMark("done", "")).toBe(false);
  });
});

describe("sidebar chapter row", () => {
  it("marks a draft and a revision that have no word target", () => {
    const draft = render(row(sampleChapter({ writingStatus: "drafting", wordCountTarget: null })));
    const revision = render(
      row(sampleChapter({ id: "c2", writingStatus: "revising", wordCountTarget: null })),
    );

    expect(missingMark(draft.container)?.textContent).toBe("未设目标");
    expect(draft.container.textContent).toContain("480");
    expect(missingMark(revision.container)?.textContent).toBe("未设目标");
  });

  it("does not mark a chapter that already has a target", () => {
    const view = render(row(sampleChapter({ writingStatus: "drafting", wordCountTarget: 2400 })));
    expect(missingMark(view.container)).toBeNull();
    expect(view.container.textContent).toContain("480/2400");
  });

  it("does not mark idea or done chapters even when the target is missing", () => {
    const idea = render(row(sampleChapter({ writingStatus: "idea", wordCountTarget: null })));
    const done = render(
      row(sampleChapter({ id: "c3", writingStatus: "done", wordCountTarget: 0 })),
    );
    expect(missingMark(idea.container)).toBeNull();
    expect(missingMark(done.container)).toBeNull();
  });

  it("reads zero as unset on a draft", () => {
    const view = render(row(sampleChapter({ writingStatus: "revising", wordCountTarget: 0 })));
    expect(missingMark(view.container)?.textContent).toBe("未设目标");
  });

  it("drops the mark after a target is set and brings it back when the target is cleared", () => {
    function Harness() {
      const [target, setTarget] = useState<number | null>(null);
      return (
        <>
          <button
            type="button"
            onClick={() => setTarget(2400)}
          >
            set-target
          </button>
          <button
            type="button"
            onClick={() => setTarget(null)}
          >
            clear-target
          </button>
          {row(sampleChapter({ writingStatus: "drafting", wordCountTarget: target }))}
        </>
      );
    }

    const view = render(<Harness />);
    expect(missingMark(view.container)?.textContent).toBe("未设目标");

    act(() => {
      view.container.querySelectorAll("button")[0]?.click();
    });
    expect(missingMark(view.container)).toBeNull();

    act(() => {
      view.container.querySelectorAll("button")[1]?.click();
    });
    expect(missingMark(view.container)?.textContent).toBe("未设目标");
  });

  it("updates the sidebar row from the volume tree without touching word count or order", () => {
    const chapter = sampleChapter({ writingStatus: "revising", wordCountTarget: null, order: 4 });
    const tree = sampleTree(chapter);
    const view = render(row(tree.volumes[0]?.chapters[0] ?? chapter));
    expect(missingMark(view.container)).not.toBeNull();

    const withTarget = applyWordCountTargetToVolumeTree(tree, {
      id: chapter.id,
      wordCountTarget: 8000,
      updatedAt: "2026-09-24T00:00:00Z",
    });
    const updated = withTarget.volumes[0]?.chapters[0];
    expect(updated?.wordCount).toBe(480);
    expect(updated?.order).toBe(4);
    expect(updated?.title).toBe("雨停之前");
    expect(updated?.synopsis).toBe("雨停的时候把门打开");

    view.rerender(row(updated ?? chapter));
    expect(missingMark(view.container)).toBeNull();

    const cleared = applyWordCountTargetToVolumeTree(withTarget, {
      id: chapter.id,
      wordCountTarget: null,
      updatedAt: "2026-09-24T00:05:00Z",
    });
    view.rerender(row(cleared.volumes[0]?.chapters[0] ?? chapter));
    expect(missingMark(view.container)?.textContent).toBe("未设目标");
  });
});
