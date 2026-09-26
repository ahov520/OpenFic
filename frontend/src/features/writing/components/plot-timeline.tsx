import { Button, Dialog, Flex, Select, Text, TextArea } from "@radix-ui/themes";
import axios from "axios";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { toast } from "@/components";
import type {
  PlotBeat,
  PlotBeatKind,
  PlotChapterOption,
  PlotThread,
} from "@/lib/plot-thread";
import { PLOT_BEAT_KINDS } from "@/lib/plot-thread";

import {
  useCreatePlotBeat,
  useDeletePlotBeat,
  useUpdatePlotBeat,
} from "../hooks/use-plot-threads";
import { buildTimelineRows } from "../lib/plot-timeline";
import "./plot-timeline.css";

interface PlotTimelineProps {
  projectId: string;
  threads: PlotThread[];
  chapters: PlotChapterOption[];
  disabled?: boolean;
  onOpenChapter: (chapterId: string, chapterTitle: string) => void;
}

interface EditingCell {
  thread: PlotThread;
  chapter: PlotChapterOption;
  beat: PlotBeat | null;
}

/** 情节线时间轴：行是情节线，列是按阅读顺序排列的章节，格子点击可直接增改节拍。 */
export function PlotTimeline({
  projectId,
  threads,
  chapters,
  disabled = false,
  onOpenChapter,
}: PlotTimelineProps) {
  const { t } = useTranslation();
  const rows = buildTimelineRows(threads, chapters);
  const [editing, setEditing] = useState<EditingCell | null>(null);
  const [kind, setKind] = useState<PlotBeatKind>("plant");
  const [note, setNote] = useState("");

  const createBeat = useCreatePlotBeat(projectId);
  const updateBeat = useUpdatePlotBeat(projectId);
  const deleteBeat = useDeletePlotBeat(projectId);

  const openCell = (thread: PlotThread, chapter: PlotChapterOption, beat: PlotBeat | null) => {
    if (disabled) return;
    setEditing({ thread, chapter, beat });
    setKind(beat?.kind ?? "plant");
    setNote(beat?.note ?? "");
  };

  const close = () => setEditing(null);

  const save = async () => {
    if (!editing) return;
    try {
      if (editing.beat) {
        await updateBeat.mutateAsync({
          beatId: editing.beat.id,
          data: { kind, note: note.trim() },
        });
      } else {
        await createBeat.mutateAsync({
          threadId: editing.thread.id,
          data: { chapterId: editing.chapter.id, kind, note: note.trim() },
        });
      }
      close();
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        toast.error(t("writing.plotThreads.duplicateBeat"));
      } else {
        toast.error(t("writing.plotThreads.saveFailed"));
      }
    }
  };

  const remove = async () => {
    if (!editing?.beat) return;
    try {
      await deleteBeat.mutateAsync(editing.beat.id);
      close();
    } catch {
      toast.error(t("writing.plotThreads.saveFailed"));
    }
  };

  const pending = createBeat.isPending || updateBeat.isPending || deleteBeat.isPending;

  return (
    <div className="plot-timeline-scroll">
      <div
        className="plot-timeline-grid"
        style={{ gridTemplateColumns: `var(--plot-timeline-name-width) repeat(${chapters.length}, var(--plot-timeline-cell-width))` }}
      >
        <div className="plot-timeline__corner">
          {t("writing.plotThreads.timelineCorner")}
        </div>
        {chapters.map((chapter) => (
          <button
            key={chapter.id}
            type="button"
            className="plot-timeline__chapter"
            title={t("writing.plotThreads.timelineChapterTitle", {
              order: chapter.globalOrder,
              title: chapter.title,
              volume: chapter.volumeTitle,
            })}
            onClick={() => onOpenChapter(chapter.id, chapter.title)}
          >
            {chapter.globalOrder}
          </button>
        ))}
        {rows.map((row) => (
          <TimelineRowCells
            key={row.thread.id}
            thread={row.thread}
            cells={row.cells}
            disabled={disabled}
            onCellClick={openCell}
          />
        ))}
      </div>
      {chapters.length === 0 && (
        <Text
          as="p"
          size="1"
          color="gray"
          mt="3"
        >
          {t("writing.plotThreads.noChapters")}
        </Text>
      )}

      <Dialog.Root
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <Dialog.Content maxWidth="400px">
          {editing && (
            <>
              <Dialog.Title size="2">
                {t("writing.plotThreads.timelineEditTitle", {
                  thread: editing.thread.name,
                  order: editing.chapter.globalOrder,
                  chapter: editing.chapter.title,
                })}
              </Dialog.Title>
              <Dialog.Description
                size="1"
                color="gray"
              >
                {t("writing.plotThreads.timelineEditHint")}
              </Dialog.Description>
              <Flex
                direction="column"
                gap="3"
                mt="3"
              >
                <Flex
                  align="center"
                  gap="2"
                >
                  <Text size="1">{t("writing.plotThreads.kind")}</Text>
                  <Select.Root
                    size="1"
                    value={kind}
                    onValueChange={(value) => setKind(value as PlotBeatKind)}
                  >
                    <Select.Trigger aria-label={t("writing.plotThreads.kind")} />
                    <Select.Content>
                      {PLOT_BEAT_KINDS.map((item) => (
                        <Select.Item
                          key={item}
                          value={item}
                        >
                          {t(`writing.plotThreads.kinds.${item}`)}
                        </Select.Item>
                      ))}
                    </Select.Content>
                  </Select.Root>
                </Flex>
                <TextArea
                  size="1"
                  placeholder={t("writing.plotThreads.notePlaceholder")}
                  value={note}
                  maxLength={2000}
                  onChange={(event) => setNote(event.target.value)}
                  style={{ minHeight: 64 }}
                />
                <Flex
                  justify="between"
                  gap="2"
                >
                  {editing.beat ? (
                    <Button
                      variant="soft"
                      color="red"
                      size="1"
                      disabled={pending}
                      onClick={() => void remove()}
                    >
                      {t("writing.plotThreads.deleteBeat")}
                    </Button>
                  ) : (
                    <span />
                  )}
                  <Flex
                    gap="2"
                    align="center"
                  >
                    <Button
                      variant="soft"
                      color="gray"
                      size="1"
                      onClick={() => onOpenChapter(editing.chapter.id, editing.chapter.title)}
                    >
                      {t("writing.plotThreads.timelineOpenChapter")}
                    </Button>
                    <Button
                      variant="soft"
                      color="gray"
                      size="1"
                      onClick={close}
                    >
                      {t("common.cancel")}
                    </Button>
                    <Button
                      size="1"
                      loading={pending}
                      onClick={() => void save()}
                    >
                      {t("common.confirm")}
                    </Button>
                  </Flex>
                </Flex>
              </Flex>
            </>
          )}
        </Dialog.Content>
      </Dialog.Root>
    </div>
  );
}

function TimelineRowCells({
  thread,
  cells,
  disabled,
  onCellClick,
}: {
  thread: PlotThread;
  cells: ReturnType<typeof buildTimelineRows>[number]["cells"];
  disabled: boolean;
  onCellClick: (thread: PlotThread, chapter: PlotChapterOption, beat: PlotBeat | null) => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <Flex
        align="center"
        className="plot-timeline__name"
        title={thread.intent || thread.name}
      >
        <Text
          size="1"
          truncate
        >
          {thread.name}
        </Text>
      </Flex>
      {cells.map((cell) => {
        const kindLabel = cell.beat
          ? t(`writing.plotThreads.kinds.${cell.beat.kind}`)
          : "";
        if (!cell.beat) {
          return (
            <button
              key={cell.chapter.id}
              type="button"
              className="plot-timeline__cell plot-timeline__cell--empty"
              aria-label={t("writing.plotThreads.timelineAddBeat", {
                thread: thread.name,
                order: cell.chapter.globalOrder,
              })}
              disabled={disabled}
              onClick={() => onCellClick(thread, cell.chapter, null)}
            />
          );
        }
        return (
          <button
            key={cell.chapter.id}
            type="button"
            className={`plot-timeline__cell plot-timeline__cell--${cell.beat.kind}`}
            title={t("writing.plotThreads.timelineCellTitle", {
              chapter: cell.chapter.title,
              kind: kindLabel,
              note: cell.beat.note,
            })}
            disabled={disabled}
            onClick={() => onCellClick(thread, cell.chapter, cell.beat)}
          >
            {kindLabel.slice(0, 1)}
          </button>
        );
      })}
    </>
  );
}
