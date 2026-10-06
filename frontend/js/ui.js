// Shared shell (sidebar, top bar, footer), components and safe rendering helpers.
// Dynamic content is always inserted with textContent / DOM nodes, never as HTML.
import { icon } from "./icons.js";
import { config, explain } from "./api.js";
import { listConversations, listSaved, deleteConversation } from "./storage.js";

export const SLOGAN = "إجابةٌ تستند إلى أصل.";
export const SUBTITLE = "محتوى شرعي قابل للتتبع إلى مصدره.";
export const FOOTER_NOTE = "تعتمد بصيرة على المصادر المحددة ضمن الحزمة العلمية لتحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي، ولا يختار نموذج الذكاء الاصطناعي مصادره بشكل مستقل.";
export const AI_NOTICE = "قد يخطئ الذكاء الاصطناعي في الصياغة؛ لذلك تعرض بصيرة المصدر لتتمكني من التحقق بنفسك.";
export const MSG = {
  noEvidence: "لم أجد في المصادر المتاحة لدي أدلة كافية وموثوقة للإجابة عن هذه المسألة، لذلك لن أقدم حكمًا غير موثق.",
  unavailable: "تعذر الاتصال بالخدمة حاليًا. حاولي مرة أخرى بعد قليل.",
  server: "حدث خلل تقني أثناء معالجة الطلب. لم تُعرض أي إجابة غير موثقة. حاولي مرة أخرى بعد قليل.",
  invalid: "تعذر قبول الطلب. تأكدي من أن النص غير فارغ وضمن الطول المسموح.",
  searching: "جارٍ البحث في المصادر...",
  preparing: "جارٍ إعداد الإجابة...",
};

const NAV = [
  { key: "home", href: "index.html", label: "الرئيسية", icon: "home" },
  { key: "ask", href: "index.html#ask", label: "اسألي بصيرة", icon: "chat" },
  { key: "verify", href: "verify.html", label: "تحققي من دليل", icon: "search" },
  { key: "sources", href: "sources.html", label: "المصادر", icon: "book" },
  { key: "about", href: "about.html", label: "عن بصيرة", icon: "info" },
];
const HISTORY_SHOWN = 6;

// ---------- DOM helper ----------
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function logo({ large = false, href = "index.html", tag = "a" } = {}) {
  const attrs = { class: `logo${large ? " logo-lg" : ""}` };
  if (tag === "a") { attrs.href = href; attrs["aria-label"] = "بصيرة — الرئيسية"; }
  return el(tag, attrs,
    el("img", { src: "assets/logo/mark.svg", alt: "", width: large ? 84 : 40, height: large ? 84 : 40 }),
    el("span", { class: "logo-text" }, el("span", { class: "logo-ar", text: "بصيرة" }), el("span", { class: "logo-en", text: "Baseerah AI" })));
}

// ---------- Shell ----------
let activeKey = "home";
let currentConversation = null;

export function initShell(key) {
  activeKey = key;
  document.documentElement.lang = "ar";
  document.documentElement.dir = "rtl";
  const app = document.querySelector(".app");
  if (config.useMock) {
    document.body.prepend(el("div", { class: "mock-banner", role: "status",
      text: "وضع تجريبي: البيانات المعروضة بديلة لاختبار الواجهة وليست محتوى شرعيًا." }));
  }
  app.prepend(buildSidebar(), el("div", { class: "sidebar-backdrop", hidden: true }));
  const main = app.querySelector(".main-col");
  main.prepend(buildTopbar());
  main.append(buildFooter());
  document.body.append(el("div", { class: "toast-region", "aria-live": "polite", role: "status" }));
  wireDrawer();
  renderHistory();
  window.addEventListener("baseerah:storage", () => { renderHistory(); renderSavedBadge(); });
  renderSavedBadge();
}

function navLinks(cls) {
  return el("nav", { class: cls, "aria-label": cls === "nav" ? "التنقل الرئيسي" : "روابط الصفحات" },
    NAV.map((n) => el("a", { href: n.href, "data-key": n.key, "aria-current": n.key === activeKey ? "page" : null },
      cls === "nav" ? icon(n.icon) : null, el("span", { text: n.label }))));
}

export function setActiveNav(key) {
  activeKey = key;
  document.querySelectorAll(".nav a, .topnav a").forEach((a) => {
    if (a.dataset.key === key) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

function buildSidebar() {
  return el("aside", { class: "sidebar", id: "sidebar", "aria-label": "الشريط الجانبي" },
    el("div", { class: "sidebar-head" }, logo(),
      el("button", { class: "icon-btn sidebar-close", type: "button", "aria-label": "إغلاق القائمة" }, icon("x"))),
    el("a", { class: "btn btn-primary btn-block", href: "index.html?new=1", "data-new-chat": "" }, icon("plus"), "محادثة جديدة"),
    navLinks("nav"),
    el("section", { "aria-labelledby": "history-title" },
      el("h2", { class: "sidebar-section-title", id: "history-title", text: "المحادثات السابقة" }),
      el("ul", { class: "history", id: "history-list" }),
      el("button", { class: "history-more", type: "button", id: "history-more", hidden: true, "aria-expanded": "false", text: "عرض المزيد..." })),
    el("div", { class: "sidebar-foot nav" },
      el("a", { href: "saved.html", "data-key": "saved", "aria-current": activeKey === "saved" ? "page" : null },
        icon("bookmark"), el("span", { text: "المحفوظات" }), el("span", { class: "badge", id: "saved-badge", hidden: true }))));
}

function buildTopbar() {
  return el("header", { class: "topbar" },
    el("button", { class: "icon-btn menu-toggle", type: "button", "aria-label": "فتح القائمة", "aria-controls": "sidebar", "aria-expanded": "false" }, icon("menu")),
    el("span", { class: "topbar-logo" }, logo()),
    navLinks("topnav"));
}

function buildFooter() {
  const links = [
    ["index.html", "الرئيسية"], ["sources.html", "المصادر"], ["about.html", "عن بصيرة"],
    ["privacy.html", "الخصوصية"], ["about.html#contact", "تواصل معنا"],
  ];
  return el("footer", { class: "site-footer" },
    el("div", { class: "footer-inner" },
      el("div", { class: "footer-brand" }, logo(), el("p", { class: "footer-slogan", text: SLOGAN })),
      el("p", { class: "footer-note", text: FOOTER_NOTE }),
      el("ul", { class: "footer-links" }, links.map(([h, t]) => el("li", {}, el("a", { href: h, text: t }))))));
}

export function setCurrentConversation(id) {
  currentConversation = id;
  renderHistory();
}

function renderHistory() {
  const list = document.getElementById("history-list");
  if (!list) return;
  const more = document.getElementById("history-more");
  const convs = listConversations();
  const expanded = more.getAttribute("aria-expanded") === "true";
  list.replaceChildren();
  if (!convs.length) {
    list.append(el("li", {}, el("p", { class: "history-empty", text: "لا توجد محادثات سابقة بعد. ابدئي بطرح سؤال." })));
  }
  convs.slice(0, expanded ? convs.length : HISTORY_SHOWN).forEach((c) => {
    const when = historyTime(c.updatedAt || c.createdAt);
    const remove = () => {
      deleteConversation(c.id);
      toast("حُذفت المحادثة");
      // Deleting the open conversation returns to a new one.
      if (c.id === currentConversation) location.href = "index.html?new=1";
    };
    list.append(el("li", { class: "history-item" },
      el("a", { href: `index.html?c=${encodeURIComponent(c.id)}`, title: c.title,
        "aria-current": c.id === currentConversation ? "true" : null },
        icon("chat"), el("span", { class: "history-title", text: c.title }),
        when ? el("time", { class: "history-time", datetime: new Date(c.updatedAt || c.createdAt).toISOString(), text: when }) : null),
      el("button", { class: "history-delete", type: "button", "aria-label": `حذف المحادثة: ${c.title}`, title: "حذف المحادثة",
        onclick: remove }, icon("trash", "icon-sm"))));
  });
  more.hidden = convs.length <= HISTORY_SHOWN;
  more.textContent = expanded ? "عرض أقل" : "عرض المزيد...";
  more.onclick = () => { more.setAttribute("aria-expanded", String(!expanded)); renderHistory(); };
}

function renderSavedBadge() {
  const b = document.getElementById("saved-badge");
  if (!b) return;
  const n = listSaved().length;
  b.hidden = !n;
  b.textContent = String(n);
}

function wireDrawer() {
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.querySelector(".sidebar-backdrop");
  const toggle = document.querySelector(".menu-toggle");
  const close = () => {
    sidebar.classList.remove("is-open");
    backdrop.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  };
  const open = () => {
    sidebar.classList.add("is-open");
    backdrop.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    sidebar.querySelector("a, button")?.focus();
  };
  toggle.addEventListener("click", () => (sidebar.classList.contains("is-open") ? close() : open()));
  backdrop.addEventListener("click", close);
  sidebar.querySelector(".sidebar-close").addEventListener("click", () => { close(); toggle.focus(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sidebar.classList.contains("is-open")) { close(); toggle.focus(); }
  });
  sidebar.addEventListener("click", (e) => { if (e.target.closest("a")) close(); });
}

// ---------- Feedback ----------
export function toast(text) {
  const region = document.querySelector(".toast-region");
  if (!region) return;
  const t = el("div", { class: "toast", text });
  region.append(t);
  setTimeout(() => t.remove(), 2400);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = el("textarea", { class: "sr-only", "aria-hidden": "true" });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove();
    return ok;
  }
}

export function dialog(title, body) {
  const close = el("button", { class: "icon-btn", type: "button", "aria-label": "إغلاق" }, icon("x"));
  const d = el("dialog", { class: "dialog", "aria-label": title },
    el("div", { class: "dialog-head" }, el("h2", { text: title }), close),
    el("div", { class: "dialog-body" }, body));
  close.addEventListener("click", () => d.close());
  d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
  return d;
}

export function loader(text) {
  const label = el("span", { class: "loader-text", text });
  const node = el("div", { class: "loader", role: "status" },
    el("img", { class: "loader-mark", src: "assets/logo/mark.svg", alt: "" }), label,
    el("span", { class: "loader-dots", "aria-hidden": "true" }, el("i"), el("i"), el("i")));
  node.setText = (t) => { label.textContent = t; };
  return node;
}

export function stateBlock({ iconName = "info", title, text, error = false, action = null }) {
  return el("div", { class: `state${error ? " state-error" : ""}`, role: error ? "alert" : null },
    icon(iconName), title ? el("h3", { text: title }) : null, text ? el("p", { text }) : null, action);
}

export const formatDate = (ts) => {
  try {
    return new Intl.DateTimeFormat("ar", { dateStyle: "medium", timeStyle: "short" }).format(new Date(ts));
  } catch {
    return new Date(ts).toLocaleString();
  }
};
// Short label that tells apart conversations with the same title: time today, otherwise the date.
function historyTime(ts) {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    const today = new Date().toDateString() === d.toDateString();
    return new Intl.DateTimeFormat("ar", today ? { timeStyle: "short" } : { day: "numeric", month: "short" }).format(d);
  } catch { return ""; }
}

export const formatTime = (ts) => {
  try { return new Intl.DateTimeFormat("ar", { timeStyle: "short" }).format(new Date(ts)); } catch { return ""; }
};
export const formatNumber = (n) => {
  try { return new Intl.NumberFormat("ar").format(n); } catch { return String(n); }
};

// ---------- Rich text (paragraphs + highlighted quotations), built as text nodes ----------
const QUOTE_RE = /«[^»]+»|﴿[^﴾]+﴾|“[^”]+”|"[^"]+"/g;
export function richText(text) {
  const frag = document.createDocumentFragment();
  for (const para of String(text).split(/\n{2,}/)) {
    if (!para.trim()) continue;
    const p = el("p");
    para.split("\n").forEach((line, i) => {
      if (i) p.append(el("br"));
      let last = 0;
      for (const m of line.matchAll(QUOTE_RE)) {
        if (m.index > last) p.append(line.slice(last, m.index));
        p.append(el("span", { class: "quote", text: m[0] }));
        last = m.index + m[0].length;
      }
      if (last < line.length) p.append(line.slice(last));
    });
    frag.append(p);
  }
  return frag;
}

// ---------- Sources ----------
const TYPE_LABEL = { hadith: "حديث", ayah: "آية", tafsir: "تفسير", other: "مصدر" };
const TYPE_ICON = { hadith: "book", ayah: "book", tafsir: "file", other: "layers" };

export function externalLink(url, label = "فتح المصدر الأصلي", cls = "btn") {
  if (!url) {
    return el("span", { class: cls, role: "link", "aria-disabled": "true", title: "رابط المصدر الأصلي غير متاح" },
      icon("external", "icon-sm"), label);
  }
  return el("a", { class: cls, href: url, target: "_blank", rel: "noopener noreferrer" }, icon("external", "icon-sm"), label,
    el("span", { class: "sr-only", text: " (يفتح في نافذة جديدة)" }));
}

export function excerpt(text, n = 170) {
  const t = String(text || "").replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n).trim()}…` : t;
}

export function sourceCard(s) {
  return el("article", { class: "source-card" },
    el("div", { class: "source-top" },
      el("div", { class: "source-cover", "data-type": s.type, "aria-hidden": "true" }, icon(TYPE_ICON[s.type])),
      el("div", { class: "source-meta" },
        el("h4", { class: "source-name", text: s.name }),
        el("p", { class: "source-ref", text: s.reference }),
        el("div", {}, el("span", { class: "chip chip-muted", text: TYPE_LABEL[s.type] }), " ",
          s.grade ? el("span", { class: "chip chip-success", text: `الحكم: ${s.grade}` }) : null))),
    s.text ? el("p", { class: "source-excerpt" }, el("span", { class: "sr-only", text: "مقتطف: " }), excerpt(s.text)) : null,
    el("div", { class: "source-actions" },
      el("button", { class: "btn", type: "button", onclick: () => openSources([s], s.name) }, icon("file", "icon-sm"), "عرض المصدر"),
      externalLink(s.url)),
    explainButton(s));
}

// ---------- Hadith explanation (generated, grounded in the stored text) ----------
export function explainButton(s, cls = "btn btn-ghost btn-explain") {
  if (s.type !== "hadith" || !/^hadith-\d+$/.test(s.id)) return null;
  return el("button", { class: cls, type: "button", onclick: () => openExplain(s) }, icon("sparkle", "icon-sm"), "اشرح الحديث");
}

export async function openExplain(s) {
  const result = el("div", { class: "explain-result", "aria-live": "polite" });
  const body = el("div", { class: "explain" },
    el("p", { class: "source-ref", text: s.reference }),
    el("blockquote", { class: "source-full", text: s.text }),
    result);
  dialog(`شرح الحديث — ${s.name}`, body);
  const load = async () => {
    const wait = loader("جارٍ إعداد الشرح...");
    result.replaceChildren(wait);
    const r = await explain(s.id);
    result.replaceChildren();
    if (r.storedNote) {
      result.append(el("section", { class: "explain-note" },
        el("h3", {}, icon("book"), `توضيح مخزن (${r.storedNote.source})`),
        el("div", { class: "source-full", text: r.storedNote.text })));
    }
    if (r.status === "explained") {
      result.append(el("section", { class: "answer-card explain-generated" },
        el("div", { class: "answer-label" }, icon("sparkle"), r.label || "شرح مولَّد بالذكاء الاصطناعي (ليس نصاً شرعياً)"),
        el("div", { class: "answer-text" }, richText(r.explanation)),
        r.words.length ? el("div", {}, el("h4", { text: "معاني الكلمات" }),
          el("dl", { class: "kv" }, r.words.map((w) => [el("dt", { text: w.word }), el("dd", { text: w.meaning })]))) : null,
        r.groundedOn.length ? el("p", { class: "source-ref", text: `يستند هذا الشرح إلى: ${r.groundedOn.join("، ")} فقط.` }) : null));
      result.append(el("div", { class: "notice" }, icon("info"), el("span", { text: AI_NOTICE })));
      if (r.disclosure) result.append(el("p", { class: "disclosure", text: r.disclosure }));
      return;
    }
    let text = r.message;
    if (r.status === "error") {
      text = r.errorKind === "unavailable" ? MSG.unavailable : r.errorKind === "invalid" ? MSG.invalid : (r.message || MSG.server);
    }
    result.append(el("div", { class: `answer-status${r.status === "error" ? " is-error" : " is-insufficient"}`, role: r.status === "error" ? "alert" : null },
      icon(r.status === "error" ? "alert" : "info"), el("p", { class: "answer-message", text: text || MSG.server })));
    if (r.status === "error") {
      result.append(el("button", { class: "btn", type: "button", style: "margin-top:10px", onclick: load }, icon("refresh", "icon-sm"), "إعادة المحاولة"));
    }
  };
  load();
}

export function sourceDetail(s) {
  const kv = el("dl", { class: "kv" });
  const add = (k, v) => { if (v) kv.append(el("dt", { text: k }), el("dd", { dir: "auto", text: v })); };
  add("النوع", TYPE_LABEL[s.type]);
  add("المرجع", s.reference);
  add("الحكم", s.grade);
  add("أساس الحكم", s.gradeBasis);
  if (s.dorar) add("الدرر السنية", `${s.dorar.grade}${s.dorar.muhaddith ? ` (${s.dorar.muhaddith})` : ""}`);
  add("ملاحظة الترقيم", s.numberingNote);
  return el("section", { class: "source-detail" },
    el("h3", { text: s.name }),
    s.ayah ? el("div", {}, el("p", { class: "source-ref", text: `الآية (${s.ayah.reference})` }),
      el("div", { class: "source-full is-quran", text: s.ayah.text })) : null,
    s.ayah ? el("p", { class: "source-ref", text: "التفسير:" }) : null,
    el("div", { class: `source-full${s.type === "ayah" ? " is-quran" : ""}`, text: s.text || "—" }),
    s.note ? el("div", {}, el("p", { class: "source-ref", text: `توضيح (${s.note.source})` }), el("div", { class: "source-full", text: s.note.text })) : null,
    kv,
    el("div", { class: "source-actions", style: "margin-top:12px" }, externalLink(s.url),
      el("button", { class: "btn", type: "button", onclick: async () => toast((await copyText(sourceToText(s))) ? "تم نسخ النص" : "تعذر النسخ") },
        icon("copy", "icon-sm"), "نسخ النص")));
}

export function openSources(sources, title = "المصادر المستخدمة") {
  const body = sources.length ? el("div", {}, sources.map(sourceDetail)) : stateBlock({ text: "لا توجد مصادر لعرضها." });
  return dialog(title, body);
}

export function sourceToText(s) {
  return [`${s.name} — ${s.reference}`, s.ayah ? `الآية (${s.ayah.reference}): ${s.ayah.text}` : null, s.text,
    s.grade ? `الحكم: ${s.grade}` : null, s.url ? `الرابط: ${s.url}` : null].filter(Boolean).join("\n");
}
