import { Box, Button, Dialog, Flex, Select, Text } from "@radix-ui/themes";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, Dices, Plus } from "lucide-react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components/toast";
import { createCharacter } from "@/lib/api-client";

import {
  NAME_KINDS,
  generateNames,
  type NameKind,
} from "../lib/name-generator";
import "./character-name-generator-dialog.css";

interface CharacterNameGeneratorDialogProps {
  open: boolean;
  projectId: string;
  onOpenChange: (open: boolean) => void;
}

export function CharacterNameGeneratorDialog({
  open,
  projectId,
  onOpenChange,
}: CharacterNameGeneratorDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<NameKind>("chineseFemale");
  const [names, setNames] = useState<string[]>([]);

  const regenerate = useCallback(() => {
    setNames(generateNames(kind, 24));
  }, [kind]);

  const createMutation = useMutation({
    mutationFn: (name: string) =>
      createCharacter(projectId, { name, description: "" }),
    onSuccess: (character) => {
      toast.success(t("characters.nameGenerator.created", { name: character.name }));
      void queryClient.invalidateQueries({
        queryKey: ["characters", projectId],
      });
    },
    onError: () => toast.error(t("characters.nameGenerator.createFailed")),
  });

  const handleCopy = useCallback(async (name: string) => {
    try {
      await navigator.clipboard.writeText(name);
      toast.success(t("characters.nameGenerator.copied", { name }));
    } catch {
      toast.error(t("characters.nameGenerator.copyFailed"));
    }
  }, [t]);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Dialog.Content
        maxWidth="640px"
        className="character-name-generator-dialog"
      >
        <Dialog.Title>{t("characters.nameGenerator.title")}</Dialog.Title>
        <Dialog.Description
          size="2"
          color="gray"
        >
          {t("characters.nameGenerator.hint")}
        </Dialog.Description>

        <Flex
          align="center"
          gap="2"
          mt="4"
          wrap="wrap"
        >
          <Select.Root
            size="2"
            value={kind}
            onValueChange={(value) => setKind(value as NameKind)}
          >
            <Select.Trigger aria-label={t("characters.nameGenerator.kind")} />
            <Select.Content>
              {NAME_KINDS.map((item) => (
                <Select.Item
                  key={item}
                  value={item}
                >
                  {t(`characters.nameGenerator.kinds.${item}`)}
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
          <Button
            size="2"
            onClick={regenerate}
          >
            <Dices size={14} />
            {t("characters.nameGenerator.generate")}
          </Button>
        </Flex>

        <Box className="character-name-generator-results">
          {names.length === 0 ? (
            <Text
              size="2"
              color="gray"
            >
              {t("characters.nameGenerator.empty")}
            </Text>
          ) : (
            <div className="character-name-generator-grid">
              {names.map((name) => (
                <div
                  key={name}
                  className="character-name-chip"
                >
                  <button
                    type="button"
                    className="character-name-chip-name"
                    title={t("characters.nameGenerator.copyHint")}
                    onClick={() => void handleCopy(name)}
                  >
                    <Copy size={11} />
                    {name}
                  </button>
                  <button
                    type="button"
                    className="character-name-chip-add"
                    title={t("characters.nameGenerator.createHint")}
                    disabled={createMutation.isPending}
                    onClick={() => createMutation.mutate(name)}
                  >
                    <Plus size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Box>
      </Dialog.Content>
    </Dialog.Root>
  );
}
