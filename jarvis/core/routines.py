"""
งานที่ทำเป็นรอบ — ไดโอดทุก 14 วัน / คิ้วทุก 7 วัน / ตัดผมทุกวันอังคาร

ทำไมโมดูลนี้ต้องระวังเรื่องเวลาเป็นพิเศษ:
    jarvis-personal-os-analysis ข้อ 3 เล่าถึงบั๊กคลาสสิกที่ระบบ habit รีเซ็ตผิดเวลา
    เพราะวันเปลี่ยนตอนเที่ยงคืน UTC ซึ่งตรงกับ 07:00 เช้าไทย
    คือ "หลัง" digest 06:20 ส่งไปแล้วพอดี → เตือนผิดวันทุกวันโดยไม่มีใครเห็น
    → ทุกคำถามว่า "วันนี้วันไหน" ในไฟล์นี้ผ่าน core.localdate เท่านั้น
      ไม่มี date.today() / datetime.now() / DATE('now') ของ SQLite ที่ไหนเลย

สองแบบที่ schema บังคับให้เลือกอย่างใดอย่างหนึ่ง (CHECK ใน 001_init.sql):
    interval_days → นับวันจากครั้งล่าสุด (ไดโอด 14, คิ้ว 7)
    day_of_week   → วันประจำในสัปดาห์ (ตัดผม = อังคาร)

หมายเหตุเรื่องชื่อพารามิเตอร์:
    CONTRACTS.md ตรึงพารามิเตอร์ฉีดเวลาของโมดูลนี้ไว้ว่าชื่อ `when` (เหมือน friday.py)
    ไม่ใช่ `clock` — ทำหน้าที่เดียวกันคือให้เทสต์กำหนดวันเองได้ แต่รับได้กว้างกว่า
    (str / date / datetime) เพราะโจทย์ของ routine คือ "วัน" ไม่ใช่ "เวลานาฬิกา"
    ห้ามเปลี่ยนชื่อ โมดูลอื่นถูกเขียนขนานกันโดยอิงสัญญานี้
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import NamedTuple

from . import localdate

# ค่าของ RoutineStatus.kind — ประกาศไว้ที่เดียวกันเทียบสตริงผิดตัวพิมพ์
INTERVAL = "interval"
WEEKDAY = "weekday"


class RoutineStatus(NamedTuple):
    """สถานะของ routine หนึ่งตัว ณ วันหนึ่งๆ

    days_since เป็น None ได้ (ยังไม่เคยทำ) แต่ days_until กับ next_due ไม่เป็น None
    ในทางปฏิบัติ — เพราะ "ยังไม่เคยทำ" ถือว่าถึงรอบวันนี้ จึงมีวันครบรอบเสมอ
    ประกาศเป็น Optional ตามสัญญาไว้เผื่อกรณีข้อมูลเพี้ยนในอนาคต

    days_until ติดลบได้ = เลยกำหนดมาแล้วกี่วัน (เก็บวันครบรอบจริงไว้ ไม่ปัดเป็นวันนี้
    เพราะ digest ต้องบอกได้ว่า "เกินกำหนด 2 วัน" ไม่ใช่แค่ "ถึงรอบ")
    """

    name: str
    name_th: str
    kind: str
    due: bool
    days_since: int | None
    days_until: int | None
    next_due: date | None
    last_done: str | None
    notes: str | None


def _today(when: str | date | datetime | None = None) -> date:
    """วันที่อ้างอิงของการคำนวณทั้งหมด — ประตูเดียวที่โมดูลนี้ถามว่า "วันนี้วันไหน"

    to_date() แปลง datetime แบบ aware เป็นวันตามเวลาไทยให้เอง ส่วน naive ถือเป็นเวลาไทย
    ผลจึงเท่ากับ local_date_key() ทุกกรณีที่ส่ง datetime มา แต่รับ str/date ได้ด้วย
    """
    if when is None:
        return localdate.local_date()
    return localdate.to_date(when)


def _kind(row: sqlite3.Row) -> str:
    """แถวนี้เป็น routine แบบไหน

    schema มี CHECK บังคับว่าต้องมีอย่างใดอย่างหนึ่งอยู่แล้ว การระเบิดตรงนี้จึงแปลว่า
    ฐานข้อมูลถูกแก้มาโดยข้าม CHECK (เช่น restore ผิดวิธี) — ดังกว่าเดาว่าเป็นแบบไหน
    """
    if row["interval_days"] is not None:
        return INTERVAL
    if row["day_of_week"] is not None:
        return WEEKDAY
    raise ValueError(
        f"routine '{row['name']}' ไม่มีทั้ง interval_days และ day_of_week "
        f"— ข้อมูลผิดรูป ตรวจ CHECK ใน schema/001_init.sql"
    )


def _last_done_date(row: sqlite3.Row) -> date | None:
    """แปลง last_done ที่เก็บเป็นข้อความให้เป็นวัน — NULL/ว่าง = ยังไม่เคยทำ

    ค่าที่ไม่ใช่วันที่ (เช่นใครไปเขียน '[ต้องกรอก]' ทับ) ต้องระเบิด ไม่ใช่ถือว่าไม่เคยทำ
    เพราะ "ไม่เคยทำ" = ถึงรอบทุกวัน ซึ่งจะกลายเป็นเตือนซ้ำทุกเช้าโดยไม่มีใครรู้สาเหตุ
    (002_seed.sql อธิบายไว้ว่าจึงเลือก seed เป็น NULL ไม่ใช่ placeholder)
    """
    raw = row["last_done"]
    if raw is None or not str(raw).strip():
        return None
    try:
        return localdate.to_date(str(raw))
    except ValueError as exc:
        raise ValueError(
            f"routine '{row['name']}' มี last_done ที่ไม่ใช่วันที่: {raw!r}\n"
            f"แก้ให้เป็น 'YYYY-MM-DD' หรือ NULL ถ้ายังไม่เคยทำ:\n"
            f"  UPDATE routines SET last_done = NULL WHERE name = '{row['name']}';"
        ) from exc


def _status_from_row(row: sqlite3.Row, today: date) -> RoutineStatus:
    """หัวใจของโมดูล — ตัดสินว่าถึงรอบหรือยัง และรอบหน้าวันไหน"""
    kind = _kind(row)
    last_done = _last_done_date(row)
    days_since = localdate.days_between(last_done, today) if last_done is not None else None

    if kind == INTERVAL:
        interval = int(row["interval_days"])
        if last_done is None:
            # NULL = ยังไม่เคยทำ → ถึงรอบทันที (สัญญาใน CONTRACTS.md)
            # ให้ next_due เป็นวันนี้ ไม่ใช่ None เพื่อให้ upcoming()/digest
            # เรียงลำดับและพูดถึงมันได้เหมือน routine ตัวอื่น
            due = True
            next_due = today
        else:
            due = days_since >= interval
            # วันครบรอบจริงนับจากครั้งล่าสุดเสมอ ไม่ใช่จากวันนี้ —
            # ทำคิ้ว 17 ส.ค. รอบ 7 วัน ต้องได้ 24 ส.ค. ตามตัวอย่างใน kit ส่วนที่ 1
            next_due = last_done + timedelta(days=interval)
    else:
        target_dow = int(row["day_of_week"])
        # ทำไปแล้ววันนี้ = รอบนี้จบแล้ว ต้องข้ามไปสัปดาห์หน้า
        # ไม่งั้น mark_done('haircut') เย็นวันอังคารจะยังตอบว่า "รอบหน้าวันนี้"
        # และ digest เย็นจะเตือนซ้ำทั้งที่เพิ่งตัดผมมา (เทียบกับแบบ interval ที่
        # days_since = 0 ทำให้ไม่ถึงรอบโดยอัตโนมัติอยู่แล้ว — ต้องให้สองแบบสอดคล้องกัน)
        done_today = last_done == today
        due = today.weekday() == target_dow and not done_today
        next_due = localdate.next_weekday(today, target_dow, allow_same_day=not done_today)

    return RoutineStatus(
        name=row["name"],
        name_th=row["name_th"],
        kind=kind,
        due=due,
        days_since=days_since,
        days_until=localdate.days_between(today, next_due),
        next_due=next_due,
        last_done=row["last_done"],
        notes=row["notes"],
    )


def _sorted(items: list[RoutineStatus]) -> list[RoutineStatus]:
    """เรียงวันที่ใกล้สุดก่อน — ของที่เลยกำหนดมาแล้วจึงขึ้นก่อนของที่ครบรอบวันนี้

    เรียงด้วยชื่อเป็นตัวตัดสินรอง เพื่อให้ลำดับคงที่ทุกครั้งที่รัน
    (digest ที่สลับลำดับเองไปมาจะอ่านเหมือน "คนละคน" ทุกเช้า — kit ข้อ D)
    """
    return sorted(items, key=lambda s: (s.next_due or date.max, s.name))


def list_routines(conn: sqlite3.Connection, *, active_only: bool = True) -> list[sqlite3.Row]:
    """รายการ routine ดิบจากตาราง — คืน sqlite3.Row ตามสัญญา ไม่แปลงเป็น NamedTuple"""
    sql = "SELECT * FROM routines"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY name"
    return conn.execute(sql).fetchall()


def _fetch(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    """หา routine ตามชื่อ — ไม่เจอ = KeyError พร้อมบอกว่ามีชื่ออะไรให้เลือกบ้าง

    ไม่กรอง active ตรงนี้: ถามถึงชื่อเจาะจงแล้วเงียบเพราะมันถูกปิดอยู่ จะงงกว่าตอบไป
    ตรงๆ ว่าสถานะเป็นยังไง (ตัวกรอง active มีผลกับ due_today/upcoming เท่านั้น)
    """
    row = conn.execute(
        "SELECT * FROM routines WHERE name = ? COLLATE NOCASE", (str(name).strip(),)
    ).fetchone()
    if row is None:
        known = ", ".join(r["name"] for r in conn.execute("SELECT name FROM routines ORDER BY name"))
        raise KeyError(
            f"ไม่รู้จัก routine {name!r} — ที่มีอยู่: {known or '(ยังไม่มีข้อมูลในตาราง)'}"
        )
    return row


def status(
    conn: sqlite3.Connection, name: str, when: str | date | datetime | None = None
) -> RoutineStatus:
    """สถานะของ routine ตัวเดียว ณ วันที่ `when` (ไม่ระบุ = วันนี้ตามเวลาไทย)"""
    return _status_from_row(_fetch(conn, name), _today(when))


def due_today(
    conn: sqlite3.Connection, when: str | date | datetime | None = None
) -> list[RoutineStatus]:
    """ถึงรอบวันนี้มีอะไรบ้าง — ใช้โดย digest เช้า (checklist B ข้อ 1-2)"""
    today = _today(when)
    return _sorted([s for s in (_status_from_row(r, today) for r in list_routines(conn)) if s.due])


def upcoming(
    conn: sqlite3.Connection, days: int = 7, when: str | date | datetime | None = None
) -> list[RoutineStatus]:
    """ถึงรอบภายใน N วันข้างหน้า เรียงวันใกล้สุดก่อน

    รวมของที่ถึงรอบวันนี้ (days_until = 0) และที่เลยกำหนดมาแล้ว (ติดลบ) ไว้ด้วยเสมอ
    — ของที่ค้างอยู่ย่อมอยู่ใน "N วันข้างหน้า" ยิ่งกว่าของที่ยังไม่ถึง
      ถ้าตัดออกจะหายไปจากสรุปสัปดาห์เงียบๆ ทั้งที่เป็นเรื่องเร่งที่สุด
    """
    if days < 0:
        raise ValueError(f"days ต้องไม่ติดลบ ได้รับ {days}")
    today = _today(when)
    items = (_status_from_row(r, today) for r in list_routines(conn))
    return _sorted([s for s in items if s.days_until is not None and s.days_until <= days])


def mark_done(
    conn: sqlite3.Connection, name: str, when: str | date | datetime | None = None
) -> RoutineStatus:
    """"ทำคิ้วแล้ว" → บันทึกว่าทำวันนี้ แล้วคืนสถานะของรอบใหม่

    ค่าที่เขียนลง last_done คือคีย์วันแบบเวลาไทย (เท่ากับ localDateKey()) —
    ห้ามใช้ DATE('now') ของ SQLite เพราะมันคิดเป็น UTC จะเพี้ยนไป 7 ชั่วโมง
    สั่ง "ทำคิ้วแล้ว" ตอน 4 ทุ่มครึ่งจะถูกบันทึกเป็นเมื่อวาน

    อ่านสถานะกลับจากฐานข้อมูลหลังเขียน ไม่คำนวณจากค่าในหน่วยความจำ
    เพื่อให้สิ่งที่ตอบโอม ("รอบหน้า 24 ส.ค.") เป็นสิ่งที่บันทึกไว้จริง
    (บุคลิกข้อความซื่อสัตย์: ห้ามรายงานว่าเรียบร้อยถ้ายังไม่ยืนยันว่าสำเร็จจริง)
    """
    row = _fetch(conn, name)
    today = _today(when)
    conn.execute("UPDATE routines SET last_done = ? WHERE id = ?", (today.isoformat(), row["id"]))
    conn.commit()
    return status(conn, row["name"], today)
