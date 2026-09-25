import { Button, Dialog, Flex, Progress, SegmentedControl, Select, Text } from "@radix-ui/themes";
import {
  AlertCircle,
  CheckCircle2,
  FileCheck2,
  LoaderCircle,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import "./creation-evidence-dialog.css";

import {
  cancelCreationEvidenceReport,
  createCreationEvidenceReport,
  fetchCreationEvidenceReport,
} from "@/lib/api-client";
import { subscribeBackgroundEvents } from "@/lib/background-socket";
import type { CreationEvidenceReport } from "@/lib/creation-evidence.types";
import type { VolumeWithChapters } from "@/lib/chapter.types";
import { getSocketConnectionStatus, subscribeSocketConnectionStatus } from "@/lib/socket-client";

interface CreationEvidenceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  volumes: VolumeWithChapters[];
  currentChapterId?: string | null;
}

type CreationEvidenceStep = "selecting" | "exporting" | "complete" | "error";
type CreationEvidenceScope = "project" | "chapter";

const ACTIVE_REPORT_STATUSES = new Set(["pending", "running", "cancel_requested"]);
const CREATION_EVIDENCE_I18N_KEY = "writing.creationEvidence";

function getLocalDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function triggerReportDownload(url: string | null): void {
  if (!url) return;
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function triggerAllReportDownloads(report: CreationEvidenceReport): void {
  triggerReportDownload(report.htmlDownloadUrl);
  triggerReportDownload(report.jsonDownloadUrl);
}

export function CreationEvidenceDialog({
  open,
  onOpenChange,
  projectId,
  volumes,
  currentChapterId,
}: CreationEvidenceDialogProps) {
  const { t } = useTranslation();
  const chapters = useMemo(() => volumes.flatMap((volume) => volume.chapters), [volumes]);
  const hasCurrentChapter = chapters.some((chapter) => chapter.id === currentChapterId);
  const [scope, setScope] = useState<CreationEvidenceScope>("project");
  const [chapterId, setChapterId] = useState<string | null>(null);
  const [step, setStep] = useState<CreationEvidenceStep>("selecting");
  const [report, setReport] = useState<CreationEvidenceReport | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const downloadedReportIdRef = useRef<string | null>(null);

  const activeReportId = report?.id;
  const activeReportStatus = report?.status;
  const progress = report && report.total > 0 ? (report.current / report.total) * 100 : 0;

  useEffect(() => {
    if (!open) return;
    setScope(hasCurrentChapter ? "chapter" : "project");
    setChapterId(hasCurrentChapter ? (currentChapterId ?? null) : null);
    setStep("selecting");
    setReport(null);
    setErrorMessage(null);
    setIsSubmitting(false);
    setIsCancelling(false);
    downloadedReportIdRef.current = null;
  }, [open, projectId, hasCurrentChapter, currentChapterId]);

  useEffect(() => {
    if (!open || !activeReportId || !activeReportStatus || !ACTIVE_REPORT_STATUSES.has(activeReportStatus)) {
      return;
    }
    let disposed = false;
    const refresh = async () => {
      try {
        const nextReport = await fetchCreationEvidenceReport(projectId, activeReportId);
        if (!disposed) setReport(nextReport);
      } catch (error) {
        if (!disposed) {
          setErrorMessage(
            error instanceof Error ? error.message : t(`${CREATION_EVIDENCE_I18N_KEY}.statusLoadFailed`),
          );
          setStep("error");
        }
      }
    };
    let pollingInterval: number | null = null;
    const startPolling = () => {
      if (pollingInterval !== null) return;
      void refresh();
      pollingInterval = window.setInterval(() => void refresh(), 1200);
    };
    const stopPolling = () => {
      if (pollingInterval === null) return;
      window.clearInterval(pollingInterval);
      pollingInterval = null;
    };
    const subscription = subscribeBackgroundEvents(
      projectId,
      (event) => {
        if (event.job_id !== activeReportId || !event.type.startsWith("background_job_")) return;
        if (event.type === "background_job_progress") return;
        void refresh();
      },
      () => {
        if (getSocketConnectionStatus() === "disconnected") startPolling();
      },
    );
    const unsubscribeSocketStatus = subscribeSocketConnectionStatus(() => {
      if (getSocketConnectionStatus() === "connected") stopPolling();
      else startPolling();
    });
    if (getSocketConnectionStatus() === "disconnected") startPolling();
    void refresh();
    return () => {
      disposed = true;
      subscription.close();
      unsubscribeSocketStatus();
      stopPolling();
    };
  }, [activeReportId, activeReportStatus, open, projectId, t]);

  useEffect(() => {
    if (!report) return;
    if (report.status === "succeeded") {
      setStep("complete");
      setIsCancelling(false);
      if (downloadedReportIdRef.current !== report.id) {
        downloadedReportIdRef.current = report.id;
        triggerAllReportDownloads(report);
      }
      return;
    }
    if (["failed", "timeout", "cancelled", "skipped"].includes(report.status)) {
      setStep("error");
      setIsCancelling(false);
      setErrorMessage(
        report.status === "cancelled"
          ? t(`${CREATION_EVIDENCE_I18N_KEY}.cancelled`)
          : (report.errorMessage ?? t(`${CREATION_EVIDENCE_I18N_KEY}.failed`)),
      );
    }
  }, [report, t]);

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && step === "exporting") return;
    onOpenChange(nextOpen);
  };

  const handleStart = async () => {
    const selectedChapterId = scope === "chapter" ? chapterId : null;
    if (scope === "chapter" && !selectedChapterId) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const nextReport = await createCreationEvidenceReport(projectId, {
        chapterId: selectedChapterId,
        localDate: getLocalDate(),
      });
      setReport(nextReport);
      setStep("exporting");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : t(`${CREATION_EVIDENCE_I18N_KEY}.failed`));
      setStep("error");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    if (!report || isCancelling) return;
    setIsCancelling(true);
    try {
      setReport(await cancelCreationEvidenceReport(projectId, report.id));
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : t(`${CREATION_EVIDENCE_I18N_KEY}.cancelFailed`),
      );
      setIsCancelling(false);
    }
  };

  const handleBack = () => {
    setStep("selecting");
    setReport(null);
    setErrorMessage(null);
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={handleOpenChange}
    >
      <Dialog.Content maxWidth="520px">
        <Dialog.Title>{t(`${CREATION_EVIDENCE_I18N_KEY}.title`)}</Dialog.Title>
        <Dialog.Description size="2" color="gray">
          {t(`${CREATION_EVIDENCE_I18N_KEY}.description`)}
        </Dialog.Description>

        {step === "selecting" && (
          <Flex
            direction="column"
            gap="3"
            mt="4"
          >
            <label>
              <Text
                as="div"
                size="2"
                weight="bold"
                mb="1"
              >
                {t(`${CREATION_EVIDENCE_I18N_KEY}.scope`)}
              </Text>
              <SegmentedControl.Root
                value={scope}
                onValueChange={(value) => setScope(value as CreationEvidenceScope)}
              >
                <SegmentedControl.Item value="project">
                  {t(`${CREATION_EVIDENCE_I18N_KEY}.scopeProject`)}
                </SegmentedControl.Item>
                <SegmentedControl.Item value="chapter">
                  {t(`${CREATION_EVIDENCE_I18N_KEY}.scopeChapter`)}
                </SegmentedControl.Item>
              </SegmentedControl.Root>
            </label>
            {scope === "chapter" && (
              <label>
                <Text
                  as="div"
                  size="2"
                  weight="bold"
                  mb="1"
                >
                  {t(`${CREATION_EVIDENCE_I18N_KEY}.chapter`)}
                </Text>
                <Select.Root
                  value={chapterId ?? undefined}
                  onValueChange={(value) => setChapterId(value)}
                >
                  <Select.Trigger
                    placeholder={t(`${CREATION_EVIDENCE_I18N_KEY}.chapterPlaceholder`)}
                    style={{ width: "100%" }}
                  />
                  <Select.Content>
                    {chapters.map((chapter) => (
                      <Select.Item
                        key={chapter.id}
                        value={chapter.id}
                      >
                        {chapter.title || t("writing.untitledChapter")}
                      </Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
              </label>
            )}
            <Text
              size="1"
              color="gray"
            >
              {t(`${CREATION_EVIDENCE_I18N_KEY}.outputs`)}
            </Text>
          </Flex>
        )}

        {step === "exporting" && (
          <Flex
            direction="column"
            align="center"
            gap="3"
            mt="5"
            mb="2"
          >
            <LoaderCircle
              className="creation-evidence-spinner"
              size={30}
            />
            <Text weight="bold">
              {isCancelling
                ? t(`${CREATION_EVIDENCE_I18N_KEY}.cancelling`)
                : t(`${CREATION_EVIDENCE_I18N_KEY}.exporting`)}
            </Text>
            <Progress
              value={progress}
              max={100}
              size="2"
              style={{ width: "100%" }}
            />
          </Flex>
        )}

        {step === "complete" && report && (
          <Flex
            direction="column"
            align="center"
            gap="3"
            mt="5"
            mb="2"
          >
            <CheckCircle2
              size={40}
              color="var(--green-9)"
            />
            <Text
              size="4"
              weight="bold"
            >
              {t(`${CREATION_EVIDENCE_I18N_KEY}.success`)}
            </Text>
            <div className="creation-evidence-filename">{report.filename}</div>
          </Flex>
        )}

        {step === "error" && (
          <Flex
            direction="column"
            align="center"
            gap="3"
            mt="5"
            mb="2"
          >
            <AlertCircle
              size={36}
              color="var(--red-9)"
            />
            <Text
              size="4"
              weight="bold"
            >
              {t(`${CREATION_EVIDENCE_I18N_KEY}.errorTitle`)}
            </Text>
            <Text
              size="2"
              color="gray"
              align="center"
            >
              {errorMessage ?? t(`${CREATION_EVIDENCE_I18N_KEY}.failed`)}
            </Text>
          </Flex>
        )}

        <Flex
          justify="end"
          gap="2"
          mt="4"
        >
          {step === "selecting" && (
            <>
              <Button
                variant="soft"
                color="gray"
                onClick={() => handleOpenChange(false)}
              >
                {t("common.cancel")}
              </Button>
              <Button
                onClick={() => void handleStart()}
                loading={isSubmitting}
                disabled={scope === "chapter" && !chapterId}
              >
                <FileCheck2 size={16} />
                {t(`${CREATION_EVIDENCE_I18N_KEY}.generate`)}
              </Button>
            </>
          )}
          {step === "exporting" && (
            <Button
              variant="soft"
              color="red"
              disabled={isCancelling}
              onClick={() => void handleCancel()}
            >
              <X size={16} />
              {t(`${CREATION_EVIDENCE_I18N_KEY}.cancelExport`)}
            </Button>
          )}
          {step === "complete" && report && (
            <>
              <Button
                variant="soft"
                color="gray"
                onClick={() => handleOpenChange(false)}
              >
                {t("common.close")}
              </Button>
              <Button onClick={() => triggerAllReportDownloads(report)}>
                {t(`${CREATION_EVIDENCE_I18N_KEY}.downloadAgain`)}
              </Button>
            </>
          )}
          {step === "error" && (
            <Button onClick={handleBack}>
              {t(`${CREATION_EVIDENCE_I18N_KEY}.backToScope`)}
            </Button>
          )}
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
