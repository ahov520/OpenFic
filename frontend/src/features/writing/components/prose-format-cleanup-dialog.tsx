import { Button, Checkbox, Dialog, Flex, Text } from "@radix-ui/themes";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  DEFAULT_PROSE_FORMAT_CLEANUP_RULES,
  PROSE_FORMAT_CLEANUP_RULE_OPTIONS,
  type ProseFormatCleanupRules,
} from "../lib/prose-format-cleanup";

export interface ProseFormatCleanupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 点击「执行排版」时回调，入参为勾选的规则组合 */
  onApply: (rules: ProseFormatCleanupRules) => void;
}

/**
 * 「一键排版」规则勾选对话框：每次打开默认全开，
 * 代码块与章节标记的保护由清理逻辑本身保证，无需用户勾选。
 */
export function ProseFormatCleanupDialog({
  open,
  onOpenChange,
  onApply,
}: ProseFormatCleanupDialogProps) {
  const { t } = useTranslation();
  const [rules, setRules] = useState(DEFAULT_PROSE_FORMAT_CLEANUP_RULES);

  useEffect(() => {
    if (open) setRules(DEFAULT_PROSE_FORMAT_CLEANUP_RULES);
  }, [open]);

  const handleApply = () => {
    onApply(rules);
    onOpenChange(false);
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Dialog.Content maxWidth="480px">
        <Dialog.Title>{t("writing.proseFormatCleanup.title")}</Dialog.Title>
        <Dialog.Description
          size="2"
          color="gray"
        >
          {t("writing.proseFormatCleanup.description")}
        </Dialog.Description>

        <Flex
          direction="column"
          gap="3"
          mt="4"
        >
          {PROSE_FORMAT_CLEANUP_RULE_OPTIONS.map(({ id, labelKey, hintKey }) => (
            <Flex
              key={id}
              align="start"
              gap="3"
            >
              <Checkbox
                checked={rules[id]}
                aria-label={t(labelKey)}
                onCheckedChange={(checked) =>
                  setRules((previous) => ({ ...previous, [id]: checked === true }))
                }
              />
              <Flex
                direction="column"
                gap="1"
              >
                <Text
                  size="2"
                  weight="medium"
                >
                  {t(labelKey)}
                </Text>
                <Text
                  size="1"
                  color="gray"
                >
                  {t(hintKey)}
                </Text>
              </Flex>
            </Flex>
          ))}
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
            onClick={() => onOpenChange(false)}
          >
            {t("common.cancel")}
          </Button>
          <Button
            type="button"
            onClick={handleApply}
          >
            {t("writing.proseFormatCleanup.apply")}
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
