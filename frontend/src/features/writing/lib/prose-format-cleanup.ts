/**
 * Prose Format Cleanup（「一键排版」纯函数层）
 *
 * 按正文格式基准（backend/app/skills/prose-format.yaml）对章节文本做确定性清理。
 * 规则与 yaml 的对应关系：
 * - yaml:140 / yaml:219：正文相邻段落之间只允许一个换行符 `\n`，去空行/连续换行；
 *   yaml:219「章节标记前后另算」——标记相邻的空行最多保留一个（对齐番茄/黑岩模板）。
 * - yaml:142 / yaml:220：无缩进——删除段首的全角空格（\u3000）与半角空白。
 * - 行尾空白：随无缩进一并清理，避免不可见字符残留。
 * - 全半角标点统一：复用 editor-config.ts 的 HALFWIDTH_PUNCTUATION_MAP 映射口径
 *   （避免两套约定），并只转换中文语境下的标点，英文句子与 URL 不受影响。
 *
 * 结构保护：
 * - 代码块（``` 围栏区域，含围栏行）内容完全不参与缩进与标点替换；
 * - 统一章节标记（`###1.`、`###第一章`，yaml:20-21；纯数字 `1.`，yaml:22）原样保留。
 *
 * 本模块不依赖任何节点结构：编辑器集成（按节点类型分流、单笔事务派发）
 * 见 ./prose-format-cleanup-editor。
 */

import { HALFWIDTH_PUNCTUATION_MAP } from "./editor-config";

/** 「一键排版」可勾选的清理规则，与 yaml 规则逐条对应 */
export interface ProseFormatCleanupRules {
  /** 段间压缩为单换行（去空行/连续换行，yaml:140/219） */
  compactParagraphGaps: boolean;
  /** 去段首全角（\u3000）/半角缩进（yaml:142/220） */
  trimParagraphIndent: boolean;
  /** 去行尾空白 */
  trimTrailingWhitespace: boolean;
  /** 全半角标点统一（仅中文语境） */
  convertPunctuation: boolean;
}

/** 对话框默认全开 */
export const DEFAULT_PROSE_FORMAT_CLEANUP_RULES: ProseFormatCleanupRules = {
  compactParagraphGaps: true,
  trimParagraphIndent: true,
  trimTrailingWhitespace: true,
  convertPunctuation: true,
};

export interface ProseFormatCleanupRuleOption {
  id: keyof ProseFormatCleanupRules;
  labelKey: string;
  hintKey: string;
}

/** 规则勾选对话框的渲染顺序 */
export const PROSE_FORMAT_CLEANUP_RULE_OPTIONS: readonly ProseFormatCleanupRuleOption[] = [
  {
    id: "compactParagraphGaps",
    labelKey: "writing.proseFormatCleanup.ruleCompactParagraphGaps",
    hintKey: "writing.proseFormatCleanup.ruleCompactParagraphGapsHint",
  },
  {
    id: "trimParagraphIndent",
    labelKey: "writing.proseFormatCleanup.ruleTrimParagraphIndent",
    hintKey: "writing.proseFormatCleanup.ruleTrimParagraphIndentHint",
  },
  {
    id: "trimTrailingWhitespace",
    labelKey: "writing.proseFormatCleanup.ruleTrimTrailingWhitespace",
    hintKey: "writing.proseFormatCleanup.ruleTrimTrailingWhitespaceHint",
  },
  {
    id: "convertPunctuation",
    labelKey: "writing.proseFormatCleanup.ruleConvertPunctuation",
    hintKey: "writing.proseFormatCleanup.ruleConvertPunctuationHint",
  },
];

/** 一行（或一个顶层节点）在排版里的角色；`code` 表示受保护的代码块区域 */
export type ProseFormatLineKind = "content" | "marker" | "blank" | "code";

// 章节标记（yaml:20-22）：`###1.`、`###第一章`，以及纯数字 `1.`。
// 标记前缀内的半角标点（`1.` 的句点）不参与全角转换，标记行原样保留。
const CHAPTER_MARKER_PREFIX_SOURCE =
  "^(?:#{3}\\s*\\d+\\.(?!\\d)|#{3}\\s*第[一二三四五六七八九十百千万两0-9]+章|\\d+\\.(?!\\d))";
const CHAPTER_MARKER_PREFIX_RE = new RegExp(CHAPTER_MARKER_PREFIX_SOURCE);

// ``` 围栏行；围栏之间（含围栏行本身）整段视为代码块。
// 纯文本层与编辑器集成层共用本判定，保证「代码块内容不动」口径一致。
const CODE_FENCE_RE = /^\s*`{3}/;

/** 是否是 ``` 围栏行（编辑器集成层据此把围栏段落序列整段映射为受保护区域） */
export function isCodeFenceLine(line: string): boolean {
  return CODE_FENCE_RE.test(line);
}

// 中文语境：判定半角标点是否转换的邻居字符范围（汉字、全角标点、弯引号等）
const CJK_CONTEXT_RE =
  /[\u2018-\u201d\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]/;

function isCjkContextChar(char: string | undefined): boolean {
  return char !== undefined && CJK_CONTEXT_RE.test(char);
}

function isVisible(char: string): boolean {
  return !/\s/u.test(char);
}

/**
 * 行首是否是统一章节标记（yaml:20-22 的三种格式）。
 * 用于两件事：标记相邻空行「另算」；标记前缀内的半角标点不转换。
 */
export function isChapterMarkerLine(line: string): boolean {
  return CHAPTER_MARKER_PREFIX_RE.test(line.trim());
}

/**
 * 半角标点 → 全角，复用 editor-config.ts 的 HALFWIDTH_PUNCTUATION_MAP 映射表
 * （避免两套约定）。语境门槛是清理层新增的判断，与输入时的自动转换无关；
 * 引号不在映射表内、不参与转换（正文默认就是半角 `""`，与 prose-format.yaml
 * 对话规范一致）。
 *
 * 语境判定（尽量只动中文句子里的标点，两侧不对称）：
 * - 前侧：向前跳过空白取最近的有效字符（含已转换的全角结果），
 *   `你好,世界`、`他 说 , 你好` 均转换；
 * - 后侧：只看紧邻的下一个字符、不跳过空白——英文/URL 片段与中文之间通常隔着
 *   空白，跳空白取到的中文并不代表该标点属于中文句子，因此
 *   `详情见 https://example.com/a. 详情如下`、`他说 Hello, world. 然后走了`、
 *   `写于 2024. 春天` 里的半角标点全部原样保留。
 */
export function convertProsePunctuation(line: string): string {
  const chars = Array.from(line);
  // 章节标记前缀（如 `###1.`）内的半角标点原样保留
  const markerMatch = line.match(CHAPTER_MARKER_PREFIX_RE);
  const protectedCount = markerMatch ? Array.from(markerMatch[0]).length : 0;

  const out: string[] = [];
  // 已输出的字符参与前置语境（本层转换产生的全角结果计入），跳过空白取最近的有效字符
  const previousVisible = (from: number): string | undefined => {
    for (let i = from; i >= 0; i -= 1) {
      const candidate = out[i];
      if (candidate !== undefined && isVisible(candidate)) return candidate;
    }
    return undefined;
  };

  for (let index = 0; index < chars.length; index += 1) {
    const char = chars[index] as string;
    const converted = HALFWIDTH_PUNCTUATION_MAP[char];
    if (converted === undefined || index < protectedCount) {
      out.push(char);
      continue;
    }

    const previous = previousVisible(index - 1);
    const next = chars[index + 1];
    out.push(isCjkContextChar(previous) || isCjkContextChar(next) ? converted : char);
  }

  return out.join("");
}

/** 单行清理：去段首缩进 → 去行尾空白 → 全半角标点统一（各自可单独关闭） */
export function cleanupProseLine(line: string, rules: ProseFormatCleanupRules): string {
  let result = line;
  // \s 覆盖全角空格（\u3000）、半角空格、Tab、不换行空格等空白字符
  if (rules.trimParagraphIndent) {
    result = result.replace(/^\s+/u, "");
  }
  if (rules.trimTrailingWhitespace) {
    result = result.replace(/\s+$/u, "");
  }
  if (rules.convertPunctuation) {
    result = convertProsePunctuation(result);
  }
  return result;
}

/**
 * 按「段间压缩」规则给出每个空行的去留（仅 `blank` 行可能被标记删除）：
 * - 段落与段落之间的空行全部去掉（yaml:140/219）；
 * - 章节标记相邻的空行最多保留一个（yaml:219「章节标记前后另算」，对齐平台模板）；
 * - 文档首尾的空行全部去掉。
 *
 * 编辑器集成层把顶层节点映射为同一套 kind 后复用本函数，保证两层行为一致。
 */
export function planParagraphGapCompaction(
  kinds: readonly ProseFormatLineKind[],
  enabled: boolean,
): boolean[] {
  const remove = kinds.map(() => false);
  if (!enabled) return remove;

  let index = 0;
  while (index < kinds.length) {
    if (kinds[index] !== "blank") {
      index += 1;
      continue;
    }

    let runEnd = index;
    while (runEnd < kinds.length && kinds[runEnd] === "blank") {
      runEnd += 1;
    }

    const previous = index > 0 ? kinds[index - 1] : undefined;
    const next = runEnd < kinds.length ? kinds[runEnd] : undefined;
    const atDocumentEdge = previous === undefined || next === undefined;
    const markerAdjacent = previous === "marker" || next === "marker";
    // 标记相邻时保留该空行组的第一个，多余的仍然压掉
    const keepFirst = !atDocumentEdge && markerAdjacent;

    for (let i = index + (keepFirst ? 1 : 0); i < runEnd; i += 1) {
      remove[i] = true;
    }
    index = runEnd;
  }

  return remove;
}

function classifyProseLines(lines: readonly string[]): ProseFormatLineKind[] {
  const kinds: ProseFormatLineKind[] = [];
  let inCodeFence = false;

  for (const line of lines) {
    if (isCodeFenceLine(line)) {
      inCodeFence = !inCodeFence;
      kinds.push("code");
      continue;
    }
    if (inCodeFence) {
      kinds.push("code");
      continue;
    }
    if (!line.trim()) {
      kinds.push("blank");
      continue;
    }
    kinds.push(isChapterMarkerLine(line) ? "marker" : "content");
  }

  return kinds;
}

/**
 * 整章文本清理（存储层的新行分隔格式：每个段落一行，空段落即空行）。
 * 这是纯文本层的整章入口（供存储格式文本与测试使用）；编辑器路径不经过本函数，
 * 而是按顶层节点逐段调用 cleanupProseLine，并用 isCodeFenceLine 维护同一套
 * 围栏状态机（见 ./prose-format-cleanup-editor），两层行为保持一致。
 * - `\r\n`/`\r` 统一为 `\n`；
 * - 代码块区域（``` 围栏，含围栏行）逐字保留；
 * - 空行压缩、段首缩进、行尾空白、标点统一按规则逐行执行。
 */
export function cleanupProseText(text: string, rules: ProseFormatCleanupRules): string {
  if (!text) return text;

  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const kinds = classifyProseLines(lines);
  const removeBlanks = planParagraphGapCompaction(kinds, rules.compactParagraphGaps);

  const result: string[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    if (removeBlanks[index]) continue;

    const kind = kinds[index] as ProseFormatLineKind;
    const line = lines[index] as string;
    result.push(kind === "content" || kind === "marker" ? cleanupProseLine(line, rules) : line);
  }

  return result.join("\n");
}
