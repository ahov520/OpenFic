/**
 * Sensitive Words Panel
 *
 * 敏感词命中面板（沿 FindReplacePanel 模式）：
 * - 打开时拉取词库（后端惰性 seed），对整章做防抖扫描（输入停止 ≥300ms）；
 * - 命中列表支持跳转定位与确认后一键替换单事务替换；
 * - 高亮由 SensitiveHighlight Extension 派生 decoration，不进文档；
 * - 底部词库维护区：粘贴导入（TXT/JSON）、导出下载、清空词表。
 */

import {
  Box,
  Button,
  Dialog,
  Flex,
  SegmentedControl,
  Text,
  TextArea,
  TextField,
} from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Editor } from "@tiptap/react";
import { X } from "lucide-react";
import { motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import {
  exportSensitiveWords,
  fetchSensitiveWords,
  importSensitiveWords,
  updateSensitiveWords,
} from "@/lib/api-client";

import { editorPlainText } from "../lib/margin-note-highlight";
import { mapPlainRange, replaceSensitiveWord } from "../lib/sensitive-highlight";
import {
  SENSITIVE_WORDS_LABEL_KEY,
  debounceSensitiveScan,
  scanSensitiveWords,
  type SensitiveWordHit,
} from "../lib/sensitive-words";
import { SensitiveHitList } from "./sensitive-hit-list";

interface SensitiveWordsPanelProps {
  editor: Editor;
  isAgentLocked: boolean;
  onClose: () => void;
}

const PANEL_MAX_WIDTH = 800;
const DEFAULT_REPLACEMENT = "＊＊";

type SensitiveImportFormat = "txt" | "json";

export function SensitiveWordsPanel({ editor, isAgentLocked, onClose }: SensitiveWordsPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [hits, setHits] = useState<SensitiveWordHit[]>([]);
  const [replacingHit, setReplacingHit] = useState<SensitiveWordHit | null>(null);
  const [replacement, setReplacement] = useState(DEFAULT_REPLACEMENT);
  const [importContent, setImportContent] = useState("");
  const [importFormat, setImportFormat] = useState<SensitiveImportFormat>("txt");
  const [confirmingClear, setConfirmingClear] = useState(false);
  const jumpIndexByWordRef = useRef(new Map<string, number>());

  const wordsQuery = useQuery({
    queryKey: ["sensitive-words"],
    queryFn: fetchSensitiveWords,
  });
  const words = useMemo(() => wordsQuery.data ?? [], [wordsQuery.data]);

  const applyScan = useCallback(() => {
    const result = scanSensitiveWords(editorPlainText(editor), words, {
      normalizeWidth: true,
    });
    setHits(result.hits);
    void editor.commands.setSensitiveHits(result.hits);
  }, [editor, words]);

  // 打开/词库变化：立即整章扫描一次
  useEffect(() => {
    applyScan();
  }, [applyScan]);

  // 编辑更新：防抖（输入停止 ≥300ms）后整章重扫一次；卸载时取消挂起回调
  useEffect(() => {
    const debouncedScan = debounceSensitiveScan(applyScan);
    editor.on("update", debouncedScan);
    return () => {
      editor.off("update", debouncedScan);
      debouncedScan.cancel();
    };
  }, [editor, applyScan]);

  const handleJump = useCallback(
    (hit: SensitiveWordHit) => {
      if (hit.positions.length === 0) return;
      const indexMap = jumpIndexByWordRef.current;
      const index = (indexMap.get(hit.word) ?? -1) + 1;
      const position = hit.positions[index % hit.positions.length]!;
      indexMap.set(hit.word, index);

      // 防抖窗口内文档可能已被编辑：与装饰/替换路径同口径校验命中词原文，
      // 对不上先触发一次即时重扫（等待新命中），本次不跳。
      const plain = editorPlainText(editor);
      const range = mapPlainRange(editor.state.doc, plain, position.start, position.end, hit.word);
      if (!range) {
        applyScan();
        return;
      }
      void editor.commands.setTextSelection(range);
      editor.commands.scrollIntoView();
    },
    [applyScan, editor],
  );

  const refreshWords = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["sensitive-words"] });
  }, [queryClient]);

  const importMutation = useMutation({
    mutationFn: () => importSensitiveWords(importContent, importFormat),
    onSuccess: (result) => {
      setImportContent("");
      refreshWords();
      toast.success(
        t("writing.sensitiveWords.importSuccess", {
          accepted: result.stats?.accepted ?? 0,
          duplicates: result.stats?.duplicates ?? 0,
          invalid: result.stats?.invalid ?? 0,
        }),
      );
    },
    onError: () => {
      toast.error(t("writing.sensitiveWords.importFailed"));
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => updateSensitiveWords([]),
    onSuccess: () => {
      setConfirmingClear(false);
      refreshWords();
      toast.success(t("writing.sensitiveWords.clearSuccess"));
    },
    onError: () => {
      toast.error(t("writing.sensitiveWords.importFailed"));
    },
  });

  const handleExport = useCallback((format: SensitiveImportFormat) => {
    void exportSensitiveWords(format).then((result) => {
      const blob = new Blob([result.content], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename;
      anchor.style.display = "none";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    });
  }, []);

  const handleReplace = useCallback(() => {
    const hit = replacingHit;
    if (!hit || isAgentLocked) return;
    const replaced = replaceSensitiveWord(editor, hit, replacement, {
      normalizeWidth: true,
    });
    if (replaced > 0) {
      toast.success(t("writing.sensitiveWords.replaceSuccess", { count: replaced }));
      // 文档已变化：立即重扫（Extension 的 decoration 也会随 docChanged 清空）
      applyScan();
    }
    setReplacingHit(null);
  }, [applyScan, editor, isAgentLocked, replacement, replacingHit, t]);

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
      <Box
        px="6"
        py="3"
      >
        <Flex
          direction="column"
          gap="3"
          style={{ maxWidth: PANEL_MAX_WIDTH, margin: "0 auto" }}
        >
          <Flex
            align="center"
            gap="2"
          >
            <Text
              size="2"
              weight="medium"
            >
              {t(SENSITIVE_WORDS_LABEL_KEY)}
            </Text>
            <Text
              size="1"
              color="gray"
            >
              {t("writing.sensitiveWords.scanHint")}
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

          {wordsQuery.isError ? (
            <Text
              size="2"
              color="red"
            >
              {t("writing.sensitiveWords.loadFailed")}
            </Text>
          ) : (
            <SensitiveHitList
              hits={hits}
              disabled={isAgentLocked}
              onJump={handleJump}
              onReplace={setReplacingHit}
            />
          )}

          <Flex
            direction="column"
            gap="2"
            pt="2"
            style={{ borderTop: "1px solid var(--gray-a4)" }}
          >
            <Text
              size="1"
              weight="medium"
              color="gray"
            >
              {t("writing.sensitiveWords.maintenanceTitle")}
            </Text>
            <TextArea
              size="1"
              value={importContent}
              placeholder={t("writing.sensitiveWords.importPlaceholder")}
              onChange={(event) => setImportContent(event.target.value)}
            />
            <Flex
              align="center"
              gap="2"
              wrap="wrap"
            >
              <SegmentedControl.Root
                value={importFormat}
                onValueChange={(value) => setImportFormat(value as SensitiveImportFormat)}
                size="1"
                aria-label={t("writing.sensitiveWords.importFormatLabel")}
              >
                <SegmentedControl.Item value="txt">TXT</SegmentedControl.Item>
                <SegmentedControl.Item value="json">JSON</SegmentedControl.Item>
              </SegmentedControl.Root>
              <Button
                type="button"
                size="1"
                disabled={isAgentLocked || !importContent.trim() || importMutation.isPending}
                onClick={() => importMutation.mutate()}
              >
                {t("writing.sensitiveWords.importButton")}
              </Button>
              <Button
                type="button"
                size="1"
                variant="soft"
                color="gray"
                disabled={isAgentLocked}
                onClick={() => handleExport("txt")}
              >
                {t("writing.sensitiveWords.exportTxt")}
              </Button>
              <Button
                type="button"
                size="1"
                variant="soft"
                color="gray"
                disabled={isAgentLocked}
                onClick={() => handleExport("json")}
              >
                {t("writing.sensitiveWords.exportJson")}
              </Button>
              <Button
                type="button"
                size="1"
                variant="soft"
                color={confirmingClear ? "red" : "gray"}
                disabled={isAgentLocked || clearMutation.isPending}
                onClick={() => {
                  if (confirmingClear) clearMutation.mutate();
                  else setConfirmingClear(true);
                }}
              >
                {confirmingClear
                  ? t("writing.sensitiveWords.clearConfirm")
                  : t("writing.sensitiveWords.clearButton")}
              </Button>
            </Flex>
          </Flex>
        </Flex>
      </Box>

      <Dialog.Root
        open={replacingHit !== null}
        onOpenChange={(open) => {
          if (!open) setReplacingHit(null);
        }}
      >
        <Dialog.Content maxWidth="420px">
          <Dialog.Title>{t("writing.sensitiveWords.replaceTitle")}</Dialog.Title>
          <Dialog.Description
            size="2"
            color="gray"
          >
            {t("writing.sensitiveWords.replaceDescription", {
              word: replacingHit?.word ?? "",
              count: replacingHit?.count ?? 0,
              source: replacingHit?.source || t("writing.sensitiveWords.unknownSource"),
            })}
          </Dialog.Description>
          <Flex
            direction="column"
            gap="2"
            mt="4"
          >
            <Text
              as="label"
              size="2"
              weight="medium"
              htmlFor="sensitive-replacement-input"
            >
              {t("writing.sensitiveWords.replacementLabel")}
            </Text>
            <TextField.Root
              id="sensitive-replacement-input"
              autoFocus
              value={replacement}
              placeholder={DEFAULT_REPLACEMENT}
              onChange={(event) => setReplacement(event.target.value)}
            />
          </Flex>
          <Flex
            justify="end"
            gap="3"
            mt="5"
          >
            <Button
              type="button"
              variant="soft"
              color="gray"
              onClick={() => setReplacingHit(null)}
            >
              {t("common.cancel")}
            </Button>
            <Button
              type="button"
              color="red"
              onClick={handleReplace}
            >
              {t("writing.sensitiveWords.confirmReplace")}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>
    </motion.div>
  );
}
