"""
ประกอบ DigestContext จากฐานข้อมูล — สะพานระหว่าง "ข้อมูลจริง" กับ "ตัวจัดข้อความ"

digest.py จงใจไม่แตะฐานข้อมูล (เทสต์ข้อความได้โดยไม่มี DB) ส่วน routines/friday
จงใจไม่รู้เรื่องข้อความ — ไฟล์นี้คือคนกลางที่รู้จักทั้งสองฝั่ง:
อ่าน DB ผ่านโมดูล core ตัวอื่น แล้วเรียงให้เป็นรูปที่ renderer รับ

หลักการเดียวที่คุมทั้งไฟล์: **ขาดข้อมูล = เว้นหัวข้อ ไม่ใช่เดา**
- anchor ศุกร์ยังไม่กรอก/พัง → friday=None (renderer จะเงียบเรื่องบ้าน/โรงแรมเอง)
- API ภายนอกไม่มีค่า → field เป็น None → บรรทัดนั้นหายไป (checklist E2)
- ไม่มี scaccounting transport → pending_work ว่าง → renderer ไม่พิมพ์หัวข้อ 📋
  (ห้ามใส่ "ดึงไม่ได้" ลงไปแทน — รายการว่างกับดึงไม่ได้แยกไม่ออก อย่าแกล้งแยก)
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, timedelta

from typing import Any, Mapping

from . import db, localdate, routines
from . import friday as friday_mod
from .digest import DigestContext

# extras ที่ morning_context ยอมรับ — ตรงกับ field ของ DigestContext ที่มาจาก API
# ภายนอกเท่านั้น คีย์แปลกปลอม (fetcher รุ่นใหม่ส่งอะไรเพิ่มมา) จะถูกเมินเฉยๆ
# ไม่ระเบิด เพราะ digest ต้องออกทุกเช้าแม้ fetcher จะล้ำเส้นสัญญา
_EXTRA_KEYS = frozenset(
    {"travel_minutes", "leave_by", "weather_summary", "rain_window", "aqi", "calendar_items"}
)


def _friday_plan_or_none(
    conn: sqlite3.Connection, when: str | date | datetime | None
) -> Any:
    """FridayPlan หรือ None ถ้า anchor ยังไม่กรอก/พัง — พร้อมเสียงเตือนทาง stderr

    digest เช้าต้องออกแม้ config พัง (A1: 7 วันติดห้ามขาด) แต่ "เงียบสนิท" ก็ไม่ได้
    เพราะ anchor ที่พังจะทำให้ทุกศุกร์ไม่มีบรรทัดบ้าน/โรงแรมไปเรื่อยๆ โดยไม่มีใครรู้
    → ส่งเสียงไว้ใน stderr ซึ่งโผล่ใน log ของ cron (hermes cron runs) แต่ไม่ปนใน
    ข้อความที่ส่งเข้า Telegram (stdout เท่านั้นที่ถูกส่ง)
    """
    try:
        return friday_mod.friday_state_from_db(conn, when)
    except (db.MissingPreference, ValueError) as exc:
        print(f"คำเตือน: อ่านสถานะศุกร์ไม่ได้ — {exc}", file=sys.stderr)
        return None


def _class_row(conn: sqlite3.Connection, weekday: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT first_subject, period_count, notes FROM class_schedule WHERE day_of_week = ?",
        (weekday,),
    ).fetchone()


def morning_context(
    conn: sqlite3.Connection,
    when: datetime | None = None,
    extras: Mapping[str, Any] | None = None,
) -> DigestContext:
    """ประกอบข้อมูลสำหรับ digest เช้า

    extras มาจาก fetchers.fetch_extras() — คีย์ไหนไม่มี = API ตัวนั้นดึงไม่ได้
    ซึ่งเป็นเรื่องปกติ ไม่ใช่ข้อผิดพลาดของฟังก์ชันนี้
    """
    moment = localdate.now(when)
    row = _class_row(conn, moment.weekday())

    ctx = DigestContext(
        when=moment,
        due_routines=routines.due_today(conn, moment),
        # upcoming ใช้ประกอบบรรทัด "พรุ่งนี้: ..." (renderer กรอง days_until == 1 เอง)
        upcoming_routines=routines.upcoming(conn, days=7, when=moment),
        friday=_friday_plan_or_none(conn, moment),
        first_subject=row["first_subject"] if row else None,
        period_count=row["period_count"] if row else None,
    )

    for key, value in (extras or {}).items():
        if key in _EXTRA_KEYS:
            setattr(ctx, key, value)
    return ctx


# --- เย็น ---------------------------------------------------------------------


def _utc_window_of_thai_day(day: date) -> tuple[str, str]:
    """ขอบเขตวันแบบไทย → คู่สตริง UTC สำหรับเทียบกับ datetime('now') ของ SQLite

    updated_at ในตารางเป็น UTC (datetime('now')) แต่คำถามคือ "วันนี้แบบไทย
    เกิดอะไรขึ้นบ้าง" — เที่ยงคืนไทย = 17:00 UTC ของเมื่อวาน ถ้าเทียบตรงๆ
    รายการช่วงเช้ามืดจะตกไปอยู่ผิดวัน (บั๊กตระกูลเดียวกับกฎเหล็กข้อ 3)
    """
    start_th = datetime(day.year, day.month, day.day, tzinfo=localdate.TZ)
    fmt = "%Y-%m-%d %H:%M:%S"
    from datetime import timezone

    start = start_th.astimezone(timezone.utc).strftime(fmt)
    end = (start_th + timedelta(days=1)).astimezone(timezone.utc).strftime(fmt)
    return start, end


def _booking_done_line(row: sqlite3.Row, today: date) -> str:
    """แถว booking ที่ยืนยันแล้ว → '✅ จองร้าน X พรุ่งนี้ 18:00 4 ที่ — สำเร็จ' (ตามแบบ kit)

    ใส่เฉพาะส่วนที่มีข้อมูลจริง — ไม่มี party_size ก็ไม่พิมพ์ 'None ที่'
    """
    parts = [f"จอง{row['place_name']}"]
    try:
        bdate = localdate.to_date(row["booking_date"])
        delta = (bdate - today).days
        if delta == 0:
            parts.append("วันนี้")
        elif delta == 1:
            parts.append("พรุ่งนี้")
        else:
            parts.append(localdate.thai_date_short(bdate))
    except (ValueError, TypeError):
        pass  # วันที่พังก็ยังรายงานได้ว่าจองอะไรสำเร็จ
    if row["booking_time"]:
        parts.append(str(row["booking_time"]))
    if row["party_size"]:
        parts.append(f"{row['party_size']} ที่")
    return " ".join(parts) + " — สำเร็จ"


def evening_inputs(
    conn: sqlite3.Connection, when: datetime | None = None
) -> tuple[DigestContext, list[str], list[str]]:
    """(ctx, done_items, pending_work) สำหรับ render_evening

    done_items รายงานเฉพาะสิ่งที่มีหลักฐานใน DB ว่าเกิดจริง:
    routine ที่ last_done = วันนี้ และ booking ที่ status เป็น confirmed วันนี้
    — บุคลิกข้อความซื่อสัตย์: ไม่มีหลักฐาน = ไม่อยู่ในรายการ
    """
    moment = localdate.now(when)
    today = moment.date()
    today_key = localdate.local_date_key(moment)

    done: list[str] = []
    for row in conn.execute(
        "SELECT name_th FROM routines WHERE last_done = ? ORDER BY id", (today_key,)
    ):
        # kit: "ทำคิ้วแล้ว (บันทึกรอบใหม่แล้ว)" — name_th ของคิ้วคือ 'ทำคิ้ว' อยู่แล้ว
        done.append(f"{row['name_th']}แล้ว (บันทึกรอบใหม่แล้ว)")

    start, end = _utc_window_of_thai_day(today)
    for row in conn.execute(
        "SELECT place_name, booking_date, booking_time, party_size FROM bookings "
        "WHERE status = 'confirmed' AND updated_at >= ? AND updated_at < ? ORDER BY id",
        (start, end),
    ):
        done.append(_booking_done_line(row, today))

    ctx = DigestContext(
        when=moment,
        upcoming_routines=routines.upcoming(conn, days=7, when=moment),
        friday=_friday_plan_or_none(conn, moment),
    )
    # pending_work ว่างจนกว่าจะมี scaccounting transport (Phase 2) —
    # renderer จะไม่พิมพ์หัวข้อ 📋 เอง ถูกต้องกว่าประกาศว่า "ไม่มีงานค้าง" ทั้งที่ไม่รู้
    return ctx, done, []


# --- สรุปสัปดาห์ (อาทิตย์ 20:00) ----------------------------------------------


def _haircut_note(status: Any) -> str:
    """แถวตัดผมในตารางสัปดาห์ — เป้าหมายคือแบบ kit: '✂️ ตัดผม ร้านเกษมเกษา (เย็น)'

    ชื่อร้านเอามาจากคำแรกของ notes ('ร้านเกษมเกษา ปั๊ม ปตท. บ้านสัน (ตอนเย็น)')
    ⚠️ จงใจยอมเปราะ: ถ้ารูปแบบ notes เปลี่ยน แถวจะถอยไปเหลือชื่อ routine เฉยๆ
    ซึ่งยังถูกต้อง แค่สั้นลง — มีเทสต์ตรึงแบบเต็มไว้ ถ้า seed เปลี่ยนเทสต์จะฟ้องเอง
    """
    prefix = "✂️ " if status.name == "haircut" else "📌 "
    parts = [f"{prefix}{status.name_th}"]
    notes = (status.notes or "").strip()
    if notes:
        parts.append(notes.split()[0])
        if "เย็น" in notes:
            parts.append("(เย็น)")
    return " ".join(parts)


def weekly_inputs(
    conn: sqlite3.Connection, when: datetime | None = None
) -> tuple[DigestContext, list, list]:
    """(ctx, week_rows, due_next_week) สำหรับ render_weekly — มองไป "สัปดาห์หน้า"

    รันคืนวันอาทิตย์ → สัปดาห์หน้าเริ่มพรุ่งนี้ ctx.friday จึงต้องเป็นแผนของ
    ศุกร์สัปดาห์หน้า (สัญญาของ render_weekly ระบุไว้ — ใช้ศุกร์ที่ผ่านมาจะถามเรื่อง
    จองโรงแรมผิดสัปดาห์ ซึ่งโทษเดียวกับ H10)
    """
    moment = localdate.now(when)
    next_mon = localdate.next_weekday(moment, localdate.MONDAY)
    next_sun = next_mon + timedelta(days=6)

    plan = _friday_plan_or_none(conn, next_mon)

    # routine แบบวันประจำ จัดเข้าแถวของวันนั้นในตาราง
    weekday_notes: dict[int, list[str]] = {}
    for row in routines.list_routines(conn):
        if row["day_of_week"] is None:
            continue
        status = routines.status(conn, row["name"], moment)
        weekday_notes.setdefault(int(row["day_of_week"]), []).append(_haircut_note(status))

    rows: list[tuple[date, str]] = []
    for offset in range(5):  # จ-ศ ตามแบบ kit (เสาร์อาทิตย์ไม่มีตาราง)
        day = next_mon + timedelta(days=offset)
        weekday = day.weekday()
        parts: list[str] = []
        routine_parts = weekday_notes.get(weekday, [])

        if weekday == localdate.WEDNESDAY:
            # kit: 'พ. — ⚠️ ตื่น 06:30 + ร.ด. บ่าย' — เวลาตื่นจาก preferences
            wake = db.get_pref(conn, "wake_time_wed")
            if wake:
                parts.append(f"⚠️ ตื่น {wake}")

        parts.extend(routine_parts)

        if weekday == localdate.FRIDAY and plan is not None:
            parts.append(
                "🏡 กลับบ้านจอมทอง" if plan.is_home
                else "🏨 สัปดาห์โรงแรม (คราวนี้ไม่กลับจอมทอง)"
            )

        # หมายเหตุตารางเรียน (เช่น 'บ่าย ร.ด.') เว้นเฉพาะวันที่มีแถว routine
        # อยู่แล้ว — วันอังคารมีแถวตัดผม จะไม่เติม 'เย็น: ตัดผม' ซ้ำ
        # แต่ ⚠️ ตื่นเช้าวันพุธ "ไม่ใช่" ตัวแทนของ ร.ด. — ต้องได้ทั้งสองอย่าง
        if not routine_parts:
            row = _class_row(conn, weekday)
            note = (row["notes"] or "").strip() if row else ""
            if note:
                parts.append(note)

        rows.append((day, " + ".join(parts) if parts else "ปกติ"))

    # kit: '📌 ถึงรอบสัปดาห์หน้า: • ไดโอด (พฤหัส)' — เฉพาะแบบนับวันที่ครบรอบในสัปดาห์หน้า
    # (แบบวันประจำอยู่ในตารางข้างบนแล้ว ใส่ซ้ำจะกลายเป็นเตือนตัดผมสองที่)
    due_next: list[Any] = []
    for status in routines.upcoming(conn, days=14, when=moment):
        if status.kind != "interval" or status.next_due is None:
            continue
        if next_mon <= status.next_due <= next_sun:
            due_next.append(status)

    ctx = DigestContext(when=moment, friday=plan)
    return ctx, rows, due_next


# --- รายงานความฝัน -------------------------------------------------------------


def dream_summary(conn: sqlite3.Connection, when: datetime | None = None) -> dict:
    """จัดระเบียบความจำแล้วคืน summary สำหรับ render_dream_report

    เจตนา: เรียกตอนเช้า (ก่อน digest) ให้ "จัดระเบียบ + รายงาน" จบในครั้งเดียว
    ไม่ต้องมีไฟล์สถานะส่งข้ามกันระหว่าง cron ตี 2 กับ cron ตอนเช้า —
    consolidate ปลอดภัยต่อการเรียกซ้ำอยู่แล้ว (พักเฉพาะก้อนที่เข้าเกณฑ์ ไม่ลบจริง)
    เวลาที่ขยับจาก "ตี 2" มาเป็น "ก่อน digest เช้า" ไม่เปลี่ยนพฤติกรรมอะไร
    เพราะทั้งสองช่วงไม่มีใครใช้ระบบอยู่แล้ว — สิ่งที่ H13 บังคับจริงคือ
    "รายงานทุกเช้าว่าตัดอะไรไป และกู้คืนได้" ซึ่งทางนี้ทำครบ
    """
    from . import memory

    return memory.consolidate(conn, when=when)
