import hashlib
import hmac
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
from datetime import datetime, date, timedelta
from email.message import EmailMessage
from functools import wraps
from zoneinfo import ZoneInfo
 
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, jsonify, abort, flash, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
 
# ----------------------------------------------------------------------------
# ตั้งค่าระบบ
# ----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "booking.db")
SECRET_PATH = os.path.join(BASE_DIR, ".secret_key")
 
TZ = ZoneInfo("Asia/Bangkok")
PRICE_PER_HOUR = 50        # บาทต่อชั่วโมง
PRICE_ORANGE_PER_HOUR = 150  # บาทต่อชั่วโมง (ห้องสีส้ม)
PAY_WINDOW_MIN = 30        # เวลาที่ต้องชำระเงิน (นาที)
OPEN_HOUR = 6              # เวลาเปิดให้จอง (ชั่วโมง)
CLOSE_HOUR = 22            # เวลาปิด
MAX_DAYS = 31              # จองต่อเนื่องได้สูงสุดกี่วัน
MAX_BLOCK_DAYS = 366       # แอดมินปิดห้องต่อเนื่องได้สูงสุดกี่วัน
# --- อัปโหลดสลิปโอนเงิน ---
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "slips")   # อยู่นอก static เพื่อไม่ให้เปิดดูได้ตรง ๆ
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_SLIP_MB = 5
 
# --- OTP สำหรับลืมรหัสผ่าน (ส่งทาง Gmail) ---
# ตั้งค่าผ่าน environment variable:
#   GMAIL_USER          = อีเมล Gmail ที่ใช้ส่ง เช่น yourname@gmail.com
#   GMAIL_APP_PASSWORD  = App Password 16 หลักของ Gmail (ไม่ใช่รหัสผ่านปกติ)
#   OTP_DEV_PRINT=1     = (ทดสอบเท่านั้น) พิมพ์ OTP ลง console แทนการส่งอีเมล
OTP_TTL_MIN = 10           # OTP หมดอายุกี่นาที
OTP_RESEND_SEC = 60        # ขอ OTP ใหม่ได้ทุกกี่วินาที
OTP_MAX_ATTEMPTS = 5       # กรอก OTP ผิดได้กี่ครั้ง
 
# ----------------------------------------------------------------------------
# ข้อมูลอาคาร / ผังห้องที่จองได้
#   แต่ละชั้นใช้ภาพผัง static/floors/floorN.png (ขนาดอ้างอิง 1920x1080)
#   ห้องที่กดจองได้ = รูปหลายเหลี่ยม (จุด x,y บนภาพ) วางทับบนห้องในภาพ
#   kind: "blue"   = ห้องเรียน/ห้องตัวเลข/ห้อง R
#         "orange" = ห้องสีส้ม (ลานนันทนาการ / ห้องประชุม / ED TEAL)
#   ถ้าจะเพิ่ม-ลบห้อง หรือขยับตำแหน่ง แก้ที่ลิสต์นี้ที่เดียวได้เลย
#   (id = ชื่อห้องที่เก็บในฐานข้อมูล)
# ----------------------------------------------------------------------------
def _room(rid, kind, pts):
    return {"id": rid, "kind": kind, "pts": [list(p) for p in pts]}


FLOORS = {
    1: {
        "image": "floor1.png",
        "rooms": [
            # ห้องสีส้ม (วาดก่อน เพื่อให้ห้อง R ซ้อนทับด้านบนได้)
            _room("ลานนันทนาการ", "orange",
                  [(262, 560), (490, 562), (562, 792), (558, 858), (195, 858)]),
            _room("ENJOY CLUB", "orange",
                  [(842, 322), (1003, 318), (1003, 388), (842, 392)]),
            _room("1101", "blue", [(1523, 100), (1645, 86), (1658, 135), (1535, 152)]),
            _room("1102", "blue", [(1537, 158), (1662, 143), (1675, 196), (1548, 213)]),
            _room("1103", "blue", [(1551, 215), (1680, 200), (1692, 254), (1565, 270)]),
            _room("1104", "blue", [(1566, 272), (1695, 258), (1708, 312), (1580, 330)]),
            _room("R1", "blue", [(490, 566), (572, 559), (577, 606), (490, 614)]),
            _room("R2", "blue", [(485, 622), (568, 616), (572, 664), (483, 672)]),
            _room("R3", "blue", [(478, 678), (564, 672), (568, 720), (476, 728)]),
            _room("R4", "blue", [(472, 736), (560, 730), (564, 780), (470, 790)]),
            _room("R5", "blue", [(246, 612), (338, 608), (340, 655), (243, 665)]),
            _room("R6", "blue", [(234, 668), (328, 664), (329, 712), (229, 722)]),
            _room("R7", "blue", [(222, 728), (318, 724), (318, 772), (215, 785)]),
        ],
    },
    2: {
        "image": "floor2.png",
        "rooms": [
            _room("ห้องประชุมสายสุรี จุติกุล", "orange",
                  [(585, 368), (1305, 306), (1322, 420), (598, 492)]),
            _room("1212", "blue", [(1522, 222), (1625, 205), (1652, 300), (1545, 322)]),
            _room("1218", "blue", [(1605, 482), (1712, 466), (1732, 548), (1620, 565)]),
            _room("1219", "blue", [(1630, 562), (1735, 548), (1760, 632), (1650, 652)]),
        ],
    },
    3: {
        "image": "floor3.png",
        "rooms": [
            _room("1302", "blue", [(1490, 178), (1592, 158), (1612, 212), (1505, 245)]),
            _room("1303", "blue", [(1508, 250), (1622, 228), (1642, 286), (1528, 312)]),
        ],
    },
    4: {
        "image": "floor4.png",
        "rooms": [
            _room("ED TEAL", "orange",
                  [(638, 375), (1340, 318), (1352, 402), (648, 468)]),
            # ปีกซ้าย คอลัมน์นอก
            _room("1456", "blue", [(274, 215), (358, 204), (366, 262), (280, 276)]),
            _room("1455", "blue", [(280, 278), (368, 266), (376, 328), (285, 342)]),
            _room("1454", "blue", [(288, 342), (378, 330), (386, 396), (292, 412)]),
            # ปีกซ้าย คอลัมน์ใน
            _room("1457", "blue", [(412, 190), (494, 180), (502, 238), (416, 250)]),
            _room("1458", "blue", [(420, 252), (506, 242), (514, 302), (426, 312)]),
            _room("1459", "blue", [(428, 314), (516, 304), (524, 366), (436, 376)]),
            _room("1460", "blue", [(438, 376), (526, 366), (534, 430), (444, 442)]),
            # ปีกซ้าย ล่าง
            _room("1450", "blue", [(312, 618), (412, 610), (418, 672), (316, 686)]),
            _room("1449", "blue", [(318, 684), (420, 678), (426, 742), (322, 754)]),
            _room("1448", "blue", [(322, 750), (428, 745), (433, 810), (328, 822)]),
            _room("1447", "blue", [(328, 820), (436, 815), (440, 882), (334, 895)]),
            # ปีกขวา คอลัมน์ใน
            _room("1405", "blue", [(1388, 118), (1478, 103), (1490, 158), (1396, 172)]),
            _room("1404", "blue", [(1405, 175), (1495, 163), (1505, 220), (1416, 232)]),
            _room("1403", "blue", [(1422, 236), (1512, 224), (1522, 282), (1436, 296)]),
            _room("1402", "blue", [(1440, 298), (1530, 288), (1542, 345), (1455, 358)]),
            # ปีกขวา คอลัมน์นอก
            _room("1406", "blue", [(1512, 100), (1600, 92), (1612, 140), (1524, 155)]),
            _room("1407", "blue", [(1535, 160), (1625, 150), (1635, 208), (1548, 222)]),
            _room("1408", "blue", [(1557, 220), (1652, 210), (1662, 280), (1572, 292)]),
            # ปีกขวา ล่าง
            _room("1413", "blue", [(1635, 488), (1735, 472), (1750, 530), (1650, 548)]),
            _room("1414", "blue", [(1655, 552), (1760, 538), (1773, 598), (1672, 615)]),
            _room("1415", "blue", [(1676, 620), (1783, 606), (1796, 668), (1692, 688)]),
            _room("1416", "blue", [(1698, 688), (1805, 676), (1822, 742), (1712, 762)]),
        ],
    },
}

ROOM_FLOOR = {}
for _fl, _d in FLOORS.items():
    for _room_ in _d["rooms"]:
        ROOM_FLOOR[_room_["id"]] = _fl
ROOM_KIND = {}
for _fl, _d in FLOORS.items():
    for _room_ in _d["rooms"]:
        ROOM_KIND[_room_["id"]] = _room_["kind"]


def price_for(room):
    return PRICE_ORANGE_PER_HOUR if ROOM_KIND.get(room) == "orange" else PRICE_PER_HOUR
 
# ----------------------------------------------------------------------------
# แอป
# ----------------------------------------------------------------------------
app = Flask(__name__)
 
 
def _load_secret():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    if os.path.exists(SECRET_PATH):
        with open(SECRET_PATH) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(SECRET_PATH, "w") as f:
        f.write(key)
    return key
 
 
app.config.update(
    SECRET_KEY=_load_secret(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=MAX_SLIP_MB * 1024 * 1024,
)


@app.errorhandler(413)
def too_large(_e):
    return jsonify(error=f"ไฟล์ใหญ่เกิน {MAX_SLIP_MB} MB"), 413
 
 
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db
 
 
@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()
 
 
def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            phone TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            room TEXT NOT NULL,
            floor INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            start_hour INTEGER NOT NULL,
            end_hour INTEGER NOT NULL,
            hours INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',   -- pending | paid | expired
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            paid_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_bookings_room ON bookings(room, status);
        CREATE TABLE IF NOT EXISTS room_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            floor INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            start_hour INTEGER NOT NULL,
            end_hour INTEGER NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_blocks_room ON room_blocks(room);
        CREATE TABLE IF NOT EXISTS password_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """
    )
    db.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    """)
 
    # เพิ่มคอลัมน์สำหรับคำขอยกเลิกและเหตุผลการตัดสินใจ
    booking_columns = {
        row[1] for row in
        db.execute("PRAGMA table_info(bookings)").fetchall()
    }
 
    if "cancel_requested_at" not in booking_columns:
        db.execute(
            "ALTER TABLE bookings ADD COLUMN cancel_requested_at TEXT"
        )
 
    if "decision_note" not in booking_columns:
        db.execute(
            "ALTER TABLE bookings ADD COLUMN decision_note TEXT"
        )
    for col in ("slip_image", "slip_transfer_at", "slip_uploaded_at"):
            if col not in booking_columns:
                db.execute(f"ALTER TABLE bookings ADD COLUMN {col} TEXT")
 
    # สร้างแอดมินเริ่มต้น หากยังไม่มีบัญชีแอดมิน
    admin_exists = db.execute(
        "SELECT 1 FROM admins LIMIT 1"
    ).fetchone()
 
    if not admin_exists:
        admin_username = os.environ.get(
            "ADMIN_USERNAME", "ADMINCOMED"
        )
        admin_password = os.environ.get(
            "ADMIN_PASSWORD", "ADMINCOMED"
        )
 
        db.execute(
            """
            INSERT INTO admins (username, password_hash)
            VALUES (?, ?)
            """,
            (
                admin_username,
                generate_password_hash(admin_password)
            )
        )
    db.commit()
    db.close()
 
 
# ----------------------------------------------------------------------------
# ตัวช่วย
# ----------------------------------------------------------------------------
THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
 
 
def now():
    return datetime.now(TZ)
 
 
def thai_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year + 543}"
 
 
def expire_old():
    db = get_db()
    db.execute(
        "UPDATE bookings SET status='expired' WHERE status='pending' AND expires_at <= ?",
        (now().isoformat(),),
    )
    db.commit()
 
def _th_datetime(iso):
    dt = datetime.fromisoformat(iso)
    return f"{dt.day} {THAI_MONTHS[dt.month - 1]} {dt.year + 543} เวลา {dt:%H:%M} น."

def fmt_booking(r):
    d = dict(r)
    d["start_th"] = thai_date(r["start_date"])
    d["end_th"] = thai_date(r["end_date"])
    d["same_day"] = r["start_date"] == r["end_date"]
    d["days"] = (date.fromisoformat(r["end_date"]) - date.fromisoformat(r["start_date"])).days + 1
    d["hours_per_day"] = r["end_hour"] - r["start_hour"]
    d["time_range"] = f"{r['start_hour']:02d}:00 - {r['end_hour']:02d}:00 น."
    d["created_th"] = (datetime.fromisoformat(r["created_at"]).strftime("%d/%m/") +
                       str(datetime.fromisoformat(r["created_at"]).year + 543) +
                       datetime.fromisoformat(r["created_at"]).strftime(" %H:%M น."))
    d["expires_ts"] = int(datetime.fromisoformat(r["expires_at"]).timestamp())
    d["start_full_th"] = f"{d['start_th']} เวลา {r['start_hour']:02d}:00 น."
    d["end_full_th"] = f"{d['end_th']} เวลา {r['end_hour']:02d}:00 น."
    d["slip_transfer_th"] = _th_datetime(r["slip_transfer_at"]) if r["slip_transfer_at"] else ""
    return d
 
 
def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
 
 
def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        uid = session.get("uid")
        if uid and not get_db().execute(
                "SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
            session.clear()          # บัญชีถูกแอดมินลบแล้ว
            uid = None
        if not uid:
            if request.path.startswith("/api/"):
                return jsonify(error="กรุณาเข้าสู่ระบบ"), 401
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper
 
def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            if request.path.startswith("/admin/api/"):
                return jsonify(error="กรุณาเข้าสู่ระบบแอดมิน"), 401
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper
 
@app.context_processor
def inject_globals():
    return dict(user=current_user(), PRICE_PER_HOUR=PRICE_PER_HOUR,
                PRICE_ORANGE_PER_HOUR=PRICE_ORANGE_PER_HOUR,
                PAY_WINDOW_MIN=PAY_WINDOW_MIN)

 
# ----------------------------------------------------------------------------
# บัญชีผู้ใช้
# ----------------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        pw = request.form.get("password", "")
        pw2 = request.form.get("password2", "")
 
        errors = []
        if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
            errors.append("ชื่อผู้ใช้ต้องเป็นภาษาอังกฤษ/ตัวเลข/_ ยาว 3-30 ตัวอักษร")
        if not full_name:
            errors.append("กรุณากรอกชื่อ-นามสกุล")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errors.append("รูปแบบอีเมลไม่ถูกต้อง")
        if phone and not re.fullmatch(r"[0-9\-\s+]{8,15}", phone):
            errors.append("รูปแบบเบอร์โทรไม่ถูกต้อง")
        if len(pw) < 6:
            errors.append("รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
        if pw != pw2:
            errors.append("รหัสผ่านทั้งสองช่องไม่ตรงกัน")
 
        db = get_db()
        if not errors:
            if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                errors.append("ชื่อผู้ใช้นี้ถูกใช้แล้ว")
            if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                errors.append("อีเมลนี้ถูกใช้แล้ว")
                
                
                  
 
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html", form=request.form)
 
        cur = db.execute(
            "INSERT INTO users (username,email,full_name,phone,password_hash,created_at) VALUES (?,?,?,?,?,?)",
            (username, email, full_name, phone, generate_password_hash(pw), now().isoformat()),
        )
        db.commit()
        session.clear()
        session["uid"] = cur.lastrowid
        session.permanent = True
        flash("สร้างบัญชีสำเร็จ ยินดีต้อนรับ!", "ok")
        return redirect(url_for("index"))
    return render_template("register.html", form={})
 
 
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ident = request.form.get("ident", "").strip()
        pw = request.form.get("password", "")
        row = get_db().execute(
            "SELECT * FROM users WHERE username=? OR email=?", (ident, ident.lower())
        ).fetchone()
        if row and check_password_hash(row["password_hash"], pw):
            session.clear()
            session["uid"] = row["id"]
            session.permanent = True
            return redirect(url_for("index"))
        flash("ชื่อผู้ใช้/อีเมล หรือรหัสผ่านไม่ถูกต้อง", "error")
    return render_template("login.html")
 
 
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
# ---------------------------------------------------------
# ระบบเข้าสู่ระบบแอดมิน
# ---------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
 
        db = get_db()
        admin = db.execute(
            "SELECT * FROM admins WHERE username = ?",
            (username,)
        ).fetchone()
 
        if admin and check_password_hash(
            admin["password_hash"], password
        ):
            session.clear()
            session["admin_id"] = admin["id"]
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
 
        flash("ชื่อผู้ใช้หรือรหัสผ่านแอดมินไม่ถูกต้อง", "error")
 
    return render_template("admin_login.html")
#-----------------------------------------------------------
# admin logout
#-----------------------------------------------------------
@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))
# ---------------------------------------------------------
# Dashboard แอดมิน
# ---------------------------------------------------------
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    db = get_db()
 
    bookings = db.execute("""
        SELECT
            bookings.*,
            COALESCE(users.username, '-') AS username,
            COALESCE(users.full_name, '(บัญชีถูกลบ)') AS full_name,
            COALESCE(users.email, '-') AS email,
            users.phone AS phone
        FROM bookings
        LEFT JOIN users ON users.id = bookings.user_id
        ORDER BY bookings.id DESC
    """).fetchall()
 
    rows = []
    for r in bookings:
        d = dict(r)
        d["slip_transfer_th"] = _th_datetime(d["slip_transfer_at"]) if d.get("slip_transfer_at") else ""
        rows.append(d)
    return render_template("admin_dashboard.html", bookings=rows
    )
    
# ---------------------------------------------------------
# แอดมินอนุมัติคำขอจอง
# ---------------------------------------------------------
@app.route("/admin/bookings/<int:bid>/approve", methods=["POST"])
@admin_required
def admin_approve_booking(bid):
    db = get_db()
 
    booking = db.execute(
        "SELECT * FROM bookings WHERE id = ?",
        (bid,)
    ).fetchone()
 
    if not booking:
        abort(404)
 
    if booking["status"] != "review":
        flash("คำขอนี้ไม่อยู่ในสถานะรออนุมัติ", "error")
        return redirect(url_for("admin_dashboard"))
 
    # ตรวจสอบว่ามีการจองที่ชนกันหรือไม่
    conflicts = _active_conflicts(
        db,
        booking["room"],
        booking["start_date"],
        booking["end_date"],
        booking["start_hour"],
        booking["end_hour"]
    )
 
    # ตัดรายการของตัวเองออกจากผลตรวจสอบ
    conflicts = [
        row for row in conflicts
        if row["id"] != bid
    ]
 
    if conflicts:
        flash("ช่วงเวลานี้มีการจองอื่นแล้ว ไม่สามารถอนุมัติได้", "error")
        return redirect(url_for("admin_dashboard"))
 
    expires_at = (
        now() + timedelta(minutes=PAY_WINDOW_MIN)
    ).isoformat()
 
    db.execute("""
        UPDATE bookings
        SET status = 'pending',
            expires_at = ?,
            decision_note = NULL
        WHERE id = ?
    """, (expires_at, bid))
 
    db.commit()
 
    flash("อนุมัติคำขอจองแล้ว", "ok")
    return redirect(url_for("admin_dashboard"))
 
 
# ---------------------------------------------------------
# แอดมินปฏิเสธคำขอจอง
# ---------------------------------------------------------
@app.route("/admin/bookings/<int:bid>/reject", methods=["POST"])
@admin_required
def admin_reject_booking(bid):
    db = get_db()
 
    booking = db.execute(
        "SELECT * FROM bookings WHERE id = ?",
        (bid,)
    ).fetchone()
 
    if not booking:
        abort(404)
 
    if booking["status"] != "review":
        flash("คำขอนี้ไม่อยู่ในสถานะรออนุมัติ", "error")
        return redirect(url_for("admin_dashboard"))
 
    note = request.form.get("decision_note", "").strip()
 
    db.execute("""
        UPDATE bookings
        SET status = 'rejected',
            decision_note = ?
        WHERE id = ?
    """, (note or "แอดมินปฏิเสธคำขอ", bid))
 
    db.commit()
 
    flash("ปฏิเสธคำขอจองแล้ว", "ok")
    return redirect(url_for("admin_dashboard"))
# ---------------------------------------------------------
# ผู้ใช้ส่งคำขอยกเลิกการจอง
# ---------------------------------------------------------
@app.route(
    "/booking/<int:bid>/cancel-request",
    methods=["POST"]
)
@login_required
def request_booking_cancel(bid):
    db = get_db()
 
    booking = db.execute("""
        SELECT * FROM bookings
        WHERE id = ? AND user_id = ?
    """, (bid, session["uid"])).fetchone()
 
    if not booking:
        abort(404)
 
    if booking["status"] not in ("pending", "verify", "paid"):
        flash("รายการนี้ไม่สามารถขอยกเลิกได้", "error")
        return redirect(url_for("history"))
 
    if booking["cancel_requested_at"]:
        flash("คุณส่งคำขอยกเลิกรายการนี้ไปแล้ว", "error")
        return redirect(url_for("history"))
 
    db.execute("""
        UPDATE bookings
        SET cancel_requested_at = ?
        WHERE id = ?
    """, (now().isoformat(), bid))
 
    db.commit()
 
    flash("ส่งคำขอยกเลิกแล้ว กรุณารอแอดมินอนุมัติ", "ok")
    return redirect(url_for("history"))
 
 
# ---------------------------------------------------------
# แอดมินอนุมัติคำขอยกเลิกเท่านั้น
# ไม่มี route สำหรับปฏิเสธคำขอยกเลิก
# ---------------------------------------------------------
@app.route(
    "/admin/bookings/<int:bid>/cancel-approve",
    methods=["POST"]
)
@admin_required
def admin_approve_cancel(bid):
    db = get_db()
 
    booking = db.execute(
        "SELECT * FROM bookings WHERE id = ?",
        (bid,)
    ).fetchone()
 
    if not booking:
        abort(404)
 
    if not booking["cancel_requested_at"]:
        flash("รายการนี้ไม่มีคำขอยกเลิก", "error")
        return redirect(url_for("admin_dashboard"))
 
    if booking["status"] not in ("pending", "verify", "paid"):
        flash("สถานะรายการนี้ไม่สามารถยกเลิกได้", "error")
        return redirect(url_for("admin_dashboard"))
 
    db.execute("""
        UPDATE bookings
        SET status = 'cancelled',
            decision_note = 'แอดมินอนุมัติคำขอยกเลิก'
        WHERE id = ?
    """, (bid,))
 
    db.commit()
 
    flash("อนุมัติคำขอยกเลิกแล้ว", "ok")
    return redirect(url_for("admin_dashboard"))
 
# ----------------------------------------------------------------------------
# หน้าเว็บหลัก
# ----------------------------------------------------------------------------
@app.route("/")
def landing():
    if session.get("uid"):
        return redirect(url_for("index"))
 
    return render_template("landing.html")
 
 
# หน้าแผนผังอาคารสำหรับจองห้อง
@app.route("/rooms")
@login_required
def index():
    return render_template(
        "index.html",
        floors=FLOORS,
        open_hour=OPEN_HOUR,
        close_hour=CLOSE_HOUR
    )
 
 
@app.route("/history")
@login_required
def history():
    expire_old()
    rows = get_db().execute(
        "SELECT * FROM bookings WHERE user_id=? ORDER BY id DESC", (session["uid"],)
    ).fetchall()
    return render_template("history.html", bookings=[fmt_booking(r) for r in rows])
 
 
@app.route("/booking/<int:bid>")
@login_required
def booking_slip(bid):
    expire_old()
    row = get_db().execute(
        "SELECT * FROM bookings WHERE id=? AND user_id=?", (bid, session["uid"])
    ).fetchone()
    if not row:
        abort(404)
    return render_template("slip_page.html", b=fmt_booking(row))
 
 
# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------
def _active_conflicts(db, room, s_date, e_date, s_hour, e_hour):
    return db.execute(
        """
        SELECT * FROM bookings
        WHERE room = ?
          AND (
              status IN ('review', 'verify', 'paid')
              OR (
                  status = 'pending'
                  AND expires_at > ?
              )
          )
          AND start_date <= ?
          AND end_date >= ?
          AND start_hour < ?
          AND end_hour > ?
        """,
        (
            room,
            now().isoformat(),
            e_date,
            s_date,
            e_hour,
            s_hour
        ),
    ).fetchall()
 
 
@app.route("/api/rooms/<room>/bookings")
@login_required
def api_room_bookings(room):
    if room not in ROOM_FLOOR:
        abort(404)
    expire_old()
    return jsonify(_room_schedule(get_db(), room))
 
 
@app.route("/api/bookings", methods=["POST"])
@login_required
def api_create_booking():
    data = request.get_json(silent=True) or {}
    room = str(data.get("room", ""))
    if room not in ROOM_FLOOR:
        return jsonify(error="ห้องนี้ไม่สามารถจองได้"), 400
    try:
        s_date = date.fromisoformat(str(data.get("start_date")))
        e_date = date.fromisoformat(str(data.get("end_date")))
        s_hour = int(data.get("start_hour"))
        e_hour = int(data.get("end_hour"))
    except (TypeError, ValueError):
        return jsonify(error="ข้อมูลวันที่/เวลาไม่ถูกต้อง"), 400
 
    n = now()
    if e_date < s_date:
        return jsonify(error="วันสิ้นสุดต้องไม่ก่อนวันเริ่ม"), 400
    if (e_date - s_date).days + 1 > MAX_DAYS:
        return jsonify(error=f"จองต่อเนื่องได้สูงสุด {MAX_DAYS} วัน"), 400
    if not (OPEN_HOUR <= s_hour < e_hour <= CLOSE_HOUR):
        return jsonify(error=f"เวลาจองต้องอยู่ระหว่าง {OPEN_HOUR:02d}:00-{CLOSE_HOUR:02d}:00 และเวลาสิ้นสุดต้องหลังเวลาเริ่ม"), 400
    if datetime(s_date.year, s_date.month, s_date.day, s_hour, tzinfo=TZ) <= n:
        return jsonify(error="ไม่สามารถจองย้อนหลังได้"), 400
 
    db = get_db()
    expire_old()
    if _active_conflicts(db, room, s_date.isoformat(), e_date.isoformat(), s_hour, e_hour):
        return jsonify(error="ช่วงเวลานี้มีผู้จองห้องแล้ว กรุณาเลือกช่วงเวลาอื่น"), 409
    if _block_conflicts(db, room, s_date.isoformat(), e_date.isoformat(), s_hour, e_hour):
        return jsonify(error="ห้องนี้ปิดให้บริการในช่วงเวลาดังกล่าว กรุณาเลือกช่วงเวลาอื่น"), 409
 
    days = (e_date - s_date).days + 1
    hours = days * (e_hour - s_hour)
    amount = hours * price_for(room)
    code = f"BK{n:%y%m%d}-{secrets.token_hex(2).upper()}"
    cur = db.execute(
        """INSERT INTO bookings
           (code,user_id,room,floor,start_date,end_date,start_hour,end_hour,hours,amount,status,created_at,expires_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,'review',?,?)""",
        (code, session["uid"], room, ROOM_FLOOR[room], s_date.isoformat(), e_date.isoformat(),
         s_hour, e_hour, hours, amount, n.isoformat(),
         (n + timedelta(minutes=PAY_WINDOW_MIN)).isoformat()),
    )
    db.commit()
    return jsonify(id=cur.lastrowid, url=url_for("booking_slip", bid=cur.lastrowid)), 201
 
 
@app.route("/api/bookings/<int:bid>/pay", methods=["POST"])
@login_required
# ----------------------------------------------------------------------------
# อัปโหลดสลิป -> สถานะ verify (รอแอดมินตรวจ)
# ----------------------------------------------------------------------------
def _sniff_image(head):
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None

def _remove_slip_file(filename):
    """ลบไฟล์สลิปออกจากดิสก์ (ไม่ error ถ้าไม่มีไฟล์)"""
    if not filename:
        return
    try:
        os.remove(os.path.join(UPLOAD_DIR, os.path.basename(filename)))
    except OSError:
        pass
    
@app.route("/api/bookings/<int:bid>/slip", methods=["POST"])
@login_required
def api_upload_slip(bid):
    expire_old()
    db = get_db()
    row = db.execute("SELECT * FROM bookings WHERE id=? AND user_id=?",
                     (bid, session["uid"])).fetchone()
    if not row:
        abort(404)
    if row["status"] == "expired":
        return jsonify(error="หมดเวลาชำระเงินแล้ว กรุณาจองใหม่"), 410
    if row["status"] != "pending":
        return jsonify(error="รายการนี้ไม่อยู่ในสถานะรอชำระเงิน"), 409
    if row["cancel_requested_at"]:
        return jsonify(error="คุณส่งคำขอยกเลิกรายการนี้แล้ว ไม่สามารถแนบสลิปได้"), 409

    f = request.files.get("slip")
    if not f or not f.filename:
        return jsonify(error="กรุณาแนบรูปสลิป"), 400
    ext = _sniff_image(f.stream.read(16))
    f.stream.seek(0)
    if not ext:
        return jsonify(error="รองรับเฉพาะไฟล์ภาพ JPG / PNG / WEBP"), 400

    try:
        transfer = datetime.fromisoformat(
            f"{request.form.get('transfer_date', '')}T{request.form.get('transfer_time', '')}"
        ).replace(tzinfo=TZ)
    except ValueError:
        return jsonify(error="กรุณากรอกวัน-เวลาที่โอนให้ถูกต้อง"), 400
    if transfer > now() + timedelta(minutes=5):
        return jsonify(error="วัน-เวลาที่โอนต้องไม่เป็นอนาคต"), 400
    if transfer < datetime.fromisoformat(row["created_at"]) - timedelta(minutes=5):
        return jsonify(error="วัน-เวลาที่โอนต้องไม่ก่อนเวลาที่ทำการจอง"), 400

    filename = f"{row['code']}_{secrets.token_hex(6)}.{ext}"
    f.save(os.path.join(UPLOAD_DIR, filename))

    db.execute(
        """UPDATE bookings
           SET status='verify', slip_image=?, slip_transfer_at=?, slip_uploaded_at=?,
               decision_note=NULL
           WHERE id=?""",
        (filename, transfer.isoformat(), now().isoformat(), bid),
    )
    db.commit()
    return jsonify(ok=True)


@app.route("/slip-image/<int:bid>")
def slip_image(bid):
    row = get_db().execute(
        "SELECT user_id, slip_image FROM bookings WHERE id=?", (bid,)).fetchone()
    if not row or not row["slip_image"]:
        abort(404)
    if not (session.get("is_admin") or session.get("uid") == row["user_id"]):
        abort(403)
    return send_from_directory(UPLOAD_DIR, row["slip_image"])


# ---------------------------------------------------------
# แอดมินตรวจสลิป
# ---------------------------------------------------------
@app.route("/admin/bookings/<int:bid>/slip-approve", methods=["POST"])
@admin_required
def admin_approve_slip(bid):
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
    if not b:
        abort(404)
    if b["status"] != "verify":
        flash("รายการนี้ไม่ได้อยู่ในสถานะรอตรวจสลิป", "error")
        return redirect(url_for("admin_dashboard"))
    db.execute("UPDATE bookings SET status='paid', paid_at=?, decision_note=NULL WHERE id=?",
               (now().isoformat(), bid))
    db.commit()
    flash("ยืนยันสลิปเรียบร้อย การจองเป็นสถานะชำระแล้ว", "ok")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/bookings/<int:bid>/slip-reject", methods=["POST"])
@admin_required
def admin_reject_slip(bid):
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
    if not b:
        abort(404)
    if b["status"] != "verify":
        flash("รายการนี้ไม่ได้อยู่ในสถานะรอตรวจสลิป", "error")
        return redirect(url_for("admin_dashboard"))
    note = request.form.get("decision_note", "").strip() or "สลิปไม่ถูกต้อง กรุณาแนบสลิปใหม่"
    db.execute(
        """UPDATE bookings
           SET status='pending', expires_at=?, decision_note=?,
               slip_image=NULL, slip_transfer_at=NULL, slip_uploaded_at=NULL
           WHERE id=?""",
        ((now() + timedelta(minutes=PAY_WINDOW_MIN)).isoformat(), note, bid),
    )
    db.commit()
    _remove_slip_file(b["slip_image"])
    flash("ส่งกลับให้ผู้ใช้แนบสลิปใหม่แล้ว (ให้เวลาชำระใหม่)", "ok")
    return redirect(url_for("admin_dashboard"))
 
# ----------------------------------------------------------------------------
# ตารางเวลาห้อง (การจอง + ช่วงที่แอดมินปิดห้อง)
# ----------------------------------------------------------------------------
def _room_schedule(db, room):
    today = now().date().isoformat()
    out = []
    for r in db.execute(
        """SELECT start_date,end_date,start_hour,end_hour,status FROM bookings
           WHERE room=? AND status IN ('review', 'verify', 'paid', 'pending') AND end_date >= ?""",
        (room, today),
    ).fetchall():
        d = dict(r)
        d["kind"] = "booking"
        out.append(d)
    for r in db.execute(
        """SELECT id,start_date,end_date,start_hour,end_hour,reason FROM room_blocks
           WHERE room=? AND end_date >= ?""",
        (room, today),
    ).fetchall():
        d = dict(r)
        d["kind"] = "block"
        d["status"] = "closed"
        out.append(d)
    out.sort(key=lambda x: (x["start_date"], x["start_hour"]))
    return out
 
 
def _block_conflicts(db, room, s_date, e_date, s_hour, e_hour):
    return db.execute(
        """SELECT * FROM room_blocks
           WHERE room = ? AND start_date <= ? AND end_date >= ?
             AND start_hour < ? AND end_hour > ?""",
        (room, e_date, s_date, e_hour, s_hour),
    ).fetchall()
 
 
# ----------------------------------------------------------------------------
# แอดมิน : จัดการห้อง (ปิด/เปิดการจองตามวัน-เวลา)
# ----------------------------------------------------------------------------
@app.route("/admin/rooms")
@admin_required
def admin_rooms():
    return render_template("admin_rooms.html", floors=FLOORS,
                           open_hour=OPEN_HOUR, close_hour=CLOSE_HOUR)
 
 
@app.route("/admin/api/rooms/<room>/schedule")
@admin_required
def admin_api_room_schedule(room):
    if room not in ROOM_FLOOR:
        abort(404)
    expire_old()
    return jsonify(_room_schedule(get_db(), room))
 
 
@app.route("/admin/api/blocks", methods=["POST"])
@admin_required
def admin_api_create_block():
    data = request.get_json(silent=True) or {}
    room = str(data.get("room", ""))
    if room not in ROOM_FLOOR:
        return jsonify(error="ไม่พบห้องนี้"), 400
    try:
        s_date = date.fromisoformat(str(data.get("start_date")))
        e_date = date.fromisoformat(str(data.get("end_date")))
        s_hour = int(data.get("start_hour"))
        e_hour = int(data.get("end_hour"))
    except (TypeError, ValueError):
        return jsonify(error="ข้อมูลวันที่/เวลาไม่ถูกต้อง"), 400
    reason = str(data.get("reason", "")).strip()[:200]
 
    if e_date < s_date:
        return jsonify(error="วันสิ้นสุดต้องไม่ก่อนวันเริ่ม"), 400
    if s_date < now().date():
        return jsonify(error="ไม่สามารถกำหนดย้อนหลังได้"), 400
    if (e_date - s_date).days + 1 > MAX_BLOCK_DAYS:
        return jsonify(error=f"ปิดห้องต่อเนื่องได้สูงสุด {MAX_BLOCK_DAYS} วัน"), 400
    if not (OPEN_HOUR <= s_hour < e_hour <= CLOSE_HOUR):
        return jsonify(error=f"เวลาต้องอยู่ระหว่าง {OPEN_HOUR:02d}:00-{CLOSE_HOUR:02d}:00 และเวลาสิ้นสุดต้องหลังเวลาเริ่ม"), 400
 
    db = get_db()
    expire_old()
    if _active_conflicts(db, room, s_date.isoformat(), e_date.isoformat(), s_hour, e_hour):
        return jsonify(error="ช่วงเวลานี้มีการจอง/รออนุมัติอยู่แล้ว กรุณาปฏิเสธหรือยกเลิกรายการจองนั้นก่อน"), 409
    if _block_conflicts(db, room, s_date.isoformat(), e_date.isoformat(), s_hour, e_hour):
        return jsonify(error="ช่วงเวลานี้ถูกปิดห้องไว้แล้ว"), 409
 
    cur = db.execute(
        """INSERT INTO room_blocks
           (room,floor,start_date,end_date,start_hour,end_hour,reason,created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (room, ROOM_FLOOR[room], s_date.isoformat(), e_date.isoformat(),
         s_hour, e_hour, reason or None, now().isoformat()),
    )
    db.commit()
    return jsonify(id=cur.lastrowid), 201
 
 
@app.route("/admin/api/blocks/<int:bid>", methods=["DELETE"])
@admin_required
def admin_api_delete_block(bid):
    db = get_db()
    cur = db.execute("DELETE FROM room_blocks WHERE id=?", (bid,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="ไม่พบรายการนี้"), 404
    return jsonify(ok=True)
 
 
# ----------------------------------------------------------------------------
# แอดมิน : จัดการบัญชีผู้ใช้
# ----------------------------------------------------------------------------
@app.route("/admin/users")
@admin_required
def admin_users():
    rows = get_db().execute(
        """
        SELECT u.*,
               COUNT(b.id) AS total_bookings,
               COALESCE(SUM(CASE WHEN b.status IN ('review','verify','pending','paid')
                                 THEN 1 ELSE 0 END), 0) AS active_bookings
        FROM users u
        LEFT JOIN bookings b ON b.user_id = u.id
        GROUP BY u.id
        ORDER BY u.id DESC
        """
    ).fetchall()
    return render_template("admin_users.html", users=rows)
 
 
@app.route("/admin/users/<int:uid>/delete", methods=["POST"])
@admin_required
def admin_delete_user(uid):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        abort(404)
    if request.form.get("confirm_username", "").strip() != u["username"]:
        flash("ชื่อผู้ใช้ที่พิมพ์ยืนยันไม่ตรง ยังไม่ได้ลบบัญชี", "error")
        return redirect(url_for("admin_users"))
    # ยกเลิกการจองที่ยังใช้งานอยู่ เพื่อปล่อยห้องว่าง (เก็บประวัติรายการไว้)
    db.execute(
        """UPDATE bookings
           SET status='cancelled', decision_note='บัญชีผู้ใช้ถูกลบโดยแอดมิน'
           WHERE user_id=? AND status IN ('review','verify','pending','paid')""",
        (uid,),
    )
    db.execute("DELETE FROM password_otps WHERE user_id=?", (uid,))
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    flash(f"ลบบัญชี {u['username']} เรียบร้อยแล้ว", "ok")
    return redirect(url_for("admin_users"))
 
 
# ----------------------------------------------------------------------------
# ลืมรหัสผ่าน : (ก) ยืนยันด้วยรหัสผ่านเดิม  หรือ  (ข) ยืนยันด้วย OTP ทางอีเมล
# ----------------------------------------------------------------------------
def _mask_email(email):
    local, _, domain = email.partition("@")
    return (local[:2] if len(local) > 2 else local[:1]) + "***@" + domain
 
 
def _otp_hash(uid, otp):
    key = app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"{uid}:{otp}".encode(), hashlib.sha256).hexdigest()
 
 
def _send_otp_email(to_addr, otp):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pw:
        if os.environ.get("OTP_DEV_PRINT") == "1":
            print(f"[DEV] OTP สำหรับ {to_addr}: {otp}", flush=True)
            return True
        app.logger.error("ยังไม่ได้ตั้งค่า GMAIL_USER / GMAIL_APP_PASSWORD")
        return False
    msg = EmailMessage()
    msg["Subject"] = "รหัส OTP ตั้งรหัสผ่านใหม่ - ระบบจองห้อง คณะศึกษาศาสตร์"
    msg["From"] = gmail_user
    msg["To"] = to_addr
    msg.set_content(
        f"รหัส OTP ของคุณคือ {otp}\n\n"
        f"รหัสนี้ใช้ได้ภายใน {OTP_TTL_MIN} นาที และใช้ได้ครั้งเดียว\n"
        "หากคุณไม่ได้เป็นผู้ขอ กรุณาไม่ต้องดำเนินการใด ๆ และห้ามบอกรหัสนี้กับผู้อื่น"
    )
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465,
                              context=ssl.create_default_context(), timeout=15) as s:
            s.login(gmail_user, gmail_pw)
            s.send_message(msg)
        return True
    except Exception:
        app.logger.exception("ส่งอีเมล OTP ไม่สำเร็จ")
        return False
 
 
def _fp_user():
    uid = session.get("fp_uid")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
 
 
def _new_pw_errors(pw, pw2):
    errors = []
    if len(pw) < 6:
        errors.append("รหัสผ่านใหม่ต้องมีอย่างน้อย 6 ตัวอักษร")
    if pw != pw2:
        errors.append("รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน")
    return errors
 
 
def _finish_reset(db, u, new_pw):
    db.execute("UPDATE users SET password_hash=? WHERE id=?",
               (generate_password_hash(new_pw), u["id"]))
    db.execute("DELETE FROM password_otps WHERE user_id=?", (u["id"],))
    db.commit()
    session.pop("fp_uid", None)
    session.pop("fp_otp_sent", None)
    flash("ตั้งรหัสผ่านใหม่สำเร็จ กรุณาเข้าสู่ระบบด้วยรหัสผ่านใหม่", "ok")
    return redirect(url_for("login"))
 
 
@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        ident = request.form.get("ident", "").strip()
        row = get_db().execute(
            "SELECT * FROM users WHERE username=? OR email=?", (ident, ident.lower())
        ).fetchone()
        if not row:
            flash("ไม่พบบัญชีนี้ในระบบ", "error")
            return render_template("forgot.html", target=None, masked="", otp_sent=False)
        session["fp_uid"] = row["id"]
        session.pop("fp_otp_sent", None)
        return redirect(url_for("forgot"))
 
    if request.args.get("reset"):
        session.pop("fp_uid", None)
        session.pop("fp_otp_sent", None)
        return redirect(url_for("forgot"))
 
    u = _fp_user()
    return render_template(
        "forgot.html", target=u,
        masked=_mask_email(u["email"]) if u else "",
        otp_sent=bool(u and session.get("fp_otp_sent")),
    )
 
 
@app.route("/forgot/old", methods=["POST"])
def forgot_with_old():
    u = _fp_user()
    if not u:
        return redirect(url_for("forgot"))
    old = request.form.get("old_password", "")
    pw = request.form.get("password", "")
    pw2 = request.form.get("password2", "")
 
    errors = []
    if not check_password_hash(u["password_hash"], old):
        errors.append("รหัสผ่านเดิมไม่ถูกต้อง")
    errors += _new_pw_errors(pw, pw2)
    if not errors and pw == old:
        errors.append("รหัสผ่านใหม่ต้องไม่เหมือนรหัสผ่านเดิม")
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("forgot"))
    return _finish_reset(get_db(), u, pw)
 
 
@app.route("/forgot/send-otp", methods=["POST"])
def forgot_send_otp():
    u = _fp_user()
    if not u:
        return redirect(url_for("forgot"))
    db = get_db()
    last = db.execute(
        "SELECT created_at FROM password_otps WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (u["id"],),
    ).fetchone()
    if last:
        wait = OTP_RESEND_SEC - (now() - datetime.fromisoformat(last["created_at"])).total_seconds()
        if wait > 0:
            flash(f"กรุณารออีก {int(wait) + 1} วินาที ก่อนขอ OTP ใหม่", "error")
            return redirect(url_for("forgot"))
 
    otp = f"{secrets.randbelow(10**6):06d}"
    n = now()
    db.execute("DELETE FROM password_otps WHERE user_id=?", (u["id"],))
    cur = db.execute(
        "INSERT INTO password_otps (user_id,otp_hash,expires_at,attempts,created_at) VALUES (?,?,?,0,?)",
        (u["id"], _otp_hash(u["id"], otp),
         (n + timedelta(minutes=OTP_TTL_MIN)).isoformat(), n.isoformat()),
    )
    db.commit()
 
    if _send_otp_email(u["email"], otp):
        session["fp_otp_sent"] = True
        flash(f"ส่งรหัส OTP ไปที่ {_mask_email(u['email'])} แล้ว (ใช้ได้ {OTP_TTL_MIN} นาที)", "ok")
    else:
        db.execute("DELETE FROM password_otps WHERE id=?", (cur.lastrowid,))
        db.commit()
        flash("ส่งอีเมลไม่สำเร็จ กรุณาลองใหม่ภายหลัง หรือติดต่อผู้ดูแลระบบ", "error")
    return redirect(url_for("forgot"))
 
 
@app.route("/forgot/otp", methods=["POST"])
def forgot_with_otp():
    u = _fp_user()
    if not u:
        return redirect(url_for("forgot"))
    otp = re.sub(r"\D", "", request.form.get("otp", ""))
    pw = request.form.get("password", "")
    pw2 = request.form.get("password2", "")
 
    errors = _new_pw_errors(pw, pw2)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("forgot"))
 
    db = get_db()
    row = db.execute(
        "SELECT * FROM password_otps WHERE user_id=? ORDER BY id DESC LIMIT 1", (u["id"],)
    ).fetchone()
    if (not row) or row["expires_at"] <= now().isoformat():
        flash("OTP หมดอายุหรือยังไม่ได้ขอ กรุณากดส่ง OTP ใหม่", "error")
        return redirect(url_for("forgot"))
    if row["attempts"] >= OTP_MAX_ATTEMPTS:
        db.execute("DELETE FROM password_otps WHERE id=?", (row["id"],))
        db.commit()
        flash("กรอก OTP ผิดเกินจำนวนครั้งที่กำหนด กรุณาขอ OTP ใหม่", "error")
        return redirect(url_for("forgot"))
    if not hmac.compare_digest(row["otp_hash"], _otp_hash(u["id"], otp)):
        db.execute("UPDATE password_otps SET attempts = attempts + 1 WHERE id=?", (row["id"],))
        db.commit()
        left = OTP_MAX_ATTEMPTS - row["attempts"] - 1
        flash(f"รหัส OTP ไม่ถูกต้อง (เหลืออีก {left} ครั้ง)", "error")
        return redirect(url_for("forgot"))
    return _finish_reset(db, u, pw)
 
 
init_db()
if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")