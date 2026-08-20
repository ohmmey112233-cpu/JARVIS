"""
วันที่และเวลาแบบไทย — กฎเหล็กข้อ 3 ของ spec

ทุกจุดในระบบที่ถามว่า "วันนี้วันไหน" ต้องผ่านโมดูลนี้เท่านั้น
ห้ามเรียก date.today() หรือ datetime.now() ตรงๆ ที่ไหนอีก

เหตุผล (จาก jarvis-personal-os-analysis.md):
    เที่ยงคืน UTC = 07:00 เช้าไทย
    ถ้าใช้ UTC ตัดวัน routine จะรีเซ็ตตอน 7 โมงเช้า
    คือ "หลัง" digest เช้าส่งไปแล้วพอดี → ข้อมูลเพี้ยนทุกวันโดยไม่มีใครเห็น
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Bangkok")

# ชื่อวันภาษาไทย — index ตรงกับ date.weekday() (จันทร์=0 ... อาทิตย์=6)
THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
THAI_DAYS_SHORT = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
THAI_MONTHS_SHORT = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


def now(clock: datetime | None = None) -> datetime:
    """เวลาปัจจุบันตามเวลาไทย (timezone-aware เสมอ)

    clock = ฉีดเวลาเข้ามาเพื่อทดสอบ ถ้าส่ง naive datetime มาจะถือว่าเป็นเวลาไทย
    """
    if clock is None:
        return datetime.now(TZ)
    if clock.tzinfo is None:
        return clock.replace(tzinfo=TZ)
    return clock.astimezone(TZ)


def local_date(clock: datetime | None = None) -> date:
    """วันที่วันนี้ตามเวลาไทย"""
    return now(clock).date()


def local_date_key(clock: datetime | None = None) -> str:
    """คีย์วันที่แบบ YYYY-MM-DD ตามเวลาไทย — ใช้เป็นคีย์ใน DB ทุกที่

    นี่คือฟังก์ชันที่ spec สั่งให้มี ("localDateKey()") ใช้ทุกที่ที่ถามว่าวันนี้วันไหน
    """
    return local_date(clock).isoformat()


def to_date(value: str | date | datetime) -> date:
    """แปลงอะไรก็ตามให้เป็น date แบบเวลาไทย

    รับได้ทั้ง 'YYYY-MM-DD', date, datetime (aware หรือ naive)
    naive datetime ถือว่าเป็นเวลาไทยอยู่แล้ว
    """
    if isinstance(value, datetime):
        return now(value).date()
    if isinstance(value, date):
        return value
    text = value.strip()
    if not text:
        raise ValueError("วันที่ว่างเปล่า")
    # รองรับ ISO ที่มีเวลาต่อท้ายด้วย เช่น '2026-08-20T06:20:00+07:00'
    if "T" in text or " " in text:
        parsed = datetime.fromisoformat(text)
        return now(parsed).date()
    return date.fromisoformat(text)


def days_between(start: str | date | datetime, end: str | date | datetime) -> int:
    """จำนวนวันจาก start ถึง end (end - start) นับตามวันแบบเวลาไทย"""
    return (to_date(end) - to_date(start)).days


def thai_day_name(value: str | date | datetime, short: bool = False) -> str:
    """ชื่อวันภาษาไทยของวันที่นั้น"""
    idx = to_date(value).weekday()
    return THAI_DAYS_SHORT[idx] if short else THAI_DAYS[idx]


def thai_date_short(value: str | date | datetime) -> str:
    """วันที่แบบสั้นภาษาไทย เช่น '24 ส.ค.' — ใช้ในข้อความ digest"""
    d = to_date(value)
    return f"{d.day} {THAI_MONTHS_SHORT[d.month - 1]}"


def is_weekday(value: str | date | datetime) -> bool:
    """วันจันทร์-ศุกร์ไหม (ใช้ตัดสินว่าเป็นวันเรียนไหม)"""
    return to_date(value).weekday() <= FRIDAY


def next_weekday(value: str | date | datetime, weekday: int, *, allow_same_day: bool = False) -> date:
    """วัน <weekday> ถัดไปนับจาก value

    allow_same_day=True → ถ้า value เป็นวันนั้นอยู่แล้วจะคืน value เลย
    """
    if not 0 <= weekday <= 6:
        raise ValueError(f"weekday ต้องอยู่ระหว่าง 0-6 ได้รับ {weekday}")
    d = to_date(value)
    delta = (weekday - d.weekday()) % 7
    if delta == 0 and not allow_same_day:
        delta = 7
    return d + timedelta(days=delta)


def friday_of_week(value: str | date | datetime) -> date:
    """วันศุกร์ของสัปดาห์ที่ value อยู่ (สัปดาห์เริ่มวันจันทร์)

    เสาร์/อาทิตย์ถือว่าอยู่ในสัปดาห์เดียวกับศุกร์ที่เพิ่งผ่านมา
    ใช้เป็นฐานของตรรกะศุกร์สลับสัปดาห์ (ดู friday.py)
    """
    d = to_date(value)
    return d + timedelta(days=FRIDAY - d.weekday())


def days_until_month_end(value: str | date | datetime | None = None) -> int:
    """เหลืออีกกี่วันถึงสิ้นเดือน (วันสุดท้ายของเดือนนับเป็น 0)"""
    d = to_date(value) if value is not None else local_date()
    if d.month == 12:
        first_next = date(d.year + 1, 1, 1)
    else:
        first_next = date(d.year, d.month + 1, 1)
    return (first_next - timedelta(days=1) - d).days
