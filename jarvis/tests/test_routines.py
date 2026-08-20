"""
เทสต์ของ core/routines.py — checklist B ข้อ 1-2 ของ jarvis-phase1-kit

สองข้อที่เทสต์ชุดนี้มีไว้ปกป้อง:
    "routine เตือนถูกวัน (ไดโอดครบ 14 วัน / คิ้วครบ 7 วัน)"
    "เตือนตัดผมทุกวันอังคาร ไม่เตือนวันอื่น"

ทำไมต้องละเอียดถึงระดับ 13/14/15 วัน:
    ความผิดพลาดของโมดูลนี้ไม่มี traceback ให้เห็น มีแต่ข้อความที่เตือนผิดวัน
    ซึ่งกว่าจะรู้ตัวก็เชื่อระบบไปแล้วหลายสัปดาห์ — ขอบเขตต้องถูกดักด้วยเทสต์เท่านั้น

ทุกเทสต์ฉีดวันเองผ่านพารามิเตอร์ `when` ไม่มีข้อไหนพึ่งวันจริงของเครื่อง
(เทสต์ที่ผลเปลี่ยนตามวันที่รัน = เทสต์ที่จะพังเองสักวันโดยไม่มีใครแก้อะไร)
ใช้ไฟล์ DB ชั่วคราวเสมอ ไม่แตะ ~/.jarvis/jarvis.db และไม่ต้องต่อเน็ต
"""

from __future__ import annotations

import ast
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from core import db, routines
from core.localdate import THAI_DAYS, TUESDAY, thai_date_short

# ปฏิทินอ้างอิงของเทสต์ชุดนี้ (ยืนยันแล้วว่าตรงกับวันจริง)
#   2026-08-17 จันทร์ · 08-18 อังคาร · 08-19 พุธ · 08-20 พฤหัส
#   08-21 ศุกร์ · 08-22 เสาร์ · 08-23 อาทิตย์ · 08-25 อังคาร
MON = date(2026, 8, 17)
TUE = date(2026, 8, 18)
WED = date(2026, 8, 19)
THU = date(2026, 8, 20)
NEXT_TUE = date(2026, 8, 25)


class RoutineTestBase(unittest.TestCase):
    """DB ชั่วคราวที่ migrate + seed แล้ว 1 ชุดต่อ 1 เทสต์

    last_done ถูกล้างเป็น NULL ทุกแถวหลัง migrate เสมอ แล้วแต่ละเทสต์ค่อยตั้งค่าที่
    ตัวเองต้องการเอง — เทสต์ในไฟล์นี้ตรวจ "ตรรกะของรอบ" ไม่ได้ตรวจว่า migration
    ไหนใส่ค่าอะไรไว้ (นั่นเป็นหน้าที่ของ test_seed.py)

    ทำไมต้องล้าง: migration ที่มาทีหลังมีสิทธิ์เติม last_done ของจริงลงไปได้ตามปกติ
    (เช่น 003 ที่เก็บค่าที่โอมตอบมา) ถ้าเทสต์ยังอ่านค่าจาก seed ตรงๆ อยู่ มันจะพัง
    หรือแย่กว่านั้นคือ "ผ่านทั้งที่ตรวจคนละเรื่อง" ทุกครั้งที่มีคนเพิ่มไฟล์ schema
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "jarvis-test.db"
        self.conn = db.connect(self.db_path)
        db.migrate(self.conn)
        # จุดตั้งต้นที่เทสต์ทุกข้อในไฟล์นี้ตกลงกันไว้ = ยังไม่เคยทำสักอย่าง
        self.conn.execute("UPDATE routines SET last_done = NULL")
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def set_last_done(self, name: str, value: str | date | None) -> None:
        if isinstance(value, date):
            value = value.isoformat()
        self.conn.execute("UPDATE routines SET last_done = ? WHERE name = ?", (value, name))
        self.conn.commit()

    def set_active(self, name: str, active: bool) -> None:
        self.conn.execute(
            "UPDATE routines SET active = ? WHERE name = ?", (1 if active else 0, name)
        )
        self.conn.commit()

    def names(self, items: list[routines.RoutineStatus]) -> list[str]:
        return [s.name for s in items]


# --- แบบนับวัน: ไดโอด 14 วัน / คิ้ว 7 วัน ------------------------------------


class TestIntervalBoundary(RoutineTestBase):
    """ขอบเขตของรอบ — จุดที่ผิดแล้วเตือนเร็วหรือช้าไป 1 วันทุกครั้ง"""

    def setUp(self) -> None:
        super().setUp()
        # ทำไดโอดล่าสุด 6 ส.ค. → ครบ 14 วันพอดีวันที่ 20 ส.ค.
        self.set_last_done("diode", "2026-08-06")

    def test_13_days_is_not_due_yet(self) -> None:
        s = routines.status(self.conn, "diode", WED)  # 19 ส.ค. = 13 วัน
        self.assertEqual(s.days_since, 13)
        self.assertFalse(s.due, "13 วันยังไม่ครบรอบ 14 วัน ห้ามเตือน")
        self.assertEqual(s.next_due, THU)
        self.assertEqual(s.days_until, 1)

    def test_exactly_14_days_is_due(self) -> None:
        s = routines.status(self.conn, "diode", THU)  # 20 ส.ค. = 14 วัน
        self.assertEqual(s.days_since, 14)
        self.assertTrue(s.due, "ครบ 14 วันพอดีต้องถึงรอบ (>= ไม่ใช่ >)")
        self.assertEqual(s.days_until, 0)
        self.assertEqual(s.next_due, THU)

    def test_15_days_still_due_and_reports_overdue(self) -> None:
        s = routines.status(self.conn, "diode", date(2026, 8, 21))
        self.assertEqual(s.days_since, 15)
        self.assertTrue(s.due)
        # เก็บวันครบรอบจริงไว้ ติดลบ = เลยกำหนดมาแล้วกี่วัน
        self.assertEqual(s.next_due, THU)
        self.assertEqual(s.days_until, -1)

    def test_eyebrow_uses_its_own_7_day_cycle(self) -> None:
        self.set_last_done("eyebrow", MON)  # 17 ส.ค.
        six = routines.status(self.conn, "eyebrow", date(2026, 8, 23))
        seven = routines.status(self.conn, "eyebrow", date(2026, 8, 24))
        self.assertEqual((six.days_since, six.due), (6, False))
        self.assertEqual((seven.days_since, seven.due), (7, True))

    def test_kind_and_thai_name_come_from_seed(self) -> None:
        s = routines.status(self.conn, "diode", THU)
        self.assertEqual(s.kind, routines.INTERVAL)
        self.assertEqual(s.kind, "interval")  # ค่าตามสัญญาใน CONTRACTS.md
        self.assertEqual(s.name_th, "เลเซอร์ไดโอดกำจัดขน")


class TestNeverDone(RoutineTestBase):
    """last_done = NULL คือสภาพตอนติดตั้งใหม่ (002_seed ตั้งใจปล่อยว่างไว้)"""

    def test_never_done_interval_is_due_immediately(self) -> None:
        s = routines.status(self.conn, "eyebrow", THU)
        self.assertIsNone(s.last_done)
        self.assertIsNone(s.days_since, "ยังไม่เคยทำ = นับวันจากครั้งก่อนไม่ได้")
        self.assertTrue(s.due)
        self.assertEqual(s.next_due, THU, "ถึงรอบทันที = วันครบรอบคือวันนี้")
        self.assertEqual(s.days_until, 0)

    def test_never_done_shows_up_in_due_today(self) -> None:
        self.assertEqual(self.names(routines.due_today(self.conn, WED)), ["diode", "eyebrow"])

    def test_never_done_does_not_leak_into_weekday_kind(self) -> None:
        """haircut ก็ last_done = NULL เหมือนกัน แต่ต้องไม่ถึงรอบถ้าไม่ใช่อังคาร

        กฎ "ไม่เคยทำ = ถึงรอบ" ใช้กับแบบนับวันเท่านั้น ถ้าเผลอใช้กับแบบวันประจำ
        จะเตือนตัดผมทุกวันจนกว่าจะตัดครั้งแรก = ผิด checklist B ข้อ 2
        """
        self.assertFalse(routines.status(self.conn, "haircut", WED).due)


# --- แบบวันประจำ: ตัดผมทุกวันอังคาร --------------------------------------------


class TestWeekdayRoutine(RoutineTestBase):
    def test_due_on_tuesday_only(self) -> None:
        """ไล่ครบ 7 วันติดกัน — อังคารวันเดียวที่เตือน"""
        for offset in range(7):
            day = MON + timedelta(days=offset)
            with self.subTest(day=THAI_DAYS[day.weekday()]):
                s = routines.status(self.conn, "haircut", day)
                self.assertEqual(
                    s.due,
                    day.weekday() == TUESDAY,
                    f"{day.isoformat()} ({THAI_DAYS[day.weekday()]}) ตัดสินผิด",
                )

    def test_tuesday_reports_zero_days_until(self) -> None:
        s = routines.status(self.conn, "haircut", TUE)
        self.assertEqual(s.kind, "weekday")
        self.assertTrue(s.due)
        self.assertEqual(s.next_due, TUE, "ตรงวันแล้ว รอบคือวันนี้")
        self.assertEqual(s.days_until, 0)

    def test_other_days_point_at_the_coming_tuesday(self) -> None:
        expected = {
            MON: (TUE, 1),
            WED: (NEXT_TUE, 6),
            THU: (NEXT_TUE, 5),
            date(2026, 8, 23): (NEXT_TUE, 2),  # อาทิตย์
        }
        for day, (next_due, days_until) in expected.items():
            with self.subTest(day=day.isoformat()):
                s = routines.status(self.conn, "haircut", day)
                self.assertEqual(s.next_due, next_due)
                self.assertEqual(s.days_until, days_until)

    def test_notes_and_thai_name_are_carried_through(self) -> None:
        """สรุปสัปดาห์ใน kit เขียนว่า "อ. — ✂️ ตัดผม ร้านเกษมเกษา (เย็น)"

        ชื่อร้านมาจากคอลัมน์ notes ทางเดียว ถ้า RoutineStatus ไม่ขนมันมาด้วย
        ข้อความจะเหลือแค่ "ตัดผม" โดยไม่มีอะไรพัง ไม่มีเทสต์ไหนฟ้อง
        """
        s = routines.status(self.conn, "haircut", TUE)
        self.assertEqual(s.name_th, "ตัดผม")
        self.assertEqual(s.notes, "ร้านเกษมเกษา ปั๊ม ปตท. บ้านสัน (ตอนเย็น)")
        # แบบนับวันไม่มีหมายเหตุใน seed — ต้องเป็น None ไม่ใช่สตริงว่าง
        self.assertIsNone(routines.status(self.conn, "diode", TUE).notes)

    def test_days_since_is_tracked_but_does_not_decide(self) -> None:
        """แบบวันประจำก็เก็บ last_done ไว้ดูได้ แต่ความถึงรอบมาจากวันในสัปดาห์"""
        self.set_last_done("haircut", "2026-08-11")  # อังคารก่อนหน้า
        due_day = routines.status(self.conn, "haircut", NEXT_TUE)
        self.assertEqual(due_day.days_since, 14)
        self.assertTrue(due_day.due)

        off_day = routines.status(self.conn, "haircut", THU)
        self.assertEqual(off_day.days_since, 9)
        self.assertFalse(off_day.due, "ครบ 9 วันก็ไม่เกี่ยว ไม่ใช่อังคารก็ไม่เตือน")


# --- "ทำคิ้วแล้ว" -------------------------------------------------------------


class TestMarkDone(RoutineTestBase):
    def test_kit_example_eyebrow_next_round_is_24_aug(self) -> None:
        """ตัวอย่างจริงจาก kit ส่วนที่ 1:
        โอม "ทำคิ้วแล้ว" → Jarvis "บันทึกแล้วครับ รอบหน้า 24 ส.ค."
        """
        s = routines.mark_done(self.conn, "eyebrow", MON)  # 17 ส.ค.
        self.assertEqual(s.last_done, "2026-08-17")
        self.assertEqual(s.next_due, date(2026, 8, 24))
        self.assertEqual(thai_date_short(s.next_due), "24 ส.ค.")
        self.assertEqual((s.due, s.days_since, s.days_until), (False, 0, 7))

    def test_resets_an_overdue_cycle(self) -> None:
        self.set_last_done("diode", "2026-08-01")
        before = routines.status(self.conn, "diode", THU)
        self.assertTrue(before.due)

        after = routines.mark_done(self.conn, "diode", THU)
        self.assertFalse(after.due, "เพิ่งทำวันนี้ต้องไม่ถึงรอบแล้ว")
        self.assertEqual(after.days_since, 0)
        self.assertEqual(after.next_due, date(2026, 9, 3))  # 20 ส.ค. + 14 วัน

    def test_writes_thai_local_date_key_not_utc(self) -> None:
        """กฎเหล็กข้อ 1 — สั่งตอนดึกต้องบันทึกเป็น "วันนี้" ตามเวลาไทย

        23:00 ของวันที่ 21 ส.ค. ตามเวลาไทย = 16:00 UTC ของวันที่ 21
        ถ้าโมดูลเผลอคิดเป็น UTC ก็ยังได้วันเดียวกัน จึงต้องเลือกเวลาที่ "ข้ามวัน"
        คนละด้าน: 18:00Z ของวันที่ 20 = 01:00 เช้าวันที่ 21 ตามเวลาไทย
        """
        after_thai_midnight = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)
        s = routines.mark_done(self.conn, "eyebrow", after_thai_midnight)
        self.assertEqual(s.last_done, "2026-08-21", "ต้องเป็นวันไทย ไม่ใช่วัน UTC")

        row = self.conn.execute(
            "SELECT last_done FROM routines WHERE name = 'eyebrow'"
        ).fetchone()
        self.assertEqual(row["last_done"], "2026-08-21", "ค่าที่เขียนลง DB จริงต้องตรงกัน")

    def test_haircut_done_today_moves_to_next_week(self) -> None:
        """ตัดผมเย็นวันอังคารแล้ว digest เย็นต้องไม่เตือนซ้ำ"""
        s = routines.mark_done(self.conn, "haircut", TUE)
        self.assertFalse(s.due)
        self.assertEqual(s.next_due, NEXT_TUE)
        self.assertEqual(s.days_until, 7)
        # diode/eyebrow ยังเป็น NULL อยู่จึงติดมาด้วย — ที่ต้องหายไปคือตัดผมเท่านั้น
        self.assertNotIn("haircut", self.names(routines.due_today(self.conn, TUE)))

    def test_persists_across_connections(self) -> None:
        routines.mark_done(self.conn, "eyebrow", MON)
        other = db.connect(self.db_path)
        try:
            self.assertEqual(routines.status(other, "eyebrow", MON).last_done, "2026-08-17")
        finally:
            other.close()

    def test_does_not_touch_other_routines(self) -> None:
        routines.mark_done(self.conn, "eyebrow", MON)
        self.assertIsNone(routines.status(self.conn, "diode", MON).last_done)
        self.assertIsNone(routines.status(self.conn, "haircut", MON).last_done)

    def test_unknown_name_raises_keyerror(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            routines.mark_done(self.conn, "nose")
        # ข้อความต้องบอกชื่อที่มีจริง ไม่งั้น agent จะเดาชื่อใหม่ไปเรื่อยๆ
        self.assertIn("eyebrow", str(ctx.exception))

    def test_status_of_unknown_name_raises_keyerror(self) -> None:
        with self.assertRaises(KeyError):
            routines.status(self.conn, "ไม่มีอยู่จริง", THU)

    def test_name_is_matched_case_insensitively(self) -> None:
        s = routines.mark_done(self.conn, " Eyebrow ", MON)
        self.assertEqual(s.name, "eyebrow", "คืนชื่อจริงในตาราง ไม่ใช่ที่พิมพ์มา")


# --- due_today / upcoming ------------------------------------------------------


class TestDueToday(RoutineTestBase):
    def test_only_returns_what_is_due(self) -> None:
        self.set_last_done("diode", "2026-08-11")  # ครบ 14 วันวันที่ 25
        self.set_last_done("eyebrow", "2026-08-24")  # เพิ่งทำเมื่อวาน
        due = routines.due_today(self.conn, NEXT_TUE)  # อังคาร → ตัดผมด้วย
        self.assertEqual(self.names(due), ["diode", "haircut"])

    def test_empty_when_nothing_is_due(self) -> None:
        self.set_last_done("diode", "2026-08-19")
        self.set_last_done("eyebrow", "2026-08-19")
        self.assertEqual(routines.due_today(self.conn, THU), [])

    def test_inactive_routine_is_skipped(self) -> None:
        self.set_active("haircut", False)
        self.assertEqual(self.names(routines.due_today(self.conn, TUE)), ["diode", "eyebrow"])
        # แต่ถามชื่อตรงๆ ยังตอบได้ ไม่ใช่หายไปเฉยๆ
        self.assertTrue(routines.status(self.conn, "haircut", TUE).due)


class TestUpcoming(RoutineTestBase):
    def setUp(self) -> None:
        super().setUp()
        # อ้างอิงวันพฤหัสที่ 20 ส.ค. → คิ้ว 21 ส.ค. (1 วัน) · ตัดผม 25 ส.ค. (5 วัน)
        #                              · ไดโอด 27 ส.ค. (7 วัน)
        self.set_last_done("diode", "2026-08-13")
        self.set_last_done("eyebrow", "2026-08-14")

    def test_orders_by_nearest_date_first(self) -> None:
        self.assertEqual(
            self.names(routines.upcoming(self.conn, 7, THU)), ["eyebrow", "haircut", "diode"]
        )

    def test_window_boundary_includes_exactly_n_days(self) -> None:
        self.assertIn("diode", self.names(routines.upcoming(self.conn, 7, THU)))
        self.assertNotIn(
            "diode",
            self.names(routines.upcoming(self.conn, 6, THU)),
            "ครบ 7 วันพอดีต้องหลุดออกจากหน้าต่าง 6 วัน",
        )

    def test_narrow_window(self) -> None:
        self.assertEqual(self.names(routines.upcoming(self.conn, 1, THU)), ["eyebrow"])
        self.assertEqual(routines.upcoming(self.conn, 0, THU), [])

    def test_overdue_items_come_first_and_never_drop_out(self) -> None:
        self.set_last_done("diode", "2026-08-01")  # เลยกำหนดมา 5 วัน
        window = routines.upcoming(self.conn, 7, THU)
        self.assertEqual(self.names(window)[0], "diode")
        self.assertEqual(window[0].days_until, -5)
        # แม้หน้าต่างเป็น 0 วัน ของที่ค้างอยู่ก็ต้องยังอยู่
        self.assertEqual(self.names(routines.upcoming(self.conn, 0, THU)), ["diode"])

    def test_default_window_is_seven_days(self) -> None:
        self.assertEqual(
            self.names(routines.upcoming(self.conn, when=THU)),
            self.names(routines.upcoming(self.conn, 7, THU)),
        )

    def test_inactive_routine_is_skipped(self) -> None:
        self.set_active("diode", False)
        self.assertEqual(self.names(routines.upcoming(self.conn, 7, THU)), ["eyebrow", "haircut"])

    def test_negative_window_raises(self) -> None:
        with self.assertRaises(ValueError):
            routines.upcoming(self.conn, -1, THU)


class TestListRoutines(RoutineTestBase):
    def test_lists_active_rows_in_stable_order(self) -> None:
        rows = routines.list_routines(self.conn)
        self.assertEqual([r["name"] for r in rows], ["diode", "eyebrow", "haircut"])
        self.assertIsInstance(rows[0], sqlite3.Row, "สัญญาบอกว่าคืนแถวดิบ")

    def test_active_only_filter(self) -> None:
        self.set_active("haircut", False)
        self.assertEqual([r["name"] for r in routines.list_routines(self.conn)], ["diode", "eyebrow"])
        self.assertEqual(
            [r["name"] for r in routines.list_routines(self.conn, active_only=False)],
            ["diode", "eyebrow", "haircut"],
        )


# --- เวลาไทย (กฎเหล็กข้อ 1) ----------------------------------------------------


class TestBangkokClock(RoutineTestBase):
    """วันต้องเปลี่ยนตอนเที่ยงคืนไทย ไม่ใช่เที่ยงคืน UTC (= 07:00 เช้าไทย)

    ถ้าพลาดข้อนี้ ไดโอดจะถึงรอบตอน 7 โมงเช้า คือหลัง digest 06:20 ส่งไปแล้วพอดี
    """

    def setUp(self) -> None:
        super().setUp()
        self.set_last_done("diode", "2026-08-06")  # ครบ 14 วันวันที่ 20 ส.ค.

    def test_not_due_at_2330_thai_on_the_day_before(self) -> None:
        eve = datetime(2026, 8, 19, 16, 30, tzinfo=timezone.utc)  # 23:30 ไทย ของวันที่ 19
        self.assertFalse(routines.status(self.conn, "diode", eve).due)

    def test_due_at_0030_thai_on_the_day(self) -> None:
        past_midnight = datetime(2026, 8, 19, 17, 30, tzinfo=timezone.utc)  # 00:30 ไทย ของวันที่ 20
        self.assertTrue(routines.status(self.conn, "diode", past_midnight).due)

    def test_naive_datetime_is_treated_as_thai_time(self) -> None:
        s = routines.status(self.conn, "diode", datetime(2026, 8, 20, 6, 20))
        self.assertTrue(s.due)
        self.assertEqual(s.days_since, 14)

    def test_when_accepts_string_and_date_alike(self) -> None:
        from_str = routines.status(self.conn, "diode", "2026-08-20")
        from_date = routines.status(self.conn, "diode", THU)
        self.assertEqual(from_str, from_date)

    def test_module_never_asks_the_system_clock_directly(self) -> None:
        """กันการถอยหลัง: ห้ามมีการเรียกนาฬิกาของเครื่องหรือของ SQLite ในโมดูลนี้

        ตรวจจาก AST ไม่ใช่ค้นข้อความดิบ เพราะคอมเมนต์กับ docstring ในโมดูลพูดถึง
        ชื่อฟังก์ชันต้องห้ามพวกนี้อยู่แล้ว (อธิบายว่าทำไมถึงห้าม) — ค้นข้อความจะฟ้องผิดตัว
        """
        tree = ast.parse(Path(routines.__file__).read_text(encoding="utf-8"))
        banned_calls = {"datetime.now", "datetime.utcnow", "date.today", "time.time"}
        banned_sql = ("DATE('NOW'", "CURRENT_TIMESTAMP", "CURRENT_DATE", "JULIANDAY('NOW'")

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    dotted = f"{func.value.id}.{func.attr}"
                    self.assertNotIn(
                        dotted, banned_calls, f"ห้ามเรียก {dotted}() — ต้องผ่าน core.localdate"
                    )
            # สตริงที่เป็น SQL ต้องไม่ให้ SQLite ตัดสินเรื่องวันเอง (มันคิดเป็น UTC)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                upper = node.value.upper()
                if any(k in upper for k in ("SELECT ", "UPDATE ", "INSERT ")):
                    for banned in banned_sql:
                        self.assertNotIn(banned, upper, f"ห้ามให้ SQLite คิดวันเอง: {banned}")


# --- ข้อมูลผิดรูป --------------------------------------------------------------


class TestMalformedData(RoutineTestBase):
    def test_bad_last_done_explodes_instead_of_nagging_daily(self) -> None:
        """ค่าที่ไม่ใช่วันที่ต้องระเบิด ไม่ใช่ถูกตีความว่า "ยังไม่เคยทำ"

        ถ้าเงียบแล้วถือว่าไม่เคยทำ = เตือนว่าถึงรอบทุกเช้าตลอดไป โดยไม่มีอะไรบอกสาเหตุ
        """
        self.set_last_done("diode", "[ต้องกรอก]")
        with self.assertRaises(ValueError) as ctx:
            routines.status(self.conn, "diode", THU)
        self.assertIn("diode", str(ctx.exception))

    def test_blank_last_done_counts_as_never_done(self) -> None:
        # สตริงว่างมาจากการ import ผิดพลาด ตีความเป็น NULL ได้อย่างปลอดภัย
        self.set_last_done("eyebrow", "")
        s = routines.status(self.conn, "eyebrow", THU)
        self.assertIsNone(s.days_since)
        self.assertTrue(s.due)

    def test_schema_blocks_rows_that_are_neither_kind(self) -> None:
        """CHECK ใน 001 กันแถวที่ไม่มีทั้งสองแบบ — _kind() จึงเป็นแค่ตาข่ายชั้นสอง"""
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO routines (name, name_th, interval_days, day_of_week)"
                " VALUES ('ghost', 'ผี', NULL, NULL)"
            )
        self.conn.rollback()

    def test_kind_rejects_a_row_with_neither_field(self) -> None:
        """เผื่อฐานข้อมูลถูกซ่อมมาผิดวิธีจน CHECK ไม่ถูกบังคับ"""
        broken = {"name": "ghost", "interval_days": None, "day_of_week": None}
        with self.assertRaises(ValueError):
            routines._kind(broken)


if __name__ == "__main__":
    unittest.main()
