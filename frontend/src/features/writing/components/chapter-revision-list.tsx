/**
 * Chapter Revision List
 *
 * 历史版本时间线列表（纯展示组件）：时间/类型/字数 + 全文预览入口 + 一键恢复。
 * 移动端整列表可滚动，恢复按钮完整可达，不引入独立布局。
 */

import { Button, Flex, Text } from "@radix-ui/themes";
import { RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { ChapterRevisionItem } from "@/lib/chapter.types";

import { isRestorableRevision, revisionTypeLabelKey } from "../lib/chapter-revisions";

interface ChapterRevisionListProps {
  items: ChapterRevisionItem[];
  /** 当前选中的条目（预览中） */
  activeCommitId: string | null;
  /** 恢复请求进行中，按钮禁用 */
  isRestoring: boolean;
  onSelect: (item: ChapterRevisionItem) => void;
  onRestore: (item: ChapterRevisionItem) => void;
}

function revisionTime(createdAt: string): string {
  const parsed = new Date(createdAt);
  return Number.isNaN(parsed.getTime()) ? createdAt : parsed.toLocaleString();
}

export function ChapterRevisionList({
  items,
  activeCommitId,
  isRestoring,
  onSelect,
  onRestore,
}: ChapterRevisionListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return (
      <Text
        size="2"
        color="gray"
      >
        {t("writing.chapterHistory.empty")}
      </Text>
    );
  }

  return (
    <Flex
      direction="column"
      gap="2"
      style={{
        maxHeight: "min(42vh, 340px)",
        overflowY: "auto",
        overscrollBehavior: "contain",
      }}
    >
      {items.map((item) => {
        const active = item.commitId === activeCommitId;
        return (
          <Flex
            key={item.commitId}
            align="center"
            gap="3"
            py="2"
            px="3"
            onClick={() => onSelect(item)}
            style={{
              cursor: "pointer",
              borderRadius: 8,
              border: `1px solid var(--gray-${active ? "a7" : "a5"})`,
              background: active ? "var(--gray-a3)" : "transparent",
            }}
          >
            <Flex
              direction="column"
              gap="1"
              style={{ flex: 1, minWidth: 0 }}
            >
              <Flex
                align="center"
                gap="2"
                wrap="wrap"
              >
                <Text
                  size="1"
                  weight="medium"
                  color={item.revisionType === "manual" ? "gray" : "blue"}
                >
                  {t(revisionTypeLabelKey(item.revisionType))}
                </Text>
                <Text
                  size="1"
                  color="gray"
                >
                  {revisionTime(item.createdAt)}
                </Text>
                {item.wordCount !== null && (
                  <Text
                    size="1"
                    color="gray"
                  >
                    {t("writing.chapterHistory.wordCount", { count: item.wordCount })}
                  </Text>
                )}
              </Flex>
              {item.message && (
                <Text
                  size="1"
                  color="gray"
                  style={{ overflow: "hidden", textOverflow: "ellipsis" }}
                >
                  {item.message}
                </Text>
              )}
            </Flex>
            {isRestorableRevision(item) ? (
              <Button
                type="button"
                size="1"
                variant="soft"
                disabled={isRestoring}
                onClick={(event) => {
                  event.stopPropagation();
                  onRestore(item);
                }}
                aria-label={t("writing.chapterHistory.restore")}
              >
                <RotateCcw size={13} />
                {isRestoring
                  ? t("writing.chapterHistory.restoring")
                  : t("writing.chapterHistory.restore")}
              </Button>
            ) : (
              <Text
                size="1"
                color="gray"
              >
                {t("writing.chapterHistory.restoreUnavailableHint")}
              </Text>
            )}
          </Flex>
        );
      })}
    </Flex>
  );
}
