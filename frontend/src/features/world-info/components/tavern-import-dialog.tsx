import {
  Badge,
  Box,
  Button,
  Checkbox,
  Dialog,
  Flex,
  ScrollArea,
  Text,
  TextField,
} from "@radix-ui/themes";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components/toast";
import { importTavernMaterial, previewTavernMaterial } from "@/lib/api-client";
import type { TavernPreview } from "@/lib/tavern.types";
import type { WorldInfoImportMode } from "@/lib/world-info.types";

interface TavernImportDialogProps {
  open: boolean;
  projectId: string;
  onOpenChange: (open: boolean) => void;
  onImported: () => void;
}

export function TavernImportDialog({
  open,
  projectId,
  onOpenChange,
  onImported,
}: TavernImportDialogProps) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [userName, setUserName] = useState("");
  const [mode, setMode] = useState<WorldInfoImportMode>("append");
  const [preview, setPreview] = useState<TavernPreview | null>(null);
  const [selectedBlocks, setSelectedBlocks] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setFile(null);
    setPreview(null);
    setSelectedBlocks([]);
    setBusy(false);
  };

  const handlePreview = async () => {
    if (!file || !projectId) return;
    setBusy(true);
    try {
      const next = await previewTavernMaterial(projectId, file, userName);
      setPreview(next);
      setSelectedBlocks(
        next.blocks.filter((block) => block.included).map((block) => block.blockId),
      );
    } catch {
      toast.error(t("worldInfo.importParseFailed"));
    } finally {
      setBusy(false);
    }
  };

  const handleImport = async () => {
    if (!file || !projectId || !preview) return;
    setBusy(true);
    try {
      const result = await importTavernMaterial(projectId, file, userName, mode, selectedBlocks);
      toast.success(
        t("worldInfo.tavernSuccess", {
          entries: result.importedEntries,
          rules: result.importedRules,
          skills: result.importedSkills,
        }),
      );
      onImported();
      reset();
      onOpenChange(false);
    } catch {
      toast.error(t("worldInfo.importFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <Dialog.Content style={{ maxWidth: 640 }}>
        <Dialog.Title>{t("worldInfo.tavernTitle")}</Dialog.Title>
        <Dialog.Description
          size="2"
          color="gray"
          mb="3"
        >
          {t("worldInfo.tavernHint")}
        </Dialog.Description>
        <Flex
          direction="column"
          gap="3"
        >
          <input
            type="file"
            accept=".json,.png,application/json,image/png"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setPreview(null);
            }}
          />
          <TextField.Root
            value={userName}
            placeholder={t("worldInfo.tavernProtagonistPlaceholder")}
            aria-label={t("worldInfo.tavernProtagonist")}
            onChange={(event) => setUserName(event.target.value)}
          />
          <Flex gap="2">
            <Button
              variant={mode === "append" ? "solid" : "soft"}
              onClick={() => setMode("append")}
            >
              {t("worldInfo.importModeAppend")}
            </Button>
            <Button
              variant={mode === "overwrite" ? "solid" : "soft"}
              onClick={() => setMode("overwrite")}
            >
              {t("worldInfo.importModeOverwrite")}
            </Button>
            <Button
              disabled={!file || busy}
              onClick={() => void handlePreview()}
            >
              {t("worldInfo.tavernPreview")}
            </Button>
          </Flex>
          {preview ? (
            <ScrollArea style={{ maxHeight: 360 }}>
              <Flex
                direction="column"
                gap="2"
              >
                <Text size="2">
                  {preview.kind}
                  {preview.characterName ? ` · ${preview.characterName}` : ""}
                  {preview.presetName ? ` · ${preview.presetName}` : ""}
                </Text>
                <Text
                  size="2"
                  color="gray"
                >
                  {t("worldInfo.importConstantCount")} {preview.constantCount} ·{" "}
                  {t("worldInfo.importKeywordCount")} {preview.keywordCount}
                </Text>
                {preview.descriptionPreview ? (
                  <Text size="2">{preview.descriptionPreview}</Text>
                ) : null}
                {preview.discarded.length > 0 ? (
                  <Text
                    size="2"
                    color="gray"
                  >
                    {t("worldInfo.tavernDiscarded")}: {preview.discarded.join("、")}
                  </Text>
                ) : null}
                {preview.loreEntries.slice(0, 12).map((entry) => (
                  <Flex
                    key={`${entry.name}-${entry.keywords.join("|")}`}
                    gap="2"
                    align="center"
                  >
                    <Badge color={entry.isConstant ? "blue" : "gray"}>
                      {entry.isConstant ? t("worldInfo.constantEntry") : entry.keywords.join(", ")}
                    </Badge>
                    <Text size="2">{entry.name}</Text>
                  </Flex>
                ))}
                {preview.blocks.map((block) => (
                  <Flex
                    key={block.blockId}
                    gap="2"
                    align="start"
                  >
                    <Checkbox
                      checked={selectedBlocks.includes(block.blockId)}
                      disabled={block.bucket === "discarded"}
                      onCheckedChange={(checked) => {
                        setSelectedBlocks((current) =>
                          checked
                            ? [...current, block.blockId]
                            : current.filter((id) => id !== block.blockId),
                        );
                      }}
                    />
                    <Box>
                      <Text
                        size="2"
                        weight="medium"
                      >
                        {block.bucket === "rule"
                          ? t("worldInfo.tavernRules")
                          : block.bucket === "skill"
                            ? t("worldInfo.tavernSkills")
                            : t("worldInfo.tavernDiscarded")}
                        {" · "}
                        {block.name}
                      </Text>
                      <Text
                        size="1"
                        color="gray"
                      >
                        {block.reason}
                        {block.contentPreview ? ` — ${block.contentPreview}` : ""}
                      </Text>
                    </Box>
                  </Flex>
                ))}
              </Flex>
            </ScrollArea>
          ) : null}
          <Flex
            justify="end"
            gap="2"
          >
            <Dialog.Close>
              <Button
                variant="soft"
                color="gray"
              >
                {t("common.cancel")}
              </Button>
            </Dialog.Close>
            <Button
              disabled={!preview || busy}
              onClick={() => void handleImport()}
            >
              {t("worldInfo.tavernConfirm")}
            </Button>
          </Flex>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
