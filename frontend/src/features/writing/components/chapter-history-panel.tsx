/**
 * Chapter History Panel
 *
 * 历史版本面板：列出该章 Agent 修订与手动修订的混合时间线，
 * 支持任意版本全文预览与一键恢复（调后端恢复端点）。
 * 恢复前先由编辑器落盘未保存改动（onBeforeRestore），避免脏草稿被覆盖丢失。
 * 面板结构沿 FindReplacePanel 既有模式（动效、宽度、关闭方式）。
 */

import { Box, Button, Flex, Text } from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import {
  fetchChapterRevisionDetail,
  fetchChapterRevisions,
  restoreChapterRevision,
} from "@/lib/api-client";
import type { Chapter, ChapterRevisionItem } from "@/lib/chapter.types";

import { buildRevisionTimeline } from "../lib/chapter-revisions";
import { ChapterRevisionList } from "./chapter-revision-list";

interface ChapterHistoryPanelProps {
  chapterId: string;
  /** Agent 占用时恢复被禁用（浏览不受限） */
  isAgentLocked: boolean;
  /** 恢复执行前回调：编辑器先把未保存改动落盘（保存失败应抛错中止恢复） */
  onBeforeRestore: () => Promise<void>;
  onClose: () => void;
  /** 恢复成功后回调（携带写回后的章节，由编辑器同步正文与字数） */
  onRestored: (chapter: Chapter) => void;
}

/** 面板最大宽度（与编辑器内容、FindReplacePanel 一致） */
const PANEL_MAX_WIDTH = 800;

/** 时间线单页条数（与后端分页上限对齐） */
const PAGE_SIZE = 50;

export function ChapterHistoryPanel({
  chapterId,
  isAgentLocked,
  onBeforeRestore,
  onClose,
  onRestored,
}: ChapterHistoryPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedCommitId, setSelectedCommitId] = useState<string | null>(null);
  const [olderItems, setOlderItems] = useState<ChapterRevisionItem[]>([]);
  // null = 还没加载过「更早版本」；此后记录最后一页是否满页
  const [olderPageFull, setOlderPageFull] = useState<boolean | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);

  // 切换章节时重置「更早版本」累积
  useEffect(() => {
    setOlderItems([]);
    setOlderPageFull(null);
  }, [chapterId]);

  const revisionsQuery = useQuery({
    queryKey: ["chapter-revisions", chapterId],
    queryFn: () => fetchChapterRevisions(chapterId, { offset: 0, limit: PAGE_SIZE }),
  });

  const detailQuery = useQuery({
    queryKey: ["chapter-revision-detail", chapterId, selectedCommitId],
    queryFn: () => fetchChapterRevisionDetail(chapterId, selectedCommitId as string),
    enabled: selectedCommitId !== null,
  });

  const firstPage = revisionsQuery.data ?? [];
  const hasMore = olderPageFull === null ? firstPage.length === PAGE_SIZE : olderPageFull;

  const handleLoadOlder = async () => {
    setLoadingOlder(true);
    try {
      const offset = firstPage.length + olderItems.length;
      const fetched = await fetchChapterRevisions(chapterId, {
        offset,
        limit: PAGE_SIZE,
      });
      setOlderItems((current) => [...current, ...fetched]);
      setOlderPageFull(fetched.length === PAGE_SIZE);
    } catch {
      toast.error(t("writing.chapterHistory.loadFailed"));
    } finally {
      setLoadingOlder(false);
    }
  };

  const restoreMutation = useMutation({
    mutationFn: async (item: ChapterRevisionItem) => {
      await onBeforeRestore();
      return restoreChapterRevision(chapterId, item.commitId);
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["chapter-revisions", chapterId] });
      queryClient.setQueryData<Chapter>(["chapter", chapterId], result.chapter);
      setSelectedCommitId(null);
      setOlderItems([]);
      setOlderPageFull(null);
      onRestored(result.chapter);
      toast.success(t("writing.chapterHistory.restoreSuccess"));
    },
    onError: () => {
      toast.error(t("writing.chapterHistory.restoreFailed"));
    },
  });

  const items = buildRevisionTimeline([...firstPage, ...olderItems]);

  const handleRestore = (item: ChapterRevisionItem) => {
    if (isAgentLocked) return;
    restoreMutation.mutate(item);
  };

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.06, ease: "easeOut" }}
      style={{
        overflow: "hidden",
        background: "var(--color-background)",
      }}
    >
      <Box py="3">
        <Box
          style={{
            maxWidth: PANEL_MAX_WIDTH,
            margin: "0 auto",
            padding: "0 24px",
          }}
        >
          <Flex
            direction="column"
            gap="3"
          >
            <Flex
              align="center"
              gap="2"
            >
              <Text
                size="2"
                weight="medium"
              >
                {t("writing.chapterHistory.title")}
              </Text>
              <Box style={{ flex: 1 }} />
              <Button
                type="button"
                size="1"
                variant="ghost"
                color="gray"
                highContrast
                onClick={onClose}
                aria-label={t("common.close")}
              >
                <X size={16} />
              </Button>
            </Flex>

            {revisionsQuery.isError ? (
              <Text
                size="2"
                color="red"
              >
                {t("writing.chapterHistory.loadFailed")}
              </Text>
            ) : (
              <>
                <ChapterRevisionList
                  items={items}
                  activeCommitId={selectedCommitId}
                  isRestoring={restoreMutation.isPending}
                  onSelect={(item) =>
                    setSelectedCommitId((current) =>
                      current === item.commitId ? null : item.commitId,
                    )
                  }
                  onRestore={handleRestore}
                />
                {hasMore && (
                  <Button
                    type="button"
                    size="1"
                    variant="soft"
                    color="gray"
                    disabled={loadingOlder}
                    onClick={() => void handleLoadOlder()}
                  >
                    {loadingOlder
                      ? t("writing.chapterHistory.loadingOlder")
                      : t("writing.chapterHistory.loadOlder")}
                  </Button>
                )}
              </>
            )}

            {detailQuery.data && (
              <Box
                py="2"
                px="3"
                style={{
                  maxHeight: "min(30vh, 240px)",
                  overflowY: "auto",
                  overscrollBehavior: "contain",
                  borderRadius: 8,
                  border: "1px solid var(--gray-a5)",
                  whiteSpace: "pre-wrap",
                  fontSize: "var(--font-size-base)",
                  lineHeight: 1.7,
                }}
              >
                {detailQuery.data.content || t("writing.chapterHistory.emptyPreview")}
              </Box>
            )}
          </Flex>
        </Box>
      </Box>
    </motion.div>
  );
}
