// Ask Baseerah: hero -> conversation, answers, sources, actions, local history.
import { chat } from "./api.js";
import { icon } from "./icons.js";
import { getConversation, saveTurn, isSaved, saveAnswer, unsaveAnswer, uid } from "./storage.js";
import {
  initShell, el, toast, copyText, loader, richText, sourceCard, openSources, externalLink,
  setActiveNav, setCurrentConversation, sourceToText, formatTime, AI_NOTICE, MSG,
} from "./ui.js";

// Neutral example questions (editable). Only questions — no answers or claims are hardcoded.
const SUGGESTIONS = ["ما حق الجار في الإسلام؟", "ما فضل الصدق في السنة النبوية؟", "ما آداب الأكل في السنة النبوية؟"];
const MAX_LEN = 1000;
const STAGE_MS = 2500;

initShell("home");
const main = document.getElementById("main");
const hero = document.getElementById("hero");
const chatView = document.getElementById("chat");
const thread = document.getElementById("thread");
const form = document.getElementById("composer");
const input = document.getElementById("question");
const sendBtn = document.getElementById("send");
const count = document.getElementById("char-count");
const heroSlot = document.getElementById("hero-composer-slot");
const chatSlot = document.getElementById("chat-composer-slot");

let conversationId = null;
let busy = false;

// ---------- Suggestions ----------
const sugList = document.getElementById("suggestion-list");
SUGGESTIONS.forEach((q) => sugList.append(el("li", {},
  el("button", { class: "suggestion", type: "button", onclick: () => ask(q) }, el("span", { text: q }), icon("arrowUpLeft")))));

// ---------- Composer ----------
function autosize() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 220)}px`;
  const n = input.value.length;
  count.textContent = `${n}/${MAX_LEN}`;
  count.classList.toggle("is-over", n > MAX_LEN);
  count.hidden = n < MAX_LEN * 0.8;
  sendBtn.disabled = busy || !input.value.trim() || n > MAX_LEN;
}
input.addEventListener("input", autosize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    form.requestSubmit();
  }
});
form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q || busy || q.length > MAX_LEN) return;
  input.value = "";
  autosize();
  ask(q);
});

function enterChat() {
  if (!chatView.hidden) return;
  hero.hidden = true;
  chatView.hidden = false;
  chatSlot.append(form);
  main.classList.add("is-chatting");
  setActiveNav("ask");
}

function resetToHero() {
  thread.replaceChildren();
  chatView.hidden = true;
  hero.hidden = false;
  heroSlot.append(form);
  main.classList.remove("is-chatting");
  conversationId = null;
  setCurrentConversation(null);
  setActiveNav("home");
}

// ---------- Messages ----------
function userMessage(text, at) {
  return el("div", { class: "msg msg-user" },
    el("div", { class: "avatar avatar-user", "aria-hidden": "true" }, icon("chat")),
    el("div", {}, el("div", { class: "bubble" }, el("span", { class: "sr-only", text: "سؤالك: " }), text),
      el("div", { class: "msg-time", text: formatTime(at) })));
}

function botShell() {
  const body = el("div", { class: "answer", "aria-live": "polite" });
  const node = el("div", { class: "msg msg-bot" },
    el("div", { class: "avatar", "aria-hidden": "true" }, el("img", { src: "assets/logo/mark.svg", alt: "" })), body);
  return { node, body };
}

function answerText(r) {
  const parts = [];
  if (r.answer) parts.push(r.answer);
  else if (r.message) parts.push(r.message);
  if (r.sources.length) {
    parts.push("", "المصادر:");
    r.sources.forEach((s, i) => parts.push(`${i + 1}. ${sourceToText(s)}`));
  }
  return parts.join("\n");
}

function renderResponse(body, turn, retry) {
  const r = turn.response;
  body.replaceChildren();
  if (r.status === "error") {
    const text = r.errorKind === "unavailable" ? MSG.unavailable : r.errorKind === "invalid" ? MSG.invalid : MSG.server;
    body.append(el("div", { class: "answer-card" },
      el("div", { class: "answer-status is-error", role: "alert" }, icon("alert"), el("p", { class: "answer-message", text })),
      retry ? el("div", { class: "retry-row" }, el("button", { class: "btn", type: "button", onclick: retry }, icon("refresh", "icon-sm"), "إعادة المحاولة")) : null));
    return;
  }
  if (r.status === "insufficient_evidence") {
    const text = r.kind === "clarify" && r.message ? r.message : MSG.noEvidence;
    body.append(el("div", { class: "answer-card" },
      el("div", { class: "answer-status is-insufficient" }, icon(r.kind === "clarify" ? "help" : "info"), el("p", { class: "answer-message", text }))));
    return;
  }

  const card = el("div", { class: "answer-card" });
  if (r.answer) {
    if (r.generatedLabel) card.append(el("div", { class: "answer-label" }, icon("sparkle"), r.generatedLabel));
    card.append(el("div", { class: "answer-text" }, richText(r.answer)));
    if (r.message && r.kind !== "answer") card.append(el("p", { class: "answer-message", style: "margin-top:10px", text: r.message }));
  } else {
    // No generated explanation (retrieval-only mode, or the AI provider was unavailable): show the sources only.
    card.append(el("div", { class: "answer-status" }, icon(r.kind === "referral" ? "scale" : "book"),
      el("p", { class: "answer-message", text: r.message || "وُجدت نصوص مرتبطة بالسؤال، وتُعرض كما هي من المصادر دون شرح مولَّد." })));
  }
  if (r.notice) card.append(el("div", { class: "notice notice-soft", style: "margin-top:12px" }, icon("info"), el("span", { text: r.notice })));
  body.append(card);

  const firstUrl = r.sources.find((s) => s.url)?.url || null;
  const saveBtn = el("button", { class: "btn", type: "button" });
  const paintSave = () => {
    const on = isSaved(turn.id);
    saveBtn.replaceChildren(el("span", { "aria-hidden": "true", text: on ? "★" : "☆" }), on ? "تم الحفظ" : "حفظ الإجابة");
    saveBtn.classList.toggle("is-on", on);
    saveBtn.setAttribute("aria-pressed", String(on));
  };
  saveBtn.addEventListener("click", () => {
    if (isSaved(turn.id)) {
      unsaveAnswer(turn.id);
      toast("أُزيلت الإجابة من المحفوظات");
    } else if (saveAnswer({ id: turn.id, question: turn.question, response: r })) {
      toast("تم حفظ الإجابة");
    } else {
      toast("تعذر الحفظ: مساحة التخزين في المتصفح ممتلئة");
    }
    paintSave();
  });
  paintSave();
  const copyBtn = el("button", { class: "btn", type: "button", onclick: async () => {
    toast((await copyText(`${turn.question}\n\n${answerText(r)}`)) ? "تم نسخ الإجابة" : "تعذر نسخ الإجابة");
  } }, icon("copy", "icon-sm"), "نسخ الإجابة");
  const allBtn = el("button", { class: "btn", type: "button", disabled: !r.sources.length, onclick: () => openSources(r.sources, "المصادر المستخدمة في هذه الإجابة") },
    icon("list", "icon-sm"), "عرض كل المصادر المستخدمة");
  body.append(el("div", { class: "answer-actions" }, externalLink(firstUrl, "فتح المصدر الأصلي", "btn btn-primary"), allBtn, copyBtn, saveBtn));

  if (r.sources.length) {
    body.append(el("section", { class: "sources-block", "aria-label": "المصادر المستخدمة في هذه الإجابة" },
      el("h3", {}, icon("book"), `المصادر المستخدمة في هذه الإجابة (${r.sources.length})`),
      el("div", { class: "source-grid" }, r.sources.map(sourceCard))));
  } else {
    body.append(el("p", { class: "disclosure", text: "لم تُرفق مصادر بهذه الإجابة." }));
  }
  body.append(el("div", { class: "notice" }, icon("info"), el("span", { text: AI_NOTICE })));
  if (r.disclosure) body.append(el("p", { class: "disclosure", text: r.disclosure }));
}

// ---------- Ask ----------
async function ask(question, existingTurn = null) {
  if (busy) return;
  enterChat();
  if (!conversationId) {
    conversationId = uid();
    history.replaceState(null, "", `index.html?c=${encodeURIComponent(conversationId)}`);
  }
  const turn = existingTurn || { id: uid(), question, at: Date.now(), response: null };
  let body;
  if (existingTurn) {
    body = thread.querySelector(`[data-turn="${turn.id}"] .answer`);
  } else {
    thread.append(el("div", { "data-turn": turn.id }, userMessage(question, turn.at)));
    const bot = botShell();
    body = bot.body;
    thread.lastElementChild.append(bot.node);
  }
  busy = true;
  autosize();
  const wait = loader(MSG.searching);
  body.replaceChildren(wait);
  wait.scrollIntoView({ block: "nearest", behavior: "smooth" });
  const stage = setTimeout(() => wait.setText(MSG.preparing), STAGE_MS);
  turn.response = await chat(question);
  clearTimeout(stage);
  busy = false;
  autosize();
  const retry = () => ask(question, turn);
  renderResponse(body, turn, turn.response.status === "error" ? retry : null);
  body.closest(".msg")?.scrollIntoView({ block: "start", behavior: "smooth" });
  if (turn.response.status !== "error") {
    saveTurn(conversationId, { id: turn.id, question, at: turn.at, response: turn.response });
    setCurrentConversation(conversationId);
  }
  if (window.matchMedia("(min-width: 768px)").matches) input.focus();
}

// ---------- Load state from URL ----------
function boot() {
  const params = new URLSearchParams(location.search);
  if (params.get("new")) {
    history.replaceState(null, "", "index.html");
    resetToHero();
  }
  const cid = params.get("c");
  const conv = cid ? getConversation(cid) : null;
  if (conv) {
    enterChat();
    conversationId = conv.id;
    setCurrentConversation(conv.id);
    conv.turns.forEach((t) => {
      const wrap = el("div", { "data-turn": t.id }, userMessage(t.question, t.at));
      const bot = botShell();
      wrap.append(bot.node);
      thread.append(wrap);
      renderResponse(bot.body, t, null);
    });
    thread.lastElementChild?.scrollIntoView({ block: "start" });
  } else if (cid) {
    history.replaceState(null, "", "index.html");
  }
  if (location.hash === "#ask") setActiveNav("ask");
  autosize();
  // Focus the question box on wide screens only: on phones it would pop up the keyboard on every visit.
  if (window.matchMedia("(min-width: 768px)").matches || location.hash === "#ask") input.focus();
}
window.addEventListener("hashchange", () => { if (location.hash === "#ask") { setActiveNav("ask"); input.focus(); } });
boot();
