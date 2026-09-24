import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import {
  WORD_COUNT_TARGET_MAX,
  chapterLengthProgress,
  parseWordCountTarget,
} from "@/lib/chapter-length";

import { useUpdateChapter } from "../hooks/use-chapters";

import "./chapter-plan.css";

interface ChapterWordTargetProps {
  chapterId: string;
  written: number;
  target: number | null;
  disabled?: boolean;
}

export function ChapterWordTarget({
  chapterId,
  written,
  target,
  disabled = false,
}: ChapterWordTargetProps) {
  const { t } = useTranslation();
  const updateMutation = useUpdateChapter();
  const [draft, setDraft] = useState(target == null ? "" : String(target));
  const [invalid, setInvalid] = useState(false);
  const focusedRef = useRef(false);
  const savingRef = useRef(false);
  const progress = chapterLengthProgress(written, target);
  const barWidth =
    progress.target == null
      ? 0
      : Math.min(100, Math.round((progress.written / progress.target) * 100));

  useEffect(() => {
    if (focusedRef.current) return;
    setDraft(target == null ? "" : String(target));
    setInvalid(false);
  }, [target]);

  const commit = useCallback(async () => {
    if (disabled || savingRef.current) return;
    const parsed = parseWordCountTarget(draft);
    if (!parsed.ok) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    if (parsed.value === target) return;
    savingRef.current = true;
    try {
      await updateMutation.mutateAsync({
        chapterId,
        data: { wordCountTarget: parsed.value },
      });
    } catch {
      toast.error(t("writing.chapterLength.saveFailed"));
    } finally {
      savingRef.current = false;
    }
  }, [chapterId, disabled, draft, t, target, updateMutation]);

  const paceLabel =
    progress.pace === "short"
      ? t("writing.chapterLength.short")
      : progress.pace === "over"
        ? t("writing.chapterLength.long")
        : progress.pace === "met"
          ? t("writing.chapterLength.onTarget")
          : null;

  return (
    <div
      className="chapter-length"
      data-pace={progress.pace}
      data-testid="chapter-word-target"
    >
      <div className="chapter-length__readout">
        {paceLabel ? <span className="chapter-length__badge">{paceLabel}</span> : null}
        <span>{t("writing.chapterLength.written", { count: written })}</span>
        {progress.pace === "short" ? (
          <span>{t("writing.chapterLength.remaining", { count: progress.remaining })}</span>
        ) : null}
        {progress.pace === "over" ? (
          <span>{t("writing.chapterLength.over", { count: progress.over })}</span>
        ) : null}
        {progress.pace === "met" ? <span>{t("writing.chapterLength.met")}</span> : null}
      </div>
      {progress.target != null ? (
        <div
          className="chapter-length__bar"
          aria-hidden="true"
        >
          <span style={{ width: `${barWidth}%` }} />
        </div>
      ) : null}
      <label className="chapter-length__field">
        <span>{t("writing.chapterLength.target")}</span>
        <input
          value={draft}
          disabled={disabled}
          inputMode="numeric"
          placeholder={t("writing.chapterLength.targetPlaceholder")}
          aria-label={t("writing.chapterLength.aria")}
          onFocus={() => {
            focusedRef.current = true;
          }}
          onChange={(event) => {
            focusedRef.current = true;
            setDraft(event.target.value);
            setInvalid(false);
          }}
          onBlur={() => {
            focusedRef.current = false;
            void commit();
          }}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            event.currentTarget.blur();
          }}
        />
      </label>
      {invalid ? (
        <p className="chapter-length__error">
          {t("writing.chapterLength.invalid", { max: WORD_COUNT_TARGET_MAX })}
        </p>
      ) : null}
    </div>
  );
}
