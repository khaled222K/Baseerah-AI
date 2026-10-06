// Sources & reliability: categories come from GET /sources (nothing hardcoded).
import { getSources } from "./api.js";
import { icon } from "./icons.js";
import { initShell, el, stateBlock, formatNumber, MSG } from "./ui.js";

initShell("sources");
const root = document.getElementById("categories");
const ICON = { quran: "book", hadith: "layers", tafsir: "file", other: "sparkle" };

async function load() {
  root.replaceChildren(el("div", { class: "cat-grid" }, [0, 1, 2, 3].map(() => el("div", { class: "skeleton", style: "height:150px" }))));
  const r = await getSources();
  if (r.status !== "ok") {
    root.replaceChildren(stateBlock({ iconName: "alert", error: true, text: r.errorKind === "unavailable" ? MSG.unavailable : MSG.server,
      action: el("button", { class: "btn", type: "button", onclick: load }, icon("refresh", "icon-sm"), "إعادة المحاولة") }));
    return;
  }
  if (!r.categories.length) {
    root.replaceChildren(stateBlock({ text: "لم تُنشر قائمة المصادر بعد." }));
    return;
  }
  root.replaceChildren(el("div", { class: "cat-grid" }, r.categories.map((c) => el("article", { class: "card cat-card" },
    icon(ICON[c.type] || "book"),
    el("h3", { text: c.name }),
    c.count != null ? el("span", { class: "cat-count", text: `${formatNumber(c.count)} ${c.unit}` }) : null,
    c.description ? el("p", { text: c.description }) : null,
    c.items.length ? el("ul", { class: "cat-items" }, c.items.map((i) => el("li", { text: i.count != null ? `${i.name}: ${formatNumber(i.count)}` : i.name }))) : null))));
  const g = document.getElementById("grading-info");
  if (r.grading?.basis?.length) {
    g.textContent = `أساس الحكم على الأحاديث في القاعدة: ${r.grading.basis.join("، ")}.` +
      (r.grading.dorarMatched != null ? ` ومعها حكم الدرر السنية لـ ${formatNumber(r.grading.dorarMatched)} حديثًا.` : "");
  }
}
load();
