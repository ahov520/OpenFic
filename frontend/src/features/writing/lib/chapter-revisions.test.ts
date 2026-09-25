import { describe, expect, it } from "vitest";

import type { ChapterRevisionItem } from "@/lib/chapter.types";

import {
  buildRevisionTimeline,
  isRestorableRevision,
  revisionTypeLabelKey,
} from "./chapter-revisions";

function item(overrides: Partial<ChapterRevisionItem>): ChapterRevisionItem {
  return {
    commitId: "c1",
    revisionId: "r1",
    revisionType: "manual",
    message: "手动保存",
    operation: "update",
    createdAt: "2026-09-26T10:00:00Z",
    title: "第一章",
    wordCount: 500,
    hasSnapshot: true,
    ...overrides,
  };
}

describe("buildRevisionTimeline", () => {
  it("把 Agent 修订与手动保存合并成按时间倒序的时间线", () => {
    const timeline = buildRevisionTimeline([
      item({ commitId: "manual-2", revisionType: "manual", createdAt: "2026-09-26T12:00:00Z" }),
      item({ commitId: "agent-1", revisionType: "agent", createdAt: "2026-09-26T11:30:00Z" }),
      item({ commitId: "manual-1", revisionType: "manual", createdAt: "2026-09-26T10:00:00Z" }),
    ]);

    expect(timeline.map((entry) => entry.commitId)).toEqual(["manual-2", "agent-1", "manual-1"]);
  });

  it("时间相同或缺失时保持后端次序，坏条目沉底且不丢数据", () => {
    const timeline = buildRevisionTimeline([
      item({ commitId: "a", createdAt: "2026-09-26T10:00:00Z" }),
      item({ commitId: "b", createdAt: "2026-09-26T10:00:00Z" }),
      item({ commitId: "c", createdAt: "not-a-date" }),
      item({ commitId: "d", createdAt: "2026-09-26T09:00:00Z" }),
    ]);

    expect(timeline.map((entry) => entry.commitId)).toEqual(["a", "b", "d", "c"]);
  });

  it("过滤掉没有 commitId 的坏条目", () => {
    const timeline = buildRevisionTimeline([item({ commitId: "" }), item({ commitId: "ok" })]);
    expect(timeline.map((entry) => entry.commitId)).toEqual(["ok"]);
  });

  it("按 commitId 去重（分页拼接的重叠条目保留先出现的一个）", () => {
    const timeline = buildRevisionTimeline([
      item({ commitId: "dup", revisionType: "manual", createdAt: "2026-09-26T12:00:00Z" }),
      item({ commitId: "dup", revisionType: "manual", createdAt: "2026-09-26T12:00:00Z" }),
      item({ commitId: "other", createdAt: "2026-09-26T11:00:00Z" }),
    ]);
    expect(timeline.map((entry) => entry.commitId)).toEqual(["dup", "other"]);
  });
});

describe("revisionTypeLabelKey", () => {
  it("三种已知类型各对应一个文案 key，未知类型兜底", () => {
    expect(revisionTypeLabelKey("agent")).toBe("writing.chapterHistory.typeAgent");
    expect(revisionTypeLabelKey("manual")).toBe("writing.chapterHistory.typeManual");
    expect(revisionTypeLabelKey("rollback")).toBe("writing.chapterHistory.typeRollback");
    expect(revisionTypeLabelKey("mystery")).toBe("writing.chapterHistory.typeUnknown");
  });
});

describe("isRestorableRevision", () => {
  it("有快照可恢复，create 型首条（无快照）不可恢复", () => {
    expect(isRestorableRevision(item({ hasSnapshot: true }))).toBe(true);
    expect(isRestorableRevision(item({ hasSnapshot: false }))).toBe(false);
  });
});
