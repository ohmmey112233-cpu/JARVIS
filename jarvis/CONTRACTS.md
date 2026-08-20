# สัญญาระหว่างโมดูล — อ่านก่อนเขียนโค้ดทุกไฟล์

## หลักการสถาปัตยกรรม (สำคัญที่สุด)

`jarvis/core/` = **โค้ดแกนที่ไม่ผูกกับ framework ใดๆ** — เป็น Python ล้วน
พึ่งพาแค่ stdlib + sqlite3 **ห้าม import อะไรที่เกี่ยวกับ Hermes เข้ามาในนี้เด็ดขาด**

เหตุผล: spec v3 เขียนไว้ว่า *"งาน Phase 1-5 เหมือนกันทั้งสอง track ต่างแค่ฐาน"*
ถ้า gate trial ไม่ผ่าน → Track B (สร้างเอง) โค้ดใน `core/` ต้องใช้ต่อได้ทันทีโดยไม่แก้
ตัวเชื่อมกับ Hermes อยู่ใน `skills/` เท่านั้น เป็นชั้นบางๆ ที่เรียก `core/`

## กฎเหล็ก 3 ข้อ (ผิดข้อไหน = ตีกลับ)

1. **เวลา** — ห้ามเรียก `datetime.now()`, `date.today()`, `DATE('now')` ที่ไหนทั้งสิ้น
   ใช้ `core.localdate` เท่านั้น ทุกฟังก์ชันที่เกี่ยวกับเวลาต้องรับพารามิเตอร์
   `clock: datetime | None = None` ตัวสุดท้าย เพื่อให้เทสต์ฉีดเวลาเข้าไปได้
2. **ห้ามเรียก LLM ในโค้ดแกน** — `core/` ต้องเป็น deterministic ล้วน
   เทสต์ต้องรันได้โดยไม่ต้องมี API key
3. **ลบต้องกู้คืนได้** — ทุกการลบย้ายเข้า trash ก่อน ไม่ลบจริงทันที

## ไฟล์ที่มีแล้ว (ห้ามแก้ ให้ใช้อย่างเดียว)

### `core/localdate.py`
```python
TZ = ZoneInfo("Asia/Bangkok")
THAI_DAYS       # ['จันทร์','อังคาร','พุธ','พฤหัสบดี','ศุกร์','เสาร์','อาทิตย์'] index = weekday()
THAI_DAYS_SHORT # ['จ.','อ.','พ.','พฤ.','ศ.','ส.','อา.']
MONDAY..SUNDAY = 0..6

now(clock=None) -> datetime            # aware, Asia/Bangkok
local_date(clock=None) -> date
local_date_key(clock=None) -> str      # 'YYYY-MM-DD'
to_date(str|date|datetime) -> date
days_between(start, end) -> int        # end - start
thai_day_name(value, short=False) -> str
thai_date_short(value) -> str          # '24 ส.ค.'
is_weekday(value) -> bool
next_weekday(value, weekday, *, allow_same_day=False) -> date
friday_of_week(value) -> date          # ศุกร์ของสัปดาห์นั้น (สัปดาห์เริ่มจันทร์)
days_until_month_end(value=None) -> int
```

### `schema/001_init.sql`
ตาราง: `routines`, `preferences`, `class_schedule`, `lessons`, `lessons_trash`,
`bookings`, `call_logs`, `notifications_sent`, `audit_log`, `favorite_places`, `schema_version`
อ่านไฟล์จริงก่อนเขียนโค้ดที่แตะ DB — คอมเมนต์ในไฟล์บอกที่มาของทุกตาราง

## สัญญาของ `core/db.py` (โมดูลอื่นเรียกใช้ตัวนี้)

```python
def connect(path: str | Path | None = None) -> sqlite3.Connection
    """เปิด DB + เปิด foreign_keys + row_factory = sqlite3.Row
    path=None → อ่านจาก env JARVIS_DB หรือ ~/.jarvis/jarvis.db"""

def migrate(conn: sqlite3.Connection) -> int
    """รัน schema ที่ยังไม่ได้รัน คืน version ปัจจุบัน — idempotent"""

def get_pref(conn, key: str, default: str | None = None) -> str | None
def set_pref(conn, key: str, value: str, notes: str | None = None) -> None
def require_pref(conn, key: str) -> str
    """ไม่มีค่า หรือค่าเป็น placeholder ('[ต้องกรอก]' / '') → ยก MissingPreference
    ห้ามคืนค่า default เงียบๆ เพราะ friday_anchor_date ที่ผิด = ระบบสลับด้านทั้งหมด"""

class MissingPreference(RuntimeError): ...
```

## รูปแบบข้อความ (สำหรับ digest.py)

ยึด `jarvis-phase1-kit.md` ส่วนที่ 1 **เป๊ะทุกตัวอักษร** — เว้นวรรค อีโมจิ การขึ้นบรรทัด
หลักการ 6 ข้อจาก kit ส่วนท้าย:
1. ข้อความเดียวจบ  2. ไม่เกิน 1 หน้าจอมือถือ  3. สิ่งที่ต่างจากปกติขึ้นก่อน
4. ไม่มีอะไรเปลี่ยนก็บอกบรรทัดเดียว  5. อีโมจิเป็นหัวข้อไม่ใช่ประดับ
6. ตัวเลขต้องแปลงเป็นการตัดสินใจ ("ออก 07:10 ดีกว่า" ไม่ใช่ "รถติด 15 นาที")

## ข้อห้ามจากบุคลิก (บังคับในโค้ดด้วย ไม่ใช่แค่ prompt)

- ห้ามพิมพ์คำว่า "ล็อค" เกี่ยวกับประตู — เซนเซอร์รู้แค่ปิด/เปิด (red-team H12)
- ห้ามรายงาน "เรียบร้อย" ถ้ายังไม่ยืนยันว่าสำเร็จจริง
- lesson ใหม่ทับของเก่า → ต้องบอกว่าทับอันไหน

## สไตล์โค้ด

- Python 3.11+, `from __future__ import annotations`, type hints ครบ
- คอมเมนต์ภาษาไทย อธิบาย **ทำไม** ไม่ใช่ **อะไร**
- ทุกโมดูลมีเทสต์คู่กันใน `jarvis/tests/test_<ชื่อ>.py` ใช้ `unittest` (stdlib ไม่ต้องลง pytest)
- เทสต์ต้องรันผ่านด้วย `python3 -m unittest discover -s jarvis/tests`

---

# API ของแต่ละโมดูล — กำหนดไว้แล้ว ห้ามเปลี่ยนชื่อ/ลำดับพารามิเตอร์

โมดูลถูกสร้างพร้อมกันแบบขนาน ถ้าใครเปลี่ยน signature เอง ตัวที่เรียกจะพัง
อยาก "ปรับให้ดีกว่า" ให้เพิ่มฟังก์ชันใหม่ ห้ามแก้ของเดิม

## `core/friday.py` — ศุกร์สลับสัปดาห์ (จอมทอง / โรงแรม)

```python
HOME  = "home"     # ศุกร์ที่กลับบ้านจอมทอง
HOTEL = "hotel"    # ศุกร์ที่อยู่เชียงใหม่ (สัปดาห์โรงแรม)

class FridayPlan(NamedTuple):
    friday: date        # วันศุกร์ของสัปดาห์นั้น
    state: str          # HOME | HOTEL
    is_home: bool
    weeks_from_anchor: int   # จำนวนสัปดาห์ห่างจาก anchor (ติดลบได้ถ้าก่อน anchor)

def friday_state(anchor_date, anchor_state: str, when=None) -> FridayPlan
    """สถานะของศุกร์ในสัปดาห์ที่ when อยู่
    สลับทุกสัปดาห์: ห่างจาก anchor เป็นจำนวนสัปดาห์คู่ = state เดียวกับ anchor
    ต้องถูกต้องทั้งก่อนและหลัง anchor (Python % คืนค่าบวกเสมอ ระวัง)"""

def friday_state_from_db(conn, when=None) -> FridayPlan
    """อ่าน friday_anchor_date จาก preferences ผ่าน require_pref()
    รูปแบบค่าที่เก็บ: 'YYYY-MM-DD:home' หรือ 'YYYY-MM-DD:hotel'
    (phase1-kit บอกว่าต้องระบุทั้งวันและสถานะ) — รูปแบบผิด = ValueError"""

def is_in_chiang_mai_on_friday(conn, when=None) -> bool
    """ใช้โดย Sushiro (Phase 4) — red-team H10: จองเฉพาะศุกร์ที่อยู่เชียงใหม่
    เพราะ no-show ซ้ำๆ ทำให้โดนแบนเร็วกว่าเรื่อง ToS"""
```

## `core/routines.py` — งานที่ทำเป็นรอบ

```python
class RoutineStatus(NamedTuple):
    name: str; name_th: str; kind: str      # kind = 'interval' | 'weekday'
    due: bool; days_since: int | None; days_until: int | None
    next_due: date | None; last_done: str | None; notes: str | None

def list_routines(conn, *, active_only: bool = True) -> list[sqlite3.Row]
def status(conn, name: str, when=None) -> RoutineStatus
def due_today(conn, when=None) -> list[RoutineStatus]
    """แบบ interval: days_since >= interval_days → ถึงรอบ
       แบบ weekday : วันนี้ตรงกับ day_of_week → ถึงรอบ
       last_done เป็น NULL (ยังไม่เคยทำ) → ถือว่าถึงรอบ"""
def upcoming(conn, days: int = 7, when=None) -> list[RoutineStatus]
    """ถึงรอบภายใน N วันข้างหน้า เรียงตามวันที่ใกล้สุดก่อน"""
def mark_done(conn, name: str, when=None) -> RoutineStatus
    """"ทำคิ้วแล้ว" → อัปเดต last_done = localDateKey() แล้วคืนสถานะรอบใหม่
    ชื่อ routine ไม่มีจริง → KeyError"""
```

## `core/memory.py` — lessons CRUD (kit ส่วน 5 + red-team H13)

```python
class Lesson(NamedTuple):
    id: int; topic: str; content: str; tags: list[str]
    created_at: str; superseded_by: int | None; archived_at: str | None

def remember(conn, topic, content, tags=(), when=None) -> tuple[Lesson, Lesson | None]
    """"จำไว้ว่า..." → คืน (ข้อใหม่, ข้อเก่าที่ถูกทับ|None)
    ถ้ามี lesson ที่ topic เดียวกันยังไม่ถูกทับอยู่ → ตั้ง superseded_by ให้ของเก่า
    ตัวเรียกต้องเอาข้อเก่าไปบอกโอมว่า 'ทับอันไหน' (บุคลิกข้อ 'การเรียนรู้')"""

def recall(conn, topic_or_tag: str, *, limit: int = 20) -> list[Lesson]
    """"จำอะไรเกี่ยวกับ X ไว้บ้าง" → เฉพาะข้อที่ยังไม่ถูกทับและยังไม่ archived
    ค้นแบบ substring ทั้ง topic และ tags"""

def revise(conn, topic: str, new_content: str, when=None) -> tuple[Lesson, Lesson]
    """"แก้ความจำเรื่อง X เป็น..." → ทับของเก่า คืน (ใหม่, เก่า)
    ไม่มี topic นั้น → KeyError"""

def forget(conn, topic: str, *, confirmed: bool = False, reason=None, when=None)
    """"ลืมเรื่อง X" → confirmed=False จะ **ไม่ลบ** แต่คืนรายการที่จะถูกลบ
    เพื่อให้ตัวเรียกไปถามยืนยันก่อน (kit: 'การลบต้องยืนยันก่อนเสมอ')
    confirmed=True → ย้ายเข้า lessons_trash แล้วค่อยลบจาก lessons
    คืน tuple[bool, list[Lesson]]  (ลบไปแล้วหรือยัง, รายการที่เกี่ยว)"""

def restore(conn, original_id: int) -> Lesson
    """กู้จาก trash กลับมา"""
def list_trash(conn, limit: int = 20) -> list[dict]
def consolidate(conn, *, unused_days: int = 60, when=None) -> dict
    """งานตี 2 — archived เฉพาะข้อที่ถูกทับแล้วและเก่ากว่า unused_days
    ห้ามลบจริง (H13: 'ความจำหายเงียบๆ โดยไม่มีใครตรวจ')
    คืน dict สำหรับเอาไปเขียนรายงาน 'ความฝัน' ตอนเช้า"""
```

## `core/digest.py` — เรนเดอร์ข้อความ (deterministic ล้วน ห้ามเรียก LLM)

```python
@dataclass
class DigestContext:
    """ข้อมูลที่รวบรวมมาแล้วจากภายนอก — โมดูลนี้แค่จัดรูปแบบ ไม่ไปดึงเอง
    ทุก field ที่มาจาก API ภายนอกเป็น Optional เพราะ API ล่มได้
    (checklist E: 'API ล่ม → digest ยังส่งได้ แค่ข้ามหัวข้อนั้น')"""
    when: datetime
    travel_minutes: int | None = None
    leave_by: str | None = None          # 'HH:MM'
    weather_summary: str | None = None   # '28° ไม่มีฝนช่วงเช้า'
    rain_window: str | None = None       # '07:00-08:00'
    aqi: int | None = None
    calendar_items: list[str] = field(default_factory=list)
    due_routines: list = field(default_factory=list)
    upcoming_routines: list = field(default_factory=list)
    friday: object | None = None         # FridayPlan
    first_subject: str | None = None
    period_count: str | None = None
    tomorrow_note: str | None = None

def render_morning(ctx) -> str      # kit §1 เช้าวันจันทร์/พุธ/ศุกร์
def render_evening(ctx, *, done_items, pending_work) -> str
def render_weekly(ctx, *, week_rows, due_next_week) -> str
def render_dream_report(summary: dict) -> str
def aqi_label(aqi: int) -> str      # 'อากาศดี' | 'ปานกลาง' | ...

หัวเรื่องบังคับ (kit ข้อ 5 — อีโมจิเป็นหัวข้อ):
  🚗 การเดินทาง   📌 routine   ⚠️ ผิดปกติ   🌤️/🌧️ อากาศ   💨 ฝุ่น   🏡 กลับบ้าน   🏨 โรงแรม
วันพุธต้องขึ้น ⚠️ บรรทัดแรกเสมอ (ตื่นเร็วกว่าปกติ) — kit ข้อ 3
```

## `core/booking.py` — tool กลาง (spec v3 Phase 3)

```python
class BookingRequest(NamedTuple):
    kind: str; place: str; date: str; time: str | None
    party_size: int | None; fallback_slots: list[str]

def resolve_place(conn, kind: str, place: str | None) -> sqlite3.Row
    """place=None → ดึงร้าน default ของ kind นั้นจาก favorite_places
    ไม่มีร้าน default → LookupError"""

def make_booking(conn, kind, place=None, date=None, time=None,
                 party_size=None, fallback_slots=(), when=None) -> int
    """สร้างแถวใน bookings สถานะ 'pending' คืน booking id
    **ไม่โทรจริง** — Phase 3 ค่อยต่อ Twilio/Vapi เข้ามาทีหลัง
    kind ไม่อยู่ใน 4 แบบ → ValueError"""

def answer_envelope(req: BookingRequest) -> dict
    """'ซองคำตอบล่วงหน้า' — spec Phase 3 ข้อ 2 หลัก
    คืน dict สำหรับสร้าง Quick Reply: {'question': str, 'options': [...]}
    ต้องมีตัวเลือก 'ไม่เอา ให้โทรกลับมาถาม' เสมอเป็นตัวสุดท้าย"""

def update_status(conn, booking_id: int, status: str, result_note=None) -> None
    """ห้ามตั้ง 'confirmed' โดยไม่มี result_note — บุคลิกข้อความซื่อสัตย์:
    'ห้ามรายงานว่าเรียบร้อย ถ้ายังไม่ได้ยืนยันว่าสำเร็จจริง' → ValueError"""
```

## `core/webhook.py` — รับคำสั่งเสียงจาก Siri Shortcut (red-team PART 2.5)

```python
class WebhookError(Exception):
    def __init__(self, status: int, message: str) -> None: ...

def verify_secret(headers: dict, expected: str) -> None
    """ตรวจ header 'X-Jarvis-Secret' — ต้องใช้ hmac.compare_digest
    (เทียบด้วย == จะรั่วข้อมูลผ่านเวลาที่ใช้เปรียบเทียบ)
    ไม่ตรง/ไม่มี → WebhookError(401)  /  expected ว่าง → WebhookError(500)"""

def parse_request(body: bytes | str, headers: dict, secret: str) -> dict
    """body เป็น JSON {'text': '...'} จาก Siri action 'Get Contents of URL'
    คืน {'text': str, 'source': str}   ('siri' ถ้าไม่ระบุ)
    text ว่าง → WebhookError(400) / JSON พัง → WebhookError(400)
    ยาวเกิน MAX_TEXT_LEN (2000) → WebhookError(413)"""

def build_response(reply: str, *, ok: bool = True) -> dict
    """Siri action 'Speak Text' อ่านค่าจากคีย์ 'speak' — ต้องมีคีย์นี้เสมอ"""
```
