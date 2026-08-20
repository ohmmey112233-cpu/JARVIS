"""เทสต์ตัวประกอบ DigestContext — จุดที่ DB จริงกับ renderer มาเจอกัน"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr
from datetime import datetime

from core import assemble, db
from core.digest import render_evening, render_morning, render_weekly

# วันอ้างอิง (anchor จริงใน 003 คือ ศ. 14 ส.ค. 2026 = hotel)
MON = datetime(2026, 8, 24, 6, 20)     # จันทร์ — สัปดาห์ของศุกร์ 28 ส.ค. (hotel)
WED = datetime(2026, 8, 26, 6, 0)
SUN = datetime(2026, 8, 23, 20, 0)     # อาทิตย์ — สัปดาห์หน้าคือ 24-30 ส.ค.


class MorningContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = db.connect(":memory:")
        db.migrate(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_ดึงตารางเรียนของวันนั้น(self) -> None:
        ctx = assemble.morning_context(self.conn, MON)
        self.assertEqual(ctx.first_subject, "ชีววิทยา")
        self.assertEqual(ctx.period_count, "7")

    def test_friday_plan_มาจาก_anchor_จริง(self) -> None:
        ctx = assemble.morning_context(self.conn, MON)
        # สัปดาห์ของ 24 ส.ค. → ศุกร์ 28 ส.ค. = hotel (anchor 14 ส.ค. = hotel, ห่าง 2 สัปดาห์)
        self.assertIsNotNone(ctx.friday)
        self.assertFalse(ctx.friday.is_home)

    def test_extras_ใส่เฉพาะคีย์ที่รู้จัก(self) -> None:
        ctx = assemble.morning_context(
            self.conn, MON,
            extras={"aqi": 42, "travel_minutes": 12, "คีย์แปลก": "x", "when": "ห้ามทับ"},
        )
        self.assertEqual(ctx.aqi, 42)
        self.assertEqual(ctx.travel_minutes, 12)
        # คีย์นอกสัญญาต้องถูกเมิน โดยเฉพาะ 'when' ที่ถ้าทับได้ = ฉีดเวลาผ่าน extras ได้
        self.assertEqual(ctx.when, assemble.localdate.now(MON))

    def test_anchor_ยังไม่กรอก_ได้_None_พร้อมเสียงเตือน_และ_digest_ยังออก(self) -> None:
        conn = db.connect(":memory:")
        db.migrate(conn, target_version=2)   # ตรึงก่อน 003 = ยังเป็น [ต้องกรอก]
        err = io.StringIO()
        with redirect_stderr(err):
            ctx = assemble.morning_context(conn, MON)
        self.assertIsNone(ctx.friday)
        self.assertIn("friday_anchor_date", err.getvalue())
        text = render_morning(ctx)           # A1: digest ต้องออกแม้ config พัง
        self.assertIn("อรุณสวัสดิ์", text)
        conn.close()


class EveningInputsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = db.connect(":memory:")
        db.migrate(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_routine_ที่ทำวันนี้โผล่ใน_done(self) -> None:
        self.conn.execute(
            "UPDATE routines SET last_done = '2026-08-24' WHERE name = 'eyebrow'"
        )
        _, done, _ = assemble.evening_inputs(self.conn, MON)
        self.assertIn("ทำคิ้วแล้ว (บันทึกรอบใหม่แล้ว)", done)

    def test_booking_ยืนยันวันนี้โผล่ใน_done_ตามขอบวันแบบไทย(self) -> None:
        # 23 ส.ค. 17:30 UTC = 24 ส.ค. 00:30 เวลาไทย → ต้องนับเป็น "วันนี้" ของวันที่ 24
        self.conn.execute(
            "INSERT INTO bookings (kind, place_name, booking_date, booking_time,"
            " party_size, status, result_note, updated_at) VALUES"
            " ('restaurant', 'ร้าน X', '2026-08-25', '18:00', 4, 'confirmed',"
            "  'ร้านยืนยันแล้ว', '2026-08-23 17:30:00')"
        )
        # ยืนยันเมื่อวานบ่ายไทย (24 ส.ค. 10:00 UTC = ... ) — ใส่ตัวก่อนขอบไว้เทียบ
        self.conn.execute(
            "INSERT INTO bookings (kind, place_name, booking_date, status, result_note,"
            " updated_at) VALUES ('restaurant', 'ร้านเมื่อวาน', '2026-08-20',"
            " 'confirmed', 'ok', '2026-08-23 16:59:59')"
        )
        self.conn.commit()
        _, done, _ = assemble.evening_inputs(self.conn, MON)
        joined = " / ".join(done)
        self.assertIn("จองร้าน X พรุ่งนี้ 18:00 4 ที่ — สำเร็จ", joined)
        self.assertNotIn("ร้านเมื่อวาน", joined)

    def test_pending_ว่างเสมอ_และ_renderer_ไม่พิมพ์หัวข้องานบริษัท(self) -> None:
        ctx, done, pending = assemble.evening_inputs(self.conn, MON)
        self.assertEqual(pending, [])
        self.assertNotIn("📋", render_evening(ctx, done_items=done, pending_work=pending))


class WeeklyInputsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = db.connect(":memory:")
        db.migrate(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_ตารางสัปดาห์ตรงกับแบบใน_kit(self) -> None:
        ctx, rows, _ = assemble.weekly_inputs(self.conn, SUN)
        text = render_weekly(ctx, week_rows=rows, due_next_week=[])
        self.assertIn("อ. — ✂️ ตัดผม ร้านเกษมเกษา (เย็น)", text)
        self.assertIn("พ. — ⚠️ ตื่น 06:30 + บ่าย ร.ด.", text)
        # สัปดาห์ 24-30 ส.ค. → ศุกร์ 28 = hotel
        self.assertIn("ศ. — 🏨 สัปดาห์โรงแรม (คราวนี้ไม่กลับจอมทอง)", text)
        self.assertIn("จ. — ปกติ", text)
        # ศุกร์ยังไม่ถูกยืนยัน → ต้องถามยืนยันก่อน ห้ามชวนจองโรงแรม
        self.assertIn("ศุกร์หน้าคาดว่าอยู่เชียงใหม่ 🏨 — ใช่ไหมครับ?", text)
        self.assertNotIn("จองโรงแรม", text)

    def test_friday_เป็นแผนของสัปดาห์หน้า_ไม่ใช่สัปดาห์นี้(self) -> None:
        # คืนอาทิตย์ 23 ส.ค. อยู่สัปดาห์ของศุกร์ 21 (home) แต่ต้องรายงานศุกร์ 28 (hotel)
        ctx, _, _ = assemble.weekly_inputs(self.conn, SUN)
        self.assertFalse(ctx.friday.is_home)
        self.assertEqual(ctx.friday.friday.isoformat(), "2026-08-28")

    def test_ไดโอดถึงรอบสัปดาห์หน้าอยู่ในรายการ(self) -> None:
        # last_done 15 ส.ค. + 14 วัน = 29 ส.ค. (เสาร์) อยู่ใน 24-30 ส.ค.
        _, _, due_next = assemble.weekly_inputs(self.conn, SUN)
        names = [s.name for s in due_next]
        self.assertIn("diode", names)
        self.assertNotIn("haircut", names, "แบบวันประจำอยู่ในตารางแล้ว ห้ามซ้ำ")

    def test_ยืนยันแล้วจึงชวนจองโรงแรม(self) -> None:
        from core import friday as friday_mod

        friday_mod.set_friday(self.conn, "2026-08-28", friday_mod.HOTEL)
        ctx, rows, due = assemble.weekly_inputs(self.conn, SUN)
        text = render_weekly(ctx, week_rows=rows, due_next_week=due)
        self.assertIn("จองโรงแรมให้เลยไหมครับ?", text)
        self.assertNotIn("ใช่ไหมครับ?\n", text.replace("จองโรงแรมให้เลยไหมครับ?", ""))

    def test_สัปดาห์หน้าที่กลับบ้าน_ไม่ถามเรื่องโรงแรม(self) -> None:
        SUN_HOME = datetime(2026, 8, 30, 20, 0)   # สัปดาห์หน้า = ศุกร์ 4 ก.ย. (home)
        ctx, rows, due = assemble.weekly_inputs(self.conn, SUN_HOME)
        text = render_weekly(ctx, week_rows=rows, due_next_week=due)
        self.assertIn("ศ. — 🏡 กลับบ้านจอมทอง", text)
        self.assertNotIn("จองโรงแรม", text)


class DreamSummaryTests(unittest.TestCase):
    def test_คืน_dict_ที่_renderer_อ่านได้(self) -> None:
        conn = db.connect(":memory:")
        db.migrate(conn)
        summary = assemble.dream_summary(conn, MON)
        for key in ("archived_count", "merged_topics", "unused_days"):
            self.assertIn(key, summary)
        conn.close()


if __name__ == "__main__":
    unittest.main()
