"""
tool กลางสำหรับ "จอง" ทุกชนิด — spec v3 Phase 3 ข้อ 1 และ 2

ทำไมต้องเป็น tool เดียว ไม่ใช่ tool ละชนิด (spec v3 Phase 3 ข้อ 1):
    ร้านอาหาร / ทำคิ้ว / เลเซอร์ / โรงแรม ต่างกันแค่ "ร้านไหน" กับ "ถามอะไรบ้าง"
    ขั้นตอนจริงเหมือนกันหมด: หาร้าน → นัดวันเวลา → โทร → บันทึกผล
    ถ้าแตกเป็น 4 tool ตรรกะ "ซองคำตอบล่วงหน้า" จะถูกก๊อปไป 4 ที่ แล้วแก้ไม่ครบ

ขอบเขตของไฟล์นี้ — **ไม่โทรจริง**:
    ที่นี่คือชั้นข้อมูล + ชั้นตัดสินใจเท่านั้น ไม่มี Twilio / Vapi / network / API key
    Phase 3 จะต่อชั้นโทรเข้ามาทีหลังโดย **ไม่ต้องแก้ signature ในไฟล์นี้**
    (กฎเหล็กข้อ 2 ของ CONTRACTS.md: core/ ต้อง deterministic เทสต์รันได้โดยไม่มีเน็ต)
    ชั้นโทรจะทำงานเป็น: make_booking() → answer_envelope() → ถามโอม → โทร →
    update_status() ทุกก้าวคุยกับโมดูลนี้ผ่านฟังก์ชัน 4 ตัวข้างล่างเท่านั้น

"ซองคำตอบล่วงหน้า" คืออะไร (spec v3 Phase 3 ข้อ 2 — คำตอบของโจทย์ที่ค้างมานาน):
    ปัญหา: ระหว่างอยู่บนสาย พนักงานตอบว่า "18:00 เต็ม" AI ต้องตัดสินใจเดี๋ยวนั้น
    จะถามโอมก่อนก็ไม่ทัน — H5 บอกว่าเงียบเกิน 3 วินาทีบนสายจริง = โดนวางสาย
    ทางแก้หลัก  = ถามล่วงหน้า **ก่อนโทร** ว่า "ถ้า 18:00 เต็ม เอา 19:30 / 20:00 ไหม"
                  → AI ตัดสินใจเองได้ในกรอบที่โอมอนุมัติไว้แล้ว ไม่ต้องเงียบรอ
    ทางแก้สำรอง = เจอคำถามนอกกรอบ → วางสายแล้วโทรกลับ ห้ามให้พนักงานถือสายเกิน 10 วิ
                  (ชั้นโทรเป็นคนทำ ไฟล์นี้แค่บอกว่ากรอบที่อนุมัติไว้คืออะไร)
    ตัวเลือกสุดท้ายต้องเป็น "ไม่เอา ให้โทรกลับมาถาม" **เสมอ** — ซองคำตอบเป็นการมอบอำนาจ
    ไม่ใช่การบังคับ ถ้าไม่มีทางออกนี้ โอมจะถูกบีบให้ผูกมัดล่วงหน้าทุกครั้งที่สั่งจอง

หมายเหตุเรื่องชื่อพารามิเตอร์ฉีดเวลา:
    CONTRACTS.md ตรึงไว้ว่าโมดูลนี้ใช้ `when` (เหมือน friday.py / routines.py) ไม่ใช่ `clock`
    หน้าที่เดียวกันคือให้เทสต์กำหนดวันเองได้ แต่รับกว้างกว่า (str / date / datetime)
    ห้ามเปลี่ยนชื่อ โมดูลอื่นถูกเขียนขนานกันโดยอิงสัญญานี้
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import sqlite3
from collections.abc import Iterable
from typing import Any, NamedTuple

from . import localdate

# ชนิดการจองที่รองรับ — ต้องตรงกับ CHECK ของตาราง bookings ใน schema/001_init.sql
# ประกาศไว้ที่นี่ด้วยเพื่อให้ตอบ ValueError ที่อ่านรู้เรื่องได้ก่อนถึงมือ SQLite
# (IntegrityError จาก CHECK บอกแค่ว่าผิด ไม่บอกว่ามีอะไรให้เลือกบ้าง)
RESTAURANT = "restaurant"
EYEBROW = "eyebrow"
LASER = "laser"
HOTEL = "hotel"
KINDS: tuple[str, ...] = (RESTAURANT, EYEBROW, LASER, HOTEL)

PENDING = "pending"
CALLING = "calling"
CONFIRMED = "confirmed"
FAILED = "failed"
CANCELLED = "cancelled"
NEEDS_INPUT = "needs_input"
STATUSES: tuple[str, ...] = (PENDING, CALLING, CONFIRMED, FAILED, CANCELLED, NEEDS_INPUT)

# ข้อความตัวเลือก "ขอไม่ตัดสินใจล่วงหน้า" — คัดจาก spec v3 Phase 3 ข้อ 2 ตรงตัว
# อยู่เป็นค่าคงที่เพื่อให้ชั้นโทรเทียบด้วย is_opt_out() ได้ ไม่ต้องพิมพ์สตริงซ้ำ
# (สตริงไทยที่พิมพ์ซ้ำหลายที่ = วันหนึ่งจะมีที่ใดที่หนึ่งเว้นวรรคไม่เหมือนกันแล้วเทียบไม่ติด)
OPT_OUT = "ไม่เอา ให้โทรกลับมาถาม"

# เวลาที่รับได้: 'HH:MM' หรือ 'HH.MM' (คนไทยพิมพ์จุดบ่อยพอๆ กับโคลอน)
_TIME_RE = re.compile(r"^(\d{1,2})[:.](\d{2})$")

DateLike = str | _dt.date | _dt.datetime
TimeLike = str | _dt.time | _dt.datetime


class BookingRequest(NamedTuple):
    """คำขอจองหนึ่งใบในรูปที่ชั้นโทรเอาไปใช้ได้ทันที

    ตั้งใจให้เป็นค่าที่ normalize แล้ว: date เป็น 'YYYY-MM-DD' เวลาไทย,
    time/fallback_slots เป็น 'HH:MM' — ชั้นโทรจะได้ไม่ต้องเดารูปแบบเองอีกรอบ
    """

    kind: str
    place: str
    date: str
    time: str | None
    party_size: int | None
    fallback_slots: list[str]


def _today(when: DateLike | None = None) -> _dt.date:
    """วันอ้างอิงของโมดูลนี้ — ประตูเดียวที่ถามว่า "วันนี้วันไหน"

    ต้องผ่าน core.localdate เสมอ (กฎเหล็กข้อ 1) เพราะ 00:30 คืนวันที่ 21 ตามเวลาไทย
    ยังเป็นวันที่ 20 ในสายตา UTC — จองโต๊ะไว้ผิดวันหนึ่งวันเต็มๆ โดยไม่มีอะไรฟ้อง
    """
    if when is None:
        return localdate.local_date()
    return localdate.to_date(when)


def _normalize_kind(kind: str) -> str:
    """ตรวจชนิดการจองก่อนแตะฐานข้อมูล — ผิด = ValueError พร้อมบอกตัวเลือกที่มี"""
    key = str(kind or "").strip().lower()
    if key not in KINDS:
        raise ValueError(
            f"kind ต้องเป็นอย่างใดอย่างหนึ่งใน {', '.join(KINDS)} — ได้รับ {kind!r}"
        )
    return key


def _normalize_time(value: TimeLike | None) -> str | None:
    """แปลงเวลาให้เป็น 'HH:MM' เวลาไทย — ค่าที่อ่านไม่ออกต้องระเบิด ไม่ใช่เดา

    ยอมรับ datetime ด้วย เผื่อชั้นบนแปลง "พรุ่งนี้ 6 โมงเย็น" มาเป็น datetime ทีเดียว
    แล้วส่งตัวเดียวกันมาทั้งช่อง date และ time — ตรงนั้นต้องอ่านเป็นเวลาไทย ไม่ใช่ UTC
    ไม่รับเลขลอยๆ อย่าง '6' เพราะแปลได้ทั้ง 06:00 และ 18:00 ซึ่งพลาดแล้วคือไปผิดเวลา
    """
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return localdate.now(value).strftime("%H:%M")
    if isinstance(value, _dt.time):
        return f"{value.hour:02d}:{value.minute:02d}"
    text = str(value).strip()
    if not text:
        return None
    match = _TIME_RE.match(text)
    if match is None:
        raise ValueError(f"เวลาต้องอยู่ในรูป 'HH:MM' (24 ชั่วโมง) — ได้รับ {value!r}")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f"เวลาไม่มีอยู่จริง: {value!r}")
    return f"{hour:02d}:{minute:02d}"


def _normalize_slots(slots: Iterable[TimeLike] | str | None, primary: str | None) -> list[str]:
    """จัดซองคำตอบให้เรียบร้อย: เป็น 'HH:MM' ทุกช่อง ไม่ซ้ำ และไม่มีเวลาหลักปนอยู่

    เรียงตามลำดับที่โอมให้มา ไม่เรียงใหม่ตามเวลา — ลำดับคือความชอบ
    ("19:30 ก่อน 20:00" ไม่เหมือน "20:00 ก่อน 19:30" ต่อให้เป็นเวลาชุดเดียวกัน)

    ตัดเวลาหลักออกเพราะ "ถ้า 18:00 เต็ม เอา 18:00" คือตัวเลือกที่ไม่มีความหมาย
    ถ้าปล่อยไว้ AI จะเสนอกลับไปให้พนักงานทั้งที่เพิ่งได้ยินมาว่าเต็ม
    """
    if slots is None:
        return []
    # สตริงเดี่ยวๆ ('19:30') วนลูปแล้วได้ทีละตัวอักษร — ดักไว้ก่อนจะกลายเป็นซองเน่า
    items: Iterable[TimeLike] = [slots] if isinstance(slots, str) else slots
    out: list[str] = []
    for raw in items:
        slot = _normalize_time(raw)
        if slot is None or slot == primary or slot in out:
            continue
        out.append(slot)
    return out


def _normalize_party_size(party_size: int | str | None) -> int | None:
    """จำนวนคน — None ได้ (ทำคิ้ว/เลเซอร์ไม่มีจำนวนคน) แต่ 0 หรือติดลบไม่ได้

    ดักที่นี่แทนปล่อยให้ CHECK ของ schema เป็นคนฟ้อง เพราะ IntegrityError
    ไม่ได้บอกว่าคอลัมน์ไหนผิด ตอนไล่บั๊กจากข้อความในแชทจะหาไม่เจอ
    """
    if party_size is None:
        return None
    try:
        size = int(party_size)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"party_size ต้องเป็นจำนวนเต็ม — ได้รับ {party_size!r}") from exc
    if size <= 0:
        raise ValueError(f"party_size ต้องมากกว่า 0 — ได้รับ {party_size!r}")
    return size


def _adhoc_place(conn: sqlite3.Connection, kind: str, name: str) -> sqlite3.Row:
    """สร้างแถวร้านชั่วคราวที่หน้าตาเหมือน favorite_places แต่ไม่ได้เก็บลงตาราง

    ทำไมไม่ยก LookupError ทิ้งไปเลยเมื่อหาร้านในรายการโปรดไม่เจอ:
        คำสั่งจริงจาก kit ส่วนที่ 1 คือ "จองร้าน X พรุ่งนี้ 6 โมงเย็น 4 คน"
        ร้าน X ส่วนใหญ่ไม่เคยอยู่ใน favorite_places มาก่อน การบังคับให้เพิ่มร้านโปรด
        ก่อนจองได้ = ใช้งานไม่ได้จริง (และ schema ก็ตั้ง place_id ให้เป็น NULL ได้อยู่แล้ว)
    LookupError สงวนไว้สำหรับกรณีที่ "ไม่ระบุร้าน และไม่มีร้านประจำให้เดา" เท่านั้น
    """
    return conn.execute(
        "SELECT NULL AS id, ? AS kind, ? AS name, NULL AS phone, NULL AS notes, 0 AS is_default",
        (kind, name),
    ).fetchone()


def resolve_place(
    conn: sqlite3.Connection, kind: str, place: str | None = None
) -> sqlite3.Row:
    """หาว่า "ร้านไหน" — ไม่ระบุชื่อ = ใช้ร้านประจำของชนิดนั้น

    ลำดับการหาเมื่อระบุชื่อมา:
        1) ชื่อตรงกันทั้งคำ (ไม่สนตัวพิมพ์เล็กใหญ่) ภายใน kind เดียวกัน
        2) ชื่อเป็นส่วนหนึ่งของร้านโปรดร้านเดียวเท่านั้น ('Sushiro' → 'Sushiro เมญ่า')
           ถ้าเข้าเงื่อนไขหลายร้านถือว่ากำกวม ไม่เดา ให้ถือเป็นร้านนอกรายการไปเลย
        3) ไม่เข้าเงื่อนไขไหน → ร้านนอกรายการ (place_id = NULL) จองได้ตามปกติ

    ไม่ระบุชื่อ + ไม่มีร้านประจำของ kind นั้น → LookupError (ตามสัญญา CONTRACTS.md)
    """
    kind_key = _normalize_kind(kind)
    name = str(place or "").strip()

    if not name:
        row = conn.execute(
            "SELECT * FROM favorite_places WHERE kind = ? AND is_default = 1", (kind_key,)
        ).fetchone()
        if row is None:
            raise LookupError(
                f"ไม่ได้ระบุร้าน และยังไม่มีร้านประจำของ '{kind_key}' ในตาราง favorite_places\n"
                f"ระบุชื่อร้านมาด้วย หรือตั้งร้านประจำก่อน:\n"
                f"  INSERT INTO favorite_places (kind, name, phone, is_default)\n"
                f"  VALUES ('{kind_key}', 'ชื่อร้าน', 'เบอร์', 1);"
            )
        return row

    exact = conn.execute(
        "SELECT * FROM favorite_places WHERE kind = ? AND name = ? COLLATE NOCASE",
        (kind_key, name),
    ).fetchone()
    if exact is not None:
        return exact

    # ค้นแบบบางส่วน — เอาเฉพาะตอนที่เหลือร้านเดียว ความกำกวมต้องไม่ถูกเดาแทนโอม
    partial = conn.execute(
        "SELECT * FROM favorite_places WHERE kind = ? AND name LIKE ? COLLATE NOCASE ORDER BY id",
        (kind_key, f"%{name}%"),
    ).fetchall()
    if len(partial) == 1:
        return partial[0]
    return _adhoc_place(conn, kind_key, name)


def make_booking(
    conn: sqlite3.Connection,
    kind: str,
    place: str | None = None,
    date: DateLike | None = None,
    time: TimeLike | None = None,
    party_size: int | str | None = None,
    fallback_slots: Iterable[TimeLike] | str = (),
    when: DateLike | None = None,
) -> int:
    """บันทึกคำขอจอง 1 ใบ สถานะ 'pending' คืน booking id

    **ไม่โทรจริงในขั้นนี้** — สถานะ 'pending' แปลว่า "รับเรื่องแล้ว ยังไม่ได้ทำ"
    ชั้นโทรของ Phase 3 จะเป็นคนขยับเป็น calling → confirmed/failed ผ่าน update_status()
    ตราบใดที่ยังไม่ถึง confirmed ห้ามตอบโอมว่า "เรียบร้อย" (บุคลิกข้อความซื่อสัตย์)

    date เว้นว่างได้ = วันนี้ตามเวลาไทย ("จองร้านประจำเย็นนี้") — ไม่ใช่ค่าว่างใน DB
    เพราะ booking_date เป็น NOT NULL และการจองที่ไม่มีวันคือการจองที่โทรไม่ได้

    created_at / updated_at ปล่อยให้ DEFAULT ของ schema เติม (datetime('now') = UTC)
    ตั้งใจ ไม่ขัดกฎเหล็กข้อ 1: สองคอลัมน์นั้นเป็น metadata ว่าแถวถูกแตะเมื่อไหร่
    ไม่มีตรรกะธุรกิจไหนอ่านมันไปคำนวณวัน ส่วนวันของการจองจริงอยู่ที่ booking_date
    ซึ่งมาจาก localdate เสมอ (002_seed.sql อธิบายหลักการเดียวกันนี้ไว้)
    """
    kind_key = _normalize_kind(kind)
    place_row = resolve_place(conn, kind_key, place)
    date_key = _today(when).isoformat() if date is None else localdate.to_date(date).isoformat()
    time_key = _normalize_time(time)
    slots = _normalize_slots(fallback_slots, time_key)
    size = _normalize_party_size(party_size)

    cursor = conn.execute(
        """INSERT INTO bookings
             (kind, place_name, place_id, booking_date, booking_time,
              party_size, status, fallback_slots)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            kind_key,
            place_row["name"],
            place_row["id"],
            date_key,
            time_key,
            size,
            PENDING,
            # เก็บซองเป็น JSON ตามที่ schema ระบุ ensure_ascii=False เพื่อให้อ่านออกตอนเปิดดู DB เอง
            json.dumps(slots, ensure_ascii=False) if slots else None,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _load_slots(raw: str | None) -> list[str]:
    """อ่านซองคำตอบกลับจากคอลัมน์ JSON — ข้อมูลเพี้ยนต้องดัง ไม่ใช่คืนลิสต์ว่าง

    คืนลิสต์ว่างเงียบๆ จะกลายเป็น "โทรไปโดยไม่มีกรอบที่โอมอนุมัติ" ซึ่งอันตรายกว่าพัง
    """
    if raw is None or not str(raw).strip():
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"fallback_slots ในฐานข้อมูลไม่ใช่ JSON: {raw!r}") from exc
    if not isinstance(value, list):
        raise ValueError(f"fallback_slots ต้องเป็นลิสต์ของเวลา — ได้รับ {raw!r}")
    out: list[str] = []
    for item in value:
        slot = _normalize_time(item)
        if slot is not None:
            out.append(slot)
    return out


def _fetch(conn: sqlite3.Connection, booking_id: int) -> sqlite3.Row:
    """หาแถวการจอง — ไม่เจอ = KeyError

    ห้ามเงียบ: update_status ที่ไม่โดนแถวไหนเลยแล้วคืน None เฉยๆ จะทำให้ชั้นบน
    รายงานโอมว่าอัปเดตแล้วทั้งที่ไม่มีอะไรเปลี่ยน — ตรงกับข้อห้าม "เรียบร้อยทั้งที่ยังไม่จริง"
    """
    row = conn.execute("SELECT * FROM bookings WHERE id = ?", (int(booking_id),)).fetchone()
    if row is None:
        raise KeyError(f"ไม่มีการจอง id={booking_id!r} ในฐานข้อมูล")
    return row


def request_for(conn: sqlite3.Connection, booking_id: int) -> BookingRequest:
    """ประกอบ BookingRequest กลับจากแถวที่บันทึกไว้

    มีไว้ให้ชั้นโทรของ Phase 3 ทำงานต่อจาก id ที่ make_booking คืนมาได้เลย
    (make_booking → request_for → answer_envelope → ถามโอม → โทร → update_status)
    ไม่ได้อยู่ใน CONTRACTS.md แต่เป็นฟังก์ชัน "เพิ่มใหม่" ไม่ได้แก้ของเดิม จึงไม่ผิดสัญญา
    """
    row = _fetch(conn, booking_id)
    return BookingRequest(
        kind=row["kind"],
        place=row["place_name"],
        date=row["booking_date"],
        time=row["booking_time"],
        party_size=row["party_size"],
        fallback_slots=_load_slots(row["fallback_slots"]),
    )


def is_opt_out(option: str) -> bool:
    """ตัวเลือกนี้คือ "ขอไม่ตัดสินใจล่วงหน้า" ใช่ไหม

    ให้ชั้นโทรเทียบผ่านฟังก์ชันนี้ ไม่ต้องพิมพ์สตริงไทยซ้ำในโค้ดตัวเอง
    """
    return str(option).strip() == OPT_OUT


def answer_envelope(req: BookingRequest) -> dict[str, Any]:
    """"ซองคำตอบล่วงหน้า" — spec v3 Phase 3 ข้อ 2 กลไกหลัก

    คืนของสำหรับสร้าง Quick Reply: {'question': ..., 'options': [...], 'opt_out': ...}
    ตัวอย่างจาก spec: "ถ้า 18:00 เต็ม เอา [19:30] [20:00] [ไม่เอา ให้โทรกลับมาถาม]"

    ตัวเลือกสุดท้ายเป็น OPT_OUT เสมอ ไม่มีข้อยกเว้น แม้ไม่มีเวลาสำรองสักช่อง —
    ในกรณีนั้นซองจะเหลือปุ่มเดียวคือ "ไม่เอา ให้โทรกลับมาถาม" ซึ่งเป็นคำตอบที่ตรงความจริง
    ("ยังไม่มีกรอบให้ตัดสินใจแทน เจอเต็มเมื่อไหร่ต้องกลับมาถาม") ดีกว่าไม่ส่งซองไปเลย
    แล้วปล่อยให้ AI คิดเองบนสาย

    ใส่ชื่อร้านกับวันลงในคำถามด้วย เพราะซองถูกส่งไปตอนโอมอาจกำลังทำอย่างอื่นอยู่
    ถ้าเห็นแค่ "ถ้า 18:00 เต็ม เอาเวลาไหน" จะไม่รู้ว่าร้านไหน วันไหน แล้วต้องเลื่อนหาย้อนหลัง
    (kit หลักการข้อ 1: ข้อความเดียวจบ)
    """
    primary = _normalize_time(req.time)
    slots = _normalize_slots(req.fallback_slots, primary)
    day = localdate.thai_date_short(req.date) if req.date else ""

    head = " ".join(part for part in (str(req.place or "").strip(), day) if part)
    if primary:
        body = f"ถ้า {primary} เต็ม เอาเวลาไหนแทน"
    else:
        # ไม่มีเวลาหลัก (เช่นจองโรงแรมทั้งวัน) — ถามเป็นกรณี "ถ้าไม่ว่าง" แทน
        body = "ถ้าไม่ว่าง เอายังไงต่อ"
    question = f"{head} — {body}" if head else body

    return {
        "question": question,
        "options": [*slots, OPT_OUT],
        "opt_out": OPT_OUT,
    }


def update_status(
    conn: sqlite3.Connection,
    booking_id: int,
    status: str,
    result_note: str | None = None,
) -> None:
    """อัปเดตสถานะการจอง — 'confirmed' ต้องมี result_note เสมอ

    บังคับในโค้ด ไม่ใช่แค่เขียนไว้ใน prompt เพราะบุคลิกข้อ "ความซื่อสัตย์" ระบุว่า
        "ห้ามรายงานว่า 'เรียบร้อย' ถ้ายังไม่ได้ยืนยันว่าสำเร็จจริง"
    prompt เป็นคำขอร้องต่อ LLM ซึ่งวันหนึ่งจะไม่ทำตามได้ ส่วน ValueError ตรงนี้ไม่มีวันไม่ทำตาม
    result_note คือ "ร้านตอบว่าอะไร" — ถ้าไม่มีใครจดไว้ แปลว่าไม่มีใครยืนยัน
    จึงยังไม่มีสิทธิ์ขึ้นสถานะ confirmed แล้วไปบอกโอมว่าจองได้แล้ว

    result_note = None แปลว่า "ไม่ได้แก้หมายเหตุ" ไม่ใช่ "ลบหมายเหตุ" (ใช้ COALESCE) —
    ยกเลิกการจองทีหลังไม่ควรลบคำตอบของร้านที่จดไว้ตอนโทร นั่นคือหลักฐานว่าเกิดอะไรขึ้น

    updated_at ใช้ datetime('now') ของ SQLite: ฟังก์ชันนี้ไม่มีพารามิเตอร์ฉีดเวลาตามสัญญา
    และคอลัมน์นี้เป็น metadata ของแถว ไม่มีตรรกะธุรกิจอ่านไปคำนวณวัน (ดู make_booking)
    """
    key = str(status or "").strip().lower()
    if key not in STATUSES:
        raise ValueError(
            f"status ต้องเป็นอย่างใดอย่างหนึ่งใน {', '.join(STATUSES)} — ได้รับ {status!r}"
        )

    note = None if result_note is None else str(result_note).strip()
    if key == CONFIRMED and not note:
        raise ValueError(
            "ตั้งสถานะ 'confirmed' ไม่ได้ถ้าไม่มี result_note — "
            "ต้องบันทึกก่อนว่าร้านยืนยันว่าอะไร (ห้ามรายงานว่าเรียบร้อยถ้ายังไม่ได้ยืนยันว่าสำเร็จจริง)"
        )

    row = _fetch(conn, booking_id)
    conn.execute(
        """UPDATE bookings
              SET status      = ?,
                  result_note = COALESCE(?, result_note),
                  updated_at  = datetime('now')
            WHERE id = ?""",
        (key, note or None, row["id"]),
    )
    conn.commit()
