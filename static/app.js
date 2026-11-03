// ผังอาคาร (ภาพ 3D รายชั้น + พื้นที่คลิกทับห้องที่จองได้) + หน้าต่างจองห้อง
// FLOORS, CONFIG ถูกส่งมาจาก templates/index.html (ผู้ใช้) และ templates/admin_rooms.html (แอดมิน)
// FLOORS[ชั้น] = { image, rooms:[{id, kind:"blue"|"orange", pts:[[x,y],...]}] }  (พิกัดอิงภาพ 1920x1080)
// CONFIG.admin = true  -> โหมดแอดมิน : ใช้หน้าต่างเดียวกันเพื่อ "ปิดห้อง" และยกเลิกการปิดได้
(function () {
  const svg = document.getElementById("buildingMap");
  const tip = document.getElementById("mapTip");
  const NS = "http://www.w3.org/2000/svg";
  const XLINK = "http://www.w3.org/1999/xlink";
  const ADMIN = !!CONFIG.admin;
  const MAP_W = 1920, MAP_H = 1080;

  function el(name, attrs, text) {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (text) n.textContent = text;
    return n;
  }

  let currentFloor = 1;
  const floorNum = function (f) { return Number(f); };

  function openRoom(room, floor) { openModal(room.id, floor); }

  function drawFloor(floor) {
    currentFloor = floor;
    const data = FLOORS[floor];
    svg.innerHTML = "";
    svg.setAttribute("viewBox", "0 0 " + MAP_W + " " + MAP_H);

    // ภาพผังของชั้นนั้น
    const img = el("image", { x: 0, y: 0, width: MAP_W, height: MAP_H, preserveAspectRatio: "xMidYMid meet" });
    const src = CONFIG.floorImgBase + data.image;
    img.setAttribute("href", src);
    img.setAttributeNS(XLINK, "xlink:href", src);
    svg.appendChild(img);

    // พื้นที่คลิกของห้องที่จองได้ (โปร่งใส จะเรืองแสงตอนชี้/โฟกัส)
    data.rooms.forEach(function (room) {
      const g = el("g", {
        class: "hot " + room.kind, tabindex: 0, role: "button",
        "data-room": room.id,
        "aria-label": (ADMIN ? "จัดการ" : "จอง") + roomLabel(room.id)
      });
      g.appendChild(el("polygon", { points: room.pts.map(function (p) { return p.join(","); }).join(" ") }));
      g.addEventListener("click", function () { openRoom(room, floor); });
      g.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openRoom(room, floor); }
      });
      g.addEventListener("mouseenter", function () {
        if (!window.matchMedia("(hover: hover)").matches) return;   // จอสัมผัสไม่ต้องแสดง tooltip ค้าง
        showTip(roomLabel(room.id) + (ADMIN ? " — คลิกเพื่อปิด/เปิดการจอง" : " — คลิกเพื่อจอง"), true);
      });
      g.addEventListener("mouseleave", hideTip);
      svg.appendChild(g);
    });

    document.querySelectorAll(".floor-tab").forEach(function (b) {
      b.classList.toggle("active", floorNum(b.dataset.floor) === floor);
    });
  }

  let tipTimer;
  function showTip(msg, sticky) {
    tip.textContent = msg;
    tip.classList.add("show");
    clearTimeout(tipTimer);
    if (!sticky) tipTimer = setTimeout(function () { tip.classList.remove("show"); }, 2500);
  }
  function hideTip() { clearTimeout(tipTimer); tip.classList.remove("show"); }

  document.querySelectorAll(".floor-tab").forEach(function (b) {
    b.addEventListener("click", function () { drawFloor(floorNum(b.dataset.floor)); });
  });
 
  // =====================================================================
  //                          หน้าต่างจองห้อง
  // =====================================================================
  const THAI_MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"];
  const THAI_MS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];
 
  const $ = function (id) { return document.getElementById(id); };
  const modal = $("modal"), selStart = $("selStart"), selEnd = $("selEnd");
  const btnConfirm = $("btnConfirm"), mError = $("mError"), mOk = $("mOk");
 
  // booked = รายการจอง/การปิดห้องของห้องที่เปิดอยู่ (ได้จาก API)
  // focus  = วันที่ที่คลิกล่าสุด (ใช้แสดงตารางเวลา)
  const state = { room: null, floor: null, year: 0, month: 0, start: null, end: null, picking: "end", booked: [], focus: null };
 
  function pad2(n) { return String(n).padStart(2, "0"); }
  function ymd(d) {
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
  }
  function thaiDate(d) { return d.getDate() + " " + THAI_MS[d.getMonth()] + " " + (d.getFullYear() + 543); }
  function sameDay(a, b) { return a && b && ymd(a) === ymd(b); }
  // เวลา "ตอนนี้" ตามเขตเวลาไทย (ให้ตรงกับเซิร์ฟเวอร์ ไม่ขึ้นกับเขตเวลาของเครื่องผู้ใช้)
  function bkkNow() {
    const o = {};
    new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", hourCycle: "h23" })
      .formatToParts(new Date()).forEach(function (p) { o[p.type] = p.value; });
    return { y: Number(o.year), m: Number(o.month), d: Number(o.day), h: Number(o.hour) };
  }
  function today0() { const t = bkkNow(); return new Date(t.y, t.m - 1, t.d); }
  // ชื่อห้องสำหรับแสดงผล (ไม่ซ้ำคำว่า "ห้อง" เช่น "ห้องประชุม...")
  function roomLabel(id) { return /^ห้อง/.test(id) ? id : "ห้อง " + id; }
  function parseYmd(s) { return new Date(s + "T00:00"); }
  function hr(h) { return pad2(h) + ":00"; }
 
  // ----- ตัวช่วยเกี่ยวกับรายการที่ถูกจอง/ปิด -----
  function coverOf(ds) {
    return state.booked.filter(function (r) { return r.start_date <= ds && ds <= r.end_date; });
  }
  function kindClass(r) {
    if (r.kind === "block") return "mk-block";
    if (r.status === "paid") return "mk-paid";
    return r.status === "verify" ? "mk-verify" : "mk-pending";
  }
  function slotClass(r) {
    if (r.kind === "block") return "tt-block";
    if (r.status === "paid") return "tt-paid";
    return r.status === "verify" ? "tt-verify" : "tt-pend";
  }
  function labelOf(r) {
    if (r.kind === "block") return "ปิดให้บริการ" + (r.reason ? " (" + r.reason + ")" : "");
    if (r.status === "paid") return "จองแล้ว";
    if (r.status === "review") return "รออนุมัติ";
    if (r.status === "verify") return "รอตรวจสลิป";
    return "รอชำระเงิน";
  }
  function datesOf(r) {
    const sd = parseYmd(r.start_date), ed = parseYmd(r.end_date);
    return r.start_date === r.end_date ? thaiDate(sd) : thaiDate(sd) + " – " + thaiDate(ed);
  }
 
  function fillHourSelects() {
    selStart.innerHTML = ""; selEnd.innerHTML = "";
    for (let h = CONFIG.openHour; h <= CONFIG.closeHour; h++) {
      const label = hr(h);
      if (h < CONFIG.closeHour) selStart.add(new Option(label, h));
      if (h > CONFIG.openHour) selEnd.add(new Option(label, h));
    }
    selStart.value = 9; selEnd.value = 10;
  }
 
  function hoursPerDay() { return Number(selEnd.value) - Number(selStart.value); }

  // ปรับตัวเลือกเวลาให้ถูกต้องเสมอ : เวลาสิ้นสุดต้องหลังเวลาเริ่ม, และถ้าเลือกวันนี้ (โหมดผู้ใช้) ห้ามเลือกชั่วโมงที่ผ่านมาแล้ว
  function normalizeHours() {
    const minStart = (!ADMIN && state.start && sameDay(state.start, today0())) ? bkkNow().h : -1;
    Array.prototype.forEach.call(selStart.options, function (o) { o.disabled = Number(o.value) <= minStart; });
    if (selStart.selectedOptions[0] && selStart.selectedOptions[0].disabled) {
      const firstOk = Array.prototype.find.call(selStart.options, function (o) { return !o.disabled; });
      if (firstOk) selStart.value = firstOk.value;
    }
    if (Number(selEnd.value) <= Number(selStart.value)) {
      selEnd.value = Math.min(Number(selStart.value) + 1, CONFIG.closeHour);
    }
    Array.prototype.forEach.call(selEnd.options, function (o) { o.disabled = Number(o.value) <= Number(selStart.value); });
    return Array.prototype.some.call(selStart.options, function (o) { return !o.disabled; });
  }

  // ตรวจว่าช่วงที่เลือกชนกับรายการจอง/การปิดห้องหรือไม่ (ตรรกะเดียวกับเซิร์ฟเวอร์)
  function findConflict() {
    if (!state.start || !state.end) return null;
    const s = ymd(state.start), e = ymd(state.end);
    const sh = Number(selStart.value), eh = Number(selEnd.value);
    return state.booked.find(function (r) {
      return r.start_date <= e && r.end_date >= s && r.start_hour < eh && r.end_hour > sh;
    }) || null;
  }
 
  // ----- ปฏิทิน : มีจุด (จองวันเดียว) / แถบยาว (จองหลายวัน) ที่มุมขวาบนของวันที่ -----
  function renderCalendar() {
    $("calTitle").textContent = THAI_MONTHS[state.month] + " " + (state.year + 543);
    const grid = $("calGrid");
    grid.innerHTML = "";
    const first = new Date(state.year, state.month, 1);
    const daysIn = new Date(state.year, state.month + 1, 0).getDate();
    const t0 = today0();
    for (let i = 0; i < first.getDay(); i++) grid.appendChild(document.createElement("span"));
    for (let d = 1; d <= daysIn; d++) {
      const date = new Date(state.year, state.month, d);
      const ds = ymd(date);
      const b = document.createElement("button");
      b.type = "button"; b.className = "cal-day";
      const num = document.createElement("span");
      num.className = "num"; num.textContent = d;
      b.appendChild(num);
      if (date < t0) { b.disabled = true; }
      if (sameDay(date, t0)) b.classList.add("today");
      if (state.start && state.end && date >= state.start && date <= state.end) b.classList.add("in-range");
      if (sameDay(date, state.start) || sameDay(date, state.end)) b.classList.add("edge");
      if (state.focus && sameDay(date, state.focus)) b.classList.add("focus");
 
      const cov = coverOf(ds);
      if (cov.length) {
        b.classList.add("has-booked");
        const wrap = document.createElement("span");
        wrap.className = "mk-wrap";
        cov.slice(0, 3).forEach(function (r) {
          const m = document.createElement("i");
          const multi = r.start_date !== r.end_date;
          let cls = "mk " + kindClass(r);
          if (multi) {
            cls += " bar";
            if (ds === r.start_date) cls += " bar-start";
            if (ds === r.end_date) cls += " bar-end";
          } else {
            cls += " dot";
          }
          m.className = cls;
          wrap.appendChild(m);
        });
        b.appendChild(wrap);
        b.title = cov.map(function (r) {
          return hr(r.start_hour) + "-" + hr(r.end_hour) + " " + labelOf(r);
        }).join("\n");
      }
 
      b.addEventListener("click", function () { pickDay(date); });
      grid.appendChild(b);
    }
  }
 
  // ----- ตารางเวลาของวันที่เลือก (ใต้ปฏิทิน) -----
  function renderTimetable() {
    const grid = $("ttGrid"), list = $("ttList");
    grid.innerHTML = ""; list.innerHTML = "";
    const d = state.focus;
    $("ttDate").textContent = d ? "· " + thaiDate(d) : "· คลิกวันที่ในปฏิทินเพื่อดูตาราง";
    const cov = d ? coverOf(ymd(d)) : [];
    const sS = Number(selStart.value), sE = Number(selEnd.value);
 
    for (let h = CONFIG.openHour; h < CONFIG.closeHour; h++) {
      const c = document.createElement("div");
      c.className = "tt-slot";
      c.textContent = hr(h);
      c.title = hr(h) + " - " + hr(h + 1);
      const hit = cov.find(function (r) { return r.start_hour <= h && h < r.end_hour; });
      if (hit) c.classList.add(slotClass(hit));
      if (d && h >= sS && h < sE) c.classList.add("tt-sel");
      grid.appendChild(c);
    }
 
    if (!d) return;
    if (!cov.length) {
      list.innerHTML = '<li class="muted">วันนี้ยังไม่มีการจอง</li>';
      return;
    }
    cov.slice().sort(function (a, b) { return a.start_hour - b.start_hour; }).forEach(function (r) {
      const li = document.createElement("li");
      const multi = r.start_date !== r.end_date;
      li.textContent = hr(r.start_hour) + " – " + hr(r.end_hour) + " น. · " + labelOf(r) +
        " (ถึงเวลา " + hr(r.end_hour) + ")" + (multi ? " · " + datesOf(r) : "");
      list.appendChild(li);
    });
  }
 
  function pickDay(date) {
    state.focus = date;
    if (state.picking === "end" && state.start) {
      // คลิกครั้งที่สอง : กำหนดวันสิ้นสุด (ถ้าคลิกวันก่อนวันเริ่ม ให้สลับเป็นช่วงที่ถูกต้อง)
      if (date >= state.start) { state.end = date; }
      else { state.end = state.start; state.start = date; }
      state.picking = "start";
    } else {
      // คลิกครั้งแรก (หรือเริ่มเลือกใหม่) : วันเดียวก่อน
      state.start = date; state.end = date; state.picking = "end";
    }
    renderCalendar(); updateSummary();
  }
 
  function updateSummary() {
    const hasSlot = normalizeHours();
    $("sumStart").textContent = state.start ? thaiDate(state.start) : "-";
    $("sumEnd").textContent = state.end ? thaiDate(state.end) : "-";
    const hpd = hoursPerDay();
    $("hPerDay").textContent = hpd > 0 ? hpd : 0;
    let days = 0;
    if (state.start && state.end) days = Math.round((state.end - state.start) / 86400000) + 1;
    const total = (hpd > 0 ? hpd : 0) * days;
    $("sumDays").textContent = days;
    $("sumHours").textContent = total;
    $("sumAmount").textContent = (total * state.rate).toLocaleString("th-TH");

    let ok = state.start && state.end && hpd > 0 && total > 0;
    mError.hidden = true;
    mOk.hidden = true;

    // แจ้งเหตุผลทันทีเมื่อกดยืนยันไม่ได้ (แทนที่จะรอให้เซิร์ฟเวอร์ตอบ 409 / 400)
    const conflict = findConflict();
    if (!hasSlot) {
      mError.textContent = "วันนี้ไม่มีช่วงเวลาที่จองได้แล้ว กรุณาเลือกวันอื่น";
      mError.hidden = false; ok = false;
    } else if (conflict) {
      mError.textContent = "ช่วงที่เลือกชนกับ \"" + labelOf(conflict) + "\" (" + datesOf(conflict) + " " +
        hr(conflict.start_hour) + "-" + hr(conflict.end_hour) + ") กรุณาเลือกวัน/เวลาอื่น";
      mError.hidden = false; ok = false;
    }

    btnConfirm.disabled = !ok;
    $("hMinus").disabled = hpd <= 1;
    $("hPlus").disabled = Number(selEnd.value) >= CONFIG.closeHour;
    renderTimetable();
  }
 
  // ปุ่ม เพิ่ม/ลด ชั่วโมง (ปรับเวลาสิ้นสุดทีละ 1 ชั่วโมง)
  $("hPlus").addEventListener("click", function () {
    if (Number(selEnd.value) < CONFIG.closeHour) { selEnd.value = Number(selEnd.value) + 1; updateSummary(); }
  });
  $("hMinus").addEventListener("click", function () {
    if (hoursPerDay() > 1) { selEnd.value = Number(selEnd.value) - 1; updateSummary(); }
  });
  selStart.addEventListener("change", updateSummary);   // normalizeHours() ขยับเวลาสิ้นสุดให้เอง
  selEnd.addEventListener("change", updateSummary);
 
  if ($("btnAllDay")) {
    $("btnAllDay").addEventListener("click", function () {
      selStart.value = CONFIG.openHour; selEnd.value = CONFIG.closeHour; updateSummary();
    });
  }
 
  $("calPrev").addEventListener("click", function () {
    const cur = new Date(state.year, state.month, 1);
    const t = today0();
    if (cur > new Date(t.getFullYear(), t.getMonth(), 1)) {
      cur.setMonth(cur.getMonth() - 1); state.year = cur.getFullYear(); state.month = cur.getMonth(); renderCalendar();
    }
  });
  $("calNext").addEventListener("click", function () {
    const cur = new Date(state.year, state.month, 1);
    cur.setMonth(cur.getMonth() + 1); state.year = cur.getFullYear(); state.month = cur.getMonth(); renderCalendar();
  });
 
  // ----- โหลดรายการจอง/ปิดห้อง แล้ววาดรายการ + ปฏิทิน + ตารางเวลา -----
  function scheduleUrl(room) {
    return (ADMIN ? "/admin/api/rooms/" : "/api/rooms/") + encodeURIComponent(room) + (ADMIN ? "/schedule" : "/bookings");
  }
 
  async function cancelBlock(id) {
    if (!confirm("ยืนยันยกเลิกการปิดห้องช่วงนี้? (ผู้ใช้จะกลับมาจองได้)")) return;
    try {
      const res = await fetch("/admin/api/blocks/" + id, { method: "DELETE" });
      const data = await res.json().catch(function () { return {}; });
      if (!res.ok) { mError.textContent = data.error || "เกิดข้อผิดพลาด"; mError.hidden = false; return; }
      mOk.textContent = "ยกเลิกการปิดห้องแล้ว"; mOk.hidden = false;
      loadBooked(state.room);
    } catch (e) {
      mError.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้"; mError.hidden = false;
    }
  }
 
  async function loadBooked(room) {
    const ul = $("bookedList");
    ul.innerHTML = '<li class="muted">กำลังโหลด...</li>';
    try {
      const res = await fetch(scheduleUrl(room));
      const rows = await res.json();
      if (room !== state.room) return;
      state.booked = Array.isArray(rows) ? rows : [];
      ul.innerHTML = "";
      if (!state.booked.length) {
        ul.innerHTML = '<li class="muted">' + (ADMIN ? "ยังไม่มีการจองหรือการปิดห้อง" : "ยังไม่มีการจอง") + "</li>";
      }
      state.booked.forEach(function (r) {
        const li = document.createElement("li");
        li.textContent = datesOf(r) + "  " + hr(r.start_hour) + "-" + hr(r.end_hour) + " (" + labelOf(r) + ")";
        if (ADMIN && r.kind === "block") {
          const btn = document.createElement("button");
          btn.type = "button"; btn.className = "mini-btn"; btn.textContent = "ยกเลิกการปิด";
          btn.addEventListener("click", function () { cancelBlock(r.id); });
          li.appendChild(document.createTextNode(" "));
          li.appendChild(btn);
        }
        ul.appendChild(li);
      });
      renderCalendar(); renderTimetable();
    } catch (e) {
      ul.innerHTML = '<li class="muted">โหลดข้อมูลไม่สำเร็จ</li>';
    }
  }
 
  function openModal(room, floor) {
    state.room = room; state.floor = floor;
    const rm = FLOORS[floor].rooms.find(function (r) { return r.id === room; });
    state.rate = (rm && rm.kind === "orange") ? CONFIG.priceOrange : CONFIG.pricePerHour;
    const t = today0();
    state.year = t.getFullYear(); state.month = t.getMonth();
    state.start = null; state.end = null; state.picking = "end";
    state.booked = []; state.focus = null;
    fillHourSelects();
    if ($("mReason")) $("mReason").value = "";
    hideTip();
    $("mTitle").textContent = (ADMIN ? "ปิด" : "จอง") + roomLabel(room) + " (ชั้น " + floor + ")";
    renderCalendar(); updateSummary(); loadBooked(room);
    modal.hidden = false;
    document.body.classList.add("no-scroll");
  }
  function closeModal() { modal.hidden = true; document.body.classList.remove("no-scroll"); }
 
  $("mClose").addEventListener("click", closeModal);
  modal.addEventListener("click", function (e) { if (e.target === modal) closeModal(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !modal.hidden) closeModal(); });
 
  btnConfirm.addEventListener("click", async function () {
    btnConfirm.disabled = true;
    const payload = {
      room: state.room,
      start_date: ymd(state.start), end_date: ymd(state.end),
      start_hour: Number(selStart.value), end_hour: Number(selEnd.value)
    };
    if (ADMIN) payload.reason = $("mReason").value.trim();
    try {
      const res = await fetch(ADMIN ? "/admin/api/blocks" : "/api/bookings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(function () { return {}; });
      if (res.ok) {
        if (ADMIN) {
          // ปิดห้องสำเร็จ : รีเฟรชปฏิทิน/ตาราง และเคลียร์ช่องเหตุผล
          $("mReason").value = "";
          state.start = null; state.end = null; state.picking = "end"; state.focus = null;
          await loadBooked(state.room);
          updateSummary();
          mOk.textContent = "ปิดห้องในช่วงเวลานี้เรียบร้อยแล้ว";
          mOk.hidden = false;
          return;
        }
        location.href = data.url; return;
      }
      mError.textContent = data.error || "เกิดข้อผิดพลาด";
      mError.hidden = false;
      if (res.status === 409) loadBooked(state.room);
    } catch (e) {
      mError.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้";
      mError.hidden = false;
    }
    btnConfirm.disabled = false;
  });
 
  drawFloor(1);
})();