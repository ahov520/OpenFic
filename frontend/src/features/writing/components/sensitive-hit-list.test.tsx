import { Theme } from "@radix-ui/themes";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import zhCN from "@/i18n/locales/zh-CN.json";

import type { SensitiveWordHit } from "../lib/sensitive-words";
import { SensitiveHitList } from "./sensitive-hit-list";

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

const hits: SensitiveWordHit[] = [
  {
    word: "赌博",
    source: "通用类目示例",
    count: 3,
    positions: [
      { start: 0, end: 2 },
      { start: 5, end: 7 },
      { start: 9, end: 11 },
    ],
  },
  {
    word: "枪支",
    source: "",
    count: 1,
    positions: [{ start: 20, end: 22 }],
  },
];

function hitButtons(container: HTMLElement, label: string) {
  return Array.from(container.querySelectorAll<HTMLButtonElement>("button")).filter(
    (button) => button.getAttribute("aria-label") === label,
  );
}

describe("敏感词命中列表（轻渲染）", () => {
  it("渲染命中词、来源与次数", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = render(
      <SensitiveHitList
        hits={hits}
        onJump={() => {}}
        onReplace={() => {}}
      />,
    );

    expect(view.container.textContent).toContain("赌博");
    expect(view.container.textContent).toContain("枪支");
    expect(view.container.textContent).toContain("命中 3 处");
    expect(view.container.textContent).toContain("来源：通用类目示例");
  });

  it("点击定位与替换分别回调对应条目", async () => {
    await i18n.changeLanguage("zh-CN");
    const jumped: string[] = [];
    const replaced: string[] = [];
    const view = render(
      <SensitiveHitList
        hits={hits}
        onJump={(hit) => jumped.push(hit.word)}
        onReplace={(hit) => replaced.push(hit.word)}
      />,
    );

    const jumpButtons = hitButtons(view.container, zhCN.writing.sensitiveWords.jump);
    const replaceButtons = hitButtons(
      view.container,
      zhCN.writing.sensitiveWords.replace.replace("{{word}}", "赌博"),
    );

    act(() => {
      jumpButtons[1]?.click();
      replaceButtons[0]?.click();
    });

    expect(jumped).toEqual(["枪支"]);
    expect(replaced).toEqual(["赌博"]);
  });

  it("空命中显示占位文案；禁用时按钮不可点", async () => {
    await i18n.changeLanguage("zh-CN");
    const empty = render(
      <SensitiveHitList
        hits={[]}
        onJump={() => {}}
        onReplace={() => {}}
      />,
    );
    expect(empty.container.textContent).toContain(zhCN.writing.sensitiveWords.empty);

    const disabled = render(
      <SensitiveHitList
        hits={hits}
        disabled
        onJump={() => {}}
        onReplace={() => {}}
      />,
    );
    for (const button of disabled.container.querySelectorAll("button")) {
      expect(button.disabled).toBe(true);
    }
  });
});
