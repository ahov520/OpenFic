import { Box, Dialog, ScrollArea, Text } from "@radix-ui/themes";
import { useTranslation } from "react-i18next";

import type { OpenMarginNote } from "@/lib/margin-note";

import { useOpenMarginNotes } from "../hooks/use-margin-notes";

import "./open-margin-notes-list.css";

interface OpenMarginNotesListProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenNote: (note: OpenMarginNote) => void;
}

export function OpenMarginNotesList({
  projectId,
  open,
  onOpenChange,
  onOpenNote,
}: OpenMarginNotesListProps) {
  const { t } = useTranslation();
  const { data, isLoading, isError, isFetched } = useOpenMarginNotes(projectId);
  const notes = data ?? [];
  const showEmpty = isFetched && !isError && notes.length === 0;

  return (
    <Dialog.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Dialog.Content
        className="open-margin-notes-content"
        maxWidth="720px"
        style={{ width: "min(720px, calc(100vw - 32px))" }}
      >
        <Dialog.Title className="open-margin-notes-visually-hidden">
          {t("writing.marginNotes.openList")}
        </Dialog.Title>
        <Dialog.Description className="open-margin-notes-visually-hidden">
          {t("writing.marginNotes.openListDescription")}
        </Dialog.Description>
        <div className="open-margin-notes-header">
          <Box>
            <Text
              size="4"
              weight="bold"
            >
              {t("writing.marginNotes.openList")}
            </Text>
            <Text
              as="p"
              size="1"
              color="gray"
              mt="1"
            >
              {t("writing.marginNotes.openListDescription")}
            </Text>
          </Box>
        </div>
        <ScrollArea className="open-margin-notes-body">
          {isLoading && !data && (
            <p className="open-margin-notes-status">{t("writing.marginNotes.openListLoading")}</p>
          )}
          {isError && (
            <p
              className="open-margin-notes-status"
              role="alert"
            >
              {t("writing.marginNotes.openListFailed")}
            </p>
          )}
          {showEmpty && (
            <p
              className="open-margin-notes-status"
              data-testid="open-margin-notes-empty"
            >
              {t("writing.marginNotes.openListEmpty")}
            </p>
          )}
          {notes.length > 0 && (
            <div
              className="open-margin-notes-list"
              aria-label={t("writing.marginNotes.openList")}
            >
              {notes.map((note) => {
                const chapterTitle = note.chapterTitle || t("writing.untitledChapter");
                return (
                  <button
                    key={note.id}
                    type="button"
                    className="open-margin-notes-item"
                    data-testid="open-margin-note"
                    data-note-id={note.id}
                    data-chapter-id={note.chapterId}
                    onClick={() => onOpenNote(note)}
                  >
                    <span className="open-margin-notes-chapter">{chapterTitle}</span>
                    <span className="open-margin-notes-anchor">
                      {t("writing.marginNotes.anchor")}：{note.anchorText}
                    </span>
                    <span className="open-margin-notes-body-text">{note.body}</span>
                  </button>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </Dialog.Content>
    </Dialog.Root>
  );
}
