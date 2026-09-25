import { Theme } from "@radix-ui/themes";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import i18n from "@/i18n";
import zhCN from "@/i18n/locales/zh-CN.json";

import type { ProseFormatCleanupRules } from "../lib/prose-format-cleanup";
import { DEFAULT_PROSE_FORMAT_CLEANUP_RULES } from "../lib/prose-format-cleanup";
import { ProseFormatCleanupDialog } from "./prose-format-cleanup-dialog";

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
  document.body.innerHTML = "";
});

function dialogRoot() {
  // Radix Dialog 渲染在 portal 里，从 body 上查找
  return document.body;
}

function checkboxes() {
  return Array.from(dialogRoot().querySelectorAll<HTMLButtonElement>('[role="checkbox"]'));
}

function findButton(label: string) {
  return Array.from(dialogRoot().querySelectorAll<HTMLButtonElement>("button")).find(
    (button) => button.textContent?.trim() === label,
  );
}

describe("一键排版对话框（轻渲染）", () => {
  it("渲染执行按钮、四条规则开关，且默认全开", async () => {
    await i18n.changeLanguage("zh-CN");
    const applied: ProseFormatCleanupRules[] = [];
    render(
      <ProseFormatCleanupDialog
        open
        onOpenChange={() => {}}
        onApply={(rules) => applied.push(rules)}
      />,
    );

    expect(findButton(zhCN.writing.proseFormatCleanup.apply)).toBeDefined();
    expect(dialogRoot().textContent).toContain(zhCN.writing.proseFormatCleanup.title);

    const toggles = checkboxes();
    expect(toggles).toHaveLength(4);
    for (const toggle of toggles) {
      expect(toggle.getAttribute("aria-checked")).toBe("true");
    }

    const apply = findButton(zhCN.writing.proseFormatCleanup.apply);
    act(() => {
      apply?.click();
    });
    expect(applied).toEqual([DEFAULT_PROSE_FORMAT_CLEANUP_RULES]);
  });

  it("取消勾选的规则按关传出：只关掉标点规则，其余保持全开", async () => {
    await i18n.changeLanguage("zh-CN");
    let applied: ProseFormatCleanupRules | null = null;
    render(
      <ProseFormatCleanupDialog
        open
        onOpenChange={() => {}}
        onApply={(rules) => {
          applied = rules;
        }}
      />,
    );

    const toggles = checkboxes();
    // 顺序与 PROSE_FORMAT_CLEANUP_RULE_OPTIONS 一致：标点规则是第四个
    const punctuation = toggles[3];
    expect(punctuation?.getAttribute("aria-checked")).toBe("true");
    act(() => {
      punctuation?.click();
    });
    expect(punctuation?.getAttribute("aria-checked")).toBe("false");

    act(() => {
      findButton(zhCN.writing.proseFormatCleanup.apply)?.click();
    });
    expect(applied).toEqual({
      compactParagraphGaps: true,
      trimParagraphIndent: true,
      trimTrailingWhitespace: true,
      convertPunctuation: false,
    });
  });

  it("工具栏入口与各规则的中文文案按 zh-CN 口径存在", async () => {
    await i18n.changeLanguage("zh-CN");
    expect(zhCN.writing.proseFormatCleanup.label).toBe("一键排版");
    expect(zhCN.writing.proseFormatCleanup.ruleCompactParagraphGaps).toBe("段间压缩为单换行");
    expect(zhCN.writing.proseFormatCleanup.ruleTrimParagraphIndent).toBe("去掉段首缩进");
    expect(zhCN.writing.proseFormatCleanup.ruleTrimTrailingWhitespace).toBe("去掉行尾空白");
    expect(zhCN.writing.proseFormatCleanup.ruleConvertPunctuation).toBe("半角标点转全角");
  });
});
