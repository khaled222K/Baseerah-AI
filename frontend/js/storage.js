// localStorage persistence (MVP, no accounts). Every access is guarded: storage can be full, blocked or cleared.
const KEYS = { conversations: "baseerah.conversations.v1", saved: "baseerah.saved.v1" };
const MAX_CONVERSATIONS = 40;
const MAX_SAVED = 200;

function read(key) {
  try {
    const v = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function write(key, list) {
  // On quota errors drop the oldest entries until it fits.
  let items = list.slice();
  while (true) {
    try {
      localStorage.setItem(key, JSON.stringify(items));
      return true;
    } catch {
      if (items.length <= 1) return false;
      items = items.slice(0, -1);
    }
  }
}

export const uid = () =>
  (crypto.randomUUID ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`);

// ---------- Conversations: [{id, title, createdAt, updatedAt, turns:[{id, question, response, at}]}], newest first
export function listConversations() {
  return read(KEYS.conversations).sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
}

export function getConversation(id) {
  return listConversations().find((c) => c.id === id) || null;
}

export function saveTurn(conversationId, turn) {
  const all = listConversations();
  let conv = all.find((c) => c.id === conversationId);
  if (!conv) {
    conv = { id: conversationId, title: turn.question.slice(0, 80), createdAt: Date.now(), turns: [] };
    all.unshift(conv);
  }
  const i = conv.turns.findIndex((t) => t.id === turn.id);
  if (i >= 0) conv.turns[i] = turn;
  else conv.turns.push(turn);
  conv.updatedAt = Date.now();
  write(KEYS.conversations, all.slice(0, MAX_CONVERSATIONS));
  window.dispatchEvent(new CustomEvent("baseerah:storage"));
}

export function deleteConversation(id) {
  write(KEYS.conversations, listConversations().filter((c) => c.id !== id));
  window.dispatchEvent(new CustomEvent("baseerah:storage"));
}

// ---------- Saved answers: [{id, question, response, savedAt}], newest first
export function listSaved() {
  return read(KEYS.saved).sort((a, b) => b.savedAt - a.savedAt);
}

export function isSaved(id) {
  return listSaved().some((s) => s.id === id);
}

export function saveAnswer(entry) {
  const all = listSaved().filter((s) => s.id !== entry.id);
  all.unshift({ ...entry, savedAt: Date.now() });
  const ok = write(KEYS.saved, all.slice(0, MAX_SAVED));
  window.dispatchEvent(new CustomEvent("baseerah:storage"));
  return ok;
}

export function unsaveAnswer(id) {
  write(KEYS.saved, listSaved().filter((s) => s.id !== id));
  window.dispatchEvent(new CustomEvent("baseerah:storage"));
}

export function clearAll() {
  try {
    localStorage.removeItem(KEYS.conversations);
    localStorage.removeItem(KEYS.saved);
  } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent("baseerah:storage"));
}

// Other tabs
window.addEventListener("storage", (e) => {
  if (Object.values(KEYS).includes(e.key)) window.dispatchEvent(new CustomEvent("baseerah:storage"));
});
