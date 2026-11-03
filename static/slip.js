// ตัวนับถอยหลังชำระเงิน + ปุ่มแจ้งชำระเงิน (ใช้ทั้งหน้าใบจองและหน้าประวัติ)
(function () {
  function pad(n) { return String(n).padStart(2, "0"); }
  // ชดเชยความต่างของนาฬิกาเครื่องผู้ใช้กับเซิร์ฟเวอร์ (กันรีโหลดวนไม่รู้จบ)
  let skew = 0;
  fetch(location.pathname, { method: "HEAD", cache: "no-store" }).then(function (r) {
    const d = r.headers.get("Date");
    if (d) skew = new Date(d).getTime() - Date.now();
  }).catch(function () {});

  function tick() {
    const nowS = Math.floor((Date.now() + skew) / 1000);
    document.querySelectorAll(".countdown").forEach(function (el) {
      const left = parseInt(el.dataset.expires, 10) - nowS;
      if (left <= 0) {
        el.textContent = "00:00";
        // รีโหลดได้ครั้งเดียวต่อรายการ ต่อให้นาฬิกาคลาดเคลื่อนก็ไม่วนซ้ำ
        const key = "reloaded-" + el.dataset.expires;
        if (!el.dataset.done && !sessionStorage.getItem(key)) {
          el.dataset.done = "1";
          sessionStorage.setItem(key, "1");
          location.reload();
        }
        return;
      }
      el.textContent = pad(Math.floor(left / 60)) + ":" + pad(left % 60);
    });
  }
  tick();
  setInterval(tick, 1000);
// ---------- หน้าต่างอัปโหลดสลิป ----------
  const modal = document.getElementById("payModal");
  if (modal) {
    const fileEl = document.getElementById("payFile");
    const dateEl = document.getElementById("payDate");
    const timeEl = document.getElementById("payTime");
    const preview = document.getElementById("payPreview");
    const errEl = document.getElementById("payError");
    const okBtn = document.getElementById("payConfirm");
    let bookingId = null;

    function today() {
      const d = new Date();
      return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
    }
    function showErr(msg) { errEl.textContent = msg; errEl.hidden = !msg; }
    function validate() {
      okBtn.disabled = !(fileEl.files.length && dateEl.value && timeEl.value);
    }
    function openModal(btn) {
      bookingId = btn.dataset.id;
      document.getElementById("payInfo").textContent =
        "รหัสจอง " + btn.dataset.code + " · ยอดชำระ " + btn.dataset.amount + " บาท";
      fileEl.value = ""; preview.hidden = true; showErr("");
      const d = new Date();
      dateEl.value = today(); dateEl.max = today();
      timeEl.value = pad(d.getHours()) + ":" + pad(d.getMinutes());
      validate();
      modal.hidden = false;
    }
    function closeModal() { modal.hidden = true; }

    document.querySelectorAll(".pay-btn").forEach(function (btn) {
      btn.addEventListener("click", function () { openModal(btn); });
    });
    document.getElementById("payClose").addEventListener("click", closeModal);
    modal.addEventListener("click", function (e) { if (e.target === modal) closeModal(); });

    fileEl.addEventListener("change", function () {
      showErr("");
      const f = fileEl.files[0];
      if (f && f.size > 5 * 1024 * 1024) {
        fileEl.value = ""; preview.hidden = true;
        showErr("ไฟล์ใหญ่เกิน 5 MB");
      } else if (f) {
        preview.src = URL.createObjectURL(f); preview.hidden = false;
      } else { preview.hidden = true; }
      validate();
    });
    dateEl.addEventListener("input", validate);
    timeEl.addEventListener("input", validate);

    okBtn.addEventListener("click", async function () {
      okBtn.disabled = true; showErr("");
      const fd = new FormData();
      fd.append("slip", fileEl.files[0]);
      fd.append("transfer_date", dateEl.value);
      fd.append("transfer_time", timeEl.value);
      try {
        const res = await fetch("/api/bookings/" + bookingId + "/slip", { method: "POST", body: fd });
        const data = await res.json().catch(function () { return {}; });
        if (!res.ok) { showErr(data.error || "เกิดข้อผิดพลาด"); okBtn.disabled = false; return; }
      } catch (e) {
        showErr("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้"); okBtn.disabled = false; return;
      }
      location.reload();
    });
  }
})();