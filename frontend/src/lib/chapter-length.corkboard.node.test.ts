import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import i18next from "i18next";

import { corkboardLengthLabel } from "./chapter-length.ts";

const here = dirname(fileURLToPath(import.meta.url));
const zh = JSON.parse(readFileSync(join(here, "../i18n/locales/zh-CN.json"), "utf8")) as {
  writing: { chapterLength: Record<string, string> };
};

const i18n = i18next.createInstance();
await i18n.init({
  lng: "zh-CN",
  resources: { "zh-CN": { translation: zh } },
  interpolation: { escapeValue: false },
});

function cardLabel(written: number, target: number | null): string | null {
  return (
    corkboardLengthLabel(written, target, (key, options) =>
      options ? i18n.t(key, options) : i18n.t(key),
    )?.text ?? null
  );
}

test("没有目标时不出现还差", () => {
  const text = cardLabel(40, null);
  assert.equal(text, null);
  assert.equal(cardLabel(0, null), null);
});

test("已写少于目标时显示还差", () => {
  assert.equal(cardLabel(40, 100), "还差 60");
});

test("刚好达到时不显示还差，标达标", () => {
  const text = cardLabel(100, 100);
  assert.equal(text, "达标");
  assert.equal(text?.includes("还差"), false);
});

test("超出目标时显示超出，不说还差", () => {
  const text = cardLabel(120, 100);
  assert.equal(text, "超出 20");
  assert.equal(text?.includes("还差"), false);
});

test("字数变化后还差跟着变", () => {
  assert.equal(cardLabel(70, 100), "还差 30");
  assert.equal(cardLabel(100, 100), "达标");
});

test("还差标在梗概上方，梗概再长也盖不住", () => {
  const card = readFileSync(
    join(here, "../features/writing/components/chapter-corkboard.tsx"),
    "utf8",
  );
  const mark = card.indexOf("<ChapterCorkboardLength");
  const synopsis = card.indexOf('className="chapter-corkboard-card__synopsis"');
  assert.ok(card.includes('data-testid="corkboard-length-mark"'), "卡片上要有还差标记");
  assert.ok(mark > 0 && synopsis > mark, "还差要画在梗概前面，不能只放在梗概下面");

  const css = readFileSync(join(here, "../features/writing/components/chapter-plan.css"), "utf8");
  const gapRule = css.slice(css.indexOf(".chapter-corkboard-card__gap {"));
  assert.match(gapRule, /flex-shrink:\s*0/);
  const synopsisRule = css.slice(css.lastIndexOf(".chapter-corkboard-card__synopsis {"));
  assert.match(synopsisRule, /max-height:/);
  assert.match(synopsisRule, /overflow:\s*auto/);
  assert.match(synopsisRule, /resize:\s*none/);
});
