import { Tooltip } from "@radix-ui/themes";
import { useTranslation } from "react-i18next";

import type { WritingStatus } from "@/lib/chapter-plan";
import { WRITING_STATUSES } from "@/lib/chapter-plan";

import "./chapter-plan.css";

export function WritingStatusMark({ status }: { status: WritingStatus }) {
  const { t } = useTranslation();
  const label = t(`writing.chapterPlan.statuses.${status}`);

  return (
    <Tooltip content={label}>
      <span
        className="writing-status-mark"
        data-status={status}
        aria-label={label}
      />
    </Tooltip>
  );
}

export function WritingStatusSelect({
  value,
  disabled = false,
  onChange,
}: {
  value: WritingStatus;
  disabled?: boolean;
  onChange: (status: WritingStatus) => void;
}) {
  const { t } = useTranslation();

  return (
    <select
      className="writing-status-select"
      value={value}
      disabled={disabled}
      aria-label={t("writing.chapterPlan.status")}
      onChange={(event) => onChange(event.target.value as WritingStatus)}
    >
      {WRITING_STATUSES.map((status) => (
        <option
          key={status}
          value={status}
        >
          {t(`writing.chapterPlan.statuses.${status}`)}
        </option>
      ))}
    </select>
  );
}
