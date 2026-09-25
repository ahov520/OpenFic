import { describe, expect, it } from "vitest";

import {
  cleanupProseLine,
  cleanupProseText,
  convertProsePunctuation,
  DEFAULT_PROSE_FORMAT_CLEANUP_RULES,
  isChapterMarkerLine,
  planParagraphGapCompaction,
  type ProseFormatCleanupRules,
} from "./prose-format-cleanup";

const ALL_ON = DEFAULT_PROSE_FORMAT_CLEANUP_RULES;

function withRules(overrides: Partial<ProseFormatCleanupRules>): ProseFormatCleanupRules {
  return { ...ALL_ON, ...overrides };
}

describe("段间压缩为单换行（yaml:140/219）", () => {
  it("把相邻段落之间的空行和连续换行压成一个换行符", () => {
    expect(cleanupProseText("第一段\n\n第二段", ALL_ON)).toBe("第一段\n第二段");
    expect(cleanupProseText("第一段\n\n\n\n\n第二段", ALL_ON)).toBe("第一段\n第二段");
    expect(cleanupProseText("第一段\n\n第二段\n\n\n第三段", ALL_ON)).toBe("第一段\n第二段\n第三段");
  });

  it("只含空白的行也按空行处理（全角空格、Tab、普通空格混合）", () => {
    expect(cleanupProseText("第一段\n \u3000\t \n\u3000\n第二段", ALL_ON)).toBe("第一段\n第二段");
  });

  it("去掉文档首尾的空行", () => {
    expect(cleanupProseText("\n\n\n第一段\n\n\n", ALL_ON)).toBe("第一段");
  });

  it("统一 CRLF 为单个换行符", () => {
    expect(cleanupProseText("第一段\r\n\r\n第二段\r第三段", ALL_ON)).toBe("第一段\n第二段\n第三段");
  });

  it("章节标记相邻的空行最多保留一个（yaml:219 章节标记前后另算）", () => {
    expect(cleanupProseText("###1.\n\n\n\n第一段", ALL_ON)).toBe("###1.\n\n第一段");
    expect(cleanupProseText("上一节结尾\n\n\n\n###2.\n\n\n第一段", ALL_ON)).toBe(
      "上一节结尾\n\n###2.\n\n第一段",
    );
  });

  it("纯数字标记（yaml:22）与 ###第一章 同样按标记处理", () => {
    expect(cleanupProseText("###第一章\n\n\n第一段", ALL_ON)).toBe("###第一章\n\n第一段");
    expect(cleanupProseText("1.\n\n\n第一段", ALL_ON)).toBe("1.\n\n第一段");
  });

  it("关闭规则时空行原样保留（该规则可单独关闭）", () => {
    const rules = withRules({ compactParagraphGaps: false });
    expect(cleanupProseText("第一段\n\n\n第二段", rules)).toBe("第一段\n\n\n第二段");
    expect(cleanupProseText("###1.\n\n\n\n第一段", rules)).toBe("###1.\n\n\n\n第一段");
  });
});

describe("「不做的事」：不引入缩进、不把段间规范为空行分隔", () => {
  it("不会在段间插入空行：本来就是单换行的段落保持单换行", () => {
    const input = "第一段\n第二段\n第三段";
    expect(cleanupProseText(input, ALL_ON)).toBe(input);
    expect(cleanupProseText(input, ALL_ON)).not.toContain("\n\n");
  });

  it("不会引入任何段首缩进：清理后的每一行都不以空白开头", () => {
    const output = cleanupProseText("　　第一段\n第二段\n\u3000\t第三段", ALL_ON);
    for (const line of output.split("\n")) {
      expect(line).toBe(line.trimStart());
    }
  });

  it("不会给标题或标记行加缩进，行中空白保持不动", () => {
    expect(cleanupProseText("　　###1.", ALL_ON)).toBe("###1.");
    // 逗号隔着空格也按中文语境转全角，但空格本身原样保留
    expect(cleanupProseText("他 说 , 你好", ALL_ON)).toBe("他 说 ， 你好");
    expect(cleanupProseText("你好 世界", ALL_ON)).toBe("你好 世界");
  });
});

describe("去段首全角/半角缩进（yaml:142/220）", () => {
  it("删除段首的全角空格、半角空格、Tab 及其混合", () => {
    expect(cleanupProseText("　　全角缩进", ALL_ON)).toBe("全角缩进");
    expect(cleanupProseText("  半角缩进", ALL_ON)).toBe("半角缩进");
    expect(cleanupProseText("\tTab缩进", ALL_ON)).toBe("Tab缩进");
    expect(cleanupProseText("　 \t\u3000混合缩进", ALL_ON)).toBe("混合缩进");
  });

  it("缩进与标点、空行规则组合时逐行生效", () => {
    expect(cleanupProseText("　　他说,你好.\n\n　　他走了?", ALL_ON)).toBe(
      "他说，你好。\n他走了？",
    );
  });

  it("关闭规则时缩进原样保留", () => {
    expect(cleanupProseText("　　保留缩进", withRules({ trimParagraphIndent: false }))).toBe(
      "　　保留缩进",
    );
  });
});

describe("去行尾空白", () => {
  it("删除行尾的全角/半角空白，行中空白不动", () => {
    expect(cleanupProseText("尾随空白\u3000 \t", ALL_ON)).toBe("尾随空白");
    expect(cleanupProseText("行中 空白 ", ALL_ON)).toBe("行中 空白");
  });

  it("关闭规则时行尾空白原样保留", () => {
    expect(cleanupProseText("尾随空白\u3000", withRules({ trimTrailingWhitespace: false }))).toBe(
      "尾随空白\u3000",
    );
  });
});

describe("全半角标点统一（复用 editor-config.ts 的 HALFWIDTH_PUNCTUATION_MAP 口径）", () => {
  it("转换中文语境下的八种映射标点", () => {
    expect(convertProsePunctuation("你好,世界.真的?没错!听:好;行(可以)")).toBe(
      "你好，世界。真的？没错！听：好；行（可以）",
    );
  });

  it("只转换中文语境：英文句子、URL、版本号原样保留", () => {
    expect(convertProsePunctuation("Hello, world. Really? Yes!")).toBe(
      "Hello, world. Really? Yes!",
    );
    expect(convertProsePunctuation("https://example.com/a?b=1,c")).toBe(
      "https://example.com/a?b=1,c",
    );
    expect(convertProsePunctuation("升级到 3.14 版本")).toBe("升级到 3.14 版本");
    expect(convertProsePunctuation('He said, "ok!" then left.')).toBe('He said, "ok!" then left.');
  });

  it("中英混排时只动紧邻中文的标点", () => {
    expect(convertProsePunctuation('他说:"ok"然后走了')).toBe('他说："ok"然后走了');
    expect(convertProsePunctuation("他笑了(真的)")).toBe("他笑了（真的）");
    expect(convertProsePunctuation("看 example.com,再想想")).toBe("看 example.com，再想想");
  });

  it("英文/URL 片段结尾与中文隔着空白时不转换（误伤场景回归）", () => {
    // 后侧语境只看紧邻字符、不跳过空白：URL/英文句末/日期后的标点不动
    expect(convertProsePunctuation("详情见 https://example.com/a. 详情如下")).toBe(
      "详情见 https://example.com/a. 详情如下",
    );
    expect(convertProsePunctuation("他说 Hello, world. 然后走了")).toBe(
      "他说 Hello, world. 然后走了",
    );
    expect(convertProsePunctuation("写于 2024. 春天")).toBe("写于 2024. 春天");
    expect(convertProsePunctuation("写于 2024, 春天")).toBe("写于 2024, 春天");
    expect(convertProsePunctuation("访问 https://example.com/a, 记得收藏")).toBe(
      "访问 https://example.com/a, 记得收藏",
    );
  });

  it("前侧隔着空白的中文章节仍转换（前侧跳空白取最近有效字符）", () => {
    expect(convertProsePunctuation("他 说 , 你好")).toBe("他 说 ， 你好");
  });

  it("引号不在映射口径内：正文默认半角引号（prose-format.yaml 对话规范）", () => {
    expect(convertProsePunctuation('"你走吧。"他没有动。')).toBe('"你走吧。"他没有动。');
  });

  it("连续半角标点逐个转换（本层转换产生的全角结果计入后续语境）", () => {
    expect(convertProsePunctuation("等一下...!")).toBe("等一下。。。！");
  });

  it("关闭规则时半角标点原样保留", () => {
    expect(cleanupProseText("你好,世界", withRules({ convertPunctuation: false }))).toBe(
      "你好,世界",
    );
  });
});

describe("结构与标记保护", () => {
  it("代码块内容完全不参与缩进与标点替换，空行也逐字保留", () => {
    const input = [
      "前文,你好:",
      "",
      "",
      "```text",
      "  indented, code: true",
      "second   line?",
      "",
      "  const a = 1;",
      "```",
      "",
      "",
      "后文,你好",
    ].join("\n");
    const output = cleanupProseText(input, ALL_ON);
    const outputLines = output.split("\n");

    expect(outputLines[0]).toBe("前文，你好：");
    // 围栏行与围栏内内容逐字保留
    expect(outputLines[1]).toBe("```text");
    expect(outputLines[2]).toBe("  indented, code: true");
    expect(outputLines[3]).toBe("second   line?");
    expect(outputLines[4]).toBe("");
    expect(outputLines[5]).toBe("  const a = 1;");
    expect(outputLines[6]).toBe("```");
    expect(outputLines[7]).toBe("后文，你好");
  });

  it("未闭合的代码围栏之后全部按代码块保护", () => {
    const input = "前文,你好:\n```python\nx, y = 1, 2\n后文,不动";
    const output = cleanupProseText(input, ALL_ON);
    expect(output).toBe("前文，你好：\n```python\nx, y = 1, 2\n后文,不动");
  });

  it("统一章节标记原样保留（yaml:20-21 两种格式）", () => {
    expect(cleanupProseText("###1.", ALL_ON)).toBe("###1.");
    expect(cleanupProseText("###第一章", ALL_ON)).toBe("###第一章");
    expect(cleanupProseText("###2.\n\n###第三章\n\n###4.", ALL_ON)).toBe(
      "###2.\n\n###第三章\n\n###4.",
    );
  });

  it("标记行内的句点不被转全角，标记之后的标题文本仍按规则清理", () => {
    expect(cleanupProseText("###1.开场", ALL_ON)).toBe("###1.开场");
    expect(cleanupProseText("###1.他说,走", ALL_ON)).toBe("###1.他说，走");
    expect(cleanupProseText("1.他走了", ALL_ON)).toBe("1.他走了");
  });

  it("isChapterMarkerLine 识别 yaml:20-22 的三种格式，不误判普通段落", () => {
    expect(isChapterMarkerLine("###1.")).toBe(true);
    expect(isChapterMarkerLine("###第一章")).toBe(true);
    expect(isChapterMarkerLine("1.")).toBe(true);
    expect(isChapterMarkerLine("　　###2.")).toBe(true);
    expect(isChapterMarkerLine("第一段正文")).toBe(false);
    expect(isChapterMarkerLine("### 标题")).toBe(false);
    expect(isChapterMarkerLine("3.14 是圆周率")).toBe(false);
  });
});

describe("组合输入", () => {
  it("缩进、空行、行尾空白、标点一起清理", () => {
    const input = [
      '　　她把杯子放下,说道:"你走吧。" ',
      "",
      '　　他没有动,她又说:"我说,你走吧。"\u3000',
    ].join("\n");
    const expected = ['她把杯子放下，说道："你走吧。"', '他没有动，她又说："我说，你走吧。"'].join(
      "\n",
    );
    expect(cleanupProseText(input, ALL_ON)).toBe(expected);
  });

  it("标记 + 代码块 + 正文混排的整章输入", () => {
    const input = [
      "　　###1.",
      "",
      "",
      '　　她把杯子放下,说道:"你走吧。"',
      "",
      "```text",
      "keep,  this",
      "```",
      "　　他没有动?",
    ].join("\n");
    const expected = [
      "###1.",
      "",
      '她把杯子放下，说道："你走吧。"',
      "```text",
      "keep,  this",
      "```",
      "他没有动？",
    ].join("\n");
    expect(cleanupProseText(input, ALL_ON)).toBe(expected);
  });

  it("空文本与纯空白文本不产生变化", () => {
    expect(cleanupProseText("", ALL_ON)).toBe("");
    expect(cleanupProseText("\n\n\u3000\n", ALL_ON)).toBe("");
  });
});

describe("planParagraphGapCompaction（编辑器集成层复用的空行去留计划）", () => {
  it("对段落空行组返回全删，对标记相邻空行组保留第一个", () => {
    expect(planParagraphGapCompaction(["content", "blank", "blank", "content"], true)).toEqual([
      false,
      true,
      true,
      false,
    ]);
    expect(planParagraphGapCompaction(["marker", "blank", "blank", "content"], true)).toEqual([
      false,
      false,
      true,
      false,
    ]);
    expect(planParagraphGapCompaction(["content", "blank", "marker"], true)).toEqual([
      false,
      false,
      false,
    ]);
  });

  it("文档首尾空行与代码块相邻空行都按普通空行压缩", () => {
    expect(planParagraphGapCompaction(["blank", "content", "blank"], true)).toEqual([
      true,
      false,
      true,
    ]);
    expect(planParagraphGapCompaction(["content", "blank", "code"], true)).toEqual([
      false,
      true,
      false,
    ]);
  });

  it("规则关闭时全部保留", () => {
    expect(planParagraphGapCompaction(["content", "blank", "content"], false)).toEqual([
      false,
      false,
      false,
    ]);
  });
});

describe("cleanupProseLine", () => {
  it("只处理单行，不做跨行压缩", () => {
    expect(cleanupProseLine("　　你好,世界 ", ALL_ON)).toBe("你好，世界");
  });
});
