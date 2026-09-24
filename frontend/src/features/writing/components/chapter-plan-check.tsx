import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import { fetchPlanCheck, runPlanCheck } from "@/lib/api-client";
import type { Chapter } from "@/lib/chapter.types";
import type { PlanCheck, PlanCheckGap, PlanCheckLine } from "@/lib/plan-check";

import { usePlotThreads } from "../hooks/use-plot-threads";

interface ChapterPlanCheckProps {
  chapter: Chapter;
  manuscriptRevision: number;
  disabled?: boolean;
  onPrepareCheck?: () => Promise<void>;
  onFlushPlan?: () => Promise<void>;
}

export function ChapterPlanCheck({
  chapter,
  manuscriptRevision,
  disabled = false,
  onPrepareCheck,
  onFlushPlan,
}: ChapterPlanCheckProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: board } = usePlotThreads(chapter.projectId);
  const queryKey = useMemo(() => ["plan-check", chapter.id] as const, [chapter.id]);
  const query = useQuery({
    queryKey,
    queryFn: () => fetchPlanCheck(chapter.id),
  });
  const mutation = useMutation({
    mutationFn: () => runPlanCheck(chapter.id),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey });
    },
    onSuccess: (result: PlanCheck) => {
      queryClient.setQueryData(queryKey, result);
    },
  });
  const checkingRef = useRef(false);
  const skipRefreshRef = useRef(true);
  const refetch = query.refetch;
  const beatsKey = useMemo(() => {
    const threads = board?.threads ?? [];
    return threads
      .flatMap((thread) =>
        thread.beats
          .filter((beat) => beat.chapterId === chapter.id)
          .map(
            (beat) => `${beat.id}\0${beat.kind}\0${beat.note}\0${thread.name}\0${thread.intent}`,
          ),
      )
      .sort()
      .join("\n");
  }, [board?.threads, chapter.id]);

  useEffect(() => {
    if (skipRefreshRef.current) {
      skipRefreshRef.current = false;
      return;
    }
    if (checkingRef.current) return;
    void refetch();
  }, [beatsKey, chapter.synopsis, chapter.updatedAt, manuscriptRevision, refetch]);

  const result = query.data;
  const running = mutation.isPending;

  const run = async () => {
    if (disabled || running) return;
    checkingRef.current = true;
    try {
      await onPrepareCheck?.();
      await onFlushPlan?.();
      await mutation.mutateAsync();
    } catch {
      toast.error(t("writing.planCheck.failed"));
    } finally {
      checkingRef.current = false;
    }
  };

  return (
    <section
      className="chapter-plan-check"
      aria-label={t("writing.planCheck.title")}
    >
      <div className="chapter-plan-check__header">
        <span className="chapter-plan-check__title">{t("writing.planCheck.title")}</span>
        <button
          type="button"
          className="chapter-plan-check__button"
          disabled={disabled || running}
          onClick={() => {
            void run();
          }}
        >
          {running ? t("writing.planCheck.running") : t("writing.planCheck.run")}
        </button>
      </div>
      <div
        className="chapter-plan-check__body"
        aria-live="polite"
      >
        {result ? (
          <PlanCheckBody result={result} />
        ) : (
          <p className="chapter-plan-check__hint">{t("writing.planCheck.hint")}</p>
        )}
      </div>
    </section>
  );
}

function PlanCheckBody({ result }: { result: PlanCheck }) {
  const { t } = useTranslation();
  if (!result.hasPlan) {
    return (
      <p className="chapter-plan-check__empty">
        {result.freshness === "stale"
          ? t("writing.planCheck.noPlanStale")
          : t("writing.planCheck.noPlan")}
      </p>
    );
  }
  if (
    result.freshness === "unchecked" ||
    (result.freshness === "stale" && result.source === "empty")
  ) {
    return (
      <p className="chapter-plan-check__hint">
        {result.source === "empty"
          ? t("writing.planCheck.planAdded")
          : t("writing.planCheck.prompt")}
      </p>
    );
  }

  return (
    <div data-freshness={result.freshness}>
      {result.freshness === "stale" && (
        <p className="chapter-plan-check__stale">{t("writing.planCheck.stale")}</p>
      )}
      {result.outcome === "clear" && result.source === "model" && (
        <p className="chapter-plan-check__clear">{t("writing.planCheck.modelClear")}</p>
      )}
      {result.outcome === "clear" && result.source === "literal" && (
        <p className="chapter-plan-check__clear">{t("writing.planCheck.literalClear")}</p>
      )}
      {result.outcome === "partial" && (
        <p className="chapter-plan-check__hint">{t("writing.planCheck.partial")}</p>
      )}
      {result.gaps.length > 0 && (
        <ul className="chapter-plan-check__list">
          {result.gaps.map((gap) => (
            <GapItem
              key={gap.ref}
              gap={gap}
            />
          ))}
        </ul>
      )}
      {result.unchecked.length > 0 && (
        <ul className="chapter-plan-check__list">
          {result.unchecked.map((line) => (
            <UncheckedItem
              key={line.ref}
              line={line}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function GapItem({ gap }: { gap: PlanCheckGap }) {
  const { t } = useTranslation();
  return (
    <li
      className="chapter-plan-check__gap"
      data-basis={gap.basis}
    >
      <p className="chapter-plan-check__basis">
        {gap.basis === "model"
          ? t("writing.planCheck.modelBadge")
          : t("writing.planCheck.literalBadge")}
      </p>
      <p className="chapter-plan-check__plan">{planLabel(t, gap)}</p>
      <p className="chapter-plan-check__detail">
        {gap.basis === "literal"
          ? t("writing.planCheck.missingLiteral", { items: gap.missing.join("、") })
          : gap.detail}
      </p>
    </li>
  );
}

function UncheckedItem({ line }: { line: PlanCheckLine }) {
  const { t } = useTranslation();
  return (
    <li className="chapter-plan-check__gap">
      <p className="chapter-plan-check__basis">{t("writing.planCheck.uncheckedItem")}</p>
      <p className="chapter-plan-check__plan">{planLabel(t, line)}</p>
    </li>
  );
}

function planLabel(
  t: TFunction,
  item: { origin: string; planText: string; beatKind: string | null; threadName: string | null },
) {
  const quote = item.planText;
  if (item.origin === "beat" && item.beatKind && item.threadName) {
    const kind = t(`writing.plotThreads.kinds.${item.beatKind}`);
    return t("writing.planCheck.beatLine", { kind, name: item.threadName, text: quote });
  }
  return t("writing.planCheck.synopsisLine", { text: quote });
}
