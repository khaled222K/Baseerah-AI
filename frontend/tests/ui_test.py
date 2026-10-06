"""End-to-end UI checks with Playwright (Chromium).

Needs three static servers (see README "Frontend"):
  REAL_URL  frontend pointed at a running API        (default http://localhost:5500)
  MOCK_URL  frontend copy with USE_MOCK: true         (default http://localhost:5501)
  DEAD_URL  frontend copy pointed at a closed port    (default http://localhost:5502)
Run: python frontend/tests/ui_test.py  [SHOTS=dir to save screenshots]"""
import os, re, sys
from playwright.sync_api import sync_playwright, expect

REAL = os.environ.get("REAL_URL", "http://localhost:5500")
MOCK = os.environ.get("MOCK_URL", "http://localhost:5501")
DEAD = os.environ.get("DEAD_URL", "http://localhost:5502")
SHOTS = os.environ.get("SHOTS")
CHROME = os.environ.get("CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
PAGES = ["index.html", "verify.html", "sources.html", "model.html", "saved.html", "about.html", "privacy.html"]
SIZES = {"desktop": (1366, 900), "tablet": (900, 1180), "mobile": (390, 844)}
FOOTER = "تعتمد بصيرة على المصادر المحددة ضمن الحزمة العلمية"
NO_EVIDENCE = "لم أجد في المصادر المتاحة لدي أدلة كافية وموثوقة"
AI_NOTICE = "قد يخطئ الذكاء الاصطناعي في الصياغة"
results = []


def check(name, fn):
    try:
        fn()
        results.append((True, name, ""))
    except Exception as e:  # noqa: BLE001
        results.append((False, name, str(e).splitlines()[0][:300]))


def shot(page, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=os.path.join(SHOTS, f"{name}.png"), full_page=True)


def new_page(browser, size="desktop"):
    w, h = SIZES[size]
    ctx = browser.new_context(viewport={"width": w, "height": h}, locale="ar",
                              permissions=["clipboard-read", "clipboard-write"])
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: m.type == "error" and "fonts.g" not in (m.location or {}).get("url", "")
            and page.errors.append(f"console: {m.text}"))
    page.on("dialog", lambda d: (page.errors.append(f"unexpected dialog: {d.message}"), d.dismiss()))
    return ctx, page


def ask(page, q):
    page.fill("#question", q)
    page.press("#question", "Enter")


def run(browser):
    # ---- every page, every size: loads, RTL, shell, footer, no errors, no horizontal scroll
    for size in SIZES:
        for p in PAGES:
            def t(size=size, p=p):
                ctx, page = new_page(browser, size)
                page.goto(f"{REAL}/{p}")
                page.wait_for_selector(".site-footer")
                assert page.get_attribute("html", "dir") == "rtl"
                expect(page.locator(".site-footer")).to_contain_text(FOOTER)
                for label in ["الخصوصية", "تواصل معنا", "المصادر", "عن بصيرة", "الرئيسية"]:
                    expect(page.locator(".footer-links")).to_contain_text(label)
                assert page.locator(".sidebar").count() == 1
                page.wait_for_timeout(600)
                overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                assert overflow <= 1, f"horizontal overflow {overflow}px"
                assert not page.errors, page.errors
                assert page.locator("text=تسجيل الدخول").count() == 0
                shot(page, f"{size}-{p.replace('.html', '')}")
                ctx.close()
            check(f"{size}: {p} loads (RTL, footer, no errors, no overflow)", t)

    # ---- real backend: chat, sources, actions, save, history
    ctx, page = new_page(browser)
    def chat_real():
        page.goto(f"{REAL}/index.html")
        expect(page.locator("#hero h1")).to_have_text("إجابةٌ تستند إلى أصل.")
        expect(page.locator(".subtitle")).to_have_text("محتوى شرعي قابل للتتبع إلى مصدره.")
        expect(page.locator("#chat")).to_be_hidden()
        expect(page.locator("#saved-badge")).to_be_hidden()
        assert page.locator(".suggestion").count() == 5
        expect(page.locator(".suggestion").first).to_have_text("هل يجوز إجبار المرأة على النقاب؟")
        ask(page, "ما حق الجار في الإسلام؟")
        expect(page.locator(".loader")).to_be_visible()
        page.wait_for_selector(".answer-actions", timeout=90000)
        expect(page.locator(".msg-user .bubble")).to_contain_text("ما حق الجار في الإسلام؟")
        expect(page.locator("#hero")).to_be_hidden()
        expect(page.locator("#chat-composer-slot #composer")).to_be_visible()
        acts = page.locator(".answer-actions").inner_text()
        for label in ["فتح المصدر الأصلي", "عرض كل المصادر المستخدمة", "نسخ الإجابة", "حفظ الإجابة"]:
            assert label in acts, f"missing action {label}"
        expect(page.locator(".sources-block h3")).to_contain_text("المصادر المستخدمة في هذه الإجابة")
        assert page.locator(".source-card").count() >= 1
        expect(page.locator(".msg-bot .notice:not(.notice-soft)")).to_contain_text(AI_NOTICE)
        assert "c=" in page.url
        shot(page, "real-chat-answer")
        assert not page.errors, page.errors
    check("real: chat answer with sources, 4 actions, AI notice", chat_real)

    def source_dialog():
        page.locator(".source-card .btn", has_text="عرض المصدر").first.click()
        expect(page.locator("dialog.dialog")).to_be_visible()
        text = page.locator("dialog .source-full").first.inner_text()
        assert len(text) > 10
        shot(page, "real-source-dialog")
        page.keyboard.press("Escape")
        expect(page.locator("dialog.dialog")).to_have_count(0)
    check("real: source dialog shows full stored text, Esc closes", source_dialog)

    def explain_without_llm():
        page.locator(".source-card .btn-explain").first.click()
        expect(page.locator("dialog .explain-result")).to_contain_text("غير مفعّل", timeout=30000)
        expect(page.locator("dialog blockquote")).not_to_be_empty()
        page.keyboard.press("Escape")
    check("real: hadith explain button; retrieval mode says explanation is not enabled", explain_without_llm)

    def copy_save():
        page.get_by_role("button", name="نسخ الإجابة").click()
        expect(page.locator(".toast")).to_contain_text("تم نسخ الإجابة")
        clip = page.evaluate("navigator.clipboard.readText()")
        assert "ما حق الجار" in clip and "المصادر" in clip
        save = page.locator(".answer-actions button", has_text="حفظ الإجابة")
        save.click()
        expect(page.locator(".answer-actions")).to_contain_text("تم الحفظ")
        expect(page.locator("#saved-badge")).to_have_text("1")
    check("real: copy feedback + save toggles to تم الحفظ + badge", copy_save)

    def history_reload():
        page.goto(f"{REAL}/index.html?new=1")
        expect(page.locator("#hero")).to_be_visible()
        assert page.locator("#history-list a").count() == 1
        page.locator("#history-list a").first.click()
        page.wait_for_selector(".answer-actions")
        expect(page.locator(".msg-user .bubble")).to_contain_text("ما حق الجار")
    check("real: conversation saved to history and reopens", history_reload)

    def history_dedupe_delete():
        page.goto(f"{REAL}/index.html?new=1")
        ask(page, "ما حق الجار في الإسلام؟")
        page.wait_for_selector(".answer-actions", timeout=90000)
        expect(page.locator("#history-list a")).to_have_count(1)  # same single question: one thread, not two
        expect(page.locator("#history-list .history-time").first).not_to_be_empty()
        page.locator("#history-list a").first.hover()
        page.get_by_role("button", name=re.compile("حذف المحادثة")).first.click()
        page.wait_for_url(re.compile(r"index\.html"))
        expect(page.locator("#hero")).to_be_visible()
        expect(page.locator("#history-list")).to_contain_text("لا توجد محادثات سابقة")
    check("real: asking the same question again keeps one thread; delete removes it", history_dedupe_delete)

    def saved_page():
        page.goto(f"{REAL}/saved.html")
        expect(page.locator(".saved-card")).to_have_count(1)
        page.get_by_role("button", name="فتح الإجابة").click()
        expect(page.locator("dialog.dialog")).to_be_visible()
        page.keyboard.press("Escape")
        shot(page, "real-saved")
        page.locator(".saved-card button", has_text="حذف").click()
        expect(page.locator("#saved-root")).to_contain_text("لا توجد إجابات محفوظة بعد.")
    check("real: saved page open + delete + empty state", saved_page)

    def off_topic():
        page.goto(f"{REAL}/index.html?new=1")
        ask(page, "ما هي عاصمة فرنسا؟")
        page.wait_for_selector(".answer-status", timeout=90000)
        expect(page.locator(".answer-status")).to_contain_text(NO_EVIDENCE)
        assert page.locator(".source-card").count() == 0
    check("real: off-topic question -> no-evidence message, no sources", off_topic)

    def verify_real():
        page.goto(f"{REAL}/verify.html")
        expect(page.locator("#verify-count")).to_have_text("0/500")
        page.fill("#verify-text", "لا إكراه في الدين")
        expect(page.locator("#verify-count")).to_have_text("17/500")
        page.click("#verify-btn")
        expect(page.locator(".verdict h2")).to_have_text("الدليل صحيح", timeout=60000)
        expect(page.locator(".stored-text blockquote")).to_be_visible()
        shot(page, "real-verify-matched")
        page.fill("#verify-text", "من حسن إسلام المرء تركه ما لا يعنيه")
        page.click("#verify-btn")
        expect(page.locator(".verdict h2")).to_have_text("الصيغة غير مطابقة", timeout=60000)
        assert page.locator(".stored-text").count() == 0
        page.fill("#verify-text", "كيف حالك")
        page.click("#verify-btn")
        expect(page.locator(".verify-result")).to_contain_text("لم يتم العثور على مصدر كافٍ للتحقق من هذا النص.", timeout=60000)
    check("real: verify matched / not_matched / insufficient", verify_real)

    def sources_model():
        page.goto(f"{REAL}/sources.html")
        expect(page.locator(".cat-card")).to_have_count(4, timeout=30000)
        expect(page.locator("#categories")).to_contain_text("صحيح البخاري")
        page.goto(f"{REAL}/model.html")
        expect(page.locator(".metric-table")).to_be_visible(timeout=30000)
        expect(page.locator(".metric-table")).to_contain_text("52.6%")
        expect(page.locator("#model-root")).to_contain_text("intfloat/multilingual-e5-small")
        expect(page.locator("#model-root")).to_contain_text("للقراءة فقط")
        shot(page, "real-model")
    check("real: sources from /sources, model metrics from /model-info", sources_model)
    ctx.close()

    # ---- mock adapter: every edge state
    ctx, page = new_page(browser)
    def mock_states():
        page.goto(f"{MOCK}/index.html")
        expect(page.locator(".mock-banner")).to_be_visible()
        cases = [("سؤال خطأ", "خلل تقني"), ("سؤال لا-دليل", NO_EVIDENCE), ("سؤال بدون-شرح", "دون شرح مولَّد"),
                 ("سؤال بلا-مصادر", "لم تُرفق مصادر"), ("<img src=x onerror=alert(1)> سؤال", "نص تجريبي")]
        for q, expected in cases:
            page.goto(f"{MOCK}/index.html?new=1")
            ask(page, q)
            page.wait_for_selector(".answer-card", timeout=20000)
            expect(page.locator(".msg-bot").last).to_contain_text(expected)
        expect(page.locator(".msg-user .bubble").last).to_contain_text("<img src=x")
        assert page.locator(".msg-user img").count() == 0
    check("mock: error / no-evidence / sources-only / empty sources / HTML stays text", mock_states)

    def mock_retry_and_broken_url():
        page.goto(f"{MOCK}/index.html?new=1")
        ask(page, "سؤال خطأ")
        expect(page.get_by_role("button", name="إعادة المحاولة")).to_be_visible(timeout=20000)
        page.goto(f"{MOCK}/index.html?new=1")
        ask(page, "سؤال رابط-معطل")
        page.wait_for_selector(".answer-actions", timeout=20000)
        disabled = page.locator('[aria-disabled="true"]', has_text="فتح المصدر الأصلي")
        assert disabled.count() >= 2, disabled.count()
        assert page.locator('a[href^="javascript:"]').count() == 0
    check("mock: retry button on error; javascript: URL rejected, buttons disabled", mock_retry_and_broken_url)

    def mock_slow_long():
        page.goto(f"{MOCK}/index.html?new=1")
        ask(page, "سؤال بطيء")
        expect(page.locator(".loader-text")).to_have_text("جارٍ البحث في المصادر...")
        expect(page.locator(".loader-text")).to_have_text("جارٍ إعداد الإجابة...", timeout=5000)
        page.wait_for_selector(".answer-actions", timeout=15000)
        page.goto(f"{MOCK}/index.html?new=1")
        ask(page, "سؤال طويل " + "كلمة " * 150)
        page.wait_for_selector(".answer-actions", timeout=20000)
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, overflow
        shot(page, "mock-long")
    check("mock: slow-response stages; very long question/answer stays in layout", mock_slow_long)

    def mock_verify():
        page.goto(f"{MOCK}/verify.html")
        for text, title in [("نص جزئي هنا", "تطابق جزئي"), ("نص غير-مطابق هنا", "الصيغة غير مطابقة"),
                            ("نص لا-مصدر هنا", "لا يكفي للتحقق"), ("نص خطأ هنا", "تعذر التحقق"), ("نص سليم هنا", "الدليل صحيح")]:
            page.fill("#verify-text", text)
            page.click("#verify-btn")
            expect(page.locator(".verdict h2")).to_have_text(title, timeout=10000)
        page.get_by_role("button", name="عرض التفاصيل").click()
        expect(page.locator(".details")).to_be_visible()
        page.goto(f"{MOCK}/model.html")
        expect(page.locator("#model-root")).to_contain_text("لم تُنشر نتيجة قياس نهائية بعد.", timeout=10000)
    check("mock: verify partial / not / insufficient / error / matched; model page without metrics", mock_verify)

    def mock_explain():
        page.goto(f"{MOCK}/index.html?new=1")
        ask(page, "سؤال للشرح")
        page.wait_for_selector(".answer-actions", timeout=20000)
        page.locator(".source-card .btn-explain").first.click()
        expect(page.locator("dialog .explain-generated")).to_contain_text("شرح مولَّد بالذكاء الاصطناعي", timeout=10000)
        expect(page.locator("dialog .explain-generated dl")).to_contain_text("[معنى تجريبي]")
        expect(page.locator("dialog .notice")).to_contain_text(AI_NOTICE)
        page.keyboard.press("Escape")
    check("mock: explain dialog shows labeled generated text, word meanings, AI notice", mock_explain)
    ctx.close()

    # ---- backend down
    ctx, page = new_page(browser)
    def dead():
        page.goto(f"{DEAD}/index.html")
        ask(page, "ما حق الجار؟")
        expect(page.locator(".answer-status")).to_contain_text("تعذر الاتصال بالخدمة حاليًا. حاولي مرة أخرى بعد قليل.", timeout=20000)
        page.goto(f"{DEAD}/sources.html")
        expect(page.locator("#categories")).to_contain_text("تعذر الاتصال بالخدمة حاليًا", timeout=20000)
        page.errors[:] = [e for e in page.errors if "Failed to load resource" not in e and "ERR_CONNECTION_REFUSED" not in e]
        assert not [e for e in page.errors if "pageerror" in e], page.errors
    check("backend down: friendly unavailable message on chat and sources", dead)
    ctx.close()

    # ---- mobile drawer + keyboard
    ctx, page = new_page(browser, "mobile")
    def drawer():
        page.goto(f"{REAL}/verify.html")
        sidebar = page.locator("#sidebar")
        expect(sidebar).not_to_be_in_viewport()
        page.click(".menu-toggle")
        expect(sidebar).to_be_in_viewport()
        assert page.get_attribute(".menu-toggle", "aria-expanded") == "true"
        page.wait_for_timeout(400)  # slide-in transition
        box = sidebar.bounding_box()
        assert abs(box["x"] + box["width"] - 390) < 1, box  # RTL: drawer docks to the right edge
        shot(page, "mobile-drawer-open")
        page.keyboard.press("Escape")
        expect(sidebar).not_to_be_in_viewport()
        page.keyboard.press("Tab")
    check("mobile: hamburger opens drawer, Esc closes it", drawer)

    def keyboard():
        page.goto(f"{REAL}/index.html")   # mobile viewport: no autofocus, so Tab starts at the skip link
        page.keyboard.press("Tab")
        expect(page.locator(".skip-link")).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.locator("#question")).to_be_focused()
        page.goto(f"{REAL}/verify.html")
        page.keyboard.press("Tab")
        expect(page.locator(".skip-link")).to_be_focused()
    check("keyboard: skip link reaches the question box", keyboard)
    ctx.close()


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME if os.path.exists(CHROME) else None)
    run(browser)
    browser.close()

for ok, name, err in results:
    print(("PASS " if ok else "FAIL ") + name + (f"\n     {err}" if err else ""))
failed = sum(not ok for ok, _, _ in results)
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
