// Mock adapter for UI testing without a backend (config USE_MOCK: true).
// It returns backend-shaped JSON with clearly marked PLACEHOLDER text only: no verses, hadith,
// references, scholars or rulings are invented here.
//
// Trigger words to test every UI state (type them in the question / verify box):
//   chat:   "لا-دليل" -> insufficient_evidence   "توضيح" -> clarify      "خطأ" -> error
//           "بطيء" -> slow response (7s)          "بدون-شرح" -> sources without generated text
//           "رابط-معطل" -> broken source URL      "طويل" -> very long answer   "بلا-مصادر" -> empty sources
//   verify: "جزئي" -> partial_match   "غير-مطابق" -> not_matched   "قصير" -> insufficient (too short)
//           "لا-مصدر" -> insufficient_evidence   "خطأ" -> error   anything else -> matched

const PH = "[نص تجريبي — ليس نصًا شرعيًا]";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

function placeholderSource(i, extra = {}) {
  const types = ["hadith", "ayah", "tafsir"];
  return {
    id: `mock-${i}`,
    type: types[i % 3],
    name: `مصدر تجريبي ${i + 1}`,
    reference: `مرجع تجريبي رقم ${i + 1}`,
    text: `${PH} هذا نص بديل لاختبار عرض بطاقة المصدر وطول النص داخل الواجهة فقط.`,
    url: "https://example.com/",
    grade: i % 3 === 0 ? "[حكم تجريبي]" : null,
    ...extra,
  };
}

export async function chat(question) {
  const q = String(question);
  await wait(q.includes("بطيء") ? 7000 : 900);
  if (q.includes("خطأ")) throw new Error("mock failure");
  if (q.includes("لا-دليل")) {
    return { status: "insufficient_evidence", kind: "insufficient", answer: null, message: null, sources: [] };
  }
  if (q.includes("توضيح")) {
    return { status: "insufficient_evidence", kind: "clarify", answer: null,
             message: "[رسالة تجريبية] السؤال قصير ولا يكفي لتحديد المقصود.", sources: [] };
  }
  const long = q.includes("طويل");
  const answer = q.includes("بدون-شرح") ? null
    : `${PH}\n\nهذه إجابة تجريبية لاختبار تنسيق الفقرات في الواجهة، وتتضمن «اقتباسًا تجريبيًا» لاختبار التمييز البصري.`
      + (long ? `\n\n${"فقرة تجريبية طويلة لاختبار قابلية القراءة مع النصوص العربية الطويلة. ".repeat(40)}` : "");
  const sources = q.includes("بلا-مصادر") ? []
    : [0, 1, 2].map((i) => placeholderSource(i, q.includes("رابط-معطل") ? { url: "javascript:alert(1)" } : {}));
  return {
    status: "answered", kind: "answer", answer,
    message: answer ? null : "[رسالة تجريبية] وُجدت نصوص مرتبطة بالسؤال وتُعرض دون شرح مولَّد.",
    notice: null, disclosure: "[وضع تجريبي] هذه بيانات بديلة لاختبار الواجهة فقط.", sources,
  };
}

export async function verify(text) {
  const t = String(text);
  await wait(700);
  if (t.includes("خطأ")) throw new Error("mock failure");
  if (t.includes("قصير")) return { status: "insufficient_evidence", reason: "too_short", message: null, sources: [] };
  if (t.includes("لا-مصدر")) return { status: "insufficient_evidence", reason: "no_source", message: null, sources: [] };
  if (t.includes("غير-مطابق")) {
    return { status: "not_matched", message: "[رسالة تجريبية] الصيغة المُدخلة لا تطابق أي نص مخزن.", coverage: 0.4, sources: [] };
  }
  const partial = t.includes("جزئي");
  return {
    status: partial ? "partial_match" : "matched",
    message: "[رسالة تجريبية لاختبار الواجهة]",
    coverage: partial ? 0.75 : 1, matched_words: partial ? 6 : 8, total_words: 8,
    method: "[طريقة تجريبية]",
    sources: [placeholderSource(0, { numbering_note: "[ملاحظة تجريبية حول الترقيم]" })],
  };
}

export async function sources() {
  await wait(500);
  return {
    categories: [
      { key: "a", type: "quran", name: "[فئة تجريبية أ]", description: "وصف بديل لاختبار الواجهة.", count: null, unit: "" },
      { key: "b", type: "hadith", name: "[فئة تجريبية ب]", description: "وصف بديل لاختبار الواجهة.", count: null, unit: "" },
      { key: "c", type: "tafsir", name: "[فئة تجريبية ج]", description: "وصف بديل لاختبار الواجهة.", count: null, unit: "" },
    ],
    grading: null,
  };
}

export async function modelInfo() {
  await wait(400);
  return { mode: "mock", model_name: null, provider: null, model_version: null, retrieval: {}, abstention: {}, evaluation: null };
}
