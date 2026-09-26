/**
 * Sensitive Hit List
 *
 * 敏感词命中列表（纯展示组件）：命中词/来源/次数 + 跳转 + 一键替换入口。
 * 替换的确认逻辑在面板层（Radix Dialog），本组件只回调。
 */

import { Button, Flex, Text } from "@radix-ui/themes";
import { Replace, Target } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { SensitiveWordHit } from "../lib/sensitive-words";

interface SensitiveHitListProps {
  hits: SensitiveWordHit[];
  /** 恢复/替换进行中或 Agent 占用时禁用 */
  disabled?: boolean;
  onJump: (hit: SensitiveWordHit) => void;
  onReplace: (hit: SensitiveWordHit) => void;
}

export function SensitiveHitList({
  hits,
  disabled = false,
  onJump,
  onReplace,
}: SensitiveHitListProps) {
  const { t } = useTranslation();

  if (hits.length === 0) {
    return (
      <Text
        size="2"
        color="gray"
      >
        {t("writing.sensitiveWords.empty")}
      </Text>
    );
  }

  return (
    <Flex
      direction="column"
      gap="2"
      style={{
        maxHeight: "min(38vh, 300px)",
        overflowY: "auto",
        overscrollBehavior: "contain",
      }}
    >
      {hits.map((hit) => (
        <Flex
          key={hit.word}
          align="center"
          gap="2"
          py="2"
          px="3"
          style={{
            borderRadius: 8,
            border: "1px solid var(--gray-a5)",
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
                size="2"
                weight="medium"
                color="red"
              >
                {hit.word}
              </Text>
              <Text
                size="1"
                color="gray"
              >
                {t("writing.sensitiveWords.hitCount", { count: hit.count })}
              </Text>
            </Flex>
            {hit.source && (
              <Text
                size="1"
                color="gray"
                style={{ overflow: "hidden", textOverflow: "ellipsis" }}
              >
                {t("writing.sensitiveWords.sourceLabel", { source: hit.source })}
              </Text>
            )}
          </Flex>
          <Button
            type="button"
            size="1"
            variant="soft"
            color="gray"
            disabled={disabled}
            aria-label={t("writing.sensitiveWords.jump")}
            onClick={() => onJump(hit)}
          >
            <Target size={13} />
            {t("writing.sensitiveWords.jump")}
          </Button>
          <Button
            type="button"
            size="1"
            variant="soft"
            color="red"
            disabled={disabled}
            aria-label={t("writing.sensitiveWords.replace", { word: hit.word })}
            onClick={() => onReplace(hit)}
          >
            <Replace size={13} />
            {t("writing.sensitiveWords.replace", { word: hit.word })}
          </Button>
        </Flex>
      ))}
    </Flex>
  );
}
