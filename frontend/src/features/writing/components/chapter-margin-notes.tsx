import type { Editor } from "@tiptap/react";
import axios from "axios";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import {
  MARGIN_ANCHOR_MAX,
  MARGIN_BODY_MAX,
  locateAnchor,
  type MarginNote,
} from "@/lib/margin-note";

import {
  useCreateMarginNote,
  useDeleteMarginNote,
  useMarginNotes,
  useUpdateMarginNote,
} from "../hooks/use-margin-notes";
import {
  editorPlainText,
  rangeForPlainSlice,
  readMarginSelection,
  type MarginSelection,
} from "../lib/margin-note-highlight";

import "./chapter-margin-notes.css";

interface ChapterMarginNotesProps {
  chapterId: string;
  editor: Editor | null;
  disabled?: boolean;
  composeRequest: number;
  onPrepare?: () => Promise<void>;
}

function errorDetail(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

export function ChapterMarginNotes({
  chapterId,
  editor,
  disabled = false,
  composeRequest,
  onPrepare,
}: ChapterMarginNotesProps) {
  const { t } = useTranslation();
  const { data } = useMarginNotes(chapterId);
  const createNote = useCreateMarginNote(chapterId);
  const updateNote = useUpdateMarginNote(chapterId);
  const deleteNote = useDeleteMarginNote(chapterId);
  const notes = data ?? [];
  const [draft, setDraft] = useState<MarginSelection | null>(null);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [docVersion, setDocVersion] = useState(0);
  const seenRequest = useRef(0);
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!editor) return;
    const bump = () => setDocVersion((version) => version + 1);
    editor.on("update", bump);
    return () => {
      editor.off("update", bump);
    };
  }, [editor]);

  const manuscript = useMemo(() => {
    void docVersion;
    if (!editor) return "";
    return editorPlainText(editor);
  }, [docVersion, editor]);

  const beginCompose = useCallback(() => {
    if (disabled) return;
    if (!editor) {
      setError(t("writing.marginNotes.emptySelection"));
      return;
    }
    const selection = readMarginSelection(editor);
    if (!selection) {
      setDraft(null);
      setError(t("writing.marginNotes.emptySelection"));
      panelRef.current?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (selection.anchorText.length > MARGIN_ANCHOR_MAX) {
      setDraft(null);
      setError(t("writing.marginNotes.tooLong"));
      panelRef.current?.scrollIntoView({ block: "nearest" });
      return;
    }
    setError(null);
    setBody("");
    setDraft(selection);
    panelRef.current?.scrollIntoView({ block: "nearest" });
  }, [disabled, editor, t]);

  useEffect(() => {
    if (composeRequest === seenRequest.current) return;
    seenRequest.current = composeRequest;
    if (composeRequest === 0) return;
    beginCompose();
  }, [beginCompose, composeRequest]);

  const focusNote = useCallback(
    (note: MarginNote) => {
      if (!editor) return;
      const hit = locateAnchor(
        editorPlainText(editor),
        note.anchorText,
        note.contextBefore,
        note.contextAfter,
      );
      if (!hit.aligned || hit.start == null || hit.end == null) {
        editor.commands.setMarginNoteHighlight(null);
        return;
      }
      const range = rangeForPlainSlice(editor.state.doc, hit.start, hit.end);
      if (!range) {
        editor.commands.setMarginNoteHighlight(null);
        return;
      }
      const slice = editor.state.doc.textBetween(range.from, range.to, "\n", "\n");
      if (slice !== note.anchorText) {
        editor.commands.setMarginNoteHighlight(null);
        return;
      }
      editor.commands.setMarginNoteHighlight(range);
      window.requestAnimationFrame(() => {
        editor.view.dom.querySelector(".margin-note-anchor")?.scrollIntoView({
          block: "center",
          behavior: "smooth",
        });
      });
    },
    [editor],
  );

  const save = async () => {
    if (!draft || disabled) return;
    const trimmed = body.trim();
    if (!trimmed) {
      setError(t("writing.marginNotes.emptyBody"));
      return;
    }
    if (trimmed.length > MARGIN_BODY_MAX) {
      setError(t("writing.marginNotes.saveFailed"));
      return;
    }
    try {
      await onPrepare?.();
      const note = await createNote.mutateAsync({
        anchorText: draft.anchorText,
        contextBefore: draft.contextBefore,
        contextAfter: draft.contextAfter,
        body: trimmed,
      });
      setDraft(null);
      setBody("");
      setError(null);
      focusNote(note);
    } catch (caught) {
      const message = errorDetail(caught, t("writing.marginNotes.saveFailed"));
      setError(message);
      toast.error(message);
    }
  };

  const openNotes = notes.filter((note) => note.status === "open");
  const struckNotes = notes.filter((note) => note.status === "struck");

  const renderNote = (note: MarginNote, struck: boolean) => {
    const hit = editor
      ? locateAnchor(manuscript, note.anchorText, note.contextBefore, note.contextAfter)
      : {
          aligned: note.alignment === "aligned",
          start: note.start,
          end: note.end,
        };
    return (
      <article
        key={note.id}
        className={`chapter-margin-notes__item${struck ? " chapter-margin-notes__item--struck" : ""}`}
      >
        <button
          type="button"
          className="chapter-margin-notes__anchor"
          onClick={() => focusNote(note)}
        >
          {t("writing.marginNotes.anchor")}：{note.anchorText}
        </button>
        {!hit.aligned && (
          <p className="chapter-margin-notes__misaligned">
            {t("writing.marginNotes.misaligned")}
            {note.anchorText}
          </p>
        )}
        <p className="chapter-margin-notes__item-body">{note.body}</p>
        <div className="chapter-margin-notes__item-actions">
          <button
            type="button"
            className="chapter-margin-notes__button chapter-margin-notes__button--quiet"
            disabled={disabled || updateNote.isPending}
            onClick={() => {
              void updateNote
                .mutateAsync({
                  noteId: note.id,
                  data: { status: struck ? "open" : "struck" },
                })
                .catch((caught: unknown) => {
                  toast.error(errorDetail(caught, t("writing.marginNotes.saveFailed")));
                });
            }}
          >
            {struck ? t("writing.marginNotes.restore") : t("writing.marginNotes.strike")}
          </button>
          <button
            type="button"
            className="chapter-margin-notes__button chapter-margin-notes__button--quiet"
            disabled={disabled || deleteNote.isPending}
            onClick={() => {
              if (!window.confirm(t("writing.marginNotes.deleteConfirm"))) return;
              void deleteNote.mutateAsync(note.id).catch((caught: unknown) => {
                toast.error(errorDetail(caught, t("writing.marginNotes.saveFailed")));
              });
            }}
          >
            {t("writing.marginNotes.delete")}
          </button>
        </div>
      </article>
    );
  };

  return (
    <section
      ref={panelRef}
      className="chapter-margin-notes"
      aria-label={t("writing.marginNotes.aria")}
    >
      <div className="chapter-margin-notes__header">
        <strong>{t("writing.marginNotes.title")}</strong>
        <button
          type="button"
          className="chapter-margin-notes__button"
          disabled={disabled}
          onClick={beginCompose}
        >
          {t("writing.marginNotes.add")}
        </button>
      </div>
      <p className="chapter-margin-notes__hint">{t("writing.marginNotes.hint")}</p>
      {error && <p className="chapter-margin-notes__error">{error}</p>}
      {draft && (
        <form
          className="chapter-margin-notes__composer"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <p className="chapter-margin-notes__quote">
            {t("writing.marginNotes.anchor")}：{draft.anchorText}
          </p>
          <textarea
            className="chapter-margin-notes__body-input"
            value={body}
            maxLength={MARGIN_BODY_MAX}
            placeholder={t("writing.marginNotes.placeholder")}
            disabled={disabled}
            onChange={(event) => setBody(event.target.value)}
          />
          <div className="chapter-margin-notes__actions">
            <button
              type="submit"
              className="chapter-margin-notes__button"
              disabled={disabled || createNote.isPending}
            >
              {t("writing.marginNotes.save")}
            </button>
            <button
              type="button"
              className="chapter-margin-notes__button chapter-margin-notes__button--quiet"
              onClick={() => {
                setDraft(null);
                setBody("");
                setError(null);
              }}
            >
              {t("writing.marginNotes.cancel")}
            </button>
          </div>
        </form>
      )}
      {notes.length === 0 && !draft && (
        <p className="chapter-margin-notes__empty">{t("writing.marginNotes.empty")}</p>
      )}
      {openNotes.length > 0 && (
        <div className="chapter-margin-notes__list">
          {openNotes.map((note) => renderNote(note, false))}
        </div>
      )}
      {struckNotes.length > 0 && (
        <details className="chapter-margin-notes__struck">
          <summary>{t("writing.marginNotes.struckSection", { count: struckNotes.length })}</summary>
          <div className="chapter-margin-notes__list">
            {struckNotes.map((note) => renderNote(note, true))}
          </div>
        </details>
      )}
    </section>
  );
}
