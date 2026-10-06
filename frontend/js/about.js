import { config } from "./api.js";
import { initShell, el } from "./ui.js";

initShell("about");
const p = document.getElementById("contact-text");
if (config.contactEmail) {
  p.append("يسعدنا تواصلك عبر البريد الإلكتروني: ",
    el("a", { href: `mailto:${encodeURIComponent(config.contactEmail).replace("%40", "@")}`, text: config.contactEmail }));
} else {
  p.textContent = "سيتم نشر وسيلة التواصل قريبًا.";
}
