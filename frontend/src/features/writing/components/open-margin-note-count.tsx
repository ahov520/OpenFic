import { useTranslation } from "react-i18next";

import "./chapter-plan.css";

/**
 * 未划掉旁注的数量。0 条不渲染。点开会这一章，方便去处理。
 */
export function OpenMarginNoteCount({ count, onOpen }: { count: number; onOpen: () => void }) {
  const { t } = useTranslation();
  if (!count || count <= 0) return null;
  const label = t("writing.marginNotes.openCount", { count });

  return (
    <button
      type="button"
      className="open-margin-note-count"
      data-open-margin-count={count}
      aria-label={label}
      title={label}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        onOpen();
      }}
    >
      {count}
    </button>
  );
}
