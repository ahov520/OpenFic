import "@xyflow/react/dist/style.css";

import {
  Box,
  Button,
  Dialog,
  Flex,
  Select,
  Text,
  TextArea,
  TextField,
} from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Background,
  ReactFlow,
  applyNodeChanges,
  type Edge,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import { Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components/toast";
import {
  createCharacterRelationship,
  deleteCharacterRelationship,
  fetchCharacterRelationships,
  fetchCharactersByProject,
  updateCharacterRelationship,
} from "@/lib/api-client";
import type { CharacterListItem, CharacterRelationship } from "@/lib/character.types";

import "./character-relationships-dialog.css";

interface CharacterRelationshipsDialogProps {
  open: boolean;
  projectId: string;
  onOpenChange: (open: boolean) => void;
}

/** 简单的环形布局：角色按列表顺序均匀落在一圈上。 */
function buildNodes(characters: CharacterListItem[]): Node[] {
  const count = Math.max(characters.length, 1);
  const radius = Math.max(150, count * 30);
  return characters.map((character, index) => {
    const angle = (2 * Math.PI * index) / count - Math.PI / 2;
    return {
      id: character.id,
      type: "default",
      position: {
        x: 420 + radius * Math.cos(angle),
        y: 320 + radius * Math.sin(angle),
      },
      data: { label: character.name.trim() || "?" },
      className: "character-relationship-node",
    };
  });
}

function buildEdges(relationships: CharacterRelationship[]): Edge[] {
  return relationships.map((relationship) => ({
    id: relationship.id,
    source: relationship.fromCharacterId,
    target: relationship.toCharacterId,
    label: relationship.relationType.trim() || undefined,
    className: "character-relationship-edge",
  }));
}

export function CharacterRelationshipsDialog({
  open,
  projectId,
  onOpenChange,
}: CharacterRelationshipsDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const { data: charactersData } = useQuery({
    queryKey: ["characters", projectId],
    queryFn: () => fetchCharactersByProject(projectId),
    enabled: open,
  });
  const { data: relationshipsData, isLoading } = useQuery({
    queryKey: ["character-relationships", projectId],
    queryFn: () => fetchCharacterRelationships(projectId),
    enabled: open,
  });

  const characters = useMemo(
    () => charactersData?.items ?? [],
    [charactersData?.items],
  );
  const relationships = useMemo(
    () => relationshipsData?.items ?? [],
    [relationshipsData?.items],
  );

  const [nodes, setNodes] = useState<Node[]>([]);
  useEffect(() => {
    if (!open) return;
    setNodes(buildNodes(characters));
  }, [characters, open]);

  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ["character-relationships", projectId],
    });
  }, [projectId, queryClient]);

  const createMutation = useMutation({
    mutationFn: ({
      projectId,
      characterAId,
      characterBId,
      relationType,
      description,
    }: {
      projectId: string;
      characterAId: string;
      characterBId: string;
      relationType: string;
      description: string;
    }) =>
      createCharacterRelationship(projectId, {
        characterAId,
        characterBId,
        relationType,
        description,
      }),
    onSuccess: () => {
      toast.success(t("characters.relationships.saveSuccess"));
      invalidate();
      setAddFormOpen(false);
    },
    onError: () => toast.error(t("characters.relationships.saveFailed")),
  });
  const updateMutation = useMutation({
    mutationFn: ({
      relationshipId,
      data,
    }: {
      relationshipId: string;
      data: { relationType: string; description: string };
    }) => updateCharacterRelationship(relationshipId, data),
    onSuccess: () => {
      toast.success(t("characters.relationships.saveSuccess"));
      invalidate();
      setEditingRelationship(null);
    },
    onError: () => toast.error(t("characters.relationships.saveFailed")),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteCharacterRelationship,
    onSuccess: () => {
      toast.success(t("characters.relationships.deleteSuccess"));
      invalidate();
      setEditingRelationship(null);
    },
    onError: () => toast.error(t("characters.relationships.deleteFailed")),
  });

  const [addFormOpen, setAddFormOpen] = useState(false);
  const [addAId, setAddAId] = useState("");
  const [addBId, setAddBId] = useState("");
  const [addType, setAddType] = useState("");
  const [addDescription, setAddDescription] = useState("");
  const [editingRelationship, setEditingRelationship] =
    useState<CharacterRelationship | null>(null);
  const [editType, setEditType] = useState("");
  const [editDescription, setEditDescription] = useState("");

  const openEditing = useCallback((relationship: CharacterRelationship) => {
    setEditingRelationship(relationship);
    setEditType(relationship.relationType);
    setEditDescription(relationship.description);
  }, []);

  const edges = useMemo<Edge[]>(
    () =>
      buildEdges(relationships).map((edge) => ({
        ...edge,
        ...(edge.id === editingRelationship?.id
          ? { style: { stroke: "var(--accent-9)", strokeWidth: 2 } }
          : {}),
      })),
    [relationships, editingRelationship?.id],
  );

  const handleOpenAddForm = useCallback(() => {
    setEditingRelationship(null);
    setAddAId(characters[0]?.id ?? "");
    setAddBId(characters[1]?.id ?? "");
    setAddType("");
    setAddDescription("");
    setAddFormOpen(true);
  }, [characters]);

  const handleCreate = useCallback(() => {
    if (!addAId || !addBId || addAId === addBId) return;
    createMutation.mutate({
      projectId,
      characterAId: addAId,
      characterBId: addBId,
      relationType: addType,
      description: addDescription,
    });
  }, [
    addAId,
    addBId,
    addDescription,
    addType,
    createMutation,
    projectId,
  ]);

  const characterName = useCallback(
    (characterId: string) =>
      characters.find((character) => character.id === characterId)?.name ?? "?",
    [characters],
  );

  const renderCharacterSelect = (
    value: string,
    onChange: (value: string) => void,
    label: string,
  ) => (
    <Select.Root
      size="2"
      value={value}
      onValueChange={onChange}
    >
      <Select.Trigger aria-label={label} />
      <Select.Content>
        {characters.map((character) => (
          <Select.Item
            key={character.id}
            value={character.id}
          >
            {character.name || t("characters.relationships.untitled")}
          </Select.Item>
        ))}
      </Select.Content>
    </Select.Root>
  );

  return (
    <Dialog.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Dialog.Content
        maxWidth="920px"
        className="character-relationships-dialog"
      >
        <Dialog.Title>{t("characters.relationships.title")}</Dialog.Title>
        <Dialog.Description size="2" color="gray">
          {t("characters.relationships.hint")}
        </Dialog.Description>

        <Flex
          justify="end"
          gap="2"
          mt="3"
        >
          <Button
            size="2"
            variant="soft"
            disabled={characters.length < 2 || isLoading}
            onClick={handleOpenAddForm}
          >
            {t("characters.relationships.add")}
          </Button>
        </Flex>

        {addFormOpen && (
          <Flex
            direction="column"
            gap="2"
            mt="3"
            p="3"
            className="character-relationships-form"
          >
            <Flex
              align="center"
              gap="2"
              wrap="wrap"
            >
              {renderCharacterSelect(addAId, setAddAId, t("characters.relationships.characterA"))}
              <Text size="2">{t("characters.relationships.and")}</Text>
              {renderCharacterSelect(addBId, setAddBId, t("characters.relationships.characterB"))}
              <TextField.Root
                size="2"
                placeholder={t("characters.relationships.typePlaceholder")}
                value={addType}
                onChange={(event) => setAddType(event.target.value)}
                maxLength={80}
                style={{ width: 180 }}
              />
            </Flex>
            <TextArea
              size="2"
              placeholder={t("characters.relationships.descriptionPlaceholder")}
              value={addDescription}
              onChange={(event) => setAddDescription(event.target.value)}
              maxLength={2000}
              style={{ minHeight: 60 }}
            />
            <Flex
              justify="end"
              gap="2"
            >
              <Button
                variant="soft"
                color="gray"
                onClick={() => setAddFormOpen(false)}
              >
                {t("common.cancel")}
              </Button>
              <Button
                disabled={!addAId || !addBId || addAId === addBId}
                loading={createMutation.isPending}
                onClick={handleCreate}
              >
                {t("common.confirm")}
              </Button>
            </Flex>
          </Flex>
        )}

        {editingRelationship && (
          <Flex
            direction="column"
            gap="2"
            mt="3"
            p="3"
            className="character-relationships-form"
          >
            <Text size="2" weight="medium">
              {characterName(editingRelationship.fromCharacterId)}
              {" · "}
              {characterName(editingRelationship.toCharacterId)}
            </Text>
            <TextField.Root
              size="2"
              placeholder={t("characters.relationships.typePlaceholder")}
              value={editType}
              onChange={(event) => setEditType(event.target.value)}
              maxLength={80}
            />
            <TextArea
              size="2"
              placeholder={t("characters.relationships.descriptionPlaceholder")}
              value={editDescription}
              onChange={(event) => setEditDescription(event.target.value)}
              maxLength={2000}
              style={{ minHeight: 60 }}
            />
            <Flex
              justify="between"
              gap="2"
            >
              <Button
                variant="soft"
                color="red"
                loading={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(editingRelationship.id)}
              >
                <Trash2 size={14} />
                {t("characters.relationships.delete")}
              </Button>
              <Flex gap="2">
                <Button
                  variant="soft"
                  color="gray"
                  onClick={() => setEditingRelationship(null)}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  loading={updateMutation.isPending}
                  onClick={() =>
                    updateMutation.mutate({
                      relationshipId: editingRelationship.id,
                      data: { relationType: editType, description: editDescription },
                    })
                  }
                >
                  {t("common.confirm")}
                </Button>
              </Flex>
            </Flex>
          </Flex>
        )}

        <Box className="character-relationships-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={handleNodesChange}
            onEdgeClick={(_, edge) => {
              const relationship = relationships.find((item) => item.id === edge.id);
              if (relationship) openEditing(relationship);
            }}
            fitView
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background />
          </ReactFlow>
          {characters.length < 2 && (
            <Text
              as="div"
              size="2"
              color="gray"
              className="character-relationships-empty"
            >
              {t("characters.relationships.needTwoCharacters")}
            </Text>
          )}
        </Box>
      </Dialog.Content>
    </Dialog.Root>
  );
}
