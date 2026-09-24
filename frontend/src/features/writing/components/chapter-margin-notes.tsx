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
  MARGIN_NOTE_OPEN_EVENT,
  rangeForAnchor,
  readMarginNoteOpenId,
  readMarginSelection,
  type MarginMarkNote,
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

const EMPTY_NOTES: MarginNote[] = [];

function editorViewReady(editor: Editor): boolean {
  if (editor.isDestroyed) return false;
  try {
    return editor.view.dom.isConnected;
  } catch {
    return false;
  }
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
  const notes = data ?? EMPTY_NOTES;
  const [draft, setDraft] = useState<MarginSelection | null>(null);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [docVersion, setDocVersion] = useState(0);
  const [openedNoteId, setOpenedNoteId] = useState<string | null>(null);
  const seenRequest = useRef(0);
  const panelRef = useRef<HTMLElement>(null);
  const struckDetailsRef = useRef<HTMLDetailsElement>(null);

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
      const plain = editorPlainText(editor);
      const range = rangeForAnchor(
        editor.state.doc,
        plain,
        note.anchorText,
        note.contextBefore,
        note.contextAfter,
      );
      if (!range) {
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

  const revealNote = useCallback(
    (noteId: string) => {
      const note = notes.find((item) => item.id === noteId);
      if (!note) return;
      if (note.status === "struck" && struckDetailsRef.current) {
        struckDetailsRef.current.open = true;
      }
      setOpenedNoteId(noteId);
      window.requestAnimationFrame(() => {
        document.getElementById(`margin-note-${noteId}`)?.scrollIntoView({ block: "nearest" });
      });
    },
    [notes],
  );

  useEffect(() => {
    if (!editor) return;
    const marks: MarginMarkNote[] = notes.map((note) => ({
      id: note.id,
      anchorText: note.anchorText,
      contextBefore: note.contextBefore,
      contextAfter: note.contextAfter,
      status: note.status,
    }));
    let frame = 0;
    let attempts = 0;
    let cancelled = false;
    const apply = () => {
      if (cancelled) return;
      if (!editorViewReady(editor)) {
        attempts += 1;
        if (attempts > 60) return;
        frame = window.requestAnimationFrame(apply);
        return;
      }
      editor.commands.setMarginNoteMarks(marks);
    };
    apply();
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
    };
  }, [editor, notes]);

  useEffect(() => {
    if (!editor) return;
    let frame = 0;
    let attempts = 0;
    let cancelled = false;
    let dom: HTMLElement | null = null;
    const onOpen = (event: Event) => {
      const noteId = readMarginNoteOpenId(event);
      if (!noteId) return;
      revealNote(noteId);
    };
    const attach = () => {
      if (cancelled) return;
      if (!editorViewReady(editor)) {
        attempts += 1;
        if (attempts > 60) return;
        frame = window.requestAnimationFrame(attach);
        return;
      }
      dom = editor.view.dom;
      dom.addEventListener(MARGIN_NOTE_OPEN_EVENT, onOpen);
    };
    attach();
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
      dom?.removeEventListener(MARGIN_NOTE_OPEN_EVENT, onOpen);
    };
  }, [editor, revealNote]);

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

  const repin = async (note: MarginNote) => {
    if (disabled) return;
    if (!editor) {
      setError(t("writing.marginNotes.repinEmpty"));
      panelRef.current?.scrollIntoView({ block: "nearest" });
      return;
    }
    const selection = readMarginSelection(editor);
    if (!selection) {
      setError(t("writing.marginNotes.repinEmpty"));
      panelRef.current?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (selection.anchorText.length > MARGIN_ANCHOR_MAX) {
      setError(t("writing.marginNotes.tooLong"));
      panelRef.current?.scrollIntoView({ block: "nearest" });
      return;
    }
    try {
      await onPrepare?.();
      const updated = await updateNote.mutateAsync({
        noteId: note.id,
        data: {
          anchorText: selection.anchorText,
          contextBefore: selection.contextBefore,
          contextAfter: selection.contextAfter,
        },
      });
      setError(null);
      focusNote(updated);
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
        id={`margin-note-${note.id}`}
        className={`chapter-margin-notes__item${struck ? " chapter-margin-notes__item--struck" : ""}${
          openedNoteId === note.id ? " chapter-margin-notes__item--current" : ""
        }`}
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
          {!hit.aligned && (
            <button
              type="button"
              className="chapter-margin-notes__button"
              disabled={disabled || updateNote.isPending}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                void repin(note);
              }}
            >
              {t("writing.marginNotes.repin")}
            </button>
          )}
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
          onMouseDown={(event) => event.preventDefault()}
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
        <details
          ref={struckDetailsRef}
          className="chapter-margin-notes__struck"
        >
          <summary>{t("writing.marginNotes.struckSection", { count: struckNotes.length })}</summary>
          <div className="chapter-margin-notes__list">
            {struckNotes.map((note) => renderNote(note, true))}
          </div>
        </details>
      )}
    </section>
  );
}
