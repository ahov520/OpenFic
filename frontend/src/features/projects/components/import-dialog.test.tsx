import { Theme } from "@radix-ui/themes";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import zhCN from "@/i18n/locales/zh-CN.json";

import { ImportDialog } from "./import-dialog";

vi.mock("../lib/import-api", () => ({
  confirmImportStream: vi.fn(),
  previewImportFile: vi.fn(),
  DEFAULT_IMPORT_CHUNK_SIZE: 800,
  MAX_IMPORT_CHUNK_SIZE: 100_000,
}));

vi.mock("./cover-cropper", () => ({
  CoverCropper: () => null,
}));

const mounted: Array<{ root: Root; container: HTMLDivElement }> = [];

function renderDialog() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <Theme>
        <ImportDialog
          open
          onOpenChange={() => {}}
        />
      </Theme>,
    );
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

describe("导入对话框文件格式（轻渲染）", () => {
  it("文件选择器接受 .docx/.epub 新格式", async () => {
    await i18n.changeLanguage("zh-CN");
    const view = renderDialog();

    const fileInput = document.body.querySelector<HTMLInputElement>(
      'input[type="file"].import-dialog-file-input',
    );
    expect(fileInput).not.toBeNull();

    const accepted = (fileInput?.getAttribute("accept") ?? "").split(",");
    for (const suffix of [".txt", ".md", ".zip", ".docx", ".epub"]) {
      expect(accepted).toContain(suffix);
    }
    expect(document.body.textContent).toContain(zhCN.import.supportedFormats);
  });
});
