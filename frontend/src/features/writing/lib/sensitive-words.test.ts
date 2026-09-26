import { describe, expect, it, vi } from "vitest";

import {
  SENSITIVE_SCAN_DEBOUNCE_MS,
  debounceSensitiveScan,
  normalizeSensitiveText,
  scanSensitiveWords,
  type SensitiveWordEntry,
} from "./sensitive-words";

const WORDS: SensitiveWordEntry[] = [
  { word: "赌博", source: "通用类目示例" },
  { word: "枪支", source: "通用类目示例" },
  { word: "代购彩票", source: "来源B" },
];

describe("scanSensitiveWords", () => {
  it("统计命中词与次数（精确子串匹配）", () => {
    const result = scanSensitiveWords("他去赌博，又参与赌博。", WORDS);
    expect(result.totalMatches).toBe(2);
    expect(result.hits).toHaveLength(1);
    expect(result.hits[0]).toMatchObject({ word: "赌博", source: "通用类目示例", count: 2 });
  });

  it("多命中词按首次出现位置排序，多位置列表完整", () => {
    const text = "枪支出货。之后他又赌博，再赌博，最后卖枪支。".replace("卖枪支", "接触枪支");
    const result = scanSensitiveWords(text, WORDS);
    expect(result.hits.map((hit) => hit.word)).toEqual(["枪支", "赌博"]);
    expect(result.hits[0]!.positions).toEqual([
      { start: 0, end: 2 },
      { start: 20, end: 22 },
    ]);
    expect(result.hits[0]!.count).toBe(2);
  });

  it("不做简繁/形近/同音变体：变体不命中（口径定死）", () => {
    const variants = "賭博（繁体）\ndu博（拼音）\n赌愽（形近）";
    const result = scanSensitiveWords(variants, WORDS);
    expect(result.hits).toEqual([]);
    expect(result.totalMatches).toBe(0);
  });

  it("大小写区分：精确匹配不做大小写折叠", () => {
    const result = scanSensitiveWords("abc 内容", [{ word: "ABC", source: "" }]);
    expect(result.totalMatches).toBe(0);
  });

  it("全/半角归一化开关：开启后全角命中，关闭后不命中", () => {
    const text = "加入ＱＱ群了解详情";
    const words: SensitiveWordEntry[] = [{ word: "QQ群", source: "来源C" }];

    expect(scanSensitiveWords(text, words, { normalizeWidth: true }).totalMatches).toBe(1);
    expect(scanSensitiveWords(text, words, { normalizeWidth: false }).totalMatches).toBe(0);
  });

  it("全角标点归一化：全角逗号不等于半角逗号之外的字符", () => {
    expect(normalizeSensitiveText("赌　博，ＡＢ")).toBe("赌 博,AB");
  });

  it("同位置多词命中时长词优先（词长降序交替正则）", () => {
    const words: SensitiveWordEntry[] = [
      { word: "代购", source: "短词" },
      { word: "代购彩票", source: "长词" },
    ];
    const result = scanSensitiveWords("代购彩票上线", words);
    // 长词优先命中且不重叠：短词不再单独计数
    expect(result.totalMatches).toBe(1);
    expect(result.hits[0]).toMatchObject({ word: "代购彩票", source: "长词" });
  });

  it("词表为空或文本为空时零命中，不构建空正则", () => {
    expect(scanSensitiveWords("", WORDS)).toEqual({ hits: [], totalMatches: 0 });
    expect(scanSensitiveWords("赌博", [])).toEqual({ hits: [], totalMatches: 0 });
  });

  it("词内含正则元字符时按字面匹配", () => {
    const words: SensitiveWordEntry[] = [{ word: "代.理", source: "" }];
    expect(scanSensitiveWords("联系代.理", words).totalMatches).toBe(1);
    expect(scanSensitiveWords("联系代X理", words).totalMatches).toBe(0);
  });
});

describe("debounceSensitiveScan", () => {
  function fakeScheduler() {
    let nextId = 0;
    const scheduled: Array<{ id: number; handler: () => void; delayMs: number }> = [];
    const setTimer = (handler: () => void, delayMs: number) => {
      const id = ++nextId;
      scheduled.push({ id, handler, delayMs });
      return id;
    };
    const clearTimer = (handle: unknown) => {
      const index = scheduled.findIndex((entry) => entry.id === handle);
      if (index >= 0) scheduled.splice(index, 1);
    };
    return {
      scheduled,
      setTimer,
      clearTimer,
      runLast() {
        const last = scheduled.at(-1);
        if (last) last.handler();
      },
    };
  }

  it("默认延迟为 300ms：输入停止 ≥300ms 后整章只扫一次", () => {
    const scheduler = fakeScheduler();
    const scan = vi.fn();
    const debounced = debounceSensitiveScan(scan, {
      setTimer: scheduler.setTimer,
      clearTimer: scheduler.clearTimer,
    });

    // 逐击键连续触发
    debounced("第1键");
    debounced("第2键");
    debounced("最后一键");

    // 全部中间调度被取消，只剩最后一次，且延迟为默认 300
    expect(scheduler.scheduled).toHaveLength(1);
    expect(scheduler.scheduled[0]!.delayMs).toBe(SENSITIVE_SCAN_DEBOUNCE_MS);
    expect(scan).not.toHaveBeenCalled();

    scheduler.runLast();
    expect(scan).toHaveBeenCalledTimes(1);
    expect(scan).toHaveBeenCalledWith("最后一键");
  });

  it("注入固定延迟与真实计时器组合也可控", () => {
    const scheduler = fakeScheduler();
    const scan = vi.fn();
    const debounced = debounceSensitiveScan(scan, {
      delayMs: 500,
      setTimer: scheduler.setTimer,
      clearTimer: scheduler.clearTimer,
    });

    debounced("a");
    debounced("b");
    expect(scheduler.scheduled).toHaveLength(1);
    expect(scheduler.scheduled[0]!.delayMs).toBe(500);

    scheduler.runLast();
    expect(scan).toHaveBeenCalledWith("b");
  });

  it("cancel() 取消挂起的扫描（组件卸载清理用）", () => {
    const scheduler = fakeScheduler();
    const scan = vi.fn();
    const debounced = debounceSensitiveScan(scan, {
      setTimer: scheduler.setTimer,
      clearTimer: scheduler.clearTimer,
    });

    debounced("挂起");
    expect(scheduler.scheduled).toHaveLength(1);

    debounced.cancel();
    expect(scheduler.scheduled).toHaveLength(0);

    scheduler.runLast();
    expect(scan).not.toHaveBeenCalled();
  });
});
