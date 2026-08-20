"""เทสต์ว่าค่าที่โอมกรอกเอง (003) ถูกใส่แล้วและใช้การได้จริง

เทสต์นี้ไม่ล็อกว่า "ต้องเป็นวันที่นี้เท่านั้น" เพราะค่าพวกนี้เปลี่ยนได้
(โอมกรอกใหม่ได้ด้วย migration 004) แต่ล็อก "คุณสมบัติ" ที่ห้ามผิดเด็ดขาด:
  - anchor ต้องเป็นวันศุกร์จริง
  - anchor ต้องแกะเป็น home/hotel ได้
  - ไม่มี placeholder '[ต้องกรอก]' ค้างอยู่
  - last_done ของ routine แบบนับวันต้องมีค่า ไม่งั้นจะเตือนว่าถึงรอบทุกวัน
"""

from __future__ import annotations

import unittest

from core import db, friday, routines
from core.localdate import FRIDAY, to_date


class OhmValuesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = db.connect(":memory:")
        db.migrate(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_ไม่มี_placeholder_ค้างอยู่(self) -> None:
        rows = self.conn.execute(
            "SELECT key FROM preferences WHERE value IN ('', '[ต้องกรอก]')"
        ).fetchall()
        self.assertEqual([r["key"] for r in rows], [], "ยังมี preference ที่ไม่ได้กรอก")

    def test_anchor_เป็นวันศุกร์จริง(self) -> None:
        raw = db.require_pref(self.conn, friday.PREF_KEY)
        date_part = raw.rpartition(":")[0]
        self.assertEqual(
            to_date(date_part).weekday(), FRIDAY,
            "anchor ต้องเป็นวันศุกร์ ไม่งั้นสลับสัปดาห์จะเพี้ยนทั้งหมด",
        )

    def test_anchor_แกะเป็นสถานะที่รู้จักได้(self) -> None:
        plan = friday.friday_state_from_db(self.conn)
        self.assertIn(plan.state, (friday.HOME, friday.HOTEL))

    def test_สลับด้านจริงทุกสัปดาห์(self) -> None:
        from datetime import timedelta

        base = friday.friday_state_from_db(self.conn)
        after = friday.friday_state_from_db(self.conn, base.friday + timedelta(days=7))
        before = friday.friday_state_from_db(self.conn, base.friday - timedelta(days=7))
        self.assertNotEqual(base.state, after.state, "ศุกร์ถัดไปต้องคนละด้าน")
        self.assertNotEqual(base.state, before.state, "ศุกร์ก่อนหน้าต้องคนละด้าน")
        # เว้นสองสัปดาห์ต้องกลับมาด้านเดิม
        two_weeks = friday.friday_state_from_db(self.conn, base.friday + timedelta(days=14))
        self.assertEqual(base.state, two_weeks.state, "เว้น 2 สัปดาห์ต้องกลับด้านเดิม")

    def test_routine_แบบนับวันมี_last_done_แล้ว(self) -> None:
        rows = self.conn.execute(
            "SELECT name FROM routines WHERE interval_days IS NOT NULL AND last_done IS NULL"
        ).fetchall()
        self.assertEqual(
            [r["name"] for r in rows], [],
            "routine แบบนับวันที่ไม่มี last_done จะเตือนว่าถึงรอบทุกวัน",
        )

    def test_last_done_ไม่ใช่วันในอนาคต(self) -> None:
        from core.localdate import local_date
        for row in self.conn.execute("SELECT name, last_done FROM routines WHERE last_done IS NOT NULL"):
            self.assertLessEqual(
                to_date(row["last_done"]), local_date(),
                f"last_done ของ {row['name']} เป็นวันในอนาคต",
            )

    def test_doctor_รายงานว่าพร้อมแล้ว(self) -> None:
        import io, json
        from contextlib import redirect_stdout
        import cli
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--db", ":memory:", "doctor"])
        self.assertTrue(json.loads(buf.getvalue())["data"]["ready"])


if __name__ == "__main__":
    unittest.main()
