/**
 * Sensitive Words（敏感词/平台违禁词扫描）
 *
 * 扫描口径（定死，不做其他变体归一）：
 * - 精确子串匹配（区分大小写）；
 * - 可选全/半角宽度归一化（全角 ASCII/空格 → 半角，逐字符等长映射，
 *   偏移不漂移）；不做简繁、形近、同音等变体归一。
 * - 词表合并为单次交替正则（按词长降序，同位置最长词优先），
 *   命中不重叠（匹配后从其后继续扫描）。
 *
 * 防抖：输入停止 ≥300ms 后对整章做一次扫描（而非逐击键），
 * 计时器通过 options 注入以便测试。
 */

export const SENSITIVE_SCAN_DEBOUNCE_MS = 300;

/** 工具栏 extraActions 入口的稳定 id 与 i18n 文案 key（chapter-editor 引用） */
export const SENSITIVE_WORDS_ACTION_ID = "sensitive-words";
export const SENSITIVE_WORDS_LABEL_KEY = "writing.sensitiveWords.label";

export interface SensitiveWordEntry {
  word: string;
  source: string;
}

export interface SensitiveWordPosition {
  /** 命中起始偏移（扫描文本的半开区间 [start, end)） */
  start: number;
  end: number;
}

export interface SensitiveWordHit {
  /** 命中词（词表原词） */
  word: string;
  /** 词库来源标注 */
  source: string;
  count: number;
  /** 全部命中位置，按出现次序升序 */
  positions: SensitiveWordPosition[];
}

export interface SensitiveScanResult {
  hits: SensitiveWordHit[];
  totalMatches: number;
}

export interface SensitiveScanOptions {
  /** 是否做全/半角宽度归一化（默认开启） */
  normalizeWidth?: boolean;
}

/** 全角 ASCII（\uFF01-\uFF5E）与全角空格 → 半角；逐字符等长，偏移不变。 */
export function normalizeSensitiveText(text: string): string {
  let result = "";
  for (const char of text) {
    const code = char.codePointAt(0) ?? 0;
    if (code >= 0xff01 && code <= 0xff5e) {
      result += String.fromCharCode(code - 0xfee0);
    } else if (code === 0x3000) {
      result += " ";
    } else {
      result += char;
    }
  }
  return result;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function compileWords(
  words: readonly SensitiveWordEntry[],
  normalizeWidth: boolean,
): { alternatives: string[]; byNormalizedWord: Map<string, SensitiveWordEntry> } {
  const byNormalizedWord = new Map<string, SensitiveWordEntry>();
  const alternatives: string[] = [];
  const seen = new Set<string>();

  // 词长降序：同位置最长词优先命中
  const sorted = [...words].sort((left, right) => right.word.length - left.word.length);
  for (const entry of sorted) {
    const normalizedWord = normalizeWidth ? normalizeSensitiveText(entry.word) : entry.word;
    const trimmed = normalizedWord.trim();
    if (!trimmed) continue;
    const key = normalizeWidth ? trimmed : entry.word;
    if (seen.has(key)) continue;
    seen.add(key);
    alternatives.push(escapeRegExp(normalizedWord.trim()));
    byNormalizedWord.set(normalizedWord.trim(), entry);
  }
  return { alternatives, byNormalizedWord };
}

/**
 * 整章一次扫描：返回每个命中词的次数与多位置列表。
 * 扫描在宽度归一化后的文本上进行；宽度映射逐字符等长，
 * 命中偏移可直接用于原文与编辑器纯文本。
 */
export function scanSensitiveWords(
  text: string,
  words: readonly SensitiveWordEntry[],
  options: SensitiveScanOptions = {},
): SensitiveScanResult {
  const normalizeWidth = options.normalizeWidth ?? true;
  if (!text || words.length === 0) {
    return { hits: [], totalMatches: 0 };
  }

  const { alternatives, byNormalizedWord } = compileWords(words, normalizeWidth);
  if (alternatives.length === 0) {
    return { hits: [], totalMatches: 0 };
  }

  const haystack = normalizeWidth ? normalizeSensitiveText(text) : text;
  const pattern = new RegExp(`(?:${alternatives.join("|")})`, "gu");

  const byWord = new Map<string, SensitiveWordHit>();
  let totalMatches = 0;
  for (const match of haystack.matchAll(pattern)) {
    const matched = match[0];
    const entry = byNormalizedWord.get(matched);
    if (!entry) continue;
    const start = match.index ?? 0;
    let hit = byWord.get(entry.word);
    if (!hit) {
      hit = { word: entry.word, source: entry.source, count: 0, positions: [] };
      byWord.set(entry.word, hit);
    }
    hit.positions.push({ start, end: start + matched.length });
    hit.count += 1;
    totalMatches += 1;
  }

  const hits = [...byWord.values()].sort(
    (left, right) => left.positions[0]!.start - right.positions[0]!.start,
  );
  return { hits, totalMatches };
}

export interface SensitiveScanDebounceOptions {
  /** 输入停止多少毫秒后扫描（默认 300） */
  delayMs?: number;
  /** 计时器注入（测试用假调度器断言整章一次扫描） */
  setTimer?: (handler: () => void, delayMs: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

/**
 * 防抖包装：连续调用只在停止触发 ≥delayMs 后执行一次，
 * 参数取最后一次调用。计时器可注入替换（测试不依赖真实时间）。
 */
export interface SensitiveScanDebouncedFn<A extends unknown[]> {
  (...args: A): void;
  /** 取消挂起的扫描（组件卸载/清理时调用，避免回调触达已销毁实例） */
  cancel: () => void;
}

export function debounceSensitiveScan<A extends unknown[]>(
  fn: (...args: A) => void,
  options: SensitiveScanDebounceOptions = {},
): SensitiveScanDebouncedFn<A> {
  const delayMs = options.delayMs ?? SENSITIVE_SCAN_DEBOUNCE_MS;
  const setTimer = options.setTimer ?? ((handler, ms) => window.setTimeout(handler, ms));
  const clearTimer = options.clearTimer ?? ((handle) => window.clearTimeout(handle as number));

  let handle: unknown = null;
  const debounced = (...args: A) => {
    if (handle !== null) clearTimer(handle);
    handle = setTimer(() => {
      handle = null;
      fn(...args);
    }, delayMs);
  };
  debounced.cancel = () => {
    if (handle !== null) {
      clearTimer(handle);
      handle = null;
    }
  };
  return debounced;
}
