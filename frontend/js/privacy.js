import { clearAll } from "./storage.js";
import { initShell, toast } from "./ui.js";

initShell("about");
document.getElementById("clear-data").addEventListener("click", () => {
  if (window.confirm("سيتم حذف المحادثات السابقة والإجابات المحفوظة من هذا المتصفح. هل تريدين المتابعة؟")) {
    clearAll();
    toast("تم حذف البيانات المحفوظة");
  }
});
