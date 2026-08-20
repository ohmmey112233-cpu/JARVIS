"""
เรนเดอร์ข้อความทุกแบบที่ Jarvis ส่งออก — ต่อสตริงล้วน ไม่มี LLM ในไฟล์นี้

ทำไมห้ามให้โมเดลเขียนข้อความพวกนี้เอง:
    phase1-kit ส่วนที่ 1 กำหนดหน้าตาข้อความไว้ครบ 7 แบบระดับตัวอักษร
    jarvis-personal-os-analysis เตือนว่าถ้าปล่อยให้โมเดลเรียบเรียงรูปแบบตายตัวเอง
    ข้อความจะดริฟต์ทีละนิดจนอ่านเหมือนคนละคน (checklist D ข้อ 3)
    → ที่นี่ deterministic ล้วน โมเดลไปทำงานเฉพาะที่ต้องใช้วิจารณญาณทางภาษาจริงๆ

ทำไมทุก field ที่มาจาก API ภายนอกเป็น Optional:
    checklist E: "API ตัวใดตัวหนึ่งล่ม (เช่น Air4Thai) → digest ยังส่งได้
    แค่ข้ามหัวข้อนั้น ไม่ใช่ทั้งข้อความหายไป"
    → ทุกหัวข้อในไฟล์นี้ "หายทั้งบรรทัด" เมื่อไม่มีข้อมูล
      ห้ามมีคำว่า None/null หลุดออกไปในข้อความเด็ดขาด

หลักการเขียนข้อความ 6 ข้อจาก kit ที่บังคับไว้ในโค้ดนี้ (ไม่ใช่แค่ในเอกสาร):
    1 ข้อความเดียวจบ            → ทุก render_* คืนสตริงเดียว
    2 ไม่เกิน 1 หน้าจอมือถือ     → MAX_SCREEN_LINES + เพดานของทุกรายการที่ยาวได้
    3 ต่างจากปกติขึ้นก่อน        → วันพุธขึ้น ⚠️ เป็นบรรทัดแรกเสมอ
    4 ไม่มีอะไรเปลี่ยน = บรรทัดเดียว → "📌 วันนี้ยังไม่มีอะไรถึงรอบ"
    5 อีโมจิเป็นหัวข้อ           → ค่าคงที่ด้านล่างเท่านั้น ห้ามโปรยเพิ่มระหว่างทาง
    6 ตัวเลขต้องแปลงเป็นการตัดสินใจ → _travel_lines() ไม่บอก "15 นาที" เฉยๆ
      แต่บอก "ออก 07:10 ดีกว่า" ควบไปด้วยเสมอเมื่อรู้เวลาที่ควรออก

ข้อห้ามที่บังคับด้วยโค้ด ไม่ใช่แค่ prompt:
    red-team H12 — คำว่า "ล็อค" ห้ามหลุดออกไปในข้อความใดๆ
    เซนเซอร์รู้แค่เปิด/ปิด การบอกว่าล็อคแล้วทั้งที่ไม่รู้ อันตรายกว่าไม่มีระบบเลย
    เพราะทำให้ไว้ใจผิด → ข้อความจากภายนอกทุกก้อนผ่าน _text()
    ซึ่งตัดทิ้งทั้งบรรทัดถ้าเจอคำนี้ (ยอมเสีย 1 บรรทัด ดีกว่าโกหก 1 ประโยค)

เรื่องเวลา (กฎเหล็กข้อ 1):
    ไฟล์นี้ไม่เรียก datetime.now()/date.today() เอง เวลาทั้งหมดมาจาก ctx.when
    ซึ่งผู้เรียกเตรียมมาแล้ว และถูกแปลงเป็นเวลาไทยผ่าน core.localdate เสมอ
    renderer ที่ต้องรู้ "ตอนนี้กี่โมง" รับ clock ตัวสุดท้ายไว้ให้เทสต์ฉีดเวลา
    และเป็นทางหนีทีไล่เมื่อผู้เรียกลืมใส่ ctx.when (ยอมส่งข้อความ ดีกว่าเงียบ)
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from . import localdate

__all__ = [
    "DigestContext",
    "aqi_label",
    "render_morning",
    "render_evening",
    "render_weekly",
    "render_dream_report",
    "render_call_ack",
    "render_booking_reply",
    "render_routine_done",
    "render_lesson_saved",
    "MAX_SCREEN_LINES",
    "AQI_ALERT_THRESHOLD",
]

# --- ค่าคงที่ของข้อความ (kit ส่วนที่ 1) --------------------------------------
# รวมไว้ที่เดียวเพราะเป็นของที่แก้บ่อยที่สุดเวลาอ่านแล้วรู้สึกว่า "ไม่ใช่"
# kit บอกให้แก้ข้อความก่อนแก้โค้ด — ต้องหาเจอในไฟล์เดียวโดยไม่ต้องไล่ทั้งฟังก์ชัน

FIRST_PERIOD_TIME = "08:20"  # คาบแรกเริ่มเวลานี้ทุกวัน (kit ส่วนที่ 3 หัวตาราง)
ROUTE_LABEL = "หอ→โรงเรียน"

# วันพุธตื่นเร็วกว่าปกติเท่าไหร่ = wake_time (06:50) − wake_time_wed (06:30)
# เก็บเป็นตัวเลขเดียวเพราะ core/ อ่าน preferences เองไม่ได้ (ไม่มี conn ในสัญญา)
WAKE_EARLIER_MINUTES = 20
WEDNESDAY_ALERT = f"⚠️ วันนี้พุธ ตื่นเร็วกว่าปกติ {WAKE_EARLIER_MINUTES} นาที"
WEDNESDAY_MORNING = "เช้า: เรียนถึงเที่ยง"
# ช่วงเวลา ~16:30-17:00 มาจาก preference rd_end_estimate = 16:45 (kit ส่วนที่ 3)
WEDNESDAY_AFTERNOON = "บ่าย: ร.ด. (เลิกไม่แน่นอน ~16:30-17:00)"

FRIDAY_HOME_LINES = (
    "วันนี้ศุกร์ — สัปดาห์นี้กลับบ้านจอมทอง 🏡",
    "(ไม่ใช่สัปดาห์โรงแรม)",
)
FRIDAY_HOTEL_LINES = (
    "วันนี้ศุกร์ — สัปดาห์นี้เป็นสัปดาห์โรงแรม 🏨",
    "(คราวนี้ไม่กลับจอมทอง)",
)
HOME_TRIP_LINE = "เย็นนี้: โรงเรียน→จอมทอง ~1 ชม. 20 นาที"

CALENDAR_HEADING = "📅 วันนี้มีนัด:"
NOTHING_DUE = "📌 วันนี้ยังไม่มีอะไรถึงรอบ"
DUE_HEADING = "📌 ถึงรอบวันนี้:"

EVENING_GREETING = "เย็นนี้เป็นไงบ้างครับ 🌙"
EVENING_DONE_HEADING = "วันนี้ที่เกิดขึ้น:"
EVENING_NOTHING = "วันนี้ไม่มีอะไรที่ต้องรายงานครับ"
EVENING_CLOSER = "เตือนอีกทีตอนเช้าครับ"

WEEKLY_GREETING = "สัปดาห์หน้ามีอะไรบ้าง 📅"
WEEKLY_DUE_HEADING = "📌 ถึงรอบสัปดาห์หน้า:"
WEEKLY_NOTHING = "สัปดาห์หน้ายังไม่มีอะไรพิเศษครับ"
HOTEL_QUESTION = "จองโรงแรมให้เลยไหมครับ?"

DREAM_GREETING = "เมื่อคืนจัดระเบียบความจำครับ"
DREAM_NOTHING = "เมื่อคืนจัดระเบียบความจำครับ ไม่มีอะไรต้องพักไว้"
DREAM_HINT = '— ดูรายการที่พักไว้ พิมพ์ "ดูความจำที่พัก"'

CALL_ACK = "กำลังโทรให้ครับ รอสักครู่"
BOOKING_OK = "เรียบร้อยครับ ✅"
BOOKING_FAILED = "ยังไม่สำเร็จครับ"
CALENDAR_ADDED = "ใส่ปฏิทินให้แล้ว"
LESSON_SAVED = "จำแล้วครับ"
ROUTINE_SAVED = "บันทึกแล้วครับ"

BULLET = "   • "  # เว้นหน้า 3 ช่องตาม kit (ใช้ทั้งเย็น/สัปดาห์/รายการยาว)
CONTINUATION = "   "  # บรรทัดต่อของหัวข้อ 🚗 ("   ออก 07:15 ถึงสบายๆ")

# --- เกณฑ์ตัดสินใจ (ตัวเลขที่แปลงเป็นคำพูด) ----------------------------------

# เวลาเดินทางหอ→โรงเรียนแบบปกติ ใช้ตัดสินว่า "รถติดกว่าปกติ" ไหม
# ตัวอย่างใน kit: จันทร์ 12 / ศุกร์ 11 = ปกติ, พุธ 15 = ติดกว่าปกติ
# → เกินค่าปกติเกิน 2 นาทีเมื่อไหร่ถือว่าติด (ไม่ใช่ 1 นาทีก็บ่น)
NORMAL_TRAVEL_MINUTES = 12
TRAFFIC_SLACK_MINUTES = 2

# preference aqi_alert_threshold = 100 (kit ส่วนที่ 3) "เกินเท่านี้ถึงเตือนใส่แมสก์"
AQI_ALERT_THRESHOLD = 100
MASK_HINT = " → ใส่แมสก์"

# แถบ AQI ตามเกณฑ์ไทย (Air4Thai) เพราะ checklist B บอกให้ค่าตรงกับที่เปิด Air4Thai ดูเอง
# ถ้าใช้แถบแบบอเมริกา ค่า 30 จะกลายเป็น "ดี" คนละสีกับที่แอปแสดง = เถียงกับของจริง
AQI_BANDS: tuple[tuple[int, str], ...] = (
    (25, "อากาศดีมาก"),
    (50, "อากาศดี"),
    (100, "ปานกลาง"),
    (200, "เริ่มมีผลกระทบต่อสุขภาพ"),
)
AQI_WORST_LABEL = "มีผลกระทบต่อสุขภาพ"

# --- เพดานความยาว (kit หลักการข้อ 2) -----------------------------------------
# 1 หน้าจอมือถือ ≈ 28 บรรทัด — ข้อความจริงตามตัวอย่าง kit อยู่ที่ 12-14 บรรทัด
# ค่าพวกนี้คือ "เพดานกันบวม" เวลามีนัด 10 รายการหรือ routine ถึงรอบพร้อมกันหลายตัว
MAX_SCREEN_LINES = 28
MORNING_LIST_LIMIT = 3
EVENING_DONE_LIMIT = 4
EVENING_PENDING_LIMIT = 5
WEEKLY_ROW_LIMIT = 7
WEEKLY_LIST_LIMIT = 4
DREAM_TOPIC_LIMIT = 2

# คำที่ห้ามหลุดออกไปเด็ดขาด — red-team H12 (เซนเซอร์รู้แค่เปิด/ปิด ไม่รู้ว่าล็อคไหม)
BANNED_WORDS = ("ล็อค",)

# ค่าที่ผู้เรียกส่งมาแล้วแปลว่า "ไม่มีข้อมูล" ไม่ใช่ข้อความจริง
# (JSON จาก API ที่ล่มมักส่ง "null"/"None" มาเป็นสตริงตรงๆ ถ้าไม่กรองจะไปโผล่ในข้อความ)
EMPTY_TEXTS = {"none", "null", "nil", "-", "n/a"}

# คำขึ้นต้นที่บอกช่วงเวลาอยู่แล้ว — เจอแล้วห้ามเติม "พรุ่งนี้: " ซ้ำหน้าอีก
TIME_PREFIXES = ("พรุ่งนี้", "เย็นนี้", "คืนนี้", "บ่ายนี้", "เช้านี้", "สุดสัปดาห์")

# ค่าที่ RoutineStatus.kind เป็นได้ (ประกาศซ้ำแทนการ import core.routines
# เพื่อให้โมดูลนี้ไม่ผูกกับโมดูลที่แตะ DB — เรนเดอร์เป็นงาน pure ล้วน)
KIND_INTERVAL = "interval"


@dataclass
class DigestContext:
    """ข้อมูลที่รวบรวมมาแล้วจากภายนอก — โมดูลนี้แค่จัดรูปแบบ ไม่ไปดึงเอง

    ทุก field ที่มาจาก API ภายนอกเป็น Optional เพราะ API ล่มได้
    (checklist E: 'API ล่ม → digest ยังส่งได้ แค่ข้ามหัวข้อนั้น')

    แยกการ "หาข้อมูล" ออกจากการ "จัดข้อความ" แบบนี้ทำให้เทสต์ข้อความได้ทุกแบบ
    โดยไม่ต้องมีเน็ต ไม่ต้องมี API key และไม่ต้องมีฐานข้อมูลสักตัว
    """

    when: datetime
    travel_minutes: int | None = None
    leave_by: str | None = None  # 'HH:MM'
    weather_summary: str | None = None  # '28° ไม่มีฝนช่วงเช้า'
    rain_window: str | None = None  # '07:00-08:00'
    aqi: int | None = None
    calendar_items: list[str] = field(default_factory=list)
    due_routines: list = field(default_factory=list)
    upcoming_routines: list = field(default_factory=list)
    friday: object | None = None  # FridayPlan
    first_subject: str | None = None
    period_count: str | None = None
    tomorrow_note: str | None = None


# --- ตัวช่วยทำความสะอาดข้อมูลจากภายนอก ---------------------------------------


def _text(value: Any) -> str | None:
    """ทำให้ข้อความจากภายนอกปลอดภัยพอจะเอาไปต่อเป็นข้อความจริง

    คืน None = "ไม่ต้องพิมพ์บรรทัดนี้" ซึ่งเป็นพฤติกรรมที่ checklist E ต้องการ
    ยุบช่องว่าง/ขึ้นบรรทัดใหม่ทิ้ง เพราะข้อความหลายบรรทัดจากผู้เรียกจะทำให้
    โครงย่อหน้าที่ kit กำหนดไว้เพี้ยนทั้งข้อความ (และนับบรรทัดกันบวมไม่ได้)
    """
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text or text.lower() in EMPTY_TEXTS:
        return None
    for word in BANNED_WORDS:
        if word in text:
            # H12: ทิ้งทั้งบรรทัดเงียบๆ ดีกว่าปล่อยคำสัญญาที่เซนเซอร์ยืนยันไม่ได้ออกไป
            return None
    return text


def _lines(values: Iterable[Any] | None) -> list[str]:
    """รายการข้อความจากภายนอก → เฉพาะบรรทัดที่ใช้ได้จริง"""
    if not values:
        return []
    cleaned: list[str] = []
    for value in values:
        text = _text(value)
        if text:
            cleaned.append(text)
    return cleaned


def _int(value: Any) -> int | None:
    """ตัวเลขจาก API → int หรือ None ถ้าอ่านไม่ออก

    กัน bool ออกไปด้วย เพราะ True จะกลายเป็น 1 แล้วไปโผล่เป็น "AQI 1"
    ซึ่งดูเหมือนข้อมูลจริงทั้งที่เป็นค่าที่ส่งมาผิดชนิด
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """อ่านค่าจาก NamedTuple / dataclass / dict ด้วยทางเดียวกัน

    ทำแบบนี้เพื่อให้ digest ไม่ต้อง import core.routines / core.friday
    (ตัวเรนเดอร์ไม่ควรผูกกับโมดูลที่แตะ DB) และเทสต์ยัด stub ง่ายๆ ได้
    """
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _bullets(items: Sequence[str], limit: int) -> list[str]:
    """แปลงรายการเป็นบรรทัด • พร้อมเพดานกันข้อความบวมเกิน 1 หน้าจอ

    ถ้าเกินเพดานแค่ 1 รายการจะแสดงทั้งหมด — เพราะบรรทัด "และอีก 1 รายการ"
    กินที่เท่ากับแสดงของจริง แต่ให้ข้อมูลน้อยกว่า
    """
    if len(items) <= limit + 1:
        shown, rest = list(items), 0
    else:
        shown, rest = list(items[:limit]), len(items) - limit
    lines = [f"{BULLET}{item}" for item in shown]
    if rest:
        lines.append(f"{BULLET}และอีก {rest} รายการ")
    return lines


def _join(blocks: Sequence[Sequence[str]]) -> str:
    """ต่อย่อหน้าเป็นข้อความเดียว — ย่อหน้าคั่นด้วยบรรทัดว่าง 1 บรรทัด (ตาม kit)

    ตาข่ายชั้นสุดท้ายของ H12 อยู่ตรงนี้ด้วย: ต่อให้มีทางไหนหลุด _text() มาได้
    บรรทัดที่มีคำต้องห้ามจะไม่ถูกส่งออกไป
    """
    paragraphs: list[str] = []
    for block in blocks:
        lines = [
            line for line in block if line and not any(w in line for w in BANNED_WORDS)
        ]
        if lines:
            paragraphs.append("\n".join(lines))
    return "\n\n".join(paragraphs)


def _moment(ctx: DigestContext, clock: datetime | None = None) -> datetime:
    """เวลาอ้างอิงของข้อความ — ประตูเดียวที่โมดูลนี้ยุ่งกับเวลา

    ctx.when ที่ไม่ใช่ datetime (เช่นส่ง date หรือสตริงมา) ต้องระเบิด ไม่ใช่เดา:
    หัวข้อความคือ "อรุณสวัสดิ์ครับ ☀️ 06:20" ถ้าเดาเวลาเป็น 00:00 ให้
    ข้อความจะดูปกติทุกอย่างแต่บอกเวลาผิด ซึ่งจับได้ยากกว่าพังตั้งแต่แรกมาก
    """
    when = getattr(ctx, "when", None)
    if isinstance(when, datetime):
        return localdate.now(when)
    if when is not None:
        raise TypeError(
            f"DigestContext.when ต้องเป็น datetime ได้รับ {type(when).__name__} "
            f"({when!r}) — ข้อความบอกเวลาเป็นชั่วโมง:นาที จึงเดาจากวันที่อย่างเดียวไม่ได้"
        )
    # ผู้เรียกลืมใส่เวลา → ยังส่งข้อความได้ด้วยเวลาปัจจุบันแบบไทย (checklist E)
    return localdate.now(clock)


# --- ฝุ่น --------------------------------------------------------------------


def aqi_label(aqi: int) -> str:
    """คำอธิบายคุณภาพอากาศตามเกณฑ์ไทย (Air4Thai)

    ค่าติดลบ/อ่านไม่ออก = ข้อมูลเสีย ต้องระเบิดให้ผู้เรียกรู้
    ส่วน digest จะดักไว้เองแล้วข้ามหัวข้อฝุ่นไปทั้งบรรทัด (checklist E)
    """
    value = _int(aqi)
    if value is None or value < 0:
        raise ValueError(f"ค่า AQI ต้องเป็นจำนวนเต็มไม่ติดลบ ได้รับ {aqi!r}")
    for upper, label in AQI_BANDS:
        if value <= upper:
            return label
    return AQI_WORST_LABEL


def _aqi_line(aqi: Any) -> str | None:
    """บรรทัด 💨 — ไม่มีข้อมูลหรือข้อมูลเสียก็หายทั้งบรรทัด ไม่ทำให้ digest ล้ม"""
    value = _int(aqi)
    if value is None:
        return None
    try:
        label = aqi_label(value)
    except ValueError:
        return None
    line = f"💨 AQI {value} — {label}"
    if value > AQI_ALERT_THRESHOLD:
        # หลักการข้อ 6: ตัวเลขต้องกลายเป็นการตัดสินใจ ไม่ใช่ให้ไปตีความเอง
        line += MASK_HINT
    return line


# --- ชิ้นส่วนของข้อความเช้า ---------------------------------------------------


def _day_class_lines(moment: datetime, ctx: DigestContext) -> list[str]:
    """หัวเรื่องวันแบบปกติ (จ./อ./พฤ.) — 2 บรรทัดตามตัวอย่างเช้าวันจันทร์

        วันนี้จันทร์ เรียน 8 คาบเต็ม
        คาบแรก ชีววิทยา 08:20
    """
    head = f"วันนี้{localdate.thai_day_name(moment)}"
    periods = _text(ctx.period_count)
    if periods:
        count = _int(periods)
        # period_count เก็บเป็น TEXT เพราะวันพุธเป็น 'ครึ่งวัน' ไม่ใช่ตัวเลข (schema 001)
        head += f" เรียน {count} คาบเต็ม" if count else f" เรียน{periods}"
    lines = [head]
    subject = _text(ctx.first_subject)
    if subject:
        lines.append(f"คาบแรก {subject} {FIRST_PERIOD_TIME}")
    return lines


def _friday_class_line(ctx: DigestContext) -> str | None:
    """ตารางเรียนแบบย่อบรรทัดเดียวสำหรับวันศุกร์

        เรียน 7 คาบ คาบแรกชีววิทยา 08:20

    ย่อเหลือบรรทัดเดียวเพราะหัวเรื่องศุกร์กินไป 2 บรรทัดแล้ว (หลักการข้อ 2)
    เว้นวรรคต่างจากวันปกติจริงตามตัวอย่างใน kit — ไม่ใช่พิมพ์ตก
    """
    parts: list[str] = []
    periods = _text(ctx.period_count)
    if periods:
        count = _int(periods)
        parts.append(f"เรียน {count} คาบ" if count else f"เรียน{periods}")
    subject = _text(ctx.first_subject)
    if subject:
        parts.append(f"คาบแรก{subject} {FIRST_PERIOD_TIME}")
    return " ".join(parts) if parts else None


def _travel_lines(ctx: DigestContext) -> list[str]:
    """หัวข้อ 🚗 — หัวใจของหลักการข้อ 6 (ตัวเลขต้องกลายเป็นการตัดสินใจ)

    3 หน้าตาที่ kit กำหนดไว้ และกติกาที่ทำให้ได้ทั้งสามแบบจากข้อมูลชุดเดียว:
        จันทร์ 'ตอนนี้ 12 นาที' + 'ออก 07:15 ถึงสบายๆ'  → ปกติ และรู้เวลาที่ควรออก
        พุธ    '15 นาที (รถติดกว่าปกติ)' + 'ออก 07:10 ดีกว่า' → ช้ากว่าปกติ
        ศุกร์  '11 นาที'                                  → ไม่รู้เวลาที่ควรออก
    คำว่า "ตอนนี้" ใช้เฉพาะตอนที่มีบรรทัดตัดสินใจตามมาและรถไม่ติด
    เพราะมันแปลว่า "ตอนนี้เท่านี้ ออกตามนี้แล้วสบาย" ไม่ใช่รายงานตัวเลขลอยๆ
    """
    minutes = _int(ctx.travel_minutes)
    if minutes is not None and minutes <= 0:
        # 0 หรือติดลบ = ค่าที่ Routes API ส่งมาผิด ไม่ใช่ "ไปถึงทันที"
        minutes = None
    leave = _text(ctx.leave_by)
    if minutes is None and leave is None:
        return []

    if minutes is None:
        # รู้แค่เวลาที่ควรออก — ยังมีค่าที่สุดสำหรับโอม จึงเก็บบรรทัดตัดสินใจไว้
        return [f"🚗 ออก {leave} ถึงสบายๆ"]

    heavy = minutes - NORMAL_TRAVEL_MINUTES > TRAFFIC_SLACK_MINUTES
    prefix = "ตอนนี้ " if (leave and not heavy) else ""
    suffix = " (รถติดกว่าปกติ)" if heavy else ""
    lines = [f"🚗 {ROUTE_LABEL} {prefix}{minutes} นาที{suffix}"]
    if leave:
        lines.append(f"{CONTINUATION}ออก {leave} " + ("ดีกว่า" if heavy else "ถึงสบายๆ"))
    return lines


def _weather_lines(ctx: DigestContext) -> list[str]:
    """หัวข้ออากาศ + ฝุ่น

    ฝนชนะแดดเสมอเมื่อรู้ทั้งคู่ (หลักการข้อ 3: สิ่งที่ต่างจากปกติขึ้นก่อน)
    และเพราะบรรทัดฝนมีการตัดสินใจติดมาด้วย ("→ พกร่ม") ส่วนบรรทัดอุณหภูมิไม่มี
    """
    lines: list[str] = []
    rain = _text(ctx.rain_window)
    summary = _text(ctx.weather_summary)
    if rain:
        lines.append(f"🌧️ ฝนน่าจะตก {rain} → พกร่ม")
    elif summary:
        lines.append(f"🌤️ {summary}")
    aqi = _aqi_line(ctx.aqi)
    if aqi:
        lines.append(aqi)
    return lines


def _routine_phrase(item: Any) -> str | None:
    """RoutineStatus → วลีสั้นๆ สำหรับบรรทัด 📌

    ความต่างของสองแบบใน kit ("ครบ 7 วันแล้ว" กับ "ครบ 14 วันวันนี้")
    คือเลยกำหนดมาแล้ว กับ ครบรอบพอดีวันนี้ — ไม่ใช่การเล่นคำ
    รอบกี่วันคำนวณจาก days_since + days_until เพราะ RoutineStatus ไม่ได้ส่ง
    interval_days มาให้ (สัญญาตรึงไว้แล้ว ห้ามแก้) แต่สองค่านี้บอกได้เท่ากัน:
        days_since = วันนี้ − ครั้งล่าสุด, days_until = ครบรอบ − วันนี้
        รวมกัน = ครบรอบ − ครั้งล่าสุด = ความยาวของรอบพอดี
    """
    if isinstance(item, str):
        return _text(item)

    name = _text(_attr(item, "name_th")) or _text(_attr(item, "name"))
    if name is None:
        return None

    kind = _text(_attr(item, "kind"))
    days_since = _int(_attr(item, "days_since"))
    days_until = _int(_attr(item, "days_until"))

    if kind == KIND_INTERVAL and days_since is None:
        # ยังไม่เคยบันทึกว่าทำ = ถึงรอบทันทีตามสัญญาของ routines.py
        # แต่ห้ามบอกว่า "ครบ N วัน" เพราะไม่รู้จริงๆ ว่าครั้งล่าสุดเมื่อไหร่
        return f"{name} — ยังไม่เคยบันทึกว่าทำเมื่อไหร่"

    if kind == KIND_INTERVAL and days_since is not None and days_until is not None:
        interval = days_since + days_until
        if interval > 0:
            if days_until == 0:
                return f"{name} ครบ {interval} วันวันนี้"
            if days_until < 0:
                return f"{name} ครบ {interval} วันแล้ว"

    if days_until is not None:
        if days_until == 0:
            return f"{name} วันนี้"
        if days_until < 0:
            return f"{name} เลยรอบมา {-days_until} วันแล้ว"
    return name


def _upcoming_phrase(item: Any) -> str | None:
    """RoutineStatus → 'ไดโอด (พฤหัสบดี)' สำหรับสรุปสัปดาห์"""
    if isinstance(item, str):
        return _text(item)
    name = _text(_attr(item, "name_th")) or _text(_attr(item, "name"))
    if name is None:
        return None
    next_due = _attr(item, "next_due")
    if next_due is None:
        return name
    try:
        return f"{name} ({localdate.thai_day_name(next_due)})"
    except (ValueError, TypeError):
        # วันที่อ่านไม่ออก → บอกชื่อไปก่อน ดีกว่าตัดรายการทิ้งทั้งอัน
        return name


def _tomorrow_line(ctx: DigestContext, moment: datetime) -> str | None:
    """บรรทัดปิดท้าย 'พรุ่งนี้: ...'

    ถ้าผู้เรียกเขียนมาเองแล้วก็ใช้ตามนั้น (kit: 'พรุ่งนี้: อังคาร มีตัดผมตอนเย็น')
    ไม่มีมาก็ประกอบเองจาก routine ที่ถึงรอบพรุ่งนี้ — ไม่มีอะไรเลยก็ไม่ต้องพูด
    (หลักการข้อ 4: ไม่ต้องรายงานสิ่งที่ไม่มีอะไรเปลี่ยน)
    """
    note = _text(ctx.tomorrow_note)
    if note:
        if note.startswith(TIME_PREFIXES):
            return note
        return f"พรุ่งนี้: {note}"

    names: list[str] = []
    for item in ctx.upcoming_routines or ():
        if isinstance(item, str):
            continue
        if _int(_attr(item, "days_until")) == 1:
            name = _text(_attr(item, "name_th")) or _text(_attr(item, "name"))
            if name:
                names.append(name)
    if not names:
        return None
    day = localdate.thai_day_name(moment.date() + timedelta(days=1))
    return f"พรุ่งนี้: {day} มี{' + '.join(names[:MORNING_LIST_LIMIT])}"


def render_morning(ctx: DigestContext, clock: datetime | None = None) -> str:
    """digest เช้า — 3 หน้าตาตาม kit ส่วนที่ 1 (จันทร์ปกติ / พุธ ⚠️ / ศุกร์ 🏡)

    ลำดับหัวข้อคือหลักการข้อ 3 ที่แปลงเป็นโค้ด: สิ่งที่ต่างจากปกติอยู่บนสุด
    (⚠️ ตื่นเร็ววันพุธ / 🏡 สัปดาห์กลับบ้าน) แล้วค่อยเป็นของประจำวัน

    clock ใช้เฉพาะตอน ctx.when ไม่ได้ตั้งมา — ทุกฟังก์ชันที่ยุ่งกับเวลาต้อง
    ฉีดเวลาได้ตามกฎเหล็กข้อ 1 และเทสต์ทั้งไฟล์นี้รันโดยไม่แตะนาฬิกาจริงเลย
    """
    moment = _moment(ctx, clock)
    weekday = moment.weekday()
    blocks: list[list[str]] = [[f"อรุณสวัสดิ์ครับ ☀️ {moment:%H:%M}"]]

    is_home = _attr(ctx.friday, "is_home")
    show_friday = weekday == localdate.FRIDAY and is_home is not None

    if weekday == localdate.WEDNESDAY:
        # kit ข้อ 3 + checklist A2: วันพุธต้องขึ้น ⚠️ เป็นบรรทัดแรกเสมอ
        # และเป็นย่อหน้าของตัวเอง เพื่อให้สะดุดตาตอนอ่านผ่านๆ ตอนเพิ่งตื่น
        blocks.append([WEDNESDAY_ALERT])
        blocks.append([WEDNESDAY_MORNING, WEDNESDAY_AFTERNOON])
    elif show_friday:
        blocks.append(list(FRIDAY_HOME_LINES if is_home else FRIDAY_HOTEL_LINES))
        line = _friday_class_line(ctx)
        if line:
            blocks.append([line])
    else:
        # ศุกร์ที่ยังไม่รู้สถานะ (anchor ยังไม่ได้กรอก) จะตกมาทางนี้ —
        # เงียบเรื่องบ้าน/โรงแรมไปเลย ดีกว่าเดาแล้วบอกผิดด้าน (friday.py คุมเรื่องนี้อยู่)
        blocks.append(_day_class_lines(moment, ctx))

    events = _lines(ctx.calendar_items)
    if len(events) == 1:
        blocks.append([f"📅 {events[0]}"])
    elif events:
        blocks.append([CALENDAR_HEADING] + _bullets(events, MORNING_LIST_LIMIT))

    travel = _travel_lines(ctx)
    weather = _weather_lines(ctx)
    if len(travel) == 1:
        # การเดินทางบรรทัดเดียวเกาะกลุ่มกับอากาศ/ฝุ่น (ตัวอย่างเช้าวันศุกร์)
        # มี 2 บรรทัดเมื่อไหร่แยกเป็นย่อหน้าของตัวเอง (จันทร์/พุธ) ไม่งั้นอ่านเป็นพืดเดียว
        blocks.append(travel + weather)
    else:
        blocks.append(travel)
        blocks.append(weather)

    due = [p for p in (_routine_phrase(i) for i in ctx.due_routines or ()) if p]
    if not due:
        blocks.append([NOTHING_DUE])  # หลักการข้อ 4
    elif len(due) == 1:
        blocks.append([f"📌 {due[0]}"])
    else:
        blocks.append([DUE_HEADING] + _bullets(due, MORNING_LIST_LIMIT))

    tail: list[str] = []
    if show_friday and is_home:
        # เฉพาะสัปดาห์กลับจอมทองเท่านั้นที่มีขาเย็นยาวๆ ต้องเผื่อเวลา
        tail.append(HOME_TRIP_LINE)
    tomorrow = _tomorrow_line(ctx, moment)
    if tomorrow:
        tail.append(tomorrow)
    blocks.append(tail)

    return _join(blocks)


# --- สรุปตอนเย็น 18:30 -------------------------------------------------------


def render_evening(
    ctx: DigestContext,
    *,
    done_items: Iterable[Any],
    pending_work: Iterable[Any],
    clock: datetime | None = None,
) -> str:
    """digest เย็น — kit ส่วนที่ 1 หัวข้อ "สรุปตอนเย็น (18:30)"

    done_items = สิ่งที่ "เกิดขึ้นจริงแล้ว" วันนี้ ผู้เรียกเป็นคนตัดสินว่าอะไรสำเร็จ
    เพราะโมดูลนี้ไม่รู้ผลจริง — บุคลิกข้อความซื่อสัตย์ห้ามเดาแทนว่าเรียบร้อยแล้ว

    pending_work ว่าง = **ไม่พิมพ์หัวข้อ 📋 เลย** ไม่ใช่พิมพ์ว่า "ไม่มีงานค้าง"
    เพราะรายการว่างมีได้ 2 สาเหตุ คือไม่มีงานค้างจริง กับ ดึงจาก scaccounting ไม่ได้
    ซึ่งโมดูลนี้แยกไม่ออก การประกาศว่า "ไม่มีงานค้าง" ตอน API ล่ม = โกหกเต็มๆ
    """
    moment = _moment(ctx, clock)
    blocks: list[list[str]] = [[EVENING_GREETING]]

    done = _lines(done_items)
    if done:
        shown = done[:EVENING_DONE_LIMIT]
        lines = [EVENING_DONE_HEADING] + [f"✅ {item}" for item in shown]
        if len(done) > len(shown):
            lines.append(f"{BULLET}และอีก {len(done) - len(shown)} รายการ")
        blocks.append(lines)
    else:
        blocks.append([EVENING_NOTHING])  # หลักการข้อ 4: บรรทัดเดียวพอ

    pending = _lines(pending_work)
    if pending:
        # นับจากจำนวนจริง ไม่ใช่จำนวนที่โชว์ — ตัดให้สั้นได้ แต่ห้ามรายงานตัวเลขต่ำกว่าจริง
        blocks.append(
            [f"📋 งานบริษัทค้างอยู่ {len(pending)} รายการ"]
            + _bullets(pending, EVENING_PENDING_LIMIT)
        )

    tomorrow = _tomorrow_line(ctx, moment)
    if tomorrow:
        blocks.append([tomorrow, EVENING_CLOSER])

    return _join(blocks)


# --- สรุปสัปดาห์ อาทิตย์ 20:00 ------------------------------------------------


def _week_label(value: Any) -> str | None:
    """หัวแถวของตารางสัปดาห์ — วันที่จะถูกแปลงเป็นชื่อวันย่อ ('จ.' 'อ.' ...)"""
    if isinstance(value, (date, datetime)):
        return localdate.thai_day_name(value, short=True)
    return _text(value)


def _week_row(value: Any) -> str | None:
    """1 แถวของตารางสัปดาห์ → 'อ. — ✂️ ตัดผม ร้านเกษมเกษา (เย็น)'

    รับได้ทั้งสตริงสำเร็จรูป, คู่ (วัน, เรื่อง) และ dict — เพราะผู้เรียกที่ประกอบ
    ตารางนี้อยู่คนละชั้น (skills/) และไม่ควรต้องรู้ว่าเส้นคั่นเป็น '—' หรือ '-'
    """
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, Mapping):
        label = value.get("day", value.get("label"))
        note = value.get("note", value.get("text"))
    elif isinstance(value, Sequence) and len(value) == 2:
        label, note = value
    else:
        return _text(value)
    label_text = _week_label(label)
    note_text = _text(note)
    if label_text and note_text:
        return f"{label_text} — {note_text}"
    return note_text or label_text


def render_weekly(
    ctx: DigestContext,
    *,
    week_rows: Iterable[Any],
    due_next_week: Iterable[Any],
) -> str:
    """สรุปสัปดาห์คืนวันอาทิตย์ — kit ส่วนที่ 1 หัวข้อ "สรุปสัปดาห์ (อาทิตย์ 20:00)"

    ไม่มีพารามิเตอร์ clock เพราะไม่มีบรรทัดไหนถามว่า "ตอนนี้กี่โมง" เลย:
    ทุกอย่างมาจาก week_rows / due_next_week / ctx.friday ที่ผู้เรียกเตรียมมาแล้ว
    (ctx.friday ต้องเป็นแผนของ **ศุกร์สัปดาห์หน้า** ไม่ใช่ศุกร์ที่เพิ่งผ่านไป)

    คำถามปิดท้าย "จองโรงแรมให้เลยไหมครับ?" ขึ้นเฉพาะสัปดาห์โรงแรมเท่านั้น
    ไม่รู้สถานะ (is_home เป็น None เพราะ anchor ยังไม่ได้กรอก) = ไม่ถาม
    ถามผิดสัปดาห์แปลว่าจองโรงแรมทิ้งไว้ในคืนที่โอมกลับจอมทอง (H10 คนละเรื่องแต่โทษเดียวกัน)
    """
    blocks: list[list[str]] = [[WEEKLY_GREETING]]

    rows = [r for r in (_week_row(v) for v in week_rows or ()) if r][:WEEKLY_ROW_LIMIT]
    if rows:
        blocks.append(rows)

    due = [p for p in (_upcoming_phrase(i) for i in due_next_week or ()) if p]
    if due:
        blocks.append([WEEKLY_DUE_HEADING] + _bullets(due, WEEKLY_LIST_LIMIT))

    if not rows and not due:
        blocks.append([WEEKLY_NOTHING])

    if _attr(ctx.friday, "is_home") is False:
        blocks.append([HOTEL_QUESTION])

    return _join(blocks)


# --- รายงาน "ความฝัน" (เช้าหลัง consolidation ตี 2) ---------------------------


def _idle_period(days: int | None) -> str | None:
    """'ไม่ได้ใช้มา 2 เดือน' — ปัดลงเสมอ

    ปัดลงเพราะข้อความนี้เป็นคำรับประกันขั้นต่ำ ("อย่างน้อยเท่านี้")
    ปัดขึ้นเมื่อไหร่กลายเป็นพูดเกินจริงเรื่องอายุของความจำที่เพิ่งพักไป
    """
    if days is None or days <= 0:
        return None
    if days >= 30:
        return f"{days // 30} เดือน"
    return f"{days} วัน"


def render_dream_report(summary: dict) -> str:
    """รายงานตอนเช้าว่าเมื่อคืนจัดระเบียบความจำอะไรไปบ้าง

    รับ dict ที่ memory.consolidate() คืนมาตรงๆ

    ทำไมต้องมีข้อความนี้ (red-team H13):
        "consolidation ตอนตี 2 ที่ mark archived เอง = ความจำหายเงียบๆ
         โดยไม่มีใครตรวจ → ให้รายงานทุกเช้าว่าตัดอะไรไป และให้กู้คืนได้"
    ทุกก้อนที่ถูกพักต้องปรากฏเป็นตัวเลขในนี้ และต้องบอกวิธีไปดูของจริงเสมอ
    """
    archived_count = _int(summary.get("archived_count")) or 0
    merged = summary.get("merged_topics") or []
    skipped = summary.get("skipped") or []

    if not archived_count and not merged and not skipped:
        return DREAM_NOTHING  # หลักการข้อ 4: ไม่มีอะไรเปลี่ยนก็บรรทัดเดียวจบ

    blocks: list[list[str]] = [[DREAM_GREETING]]

    for entry in list(merged)[:DREAM_TOPIC_LIMIT]:
        topic = _text(_attr(entry, "topic"))
        kept = _int(_attr(entry, "kept")) or 0
        merged_from = _int(_attr(entry, "merged_from"))
        archived = _int(_attr(entry, "archived")) or 0
        if merged_from is None:
            merged_from = archived + kept
        if kept == 1:
            head = f"รวมเรื่องซ้ำ {merged_from} ก้อนเป็นก้อนเดียว"
        elif kept > 1:
            head = f"รวมเรื่องซ้ำ {merged_from} ก้อนเหลือ {kept} ก้อน"
        else:
            # ไม่เหลือก้อนที่ยังใช้อยู่เลย = พักไปทั้งเรื่อง ห้ามเรียกว่า "รวม"
            head = f"พักเรื่องซ้ำไปทั้ง {archived} ก้อน"
        lines = [head]
        if topic:
            lines.append(f"(เรื่อง{topic})")
        blocks.append(lines)

    if len(merged) > DREAM_TOPIC_LIMIT:
        blocks.append([f"(และอีก {len(merged) - DREAM_TOPIC_LIMIT} เรื่อง)"])

    if archived_count:
        period = _idle_period(_int(summary.get("unused_days")))
        head = f"พักไว้ {archived_count} ก้อน"
        if period:
            head += f"ที่ไม่ได้ใช้มา {period}"
        blocks.append([head, DREAM_HINT])

    if skipped:
        # ข้ามแล้วเงียบ = ความจำหายโดยไม่มีใครตรวจแบบเดียวกับที่ H13 ห้ามไว้
        blocks.append([f"⚠️ ข้าม {len(skipped)} ก้อนที่อ่านเวลาไม่ออก ต้องไปดูเอง"])

    return _join(blocks)


# --- ตอบตอนสั่งงาน (kit ส่วนที่ 1 หัวข้อ "ตอบตอนสั่งงาน") ----------------------
# สัญญาใน CONTRACTS.md ไม่ได้ตรึง 4 ฟังก์ชันนี้ไว้ (ตรึงแค่ 4 render หลัก + aqi_label)
# จึงเป็นของเพิ่ม ไม่ใช่การแก้ของเดิม — เพราะข้อความ 3 แบบนี้อยู่ใน kit ส่วนที่ 1
# เท่ากับอีก 4 แบบ และเป็นจุดที่บุคลิก "ห้ามรายงานเรียบร้อยถ้ายังไม่ยืนยัน" ต้องบังคับจริง


def render_call_ack() -> str:
    """ตอบรับตอนเริ่มโทร — ยังไม่รู้ผล จึงห้ามมีคำว่าเรียบร้อยเด็ดขาด"""
    return CALL_ACK


def render_booking_reply(
    place: str,
    date_text: str | None = None,
    time_text: str | None = None,
    party_size: int | None = None,
    *,
    confirmed: bool,
    booked_name: str | None = None,
    calendar_added: bool = False,
    note: str | None = None,
) -> str:
    """ผลการจอง

        เรียบร้อยครับ ✅
        [X] พรุ่งนี้ 18:00 4 ที่ ชื่อโอม
        ใส่ปฏิทินให้แล้ว

    confirmed เป็นพารามิเตอร์บังคับแบบ keyword ตั้งใจให้ผู้เรียก "ต้องตอบ"
    ว่ายืนยันแล้วจริงไหม จะลืมไม่ได้ — บุคลิกข้อความซื่อสัตย์:
    "ห้ามรายงานว่าเรียบร้อย ถ้ายังไม่ได้ยืนยันว่าสำเร็จจริง"
    และเมื่อยังไม่สำเร็จ จะไม่พิมพ์ว่าใส่ปฏิทินให้แล้วด้วย แม้ผู้เรียกจะสั่งมา
    """
    detail = " ".join(
        part
        for part in (
            _text(place),
            _text(date_text),
            _text(time_text),
            f"{_int(party_size)} ที่" if _int(party_size) else None,
            f"ชื่อ{_text(booked_name)}" if _text(booked_name) else None,
        )
        if part
    )
    lines = [BOOKING_OK if confirmed else BOOKING_FAILED]
    if detail:
        lines.append(detail)
    if confirmed and calendar_added:
        lines.append(CALENDAR_ADDED)
    reason = _text(note)
    if reason:
        lines.append(reason)
    return _join([lines])


def render_routine_done(status: Any) -> str:
    """"ทำคิ้วแล้ว" → "บันทึกแล้วครับ รอบหน้า 24 ส.ค."

    รับ RoutineStatus ที่ mark_done() คืนมา (อ่านกลับจาก DB แล้ว)
    ไม่มี next_due ก็บอกแค่ว่าบันทึกแล้ว — ห้ามเดาวันรอบหน้าให้
    """
    next_due = _attr(status, "next_due")
    if next_due is None:
        return ROUTINE_SAVED
    try:
        return f"{ROUTINE_SAVED} รอบหน้า {localdate.thai_date_short(next_due)}"
    except (ValueError, TypeError):
        return ROUTINE_SAVED


def render_lesson_saved(
    topic: str | None = None,
    *,
    superseded: Any = None,
    follow_up: str | None = None,
) -> str:
    """"จำไว้ว่า..." → "จำแล้วครับ คราวนี้จะเตือนก่อน"

    superseded = lesson เก่าที่เพิ่งถูกทับ (ตัวที่ 2 ที่ memory.remember() คืนมา)
    ต้องบอกออกไปเสมอว่าทับอันไหน — บุคลิกข้อ "การเรียนรู้" และ CONTRACTS.md
    ระบุไว้ตรงๆ ว่า "lesson ใหม่ทับของเก่า → ต้องบอกว่าทับอันไหน"
    ทับเงียบๆ แปลว่าโอมไม่มีทางรู้ว่าความจำเดิมหายไปตอนไหน
    """
    head = LESSON_SAVED
    extra = _text(follow_up)
    if extra:
        head += f" {extra}"
    lines = [head]
    if superseded is not None:
        old = _text(_attr(superseded, "content")) or _text(_attr(superseded, "topic"))
        if old:
            lines.append(f"(ทับของเดิม: {old})")
    elif _text(topic):
        lines.append(f"(เรื่อง{_text(topic)})")
    return _join([lines])
