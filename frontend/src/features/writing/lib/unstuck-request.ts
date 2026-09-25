/**
 * 「卡住了」救援请求。
 *
 * 把结构化救援请求（前情摘要指引 + 本章节拍 + 当前正文结尾）组装成发给
 * Agent 会话的 mention 标记文本；走向由 Agent 按内置 unstuck 技能给出，
 * 这里只负责组装请求，不产出任何正文。
 */

import { buildLineRangeMentionTag } from "@/features/assistant/lib/mention-text";

export const UNSTUCK_SKILL_ID = "builtin-skill--unstuck";
/** 与 backend/app/skills/unstuck.yaml 的 name 字段保持一致；activate_skill 也可按 id 解析。 */
export const UNSTUCK_SKILL_NAME = "卡住了";

export const UNSTUCK_TAIL_MAX_LINES = 12;
export const UNSTUCK_TAIL_MAX_CHARS = 600;

export interface EditorTail {
  /** 结尾窗口文本（已去首尾空白）。 */
  text: string;
  /** 窗口首行行号（1 起，与编辑器行号一致）。 */
  startLine: number;
  /** 窗口末行行号。 */
  endLine: number;
}

/** 取整章纯文本的结尾窗口；整章都是空白时返回 null。 */
export function extractEditorTail(
  docText: string,
  maxLines = UNSTUCK_TAIL_MAX_LINES,
  maxChars = UNSTUCK_TAIL_MAX_CHARS,
): EditorTail | null {
  const lines = docText.replace(/\r\n/g, "\n").split("\n");
  if (lines.every((line) => !line.trim())) return null;

  let start = Math.max(0, lines.length - maxLines);
  const joinTail = () => lines.slice(start).join("\n").trim();
  let text = joinTail();
  while (start < lines.length - 1 && text.length > maxChars) {
    start += 1;
    text = joinTail();
  }
  return { text, startLine: start + 1, endLine: lines.length };
}

export interface UnstuckRequestParams {
  /** 由 buildSkillCommandTag 生成的技能引用标签。 */
  skillTag: string;
  /** 本地化的求助指令（含 3 个走向的输出要求与禁止写正文的约束）。 */
  instruction: string;
  /** 本地化的前情摘要获取指引（复用库内章节摘要，由 Agent 自行读取）。 */
  previousContextLabel: string;
  previousContextHint: string;
  chapterId: string;
  /** 章节显示名，用于结尾快照的 mention 标签。 */
  chapterLabel: string;
  synopsis: string;
  synopsisLabel: string;
  synopsisEmptyHint: string;
  endingLabel: string;
  endingEmptyHint: string;
  /** 编辑器全文（块间以换行分隔）。 */
  docText: string;
}

/** 组装完整救援请求；发送后由后端把 mention 编译为章节锚点与快照引用。 */
export function buildUnstuckRequest(params: UnstuckRequestParams): string {
  const {
    skillTag,
    instruction,
    previousContextLabel,
    previousContextHint,
    chapterId,
    chapterLabel,
    synopsis,
    synopsisLabel,
    synopsisEmptyHint,
    endingLabel,
    endingEmptyHint,
    docText,
  } = params;

  const normalizedSynopsis = synopsis.trim();
  const tail = extractEditorTail(docText);

  const lines = [
    skillTag,
    "",
    instruction,
    "",
    `【${previousContextLabel}】${previousContextHint}`,
    `【${synopsisLabel}】${normalizedSynopsis || synopsisEmptyHint}`,
  ];

  if (tail) {
    lines.push(
      `【${endingLabel}】`,
      buildLineRangeMentionTag({
        chapterId,
        startLine: tail.startLine,
        endLine: tail.endLine,
        label: `${chapterLabel} L${tail.startLine}-${tail.endLine}`,
        snapshotText: tail.text,
      }),
    );
  } else {
    lines.push(`【${endingLabel}】${endingEmptyHint}`);
  }

  return lines.join("\n");
}
