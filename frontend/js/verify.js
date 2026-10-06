// Verify evidence: compares submitted wording with stored texts (backend /verify).
import { verify } from "./api.js";
import { icon } from "./icons.js";
import { initShell, el, loader, toast, copyText, externalLink, sourceDetail, explainButton, MSG } from "./ui.js";

initShell("verify");
const MAX = 500;
const form = document.getElementById("verify-form");
const input = document.getElementById("verify-text");
const btn = document.getElementById("verify-btn");
const counter = document.getElementById("verify-count");
const out = document.getElementById("verify-result");
let busy = false;

function update() {
  const n = input.value.length;
  counter.textContent = `${n}/${MAX}`;
  counter.classList.toggle("is-over", n >= MAX);
  btn.disabled = busy || !input.value.trim();
}
input.addEventListener("input", update);

const VERDICT = {
  matched: { cls: "is-matched", icon: "check", title: "الدليل صحيح" },
  partial_match: { cls: "is-partial", icon: "help", title: "تطابق جزئي" },
  not_matched: { cls: "is-not", icon: "alert", title: "الصيغة غير مطابقة" },
  insufficient_evidence: { cls: "is-insufficient", icon: "info", title: "لا يكفي للتحقق" },
  error: { cls: "is-error", icon: "alert", title: "تعذر التحقق" },
};

function render(r) {
  const v = VERDICT[r.status];
  let message;
  if (r.status === "error") message = r.errorKind === "unavailable" ? MSG.unavailable : r.errorKind === "invalid" ? MSG.invalid : MSG.server;
  else if (r.status === "insufficient_evidence") {
    message = "لم يتم العثور على مصدر كافٍ للتحقق من هذا النص.";
    if (r.reason === "too_short") message += " النص قصير جدًا؛ أدخلي ثلاث كلمات على الأقل.";
  } else if (r.status === "not_matched") {
    message = r.message || "الصيغة المُدخلة لا تطابق النص المخزن في المصادر المتاحة لدى بصيرة.";
  } else message = r.message || "";

  const card = el("article", { class: "card card-pad" },
    el("div", { class: `verdict ${v.cls}` }, el("div", { class: "verdict-icon", "aria-hidden": "true" }, icon(v.icon)), el("h2", { text: v.title })),
    message ? el("p", { text: message, role: r.status === "error" ? "alert" : null }) : null);

  const s = r.sources[0];
  if (s && (r.status === "matched" || r.status === "partial_match")) {
    card.append(el("p", { class: "source-ref", text: r.status === "partial_match"
      ? "النص المخزن الأقرب (يُعرض كما هو للمقارنة، وليس مطابقًا لما أدخلتِه):" : "النص كما هو في المصدر المخزن:" }));
    card.append(el("div", { class: "stored-text" },
      el("div", { class: "source-cover", "data-type": s.type, "aria-hidden": "true" }, icon(s.type === "tafsir" ? "file" : "book")),
      el("blockquote", { text: s.text })));
    const info = el("dl", { class: "kv" });
    const add = (k, val) => { if (val != null && val !== "") info.append(el("dt", { text: k }), el("dd", { dir: "auto" }, val)); };
    add("المصدر", s.name);
    add("المرجع", s.reference);
    add("الحكم", s.grade);
    if (r.coverage != null) {
      add("نسبة التطابق اللفظي", el("span", {}, el("span", { class: "meter", "aria-hidden": "true" }, el("i", { style: `width:${Math.round(r.coverage * 100)}%` })),
        ` ${Math.round(r.coverage * 100)}%` + (r.matchedWords != null ? ` (${r.matchedWords} من أصل ${r.totalWords} كلمات)` : "")));
    }
    add("طريقة التحقق", r.method);
    card.append(info);
    const details = el("div", { class: "details", hidden: true }, sourceDetail(s));
    const toggle = el("button", { class: "btn", type: "button", "aria-expanded": "false" }, icon("chevronDown", "icon-sm"), "عرض التفاصيل");
    toggle.addEventListener("click", () => {
      details.hidden = !details.hidden;
      toggle.setAttribute("aria-expanded", String(!details.hidden));
      toggle.lastChild.textContent = details.hidden ? "عرض التفاصيل" : "إخفاء التفاصيل";
    });
    card.append(el("div", { class: "verify-actions", style: "margin-top:14px" },
      externalLink(s.url, "فتح المصدر الأصلي", "btn btn-primary"),
      el("button", { class: "btn", type: "button", onclick: async () => toast((await copyText(`${s.text}\n${s.name} — ${s.reference}`)) ? "تم نسخ النص" : "تعذر النسخ") },
        icon("copy", "icon-sm"), "نسخ النص"),
      explainButton(s, "btn"),
      toggle), details);
  }
  if (r.status === "error") {
    card.append(el("button", { class: "btn", type: "button", onclick: () => form.requestSubmit() }, icon("refresh", "icon-sm"), "إعادة المحاولة"));
  }
  out.replaceChildren(card);
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || busy) return;
  busy = true;
  update();
  out.replaceChildren(el("div", { class: "card card-pad" }, loader("جارٍ مطابقة النص مع المصادر...")));
  const r = await verify(text);
  busy = false;
  update();
  render(r);
  out.querySelector("h2")?.setAttribute("tabindex", "-1");
  out.querySelector("h2")?.focus();
});
update();
