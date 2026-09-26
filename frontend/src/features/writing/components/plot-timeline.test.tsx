import { Theme } from "@radix-ui/themes";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import type { PlotChapterOption, PlotThread } from "@/lib/plot-thread";

import { PlotTimeline } from "./plot-timeline";

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
  vi.clearAllMocks();
});

const createMutate = vi.fn(async () => undefined);
const updateMutate = vi.fn(async () => undefined);
const deleteMutate = vi.fn(async () => undefined);

vi.mock("../hooks/use-plot-threads", () => ({
  useCreatePlotBeat: () => ({ mutateAsync: createMutate, isPending: false }),
  useUpdatePlotBeat: () => ({ mutateAsync: updateMutate, isPending: false }),
  useDeletePlotBeat: () => ({ mutateAsync: deleteMutate, isPending: false }),
}));

const chapterA: PlotChapterOption = {
  id: "c1",
  title: "第一章",
  globalOrder: 1,
  volumeTitle: "第一卷",
};
const chapterB: PlotChapterOption = {
  id: "c2",
  title: "第二章",
  globalOrder: 2,
  volumeTitle: "第一卷",
};

const thread: PlotThread = {
  id: "t1",
  projectId: "p1",
  name: "铜镜",
  intent: "灯要在后文对上",
  status: "active",
  sortOrder: 0,
  issues: [],
  hasPlant: true,
  hasPayoff: false,
  lastChapterId: "c1",
  lastChapterTitle: "第一章",
  lastGlobalOrder: 1,
  lastKind: "plant",
  chaptersSinceLast: null,
  gapChapters: [],
  gapRange: null,
  beats: [
    {
      id: "beat-1",
      threadId: "t1",
      chapterId: "c1",
      chapterTitle: "第一章",
      volumeTitle: "第一卷",
      globalOrder: 1,
      kind: "plant",
      note: "灯还亮着",
    },
  ],
};

function clickCell(container: HTMLDivElement, selector: string) {
  const cell = container.querySelector<HTMLButtonElement>(selector);
  expect(cell).not.toBeNull();
  act(() => {
    cell!.click();
  });
}

describe("PlotTimeline 格子编辑", () => {
  it("点击空格子弹窗后保存，调用 createPlotBeat", async () => {
    const { container } = render(
      <PlotTimeline
        projectId="p1"
        threads={[thread]}
        chapters={[chapterA, chapterB]}
        onOpenChapter={vi.fn()}
      />,
    );

    clickCell(container, ".plot-timeline__cell--empty");
    expect(
      document.querySelector(".plot-timeline-edit, [role='dialog']") !== null ||
        container.ownerDocument.querySelector("[role='dialog']") !== null,
    ).toBe(true);

    const dialog = [...document.querySelectorAll("[role='dialog']")].at(-1)!;
    const confirm = [...dialog.querySelectorAll("button")].find((button) =>
      button.textContent?.includes(i18n.t("common.confirm")),
    );
    expect(confirm).toBeTruthy();
    await act(async () => {
      confirm!.click();
    });

    expect(createMutate).toHaveBeenCalledTimes(1);
    expect(createMutate).toHaveBeenCalledWith({
      threadId: "t1",
      data: { chapterId: "c2", kind: "plant", note: "" },
    });
  });

  it("点击已有节拍保存时调用 updatePlotBeat，删除时调用 deletePlotBeat", async () => {
    const { container } = render(
      <PlotTimeline
        projectId="p1"
        threads={[thread]}
        chapters={[chapterA, chapterB]}
        onOpenChapter={vi.fn()}
      />,
    );

    clickCell(container, ".plot-timeline__cell--plant");
    const dialog = [...document.querySelectorAll("[role='dialog']")].at(-1)!;
    const confirm = [...dialog.querySelectorAll("button")].find((button) =>
      button.textContent?.includes(i18n.t("common.confirm")),
    );
    await act(async () => {
      confirm!.click();
    });
    expect(updateMutate).toHaveBeenCalledWith({
      beatId: "beat-1",
      data: { kind: "plant", note: "灯还亮着" },
    });

    clickCell(container, ".plot-timeline__cell--plant");
    const dialogAgain = [...document.querySelectorAll("[role='dialog']")].at(-1)!;
    const remove = [...dialogAgain.querySelectorAll("button")].find((button) =>
      button.textContent?.includes(i18n.t("writing.plotThreads.deleteBeat")),
    );
    await act(async () => {
      remove!.click();
    });
    expect(deleteMutate).toHaveBeenCalledWith("beat-1");
  });

  it("disabled 时空格子点击不弹窗", () => {
    const { container } = render(
      <PlotTimeline
        projectId="p1"
        threads={[thread]}
        chapters={[chapterA, chapterB]}
        disabled
        onOpenChapter={vi.fn()}
      />,
    );
    clickCell(container, ".plot-timeline__cell--empty");
    const editTitles = [...document.querySelectorAll("[role='dialog']")].filter(
      (dialog) => dialog.textContent?.includes(i18n.t("common.confirm")),
    );
    expect(editTitles).toHaveLength(0);
  });
});
