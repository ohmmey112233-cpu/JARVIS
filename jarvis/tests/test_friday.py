"""
เทสต์ศุกร์สลับสัปดาห์ — checklist B ของ phase1-kit บอกว่าต้องถูก "2 ศุกร์ติดกัน"
ที่นี่ตรวจ 6 ศุกร์ติดกันทั้งสองด้านของ anchor เพราะบั๊กที่กลัวที่สุดคือ
"ถูกฝั่งอนาคต แต่ผิดฝั่งอดีต" ซึ่งเทสต์ 2 ศุกร์แบบไปข้างหน้าอย่างเดียวจับไม่ได้

ทุกเทสต์ใช้ DB ในหน่วยความจำ ไม่แตะไฟล์จริง และไม่ต้องมีเน็ต/API key
"""

from __future__ import annotations

import ast
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from core import db, friday, localdate

# ปฏิทินอ้างอิงที่ใช้ทั้งไฟล์ (ยืนยันว่าเป็นศุกร์จริงใน test_reference_dates_are_fridays)
ANCHOR = "2026-08-14"  # ศุกร์
FRIDAYS = [
    "2026-07-24",  # anchor - 3
    "2026-07-31",  # anchor - 2
    "2026-08-07",  # anchor - 1
    "2026-08-14",  # anchor
    "2026-08-21",  # anchor + 1
    "2026-08-28",  # anchor + 2
    "2026-09-04",  # anchor + 3
    "2026-09-11",  # anchor + 4
    "2026-09-18",  # anchor + 5
]


class FridayStateTest(unittest.TestCase):
    """ตรรกะล้วน ไม่แตะ DB"""

    def test_reference_dates_are_fridays(self) -> None:
        # กันเทสต์ทั้งไฟล์หลอกตัวเอง: ถ้าวันที่อ้างอิงไม่ใช่ศุกร์ ผลอื่นเชื่อไม่ได้เลย
        for value in FRIDAYS:
            self.assertEqual(
                date.fromisoformat(value).weekday(), localdate.FRIDAY, value
            )

    def test_anchor_week_keeps_anchor_state(self) -> None:
        for state in (friday.HOME, friday.HOTEL):
            with self.subTest(state=state):
                plan = friday.friday_state(ANCHOR, state, ANCHOR)
                self.assertEqual(plan.state, state)
                self.assertEqual(plan.weeks_from_anchor, 0)
                self.assertEqual(plan.friday, date(2026, 8, 14))

    def test_six_consecutive_fridays_alternate_from_home_anchor(self) -> None:
        expected = [
            friday.HOME,  # 08-14 = anchor
            friday.HOTEL,  # 08-21
            friday.HOME,  # 08-28
            friday.HOTEL,  # 09-04
            friday.HOME,  # 09-11
            friday.HOTEL,  # 09-18
        ]
        for offset, want in enumerate(expected):
            day = FRIDAYS[3 + offset]
            with self.subTest(friday=day):
                plan = friday.friday_state(ANCHOR, friday.HOME, day)
                self.assertEqual(plan.state, want)
                self.assertEqual(plan.weeks_from_anchor, offset)
                self.assertEqual(plan.friday.isoformat(), day)

    def test_six_consecutive_fridays_alternate_from_hotel_anchor(self) -> None:
        # anchor อีกด้าน ต้องได้ผลตรงข้ามกันทุกช่องแบบเป๊ะๆ
        for offset in range(6):
            day = FRIDAYS[3 + offset]
            with self.subTest(friday=day):
                home_anchor = friday.friday_state(ANCHOR, friday.HOME, day)
                hotel_anchor = friday.friday_state(ANCHOR, friday.HOTEL, day)
                self.assertNotEqual(home_anchor.state, hotel_anchor.state)
                self.assertEqual(
                    hotel_anchor.state,
                    friday.HOTEL if offset % 2 == 0 else friday.HOME,
                )

    def test_is_home_matches_state(self) -> None:
        for day in FRIDAYS:
            for anchor_state in (friday.HOME, friday.HOTEL):
                with self.subTest(day=day, anchor_state=anchor_state):
                    plan = friday.friday_state(ANCHOR, anchor_state, day)
                    self.assertEqual(plan.is_home, plan.state == friday.HOME)

    def test_dates_before_anchor_get_negative_weeks(self) -> None:
        # นี่คือบั๊กที่โจทย์เตือนไว้: parity ถูกแต่ตัวเลขต้องติดลบด้วย
        cases = [("2026-08-07", -1), ("2026-07-31", -2), ("2026-07-24", -3)]
        for day, want_weeks in cases:
            with self.subTest(day=day):
                plan = friday.friday_state(ANCHOR, friday.HOME, day)
                self.assertEqual(plan.weeks_from_anchor, want_weeks)

    def test_states_before_anchor_alternate_correctly(self) -> None:
        expected = {
            "2026-07-24": friday.HOTEL,  # -3 สัปดาห์ = คี่ = สลับ
            "2026-07-31": friday.HOME,  # -2 = คู่ = เหมือน anchor
            "2026-08-07": friday.HOTEL,  # -1 = คี่ = สลับ
            "2026-08-14": friday.HOME,  # anchor
        }
        for day, want in expected.items():
            with self.subTest(day=day):
                self.assertEqual(friday.friday_state(ANCHOR, friday.HOME, day).state, want)

    def test_symmetric_offsets_have_same_state(self) -> None:
        # ห่างเท่ากันคนละฝั่ง anchor ต้องได้สถานะเดียวกันเสมอ
        for weeks in range(1, 9):
            before = date(2026, 8, 14) - timedelta(weeks=weeks)
            after = date(2026, 8, 14) + timedelta(weeks=weeks)
            with self.subTest(weeks=weeks):
                plan_before = friday.friday_state(ANCHOR, friday.HOTEL, before)
                plan_after = friday.friday_state(ANCHOR, friday.HOTEL, after)
                self.assertEqual(plan_before.state, plan_after.state)
                self.assertEqual(plan_before.weeks_from_anchor, -weeks)
                self.assertEqual(plan_after.weeks_from_anchor, weeks)

    def test_far_future_and_past_parity_holds(self) -> None:
        # 52 สัปดาห์ = เลขคู่ → เหมือน anchor ทั้งสองฝั่ง (กันบั๊กสะสมจากการนับวัน)
        plus = friday.friday_state(ANCHOR, friday.HOME, "2027-08-13")
        minus = friday.friday_state(ANCHOR, friday.HOME, "2025-08-15")
        self.assertEqual(plus.weeks_from_anchor, 52)
        self.assertEqual(minus.weeks_from_anchor, -52)
        self.assertEqual(plus.state, friday.HOME)
        self.assertEqual(minus.state, friday.HOME)

    def test_weekend_belongs_to_friday_that_just_passed(self) -> None:
        # เสาร์ 22 / อาทิตย์ 23 ส.ค. ยังเป็นสัปดาห์ของศุกร์ 21 ส.ค.
        for day in ("2026-08-22", "2026-08-23"):
            with self.subTest(day=day):
                plan = friday.friday_state(ANCHOR, friday.HOME, day)
                self.assertEqual(plan.friday, date(2026, 8, 21))
                self.assertEqual(plan.weeks_from_anchor, 1)
                self.assertEqual(plan.state, friday.HOTEL)

    def test_monday_after_weekend_starts_new_week(self) -> None:
        # จันทร์ 24 ส.ค. = สัปดาห์ใหม่ ชี้ไปศุกร์ 28 ส.ค. ไม่ใช่ 21 ส.ค.
        plan = friday.friday_state(ANCHOR, friday.HOME, "2026-08-24")
        self.assertEqual(plan.friday, date(2026, 8, 28))
        self.assertEqual(plan.weeks_from_anchor, 2)
        self.assertEqual(plan.state, friday.HOME)

    def test_midweek_points_at_upcoming_friday(self) -> None:
        # จันทร์-พฤหัสของสัปดาห์เดียวกัน ต้องได้ศุกร์ 21 ส.ค. เหมือนกันหมด
        for day in ("2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20"):
            with self.subTest(day=day):
                plan = friday.friday_state(ANCHOR, friday.HOME, day)
                self.assertEqual(plan.friday, date(2026, 8, 21))
                self.assertEqual(plan.state, friday.HOTEL)

    def test_whole_week_agrees_with_its_friday(self) -> None:
        # ทุกวันในสัปดาห์เดียวกัน (จันทร์→อาทิตย์) ต้องรายงานศุกร์ตัวเดียวกัน
        monday = date(2026, 8, 24)
        plans = [
            friday.friday_state(ANCHOR, friday.HOTEL, monday + timedelta(days=i))
            for i in range(7)
        ]
        self.assertEqual({p.friday for p in plans}, {date(2026, 8, 28)})
        self.assertEqual({p.state for p in plans}, {friday.HOTEL})

    def test_accepts_date_datetime_and_string(self) -> None:
        want = friday.friday_state(ANCHOR, friday.HOME, "2026-08-21")
        variants = [
            date(2026, 8, 21),
            datetime(2026, 8, 21, 6, 20),  # naive = ถือว่าเวลาไทย
            datetime(2026, 8, 21, 6, 20, tzinfo=localdate.TZ),
            "2026-08-21T06:20:00+07:00",
        ]
        for value in variants:
            with self.subTest(value=value):
                self.assertEqual(friday.friday_state(ANCHOR, friday.HOME, value), want)

    def test_anchor_accepts_date_object(self) -> None:
        plan = friday.friday_state(date(2026, 8, 14), friday.HOME, "2026-08-21")
        self.assertEqual(plan.state, friday.HOTEL)

    def test_utc_evening_is_next_thai_day(self) -> None:
        # 21 ส.ค. 18:00 UTC = 22 ส.ค. 01:00 ไทย (เสาร์) → ยังเป็นสัปดาห์ศุกร์ 21
        # ข้อนี้พิสูจน์แค่ว่า aware datetime รับได้และไม่หลุดไปสัปดาห์อื่น
        # (ตัวที่พิสูจน์เรื่องโซนเวลาจริงๆ คือเทสต์ถัดไป — ดูเหตุผลที่นั่น)
        clock = datetime(2026, 8, 21, 18, 0, tzinfo=timezone.utc)
        plan = friday.friday_state(ANCHOR, friday.HOME, clock)
        self.assertEqual(plan.friday, date(2026, 8, 21))
        self.assertEqual(plan.state, friday.HOTEL)

    def test_utc_sunday_evening_belongs_to_the_thai_monday_week(self) -> None:
        """กฎเหล็กข้อ 1 ของจริง — เคสเดียวที่แยก "ตัดวันแบบไทย" ออกจาก "ตัดวันแบบ UTC" ได้

        อาทิตย์ 23 ส.ค. 18:00 UTC = จันทร์ 24 ส.ค. 01:00 ไทย → สัปดาห์ใหม่ ศุกร์ 28 ส.ค.
        ถ้าเผลอตัดวันด้วย UTC จะได้อาทิตย์ 23 → ศุกร์ 21 ส.ค. ซึ่ง **สลับด้านทั้งสถานะ**
        (home ↔ hotel) = จอง Sushiro ในสัปดาห์ที่กลับจอมทองพอดี (red-team H10)

        หมายเหตุว่าทำไมต้องเป็นคืนวันอาทิตย์: เวลาที่ UTC กับไทยคนละวันแต่ยัง
        อยู่สัปดาห์เดียวกัน (เช่น คืนวันศุกร์) จะให้ผลเท่ากันทั้งสองแบบ
        เทสต์แบบนั้นจึงผ่านได้แม้โค้ดจะตัดวันผิดโซน
        """
        clock = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)
        plan = friday.friday_state(ANCHOR, friday.HOME, clock)
        self.assertEqual(plan.friday, date(2026, 8, 28))
        self.assertEqual(plan.weeks_from_anchor, 2)
        self.assertEqual(plan.state, friday.HOME)

        # เทียบกับ 17:00 UTC ของวันเดียวกัน (= เที่ยงคืนไทยพอดี) ต้องได้สัปดาห์เดียวกัน
        midnight_ict = datetime(2026, 8, 23, 17, 0, tzinfo=timezone.utc)
        self.assertEqual(friday.friday_state(ANCHOR, friday.HOME, midnight_ict), plan)

    def test_module_never_asks_the_system_clock_directly(self) -> None:
        """กฎเหล็กข้อ 1 — โมดูลนี้ห้ามถามนาฬิกาเครื่อง/ของ SQLite เอง ต้องผ่าน core.localdate

        ตรวจจาก AST ไม่ใช่ค้นข้อความดิบ เพราะ docstring ในโมดูลพูดถึงชื่อฟังก์ชัน
        ต้องห้ามพวกนี้อยู่แล้ว (อธิบายว่าทำไมถึงห้าม) — ค้นข้อความจะฟ้องผิดตัว
        """
        tree = ast.parse(Path(friday.__file__).read_text(encoding="utf-8"))
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
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                upper = node.value.upper()
                if any(k in upper for k in ("SELECT ", "UPDATE ", "INSERT ")):
                    for banned in banned_sql:
                        self.assertNotIn(banned, upper, f"ห้ามให้ SQLite คิดวันเอง: {banned}")

    def test_when_none_uses_local_today(self) -> None:
        # when=None ต้องให้ผลเท่ากับส่ง "วันนี้แบบเวลาไทย" เข้าไปตรงๆ
        self.assertEqual(
            friday.friday_state(ANCHOR, friday.HOME),
            friday.friday_state(ANCHOR, friday.HOME, localdate.local_date()),
        )

    def test_state_is_case_and_space_tolerant(self) -> None:
        plan = friday.friday_state(ANCHOR, " HOME ", "2026-08-14")
        self.assertEqual(plan.state, friday.HOME)

    def test_unknown_state_raises_value_error(self) -> None:
        for bad in ("condo", "", "บ้าน", "hom"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    friday.friday_state(ANCHOR, bad, "2026-08-14")

    def test_non_friday_anchor_raises_value_error(self) -> None:
        # ข้อผิดพลาดตอนกรอกข้อมูล ต้องดังทันที ไม่ใช่ปัดให้เป็นศุกร์ใกล้ๆ เงียบๆ
        for bad in ("2026-08-13", "2026-08-15", "2026-08-16"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as ctx:
                    friday.friday_state(bad, friday.HOME, "2026-08-21")
                self.assertIn("ศุกร์", str(ctx.exception))

    def test_unparsable_anchor_raises_value_error(self) -> None:
        for bad in ("14/08/2026", "not-a-date", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    friday.friday_state(bad, friday.HOME, "2026-08-21")


class FridayFromDbTest(unittest.TestCase):
    """ผ่าน preferences จริงใน DB ชั่วคราว"""

    def setUp(self) -> None:
        self.conn = db.connect(":memory:")
        db.migrate(self.conn)
        self.addCleanup(self.conn.close)

    def set_anchor(self, value: str) -> None:
        db.set_pref(self.conn, friday.PREF_KEY, value)

    def test_reads_home_anchor(self) -> None:
        self.set_anchor("2026-08-14:home")
        plan = friday.friday_state_from_db(self.conn, "2026-08-14")
        self.assertEqual(plan.state, friday.HOME)
        self.assertTrue(plan.is_home)
        self.assertEqual(plan.weeks_from_anchor, 0)

    def test_reads_hotel_anchor(self) -> None:
        self.set_anchor("2026-08-14:hotel")
        plan = friday.friday_state_from_db(self.conn, "2026-08-14")
        self.assertEqual(plan.state, friday.HOTEL)
        self.assertFalse(plan.is_home)

    def test_alternates_across_six_fridays_from_db(self) -> None:
        self.set_anchor("2026-08-14:home")
        got = [
            friday.friday_state_from_db(self.conn, day).state for day in FRIDAYS[3:]
        ]
        self.assertEqual(
            got,
            [
                friday.HOME,
                friday.HOTEL,
                friday.HOME,
                friday.HOTEL,
                friday.HOME,
                friday.HOTEL,
            ],
        )

    def test_alternates_backwards_from_db(self) -> None:
        self.set_anchor("2026-08-14:hotel")
        got = [
            (day, friday.friday_state_from_db(self.conn, day).weeks_from_anchor)
            for day in FRIDAYS[:3]
        ]
        self.assertEqual(got, [("2026-07-24", -3), ("2026-07-31", -2), ("2026-08-07", -1)])

    def test_value_with_surrounding_spaces_still_works(self) -> None:
        self.set_anchor("  2026-08-14 : HOTEL ")
        plan = friday.friday_state_from_db(self.conn, "2026-08-14")
        self.assertEqual(plan.state, friday.HOTEL)

    def test_missing_preference_propagates(self) -> None:
        # ไม่มีคีย์เลย → ต้องเป็น MissingPreference ไม่ใช่ ValueError หรือค่า default
        #
        # ลบแถวทิ้งเองแทนที่จะหวังว่า seed จะเป็น '[ต้องกรอก]' อยู่:
        # ไฟล์ schema ใหม่ (003_ohm_values.sql) เติมค่าจริงให้ตั้งแต่ migrate()
        # เทสต์ที่ยืมสภาพจาก seed จึงเปลี่ยนความหมายไปเงียบๆ เมื่อ seed เปลี่ยน
        self.conn.execute("DELETE FROM preferences WHERE key = ?", (friday.PREF_KEY,))
        self.conn.commit()
        self.assertIsNone(db.get_pref(self.conn, friday.PREF_KEY))
        with self.assertRaises(db.MissingPreference):
            friday.friday_state_from_db(self.conn, "2026-08-14")

    def test_unfilled_placeholder_propagates(self) -> None:
        # ค่าที่ kit ใส่ไว้ให้กรอก — ต้องระเบิดเหมือนไม่มีค่า
        self.set_anchor("[ต้องกรอก]")
        with self.assertRaises(db.MissingPreference):
            friday.friday_state_from_db(self.conn, "2026-08-14")

    def test_malformed_values_raise_value_error_with_format_hint(self) -> None:
        bad_values = [
            "2026-08-14",  # ลืมระบุด้าน
            "2026-08-14:",  # ด้านว่าง
            "2026-08-14:condo",  # ด้านที่ไม่รู้จัก
            "home:2026-08-14",  # สลับที่กัน
            "14-08-2026:home",  # รูปแบบวันผิด
            "2026-13-40:home",  # วันที่ไม่มีจริง
            ":home",  # ไม่มีวัน
        ]
        for bad in bad_values:
            with self.subTest(bad=bad):
                self.set_anchor(bad)
                with self.assertRaises(ValueError) as ctx:
                    friday.friday_state_from_db(self.conn, "2026-08-14")
                message = str(ctx.exception)
                self.assertIn("YYYY-MM-DD:home", message)
                self.assertIn(friday.PREF_KEY, message)

    def test_non_friday_anchor_in_db_raises_value_error(self) -> None:
        self.set_anchor("2026-08-13:home")  # พฤหัสบดี
        with self.assertRaises(ValueError) as ctx:
            friday.friday_state_from_db(self.conn, "2026-08-14")
        self.assertIn("ศุกร์", str(ctx.exception))

    def test_missing_preference_is_not_value_error(self) -> None:
        # MissingPreference สืบทอดจาก RuntimeError — ผู้เรียกต้องแยกสองกรณีนี้ออกจากกันได้
        self.assertFalse(issubclass(db.MissingPreference, ValueError))


class SushiroGateTest(unittest.TestCase):
    """red-team H10 — จองเฉพาะศุกร์ที่อยู่ในเมืองเชียงใหม่"""

    def setUp(self) -> None:
        self.conn = db.connect(":memory:")
        db.migrate(self.conn)
        self.addCleanup(self.conn.close)

    def test_books_only_on_hotel_fridays(self) -> None:
        db.set_pref(self.conn, friday.PREF_KEY, "2026-08-14:home")
        got = [
            friday.is_in_chiang_mai_on_friday(self.conn, day) for day in FRIDAYS[3:]
        ]
        # ไม่มีศุกร์ไหนถูกยืนยัน → ประตูปิดหมด แม้การคาดเดาจะบอกว่าอยู่เชียงใหม่
        # (H10: เดาผิดแล้ว no-show โดนแบน ต้นทุนสูงกว่าการไม่จองมาก)
        self.assertEqual(got, [False] * 6)

    def test_ยืนยันแล้วเท่านั้นจึงเปิดประตู(self) -> None:
        db.set_pref(self.conn, friday.PREF_KEY, "2026-08-14:home")
        hotel_friday = FRIDAYS[4]          # การคาดเดาบอกว่าอยู่เชียงใหม่
        self.assertFalse(friday.is_in_chiang_mai_on_friday(self.conn, hotel_friday))
        friday.set_friday(self.conn, hotel_friday, friday.HOTEL)
        self.assertTrue(friday.is_in_chiang_mai_on_friday(self.conn, hotel_friday))
        # ยืนยันว่ากลับบ้าน → ปิดประตูแม้เคยเปิดมาก่อน
        friday.set_friday(self.conn, hotel_friday, friday.HOME)
        self.assertFalse(friday.is_in_chiang_mai_on_friday(self.conn, hotel_friday))

    def test_require_confirmed_False_กลับไปใช้การคาดเดา(self) -> None:
        db.set_pref(self.conn, friday.PREF_KEY, "2026-08-14:home")
        got = [
            friday.is_in_chiang_mai_on_friday(self.conn, d, require_confirmed=False)
            for d in FRIDAYS[3:]
        ]
        self.assertEqual(got, [False, True, False, True, False, True])

    def test_hotel_anchor_flips_the_gate(self) -> None:
        db.set_pref(self.conn, friday.PREF_KEY, "2026-08-14:hotel")
        got = [
            friday.is_in_chiang_mai_on_friday(self.conn, day, require_confirmed=False)
            for day in FRIDAYS[3:]
        ]
        self.assertEqual(got, [True, False, True, False, True, False])

    def test_gate_agrees_with_plan_on_every_day_of_a_week(self) -> None:
        db.set_pref(self.conn, friday.PREF_KEY, "2026-08-14:home")
        monday = date(2026, 8, 17)
        for i in range(7):
            day = monday + timedelta(days=i)
            with self.subTest(day=day):
                plan = friday.friday_state_from_db(self.conn, day)
                self.assertEqual(
                    friday.is_in_chiang_mai_on_friday(self.conn, day, require_confirmed=False),
                    not plan.is_home,
                )

    def test_gate_raises_when_anchor_unfilled(self) -> None:
        # ไม่ยอมคืน False เงียบๆ เพราะระบบจองที่หยุดทำงานเงียบๆ ก็เป็นบั๊กเหมือนกัน
        db.set_pref(self.conn, friday.PREF_KEY, "[ต้องกรอก]")
        with self.assertRaises(db.MissingPreference):
            friday.is_in_chiang_mai_on_friday(self.conn, "2026-08-21")


if __name__ == "__main__":
    unittest.main()
