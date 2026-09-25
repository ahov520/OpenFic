import { describe, expect, it } from "vitest";

import {
  UNSTUCK_SKILL_ID,
  UNSTUCK_SKILL_NAME,
  buildUnstuckRequest,
  extractEditorTail,
  type UnstuckRequestParams,
} from "./unstuck-request";

const baseParams: UnstuckRequestParams = {
  skillTag: `<of-skill id="${UNSTUCK_SKILL_ID}" name="${UNSTUCK_SKILL_NAME}" />`,
  instruction: "只要走向，不要正文。",
  previousContextLabel: "前情摘要",
  previousContextHint: "先读章节摘要。",
  chapterId: "chapter-1",
  chapterLabel: "第三章",
  synopsis: "  主角拿到铜钥匙。 ",
  synopsisLabel: "本章节拍",
  synopsisEmptyHint: "(未填写)",
  endingLabel: "当前正文结尾",
  endingEmptyHint: "(本章还没有正文)",
  docText: "第一段。\n第二段。",
};

describe("提取正文结尾窗口", () => {
  it("空白章节取不到结尾窗口", () => {
    expect(extractEditorTail("")).toBeNull();
    expect(extractEditorTail("\n \n\t\n")).toBeNull();
  });

  it("短章节返回全文，行号从 1 起", () => {
    expect(extractEditorTail("第一段。\n\n第二段。")).toEqual({
      text: "第一段。\n\n第二段。",
      startLine: 1,
      endLine: 3,
    });
  });

  it("超过行数上限时只取末尾窗口", () => {
    const lines = Array.from({ length: 20 }, (_, index) => `第${index + 1}行`);
    const tail = extractEditorTail(lines.join("\n"), 12, 600);
    expect(tail).not.toBeNull();
    expect(tail?.startLine).toBe(9);
    expect(tail?.endLine).toBe(20);
    expect(tail?.text.split("\n")[0]).toBe("第9行");
    expect(tail?.text.split("\n")).toHaveLength(12);
  });

  it("超过字数上限时按整行向前收缩", () => {
    const lines = ["短", "一".repeat(400), "二".repeat(400), "尾行"];
    const tail = extractEditorTail(lines.join("\n"), 12, 500);
    expect(tail?.text).toBe(`${"二".repeat(400)}\n尾行`);
    expect(tail?.startLine).toBe(3);
    expect(tail?.endLine).toBe(4);
  });

  it("字数上限极小时至少保留末行", () => {
    const lines = ["短", "一".repeat(400), "二".repeat(400), "尾行"];
    const tail = extractEditorTail(lines.join("\n"), 12, 2);
    expect(tail).toEqual({ text: "尾行", startLine: 4, endLine: 4 });
  });

  it("CRLF 一律按行拆分", () => {
    expect(extractEditorTail("甲。\r\n乙。")).toEqual({
      text: "甲。\n乙。",
      startLine: 1,
      endLine: 2,
    });
  });
});

describe("组装救援请求", () => {
  it("请求里带技能引用、指令与前情指引", () => {
    const markup = buildUnstuckRequest(baseParams);
    expect(markup).toContain(`<of-skill id="${UNSTUCK_SKILL_ID}"`);
    expect(markup).toContain("只要走向，不要正文。");
    expect(markup).toContain("【前情摘要】先读章节摘要。");
  });

  it("有梗概与正文时嵌结尾快照，行号与文本对应", () => {
    const markup = buildUnstuckRequest(baseParams);
    expect(markup).toContain("【本章节拍】主角拿到铜钥匙。");
    expect(markup).toContain("【当前正文结尾】");
    expect(markup).toContain(
      '<of-mention chapter_id="chapter-1" line_start="1" line_end="2" label="第三章 L1-2">第一段。\n第二段。</of-mention>',
    );
    expect(markup).not.toContain("(本章还没有正文)");
  });

  it("梗概与正文都为空时走兜底文案", () => {
    const markup = buildUnstuckRequest({ ...baseParams, synopsis: "  ", docText: "\n \n" });
    expect(markup).toContain("【本章节拍】(未填写)");
    expect(markup).toContain("【当前正文结尾】(本章还没有正文)");
    expect(markup).not.toContain("<of-mention chapter_id=");
  });

  it("技能常量与内置 YAML 约定一致", () => {
    expect(UNSTUCK_SKILL_ID).toBe("builtin-skill--unstuck");
    expect(UNSTUCK_SKILL_NAME).toBe("卡住了");
  });
});
