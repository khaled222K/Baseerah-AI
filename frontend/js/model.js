// Model information: every value comes from GET /model-info. Metrics are shown only if the backend publishes them.
import { getModelInfo } from "./api.js";
import { icon } from "./icons.js";
import { initShell, el, stateBlock, MSG } from "./ui.js";

initShell("about");
const root = document.getElementById("model-root");
const NA = "غير متوفر";
const VARIANT = { fts: "بحث بالكلمات فقط (BM25)", vector: "بحث بالمعنى فقط", hybrid: "بحث هجين (RRF)",
  "hybrid+rerank": "هجين + إعادة ترتيب", "hybrid+rerank+rewrites (default)": "هجين + إعادة ترتيب + إعادة صياغة (المعتمد)" };
const pct = (x) => (typeof x === "number" ? `${(x * 100).toFixed(1)}%` : "—");

function card(title, iconName, ...body) {
  return el("article", { class: "card info-card" }, el("h3", {}, icon(iconName), title), ...body);
}
function kv(pairs) {
  const dl = el("dl", { class: "kv" });
  pairs.forEach(([k, v]) => dl.append(el("dt", { text: k }), el("dd", { class: v ? null : "placeholder", dir: v ? "auto" : null, text: v || NA })));
  return dl;
}

function evaluation(ev) {
  if (!ev) return el("p", { class: "placeholder", text: "لم تُنشر نتيجة قياس نهائية بعد." });
  const wrap = el("div");
  if (Array.isArray(ev.retrieval) && ev.retrieval.length) {
    const rows = ev.retrieval.map((m) => el("tr", { class: /default/.test(m.variant) ? "is-default" : null },
      el("td", { text: VARIANT[m.variant] || m.variant }), el("td", { class: "num", text: pct(m["R@1"]) }),
      el("td", { class: "num", text: pct(m["R@3"]) }), el("td", { class: "num", text: pct(m["R@10"]) }),
      el("td", { class: "num", text: typeof m.MRR === "number" ? m.MRR.toFixed(3) : "—" })));
    wrap.append(el("p", { text: `دقة الاسترجاع على ${ev.retrieval[0].n} سؤالًا موثّق الإجابة:` }),
      el("div", { class: "table-wrap" }, el("table", { class: "metric-table" },
        el("caption", { class: "sr-only", text: "نتائج قياس الاسترجاع" }),
        el("thead", {}, el("tr", {}, ["الطريقة", "R@1", "R@3", "R@10", "MRR"].map((h) => el("th", { scope: "col", text: h })))),
        el("tbody", {}, rows))));
  }
  const e2e = ev.end_to_end?.default;
  if (e2e) {
    wrap.append(el("p", { style: "margin-top:12px", text:
      `من البداية إلى النهاية: عُرض النص المتوقع في ${e2e.expected_text_shown} من ${e2e.positives} سؤالًا، ` +
      `ورُفض ${e2e.out_of_scope_rejected} من ${e2e.out_of_scope} أسئلة خارج النطاق.` }));
  }
  if (ev.gulf_holdout) {
    wrap.append(el("p", { text: `أسئلة باللهجة الخليجية لم تُستخدم في الضبط (${ev.gulf_holdout.n}): R@10 = ${pct(ev.gulf_holdout["R@10"])}، MRR = ${ev.gulf_holdout.MRR}.` }));
  }
  if (ev.definitions) wrap.append(el("p", { class: "source-ref", text: `R@k: ${ev.definitions["R@k"]}. MRR: ${ev.definitions.MRR}.` }));
  if (Array.isArray(ev.caveats) && ev.caveats.length) {
    wrap.append(el("h4", { text: "حدود هذا القياس" }), el("ul", {}, ev.caveats.map((c) => el("li", { text: c }))));
  }
  return wrap;
}

async function load() {
  root.replaceChildren(el("div", { class: "skeleton", style: "height:280px" }));
  const m = await getModelInfo();
  if (m.status !== "ok") {
    root.replaceChildren(stateBlock({ iconName: "alert", error: true, text: m.errorKind === "unavailable" ? MSG.unavailable : MSG.server,
      action: el("button", { class: "btn", type: "button", onclick: load }, icon("refresh", "icon-sm"), "إعادة المحاولة") }));
    return;
  }
  const retrievalOnly = m.mode === "retrieval";
  root.replaceChildren(
    el("div", { class: "model-grid section" },
      card("النموذج المستخدم", "cpu",
        retrievalOnly ? el("p", { text: "يعمل الخادم حاليًا في وضع الاسترجاع فقط: لا يُستخدم نموذج لغوي لصياغة الشرح، وتُعرض النصوص من المصادر مباشرة." }) : null,
        kv([["اسم النموذج", m.modelName], ["المزوّد", m.provider], ["الإصدار", m.modelVersion]])),
      card("وظيفة الذكاء الاصطناعي", "sparkle",
        el("p", { text: "يُستخدم الذكاء الاصطناعي لفهم السؤال والبحث بالمعنى وترتيب النصوص الأقرب، ولصياغة شرح موجز عند تفعيل النموذج اللغوي. أما النصوص الشرعية نفسها فتأتي من قاعدة المصادر." })),
      card("ما الذي يفعله؟", "checkCircle", el("ul", {},
        el("li", { text: "يبحث في المصادر المحددة بالكلمات وبالمعنى." }),
        el("li", { text: "يرتّب النصوص حسب صلتها بالسؤال." }),
        el("li", { text: "يختار من النصوص المسترجعة ما يدعم الإجابة ويكتب شرحًا موجزًا (عند تفعيله)." }))),
      card("ما الذي لا يفعله؟", "x", el("ul", {},
        el("li", { text: "لا يؤلف آيات أو أحاديث، ولا يختار مصادر من خارج القاعدة." }),
        el("li", { text: "لا يُصدر فتاوى شخصية ولا يغيّر أحكام الأحاديث المخزنة." }),
        el("li", { text: "لا يبحث في الإنترنت." }))),
      card("حدود النموذج", "alert", el("ul", {},
        el("li", { text: "قد يخطئ في الصياغة أو في فهم الأسئلة المكتوبة باللهجة العامية." }),
        el("li", { text: "قد يعرض نصًا يشترك مع السؤال في كلمة دون أن يجيب عنه مباشرة؛ لذلك يُعرض المصدر دائمًا." }),
        el("li", { text: "لا يغطي إلا المصادر الموجودة في القاعدة." }))),
      card("آلية الاسترجاع", "search", kv([
        ["نموذج التمثيل الدلالي", m.retrieval.embeddingModel], ["البحث بالكلمات", m.retrieval.lexical],
        ["دمج النتائج", m.retrieval.fusion], ["إعادة الترتيب", m.retrieval.reranker]])),
      card("آلية الامتناع", "shield",
        el("p", { text: "لا يُعرض نص إلا إذا تجاوز حدود التشابه وإعادة الترتيب، وإلا تعتذر بصيرة عن الإجابة بدل تقديم حكم غير موثق." }),
        kv([["أدنى تشابه (مع تطابق لفظي)", m.abstention.minSimilarity?.toString()], ["تشابه مرتفع", m.abstention.highSimilarity?.toString()],
            ["أدنى درجة لإعادة الترتيب", m.abstention.minRerankScore?.toString()]]))),
    el("section", { class: "card card-pad section", "aria-labelledby": "acc-title" },
      el("h2", { class: "section-title", id: "acc-title" }, icon("scale"), "الدقة والاختبارات"),
      evaluation(m.evaluation)));
}
load();
