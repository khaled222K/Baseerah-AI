// Saved answers (localStorage).
import { icon } from "./icons.js";
import { listSaved, unsaveAnswer } from "./storage.js";
import { initShell, el, stateBlock, dialog, formatDate, excerpt, toast, sourceCard, richText, AI_NOTICE, MSG } from "./ui.js";

initShell("saved");
const root = document.getElementById("saved-root");

function openSaved(item) {
  const r = item.response;
  dialog(item.question, el("div", { class: "answer" },
    el("div", { class: "answer-card" },
      r.answer ? el("div", { class: "answer-text" }, richText(r.answer))
               : el("p", { class: "answer-message", text: r.message || MSG.noEvidence })),
    r.sources?.length ? el("div", { class: "source-grid" }, r.sources.map(sourceCard)) : null,
    el("div", { class: "notice" }, icon("info"), el("span", { text: AI_NOTICE }))));
}

function render() {
  const items = listSaved();
  if (!items.length) {
    root.replaceChildren(stateBlock({ iconName: "bookmark", text: "لا توجد إجابات محفوظة بعد.",
      action: el("a", { class: "btn btn-primary", href: "index.html" }, "اسألي بصيرة") }));
    return;
  }
  root.replaceChildren(el("ul", { class: "saved-list" }, items.map((it) => el("li", {},
    el("article", { class: "card saved-card" },
      el("h2", { class: "saved-q", text: it.question }),
      el("p", { class: "saved-preview", text: excerpt(it.response?.answer || it.response?.message || "", 200) }),
      el("div", { class: "saved-meta" },
        el("span", { class: "saved-date" }, icon("clock", "icon-sm"), ` حُفظت في ${formatDate(it.savedAt)}`),
        el("div", { class: "saved-actions" },
          el("button", { class: "btn", type: "button", onclick: () => openSaved(it) }, icon("file", "icon-sm"), "فتح الإجابة"),
          el("button", { class: "btn btn-ghost", type: "button", "aria-label": `حذف: ${it.question}`,
            onclick: () => { unsaveAnswer(it.id); toast("تم حذف الإجابة من المحفوظات"); render(); } }, icon("trash", "icon-sm"), "حذف"))))))));
}
window.addEventListener("baseerah:storage", render);
render();
