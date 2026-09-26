import { Box, Dialog, Flex, Text } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchCharacterAppearances } from "@/lib/api-client";

import "./character-appearances-dialog.css";

interface CharacterAppearancesDialogProps {
  open: boolean;
  projectId: string;
  onOpenChange: (open: boolean) => void;
}

/** 角色出场统计弹窗：按出场章数列出各角色的戏份占比与首末出场章。 */
export function CharacterAppearancesDialog({
  open,
  projectId,
  onOpenChange,
}: CharacterAppearancesDialogProps) {
  const { t } = useTranslation();
  const { data, isLoading } = useQuery({
    queryKey: ["character-appearances", projectId],
    queryFn: () => fetchCharacterAppearances(projectId),
    enabled: open,
  });

  const formatPercent = useCallback(
    (coverage: number) => `${Math.round(coverage * 100)}%`,
    [],
  );

  const items = data?.items ?? [];
  const maxCount = items.reduce((acc, item) => Math.max(acc, item.chapterCount), 0);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpanded = useCallback((characterId: string) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(characterId)) {
        next.delete(characterId);
      } else {
        next.add(characterId);
      }
      return next;
    });
  }, []);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Dialog.Content
        maxWidth="640px"
        className="character-appearances-dialog"
      >
        <Dialog.Title>{t("characters.appearances.title")}</Dialog.Title>
        <Dialog.Description
          size="2"
          color="gray"
        >
          {t("characters.appearances.hint")}
        </Dialog.Description>

        <Box
          mt="4"
          className="character-appearances-list"
        >
          {isLoading ? (
            <Text
              size="2"
              color="gray"
            >
              {t("common.loading")}
            </Text>
          ) : items.length === 0 ? (
            <Text
              size="2"
              color="gray"
            >
              {t("characters.appearances.empty")}
            </Text>
          ) : (
            items.map((item) => (
              <Flex
                key={item.characterId}
                direction="column"
                className="character-appearance-row"
              >
              <Flex
                align="center"
                gap="3"
                py="2"
              >
                <button
                  type="button"
                  className="character-appearance-toggle"
                  aria-expanded={expandedIds.has(item.characterId)}
                  aria-label={t("characters.appearances.toggleAria", {
                    name: item.name,
                  })}
                  onClick={() => toggleExpanded(item.characterId)}
                >
                  <Text
                    size="2"
                    weight="medium"
                    style={{ width: 120, flexShrink: 0, textAlign: "left" }}
                    truncate
                  >
                    {item.name || t("characters.relationships.untitled")}
                  </Text>
                </button>
                <Box
                  flexGrow="1"
                  className="character-appearance-bar-track"
                >
                  <Box
                    className="character-appearance-bar-fill"
                    style={{
                      width: `${
                        maxCount > 0 ? (item.chapterCount / maxCount) * 100 : 0
                      }%`,
                    }}
                  />
                </Box>
                <Text
                  size="1"
                  color="gray"
                  style={{ width: 96, flexShrink: 0, textAlign: "right" }}
                >
                  {t("characters.appearances.chapterCount", {
                    count: item.chapterCount,
                    total: item.totalChapters,
                    percent: formatPercent(item.coverage),
                  })}
                </Text>
                <Text
                  size="1"
                  color="gray"
                  style={{ width: 180, flexShrink: 0 }}
                  truncate
                >
                  {item.firstChapterTitle
                    ? t("characters.appearances.firstLast", {
                        first: item.firstChapterTitle,
                        last: item.lastChapterTitle ?? "",
                      })
                    : t("characters.appearances.neverAppeared")}
                </Text>
              </Flex>
              {expandedIds.has(item.characterId) && item.chapters.length > 0 && (
                <Flex
                  gap="2"
                  wrap="wrap"
                  pb="2"
                  pl="3"
                  className="character-appearance-chapters"
                >
                  {item.chapters.map((chapter) => (
                    <span
                      key={chapter.chapterId}
                      className="character-appearance-chapter-chip"
                    >
                      {t("characters.appearances.chapterChip", {
                        order: chapter.globalOrder,
                        title: chapter.title,
                      })}
                    </span>
                  ))}
                </Flex>
              )}
              </Flex>
            ))
          )}
        </Box>
      </Dialog.Content>
    </Dialog.Root>
  );
}
