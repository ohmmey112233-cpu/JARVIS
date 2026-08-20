"""
เทสต์ตัวเรนเดอร์ข้อความ — ยึด jarvis-phase1-kit.md ส่วนที่ 1 เป็นความจริง

ทำไมเทสต์ไฟล์นี้ถึงเทียบข้อความแบบ "ทั้งก้อนเป๊ะๆ" ไม่ใช่เช็คว่ามีคำนั้นคำนี้:
    kit บอกให้ยึดตัวอย่าง "เป๊ะทุกตัวอักษร — เว้นวรรค อีโมจิ การขึ้นบรรทัด"
    การเช็คแบบ assertIn จะปล่อยให้เว้นวรรคหรือบรรทัดว่างเพี้ยนไปเรื่อยๆ
    ซึ่งเป็นการดริฟต์แบบเดียวกับที่ personal-os-analysis เตือนไว้พอดี

สองจุดที่ผลลัพธ์ต่างจากตัวอย่างใน kit โดยตั้งใจ (มีคอมเมนต์กำกับในเทสต์ด้วย):
    1. ตัวอย่างเช้าวันศุกร์เขียน "💨 AQI 55" เฉยๆ ขณะที่วันจันทร์/พุธมีคำอธิบายต่อท้าย
       → เลือกให้มีคำอธิบายทุกครั้ง เพราะ 55 กับ 68 อยู่แถบเดียวกัน (ปานกลาง)
         ถ้าบางวันมีบางวันไม่มี จะอ่านเหมือนคนละคนเขียน (checklist D ข้อ 3)
    2. ตัวอย่างสรุปสัปดาห์เขียน "(พฤหัส)" ซึ่งไม่ใช่ทั้งชื่อเต็มและชื่อย่อ
       → ใช้ชื่อจาก core.localdate ("พฤหัสบดี") เพราะกฎเหล็กบอกว่าชื่อวัน
         ต้องมาจากที่เดียว ห้ามมีตารางชื่อวันชุดที่สองในระบบ

ทุกเทสต์รันโดยไม่แตะนาฬิกาจริง ไม่แตะเน็ต ไม่แตะฐานข้อมูล — เวลาฉีดเข้าทาง
DigestContext.when ทั้งหมด (กฎเหล็กข้อ 1)
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from core import digest, localdate
from core.friday import FridayPlan
from core.routines import RoutineStatus

# ปฏิทินอ้างอิงชุดเดียวกับ test_friday.py — 2026-08-14 เป็นศุกร์ (anchor)
MONDAY = datetime(2026, 8, 17, 6, 20)
WEDNESDAY = datetime(2026, 8, 19, 6, 0)
FRIDAY_HOME = datetime(2026, 8, 28, 6, 20)  # ห่าง anchor 2 สัปดาห์ = ด้านเดียวกับ anchor
FRIDAY_HOTEL = datetime(2026, 8, 21, 6, 20)
SUNDAY = datetime(2026, 8, 30, 20, 0)

HOME_PLAN = FridayPlan(friday=date(2026, 8, 28), state="home", is_home=True, weeks_from_anchor=2)
HOTEL_PLAN = FridayPlan(friday=date(2026, 8, 21), state="hotel", is_home=False, weeks_from_anchor=1)
# ตัวอย่างสรุปสัปดาห์ใน kit จบด้วย "จองโรงแรมให้เลยไหมครับ?" ซึ่งจะถามได้ก็ต่อเมื่อ
# รู้แน่แล้วว่าสัปดาห์นั้นอยู่เชียงใหม่ → ตัวอย่างนี้คือสัปดาห์ที่ "ยืนยันแล้ว"
# (สัปดาห์ที่ยังไม่ยืนยันจะถามยืนยันก่อน ไม่ชวนจอง — ดู UnconfirmedFridayTest)
NEXT_WEEK_HOTEL = FridayPlan(
    friday=date(2026, 9, 4), state="hotel", is_home=False, weeks_from_anchor=3,
    confirmed=True,
)


def routine(
    name: str,
    name_th: str,
    *,
    kind: str = "interval",
    due: bool = True,
    days_since: int | None = None,
    days_until: int | None = None,
    next_due: date | None = None,
    last_done: str | None = None,
    notes: str | None = None,
) -> RoutineStatus:
    """สร้าง RoutineStatus ของจริง (ไม่ใช่ stub) เพื่อให้เทสต์จับได้ถ้าสัญญาเปลี่ยน"""
    return RoutineStatus(
        name=name,
        name_th=name_th,
        kind=kind,
        due=due,
        days_since=days_since,
        days_until=days_until,
        next_due=next_due,
        last_done=last_done,
        notes=notes,
    )


class KitMorningTest(unittest.TestCase):
    """3 ตัวอย่างข้อความเช้าใน kit ส่วนที่ 1"""

    def test_monday_matches_kit_word_for_word(self) -> None:
        ctx = digest.DigestContext(
            when=MONDAY,
            travel_minutes=12,
            leave_by="07:15",
            weather_summary="28° ไม่มีฝนช่วงเช้า",
            aqi=42,
            first_subject="ชีววิทยา",
            # kit เขียน "8 คาบเต็ม" ส่วน seed จริงของวันจันทร์เป็น 7 —
            # ที่นี่ยึดตัวเลขตามตัวอย่างเพื่อพิสูจน์ว่ารูปประโยคมาจากข้อมูล ไม่ได้ฝังไว้
            period_count="8",
            tomorrow_note="อังคาร มีตัดผมตอนเย็น",
        )
        expected = (
            "อรุณสวัสดิ์ครับ ☀️ 06:20\n"
            "\n"
            "วันนี้จันทร์ เรียน 8 คาบเต็ม\n"
            "คาบแรก ชีววิทยา 08:20\n"
            "\n"
            "🚗 หอ→โรงเรียน ตอนนี้ 12 นาที\n"
            "   ออก 07:15 ถึงสบายๆ\n"
            "\n"
            "🌤️ 28° ไม่มีฝนช่วงเช้า\n"
            "💨 AQI 42 — อากาศดี\n"
            "\n"
            "📌 วันนี้ยังไม่มีอะไรถึงรอบ\n"
            "\n"
            "พรุ่งนี้: อังคาร มีตัดผมตอนเย็น"
        )
        self.assertEqual(digest.render_morning(ctx), expected)

    def test_wednesday_matches_kit_word_for_word(self) -> None:
        ctx = digest.DigestContext(
            when=WEDNESDAY,
            travel_minutes=15,
            leave_by="07:10",
            rain_window="07:00-08:00",
            aqi=68,
            # ทำคิ้วเลยกำหนดมา 1 วัน → รอบ 7 วันมาจาก days_since + days_until
            due_routines=[
                routine("eyebrow", "ทำคิ้ว", days_since=8, days_until=-1, next_due=date(2026, 8, 18))
            ],
        )
        expected = (
            "อรุณสวัสดิ์ครับ ☀️ 06:00\n"
            "\n"
            "⚠️ วันนี้พุธ ตื่นเร็วกว่าปกติ 20 นาที\n"
            "\n"
            "เช้า: เรียนถึงเที่ยง\n"
            "บ่าย: ร.ด. (เลิกไม่แน่นอน ~16:30-17:00)\n"
            "\n"
            "🚗 หอ→โรงเรียน 15 นาที (รถติดกว่าปกติ)\n"
            "   ออก 07:10 ดีกว่า\n"
            "\n"
            "🌧️ ฝนน่าจะตก 07:00-08:00 → พกร่ม\n"
            "💨 AQI 68 — ปานกลาง\n"
            "\n"
            "📌 ทำคิ้ว ครบ 7 วันแล้ว"
        )
        self.assertEqual(digest.render_morning(ctx), expected)

    def test_friday_home_week_matches_kit_word_for_word(self) -> None:
        ctx = digest.DigestContext(
            when=FRIDAY_HOME,
            travel_minutes=11,
            weather_summary="29° แดดจัด",
            aqi=55,
            friday=HOME_PLAN,
            first_subject="ชีววิทยา",
            period_count="7",
            due_routines=[
                routine("diode", "ไดโอด", days_since=14, days_until=0, next_due=date(2026, 8, 28))
            ],
        )
        expected = (
            "อรุณสวัสดิ์ครับ ☀️ 06:20\n"
            "\n"
            "วันนี้ศุกร์ — สัปดาห์นี้กลับบ้านจอมทอง 🏡\n"
            "(ไม่ใช่สัปดาห์โรงแรม)\n"
            "\n"
            "เรียน 7 คาบ คาบแรกชีววิทยา 08:20\n"
            "\n"
            "🚗 หอ→โรงเรียน 11 นาที\n"
            "🌤️ 29° แดดจัด\n"
            # kit เขียน "💨 AQI 55" เฉยๆ — ดูเหตุผลที่เติมคำอธิบายในหัวไฟล์
            "💨 AQI 55 — ปานกลาง\n"
            "\n"
            "📌 ไดโอด ครบ 14 วันวันนี้\n"
            "\n"
            "เย็นนี้: โรงเรียน→จอมทอง ~1 ชม. 20 นาที"
        )
        self.assertEqual(digest.render_morning(ctx), expected)


class KitOtherMessagesTest(unittest.TestCase):
    """อีก 4 แบบที่เหลือใน kit ส่วนที่ 1"""

    def test_evening_matches_kit_word_for_word(self) -> None:
        ctx = digest.DigestContext(
            when=datetime(2026, 8, 17, 18, 30), tomorrow_note="อังคาร ตัดผมตอนเย็น"
        )
        expected = (
            "เย็นนี้เป็นไงบ้างครับ 🌙\n"
            "\n"
            "วันนี้ที่เกิดขึ้น:\n"
            "✅ จองร้าน [X] พรุ่งนี้ 18:00 4 ที่ — สำเร็จ\n"
            "✅ ทำคิ้วแล้ว (บันทึกรอบใหม่แล้ว)\n"
            "\n"
            "📋 งานบริษัทค้างอยู่ 3 รายการ\n"
            "   • ใบกำกับภาษี บจก. A — เกินกำหนด 2 วัน\n"
            "   • ภ.ง.ด.51 บจก. B — ครบกำหนดศุกร์นี้\n"
            "   • วางบิล บจก. C — สัปดาห์หน้า\n"
            "\n"
            "พรุ่งนี้: อังคาร ตัดผมตอนเย็น\n"
            "เตือนอีกทีตอนเช้าครับ"
        )
        actual = digest.render_evening(
            ctx,
            done_items=[
                "จองร้าน [X] พรุ่งนี้ 18:00 4 ที่ — สำเร็จ",
                "ทำคิ้วแล้ว (บันทึกรอบใหม่แล้ว)",
            ],
            pending_work=[
                "ใบกำกับภาษี บจก. A — เกินกำหนด 2 วัน",
                "ภ.ง.ด.51 บจก. B — ครบกำหนดศุกร์นี้",
                "วางบิล บจก. C — สัปดาห์หน้า",
            ],
        )
        self.assertEqual(actual, expected)

    def test_weekly_matches_kit_word_for_word(self) -> None:
        ctx = digest.DigestContext(when=SUNDAY, friday=NEXT_WEEK_HOTEL)
        expected = (
            "สัปดาห์หน้ามีอะไรบ้าง 📅\n"
            "\n"
            "จ. — ปกติ\n"
            "อ. — ✂️ ตัดผม ร้านเกษมเกษา (เย็น)\n"
            "พ. — ⚠️ ตื่น 06:30 + ร.ด. บ่าย\n"
            "พฤ. — ปกติ\n"
            "ศ. — 🏨 สัปดาห์โรงแรม (คราวนี้ไม่กลับจอมทอง)\n"
            "\n"
            "📌 ถึงรอบสัปดาห์หน้า:\n"
            # kit เขียน "(พฤหัส)" — ที่นี่ใช้ชื่อวันจาก core.localdate (ดูหัวไฟล์)
            "   • ไดโอด (พฤหัสบดี)\n"
            "\n"
            "จองโรงแรมให้เลยไหมครับ?"
        )
        actual = digest.render_weekly(
            ctx,
            week_rows=[
                ("จ.", "ปกติ"),
                ("อ.", "✂️ ตัดผม ร้านเกษมเกษา (เย็น)"),
                ("พ.", "⚠️ ตื่น 06:30 + ร.ด. บ่าย"),
                ("พฤ.", "ปกติ"),
                ("ศ.", "🏨 สัปดาห์โรงแรม (คราวนี้ไม่กลับจอมทอง)"),
            ],
            due_next_week=[
                routine(
                    "diode",
                    "ไดโอด",
                    due=False,
                    days_since=11,
                    days_until=3,
                    next_due=date(2026, 9, 3),  # พฤหัสบดี
                )
            ],
        )
        self.assertEqual(actual, expected)

    def test_dream_report_matches_kit_word_for_word(self) -> None:
        # รูปคีย์ชุดนี้คือสิ่งที่ memory.consolidate() คืนมาจริง
        summary = {
            "date_key": "2026-08-18",
            "unused_days": 60,
            "archived_count": 1,
            "archived": [{"id": 4, "topic": "เวลาจองร้านอาหาร", "idle_days": 74}],
            "merged_topics": [
                {"topic": "เวลาจองร้านอาหาร", "archived": 2, "kept": 1, "merged_from": 3}
            ],
            "skipped": [],
            "nothing_to_report": False,
        }
        expected = (
            "เมื่อคืนจัดระเบียบความจำครับ\n"
            "\n"
            "รวมเรื่องซ้ำ 3 ก้อนเป็นก้อนเดียว\n"
            "(เรื่องเวลาจองร้านอาหาร)\n"
            "\n"
            "พักไว้ 1 ก้อนที่ไม่ได้ใช้มา 2 เดือน\n"
            '— ดูรายการที่พักไว้ พิมพ์ "ดูความจำที่พัก"'
        )
        self.assertEqual(digest.render_dream_report(summary), expected)

    def test_command_replies_match_kit_word_for_word(self) -> None:
        self.assertEqual(digest.render_call_ack(), "กำลังโทรให้ครับ รอสักครู่")
        self.assertEqual(
            digest.render_booking_reply(
                "[X]",
                "พรุ่งนี้",
                "18:00",
                4,
                confirmed=True,
                booked_name="โอม",
                calendar_added=True,
            ),
            "เรียบร้อยครับ ✅\n[X] พรุ่งนี้ 18:00 4 ที่ ชื่อโอม\nใส่ปฏิทินให้แล้ว",
        )
        self.assertEqual(
            digest.render_routine_done(
                routine(
                    "eyebrow",
                    "ทำคิ้ว",
                    due=False,
                    days_since=0,
                    days_until=7,
                    next_due=date(2026, 8, 24),
                    last_done="2026-08-17",
                )
            ),
            "บันทึกแล้วครับ รอบหน้า 24 ส.ค.",
        )
        self.assertEqual(
            digest.render_lesson_saved(follow_up="คราวนี้จะเตือนก่อน"),
            "จำแล้วครับ คราวนี้จะเตือนก่อน",
        )


# --- helper สำหรับเทสต์กลุ่มความทนทาน -----------------------------------------


def assert_clean(case: unittest.TestCase, text: str, label: str = "") -> None:
    """เงื่อนไขที่ข้อความทุกก้อนต้องผ่าน ไม่ว่าข้อมูลจะขาดแค่ไหน"""
    case.assertTrue(text.strip(), f"ข้อความว่างเปล่า {label}")
    for leak in ("None", "null", "nan"):
        case.assertNotIn(leak, text, f"ค่าว่างหลุดออกไปเป็นตัวอักษร {label}")
    # red-team H12 — เซนเซอร์รู้แค่เปิด/ปิด ห้ามพูดคำนี้ในทุกข้อความ
    case.assertNotIn("ล็อค", text, f"พูดคำต้องห้ามเรื่องประตู {label}")
    case.assertNotIn("\n\n\n", text, f"มีย่อหน้าว่างซ้อนกัน {label}")
    case.assertFalse(text.startswith("\n"), f"ขึ้นต้นด้วยบรรทัดว่าง {label}")
    case.assertFalse(text.endswith("\n"), f"ลงท้ายด้วยบรรทัดว่าง {label}")
    case.assertLessEqual(
        len(text.splitlines()),
        digest.MAX_SCREEN_LINES,
        f"ยาวเกิน 1 หน้าจอมือถือ {label}",
    )


class ApiOutageTest(unittest.TestCase):
    """checklist E: API ล่ม → digest ยังส่งได้ แค่ข้ามหัวข้อนั้น

    เทสต์กลุ่มนี้คือข้อที่ kit บอกว่า "คนมักลืมทดสอบ" — จึงยิงกรณีที่ทุก field
    ที่มาจากภายนอกเป็น None พร้อมกัน ซึ่งคือสภาพตอน VPS เน็ตหลุดชั่วคราว
    """

    def test_morning_with_every_optional_field_missing(self) -> None:
        for label, when, plan in (
            ("จันทร์", MONDAY, None),
            ("พุธ", WEDNESDAY, None),
            ("ศุกร์ไม่รู้สถานะ", FRIDAY_HOME, None),
            ("ศุกร์กลับบ้าน", FRIDAY_HOME, HOME_PLAN),
        ):
            with self.subTest(day=label):
                text = digest.render_morning(digest.DigestContext(when=when, friday=plan))
                assert_clean(self, text, label)
                self.assertIn("อรุณสวัสดิ์ครับ", text)
                # ไม่มีข้อมูล routine = ต้องบอกบรรทัดเดียว ไม่ใช่หายไปเฉยๆ (หลักการข้อ 4)
                self.assertIn(digest.NOTHING_DUE, text)
                for heading in ("🚗", "🌤️", "🌧️", "💨", "📅"):
                    self.assertNotIn(heading, text, f"หัวข้อที่ไม่มีข้อมูลยังโผล่ ({heading})")

    def test_evening_and_weekly_and_dream_with_nothing_to_say(self) -> None:
        ctx = digest.DigestContext(when=datetime(2026, 8, 17, 18, 30))
        evening = digest.render_evening(ctx, done_items=[], pending_work=[])
        assert_clean(self, evening, "เย็น")
        self.assertIn(digest.EVENING_NOTHING, evening)
        # ห้ามประกาศว่า "ไม่มีงานค้าง" เพราะรายการว่างอาจแปลว่าดึงข้อมูลไม่ได้
        self.assertNotIn("📋", evening)

        weekly = digest.render_weekly(
            digest.DigestContext(when=SUNDAY), week_rows=[], due_next_week=[]
        )
        assert_clean(self, weekly, "สัปดาห์")
        self.assertIn(digest.WEEKLY_NOTHING, weekly)
        # ไม่รู้ว่าศุกร์หน้าอยู่ไหน = ห้ามชวนจองโรงแรม
        self.assertNotIn(digest.HOTEL_QUESTION, weekly)

        dream = digest.render_dream_report({"nothing_to_report": True, "archived_count": 0})
        assert_clean(self, dream, "ความฝัน")
        self.assertEqual(dream, digest.DREAM_NOTHING)
        self.assertEqual(len(dream.splitlines()), 1)

    def test_dream_report_survives_a_summary_missing_every_key(self) -> None:
        assert_clean(self, digest.render_dream_report({}), "summary ว่าง")

    def test_garbage_values_from_apis_are_skipped_not_printed(self) -> None:
        ctx = digest.DigestContext(
            when=MONDAY,
            travel_minutes="ไม่รู้",  # Routes ตอบมาเป็นข้อความ
            leave_by="   ",
            weather_summary="null",  # JSON null ที่ถูก stringify มา
            rain_window="None",
            aqi=-1,  # Air4Thai ส่งค่าสำรองมาเป็นค่าติดลบ
            calendar_items=[None, "", "null"],
            period_count="None",
            first_subject=None,
            tomorrow_note="",
        )
        text = digest.render_morning(ctx)
        assert_clean(self, text, "ค่าขยะ")
        self.assertEqual(text.splitlines()[2], "วันนี้จันทร์")

    def test_aqi_out_of_range_drops_only_its_own_line(self) -> None:
        ctx = digest.DigestContext(when=MONDAY, aqi=-5, weather_summary="28° แดดจัด")
        text = digest.render_morning(ctx)
        self.assertNotIn("💨", text)
        self.assertIn("🌤️ 28° แดดจัด", text)  # หัวข้ออื่นต้องไม่โดนหางเลข


class BannedWordTest(unittest.TestCase):
    """red-team H12 — บังคับในโค้ด ไม่ใช่แค่ใน prompt

    "ประตูปิดสนิทแต่ไม่ได้ล็อค เซนเซอร์จะรายงานว่าปิด → Jarvis ตอบว่าเรียบร้อย
     ทั้งที่ไม่ได้ล็อค = อันตรายกว่าไม่มีระบบเลย เพราะไว้ใจผิด"
    ข้อความจากภายนอกจึงต้องถูกตัดทั้งบรรทัด ไม่ใช่แค่หวังว่าโมเดลจะไม่พูด
    """

    POISON = "ประตูล็อคเรียบร้อยแล้ว"

    def test_poisoned_calendar_item_is_dropped_but_message_survives(self) -> None:
        ctx = digest.DigestContext(
            when=MONDAY,
            calendar_items=[self.POISON, "ประชุมสภานักเรียน 15:30"],
            weather_summary="28° แดดจัด",
        )
        text = digest.render_morning(ctx)
        assert_clean(self, text, "calendar")
        self.assertIn("ประชุมสภานักเรียน 15:30", text)
        self.assertNotIn("ประตู", text)

    def test_poisoned_evening_and_weekly_inputs_are_dropped(self) -> None:
        ctx = digest.DigestContext(when=datetime(2026, 8, 17, 18, 30))
        evening = digest.render_evening(
            ctx, done_items=[self.POISON, "ทำคิ้วแล้ว"], pending_work=[self.POISON]
        )
        assert_clean(self, evening, "เย็น")
        self.assertIn("✅ ทำคิ้วแล้ว", evening)
        self.assertNotIn("📋", evening)  # เหลือ 0 รายการที่ใช้ได้ = ไม่ต้องมีหัวข้อ

        weekly = digest.render_weekly(
            digest.DigestContext(when=SUNDAY),
            week_rows=[("ศ.", self.POISON), "จ. — ปกติ"],
            due_next_week=[self.POISON],
        )
        assert_clean(self, weekly, "สัปดาห์")
        self.assertIn("จ. — ปกติ", weekly)

    def test_every_message_type_is_free_of_the_word(self) -> None:
        # กวาดทุก render_* ด้วยข้อมูลที่มีคำต้องห้ามปนทุกช่องที่รับข้อความได้
        ctx = digest.DigestContext(
            when=FRIDAY_HOME,
            friday=HOME_PLAN,
            weather_summary=self.POISON,
            rain_window=self.POISON,
            first_subject=self.POISON,
            period_count=self.POISON,
            tomorrow_note=self.POISON,
            calendar_items=[self.POISON],
            due_routines=[self.POISON],
        )
        messages = [
            digest.render_morning(ctx),
            digest.render_evening(ctx, done_items=[self.POISON], pending_work=[self.POISON]),
            digest.render_weekly(ctx, week_rows=[self.POISON], due_next_week=[self.POISON]),
            digest.render_dream_report({"archived_count": 1, "unused_days": 60}),
            digest.render_call_ack(),
            digest.render_booking_reply(self.POISON, confirmed=False, note=self.POISON),
            digest.render_lesson_saved(self.POISON),
        ]
        for text in messages:
            assert_clean(self, text, "กวาดทุกแบบ")


class UnconfirmedFridayTest(unittest.TestCase):
    """ศุกร์ที่ยังไม่ยืนยัน → สรุปสัปดาห์ต้อง "ถาม" ไม่ใช่ "ประกาศ"

    โอมบอกเองว่าเรื่องกลับบ้าน "แล้วแต่สถานการณ์" — ระบบที่ประกาศอย่างมั่นใจ
    จากการสลับล้วนๆ จะพาไปจองผิดสัปดาห์ (โทษเดียวกับ H10)
    """

    def _weekly(self, plan) -> str:
        return digest.render_weekly(
            digest.DigestContext(when=localdate.now(datetime(2026, 8, 30, 20, 0)), friday=plan),
            week_rows=[],
            due_next_week=[],
        )

    def test_ยังไม่ยืนยันแล้วคาดว่าอยู่เชียงใหม่_ต้องถามยืนยัน_ไม่ชวนจอง(self) -> None:
        plan = FridayPlan(friday=date(2026, 9, 4), state="hotel", is_home=False,
                          weeks_from_anchor=3, confirmed=False)
        out = self._weekly(plan)
        self.assertIn("ศุกร์หน้าคาดว่าอยู่เชียงใหม่ 🏨 — ใช่ไหมครับ?", out)
        self.assertNotIn("จองโรงแรม", out)

    def test_ยังไม่ยืนยันแล้วคาดว่ากลับบ้าน_ก็ต้องถามเหมือนกัน(self) -> None:
        plan = FridayPlan(friday=date(2026, 9, 4), state="home", is_home=True,
                          weeks_from_anchor=3, confirmed=False)
        self.assertIn("ศุกร์หน้าคาดว่ากลับบ้านจอมทอง 🏡 — ใช่ไหมครับ?", self._weekly(plan))

    def test_ยืนยันแล้วว่ากลับบ้าน_ไม่ถามอะไรเลย(self) -> None:
        plan = FridayPlan(friday=date(2026, 9, 4), state="home", is_home=True,
                          weeks_from_anchor=3, confirmed=True)
        out = self._weekly(plan)
        self.assertNotIn("ใช่ไหมครับ", out)
        self.assertNotIn("จองโรงแรม", out)

    def test_ไม่รู้สถานะเลย_ไม่ถามอะไรทั้งนั้น(self) -> None:
        # anchor ยังไม่กรอก → friday=None → เงียบ ดีกว่าถามเรื่องที่ยังไม่รู้ว่ามีจริงไหม
        out = self._weekly(None)
        self.assertNotIn("ใช่ไหมครับ", out)
        self.assertNotIn("จองโรงแรม", out)


class ShortWalkTest(unittest.TestCase):
    """เดิน 2 นาทีถึงโรงเรียน → ไม่ต้องมีหัวข้อ 🚗 ในข้อความเช้า"""

    def _morning(self, **kw) -> str:
        return digest.render_morning(
            digest.DigestContext(when=localdate.now(datetime(2026, 8, 24, 6, 20)), **kw)
        )

    def test_เดินทางสั้นมาก_ไม่พิมพ์หัวข้อเดินทางเลย(self) -> None:
        out = self._morning(travel_minutes=2, leave_by="07:25")
        self.assertNotIn("🚗", out)
        self.assertNotIn("07:25", out)   # บรรทัด "ออก ..." ต้องหายไปด้วย
        self.assertIn("อรุณสวัสดิ์", out)  # ที่เหลือยังครบ

    def test_ขอบเกณฑ์(self) -> None:
        self.assertNotIn("🚗", self._morning(travel_minutes=4))
        self.assertIn("🚗", self._morning(travel_minutes=5))

    def test_เดินทางไกลยังรายงานตามปกติ(self) -> None:
        # ขา โรงเรียน→จอมทอง เย็นศุกร์ ยังเป็นการเดินทางจริงที่ต้องรู้
        out = self._morning(travel_minutes=58, leave_by="16:30")
        self.assertIn("🚗", out)
        self.assertIn("58", out)

    def test_ฝนยังเตือนให้พกร่ม_เพราะเดินไปโรงเรียน(self) -> None:
        # เดินสั้นแต่ยังเปียกได้ — บรรทัดฝนสำคัญกว่าเดิมด้วยซ้ำ
        out = self._morning(travel_minutes=2, rain_window="07:00-08:00")
        self.assertIn("พกร่ม", out)
