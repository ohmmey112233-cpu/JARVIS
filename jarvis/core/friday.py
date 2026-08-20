"""
ศุกร์สลับสัปดาห์ — กลับบ้านจอมทอง (home) สลับกับค้างในเมืองเชียงใหม่ (hotel)

ทำไมโมดูลนี้ถึงเป็นจุดเสี่ยงที่สุดของ Phase 1:
    ทั้งระบบแขวนอยู่บนค่าตั้งต้นค่าเดียวคือ preference 'friday_anchor_date'
    ถ้า anchor ตั้งผิดด้าน ทุกศุกร์จะสลับผิดหมดทั้งปีโดยไม่มีอะไรฟ้อง
    (phase1-kit ส่วนที่ 3: "ถ้าผิด ระบบจะสลับกลับด้านทั้งหมด",
     checklist B: "ผิดแค่ครั้งเดียวคือ anchor ตั้งผิด ต้องแก้")

    red-team H10: Sushiro จองโต๊ะไว้ในศุกร์ที่โอมกลับจอมทอง = no-show ซ้ำๆ
    ซึ่งทำให้บัญชีโดนแบนเร็วกว่าเรื่อง ToS เสียอีก
    → โมดูลนี้จึงเลือก "ระเบิดดังๆ" (ValueError / MissingPreference)
      แทนการเดาค่าเงียบๆ ทุกกรณีที่ข้อมูลไม่ชัด

หมายเหตุเรื่องชื่อพารามิเตอร์:
    CONTRACTS.md ตรึงชื่อพารามิเตอร์ตัวสุดท้ายของโมดูลนี้ไว้ว่า `when`
    (ไม่ใช่ `clock` เหมือนโมดูลอื่น) — `when` ทำหน้าที่ฉีดเวลาแทนได้เหมือนกัน
    เพราะรับ datetime ได้ และ localdate.to_date() จะแปลงเป็นวันแบบเวลาไทยให้
    ห้ามเปลี่ยนชื่อเพราะโมดูลอื่นถูกเขียนขนานกันโดยอิงสัญญาเดิม
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import NamedTuple

from . import db, localdate

HOME = "home"  # ศุกร์ที่กลับบ้านจอมทอง
HOTEL = "hotel"  # ศุกร์ที่อยู่เชียงใหม่ (สัปดาห์โรงแรม)

STATES = (HOME, HOTEL)

# คีย์ใน preferences ที่เก็บ anchor — ประกาศไว้ที่เดียวเพื่อไม่ให้พิมพ์ผิดกระจาย
PREF_KEY = "friday_anchor_date"

# รูปแบบค่าที่ยอมรับ ใช้ทั้งในข้อความ error และในเอกสาร setup
PREF_FORMAT = "'YYYY-MM-DD:home' หรือ 'YYYY-MM-DD:hotel' (เช่น '2026-08-14:home')"


class FridayPlan(NamedTuple):
    """สถานะของ "ศุกร์ประจำสัปดาห์" ที่วันหนึ่งๆ ตกอยู่

    weeks_from_anchor เป็นค่าติดลบได้ (วันก่อน anchor) เพราะ digest ย้อนหลัง
    และการดีบัก anchor ต้องดูออกว่าเราอยู่ "ก่อน" หรือ "หลัง" จุดตั้งต้นกี่สัปดาห์
    """

    friday: date
    state: str
    is_home: bool
    weeks_from_anchor: int


def _normalize_state(value: str) -> str:
    """รับสถานะจากคนกรอก → คืนค่ามาตรฐาน หรือระเบิดถ้าไม่รู้จัก

    ยอมให้เว้นวรรค/ตัวพิมพ์ใหญ่เพี้ยนได้ เพราะค่านี้พิมพ์ด้วยมือใน SQL
    แต่ห้ามเดาค่าที่สะกดไม่ตรง — เดาผิดด้าน = สลับผิดทั้งปี
    """
    state = str(value).strip().lower()
    if state not in STATES:
        raise ValueError(
            f"สถานะศุกร์ต้องเป็น '{HOME}' หรือ '{HOTEL}' เท่านั้น ได้รับ {value!r}"
        )
    return state


def _flip(state: str) -> str:
    """สลับด้าน — มีแค่ 2 สถานะ สลับคือเปลี่ยนไปอีกอัน"""
    return HOTEL if state == HOME else HOME


def _anchor_friday(anchor_date: str | date | datetime) -> date:
    """แปลง anchor ให้เป็น date พร้อมยืนยันว่าเป็นวันศุกร์จริง

    ไม่ปัดให้เป็นศุกร์ที่ใกล้ที่สุดโดยอัตโนมัติ เพราะ anchor ที่ไม่ใช่ศุกร์
    แปลว่าคนกรอกเข้าใจผิดตั้งแต่ต้น (kit บอกให้กรอก "ศุกร์ล่าสุดที่ผ่านมา")
    ปัดให้เงียบๆ = ซ่อนความเข้าใจผิดนั้นไว้จนกว่าจะจองผิดวันจริง
    """
    anchor = localdate.to_date(anchor_date)
    if anchor.weekday() != localdate.FRIDAY:
        raise ValueError(
            f"anchor ต้องเป็นวันศุกร์เท่านั้น แต่ {anchor.isoformat()} เป็นวัน"
            f"{localdate.thai_day_name(anchor)} — แก้ค่า '{PREF_KEY}' ให้เป็น"
            f"ศุกร์ล่าสุดที่ผ่านมา"
        )
    return anchor


def friday_state(
    anchor_date: str | date | datetime,
    anchor_state: str,
    when: str | date | datetime | None = None,
) -> FridayPlan:
    """สถานะของศุกร์ในสัปดาห์ที่ `when` ตกอยู่

    เสาร์/อาทิตย์นับเป็นสัปดาห์เดียวกับศุกร์ที่เพิ่งผ่านมา — ใช้
    localdate.friday_of_week() ตัดสิน ไม่คิดเองซ้ำ (นิยามสัปดาห์ต้องมีที่เดียว)
    """
    anchor = _anchor_friday(anchor_date)
    state_at_anchor = _normalize_state(anchor_state)

    target = when if when is not None else localdate.local_date()
    friday = localdate.friday_of_week(target)

    delta_days = localdate.days_between(anchor, friday)
    # ปลายทางทั้งสองฝั่งเป็นวันศุกร์เสมอ ผลต่างจึงหาร 7 ลงตัวแน่นอน
    # floor division จึงไม่ปัดเพี้ยนแม้ delta ติดลบ (-14 // 7 == -2 พอดี)
    weeks = delta_days // 7

    # จุดพลาดคลาสสิก: ถ้าเก็บ weeks เป็นค่าสัมบูรณ์ จะบอกไม่ได้ว่าอยู่ก่อนหรือหลัง anchor
    # ส่วนการหาสถานะใช้ weeks % 2 ได้ตรงๆ เพราะ Python คืนค่าบวกเสมอเมื่อตัวหารเป็นบวก
    # (-1 % 2 == 1 → สลับด้าน ซึ่งถูกต้องสำหรับสัปดาห์ก่อน anchor)
    state = state_at_anchor if weeks % 2 == 0 else _flip(state_at_anchor)

    return FridayPlan(
        friday=friday,
        state=state,
        is_home=state == HOME,
        weeks_from_anchor=weeks,
    )


def _parse_anchor_pref(raw: str) -> tuple[date, str]:
    """แกะค่า 'YYYY-MM-DD:home' → (date, state)

    ใช้ rpartition เพื่อให้ค่าที่มีเวลาติดมาด้วย ('2026-08-14T00:00:home') ยังอ่านออก
    (ตัดที่ ':' ตัวขวาสุด ส่วนที่เหลือทั้งก้อนคือวันที่)
    ส่วนค่าที่ไม่มีเครื่องหมาย ':' เลย = คนกรอกลืมระบุด้าน ต้องไม่เดาให้
    """
    text = raw.strip()
    if ":" not in text:
        raise ValueError(
            f"preference '{PREF_KEY}' ต้องระบุทั้งวันและสถานะ — ได้รับ {raw!r}\n"
            f"รูปแบบที่ถูกต้อง: {PREF_FORMAT}"
        )

    date_part, _, state_part = text.rpartition(":")
    try:
        state = _normalize_state(state_part)
    except ValueError as exc:
        raise ValueError(
            f"preference '{PREF_KEY}' มีสถานะที่ไม่รู้จัก: {raw!r}\n"
            f"รูปแบบที่ถูกต้อง: {PREF_FORMAT}"
        ) from exc

    try:
        anchor = _anchor_friday(date_part)
    except ValueError as exc:
        # วันที่พังกับวันที่ไม่ใช่ศุกร์เป็นคนละความผิด แต่ทางแก้เดียวกันคือไปแก้ค่านี้
        # จึงห่อข้อความรูปแบบเข้าไปด้วยเสมอ ให้คนอ่าน error รู้ว่าต้องพิมพ์ยังไง
        raise ValueError(
            f"preference '{PREF_KEY}' ใช้ไม่ได้: {raw!r}\n"
            f"{exc}\n"
            f"รูปแบบที่ถูกต้อง: {PREF_FORMAT}"
        ) from exc

    return anchor, state


def friday_state_from_db(
    conn: sqlite3.Connection, when: str | date | datetime | None = None
) -> FridayPlan:
    """อ่าน anchor จาก preferences แล้วคำนวณสถานะศุกร์ของสัปดาห์ที่ `when` อยู่

    ใช้ require_pref() ไม่ใช่ get_pref() — ค่ายังไม่กรอกต้องได้ MissingPreference
    ทะลุขึ้นไปถึงผู้เรียก ไม่ใช่ default ที่ดูเหมือนทำงานได้แต่บอกด้านผิด
    """
    raw = db.require_pref(conn, PREF_KEY)
    anchor, state = _parse_anchor_pref(raw)
    return friday_state(anchor, state, when)


def is_in_chiang_mai_on_friday(
    conn: sqlite3.Connection, when: str | date | datetime | None = None
) -> bool:
    """ศุกร์ของสัปดาห์นั้นโอมอยู่ในตัวเมืองเชียงใหม่ไหม (ใช้โดย Sushiro, Phase 4)

    จอมทองอยู่ในจังหวัดเชียงใหม่ก็จริง แต่ห่างจากตัวเมืองราวชั่วโมงครึ่ง
    คำถามที่ Sushiro ต้องการคำตอบคือ "เย็นวันศุกร์ไปถึงร้านในเมืองได้ไหม"
    → สัปดาห์โรงแรมเท่านั้นที่ตอบว่าได้

    ไม่ดักจับ MissingPreference ไว้เอง: anchor ที่ยังไม่กรอกแล้วคืน False เงียบๆ
    จะทำให้ไม่มีใครรู้ว่าระบบจองหยุดทำงาน ปล่อยให้ Phase 4 ตัดสินใจว่าจะจัดการยังไง
    """
    return friday_state_from_db(conn, when).state == HOTEL
