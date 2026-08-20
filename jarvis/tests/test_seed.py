"""
เทสต์ของ schema/002_seed.sql — ค่า seed จาก jarvis-phase1-kit.md ส่วนที่ 3

ทำไมต้องเทสต์ไฟล์ SQL ที่ "แค่ INSERT":
    ค่าพวกนี้คือค่าที่ระบบทั้งระบบยึดเป็นความจริง ถ้า interval ไดโอดเพี้ยนเป็น 15
    หรือวันตัดผมเลื่อนไป 1 ก็ไม่มีอะไรพัง มีแค่ข้อความที่บอกวันผิดทุกสัปดาห์
    บั๊กแบบนี้ไม่มี traceback ให้เห็น ต้องดักด้วยเทสต์เท่านั้น

ใช้ไฟล์ DB ชั่วคราวเสมอ (ไม่แตะ ~/.jarvis/jarvis.db) และไม่ต้องต่อเน็ต/ไม่ต้องมี API key
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from core import db
from core.localdate import FRIDAY, MONDAY, TUESDAY, WEDNESDAY

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
SEED_FILE = SCHEMA_DIR / "002_seed.sql"

# ความจริงจาก kit ส่วนที่ 3 — เขียนซ้ำไว้ตรงนี้โดยตั้งใจ
# ถ้าใครแก้ SQL แล้วไม่ได้ตั้งใจ เทสต์จะฟ้อง เพราะต้องแก้ 2 ที่ให้ตรงกัน
EXPECTED_ROUTINES = {
    "diode": {
        "name_th": "เลเซอร์ไดโอดกำจัดขน",
        "interval_days": 14,
        "day_of_week": None,
    },
    "eyebrow": {
        "name_th": "ทำคิ้ว",
        "interval_days": 7,
        "day_of_week": None,
    },
    "haircut": {
        "name_th": "ตัดผม",
        "interval_days": None,
        "day_of_week": TUESDAY,
    },
}

EXPECTED_PREFS = {
    "wake_time": "06:50",
    "wake_time_wed": "06:30",
    "school_arrive_by": "07:35",
    "home_by_normal": "17:45",
    "rd_end_estimate": "16:45",
    "friday_anchor_date": "[ต้องกรอก]",
    "dorm_address": "หอพักมงฟอร์ตเรสซิเดนซ์",
    "school_address": "โรงเรียนมงฟอร์ตวิทยาลัย เชียงใหม่",
    "home_address": "จอมทอง เชียงใหม่",
    "aqi_alert_threshold": "100",
    "line_quota_warn_at": "250",
    "timezone": "Asia/Bangkok",
}

EXPECTED_SCHEDULE = {
    0: ("ชีววิทยา", "7", None),
    1: ("คณิตศาสตร์เพิ่มเติม", "7", "เย็น: ตัดผม"),
    2: ("ชีววิทยา", "ครึ่งวัน", "บ่าย ร.ด."),
    3: ("เคมี", "7", None),
    4: ("ชีววิทยา", "7", None),
}


class SeedTestBase(unittest.TestCase):
    """ฐานร่วม: DB ไฟล์ชั่วคราวที่ migrate แล้ว 1 ชุดต่อ 1 เทสต์

    ใช้ไฟล์จริงในโฟลเดอร์ชั่วคราวแทน ':memory:' เพราะอยากทดสอบเส้นทางเดียวกับของจริง
    (connect() สร้างโฟลเดอร์แม่ + WAL) แล้วลบทิ้งเมื่อจบ
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "jarvis-test.db"
        self.conn = db.connect(self.db_path)
        self.version = db.migrate(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()


class TestMigrationApplies(SeedTestBase):
    """001 + 002 ถูกหยิบไปรันจริงและรันซ้ำได้"""

    def test_both_migrations_applied(self) -> None:
        versions = {r[0] for r in self.conn.execute("SELECT version FROM schema_version")}
        self.assertIn(1, versions, "001_init ต้องถูกรัน")
        self.assertIn(2, versions, "002_seed ต้องถูก migrate() หยิบไปรัน")
        self.assertGreaterEqual(self.version, 2)

    def test_migrate_is_idempotent(self) -> None:
        # cron รีสตาร์ท / restore backup แล้วรัน migrate ซ้ำ ต้องไม่เกิดแถวซ้ำ
        before = self._counts()
        self.assertEqual(db.migrate(self.conn), self.version)
        self.assertEqual(db.migrate(self.conn), self.version)
        self.assertEqual(self._counts(), before)

    def test_rerun_does_not_overwrite_user_filled_values(self) -> None:
        """กรณีจริงที่ INSERT OR IGNORE มีไว้แก้: โอมกรอกค่าแล้ว migrate ซ้ำ"""
        db.set_pref(self.conn, "friday_anchor_date", "2026-08-14:home")
        self.conn.execute("UPDATE routines SET last_done = '2026-08-12' WHERE name = 'diode'")
        self.conn.commit()

        # จำลอง migrate ซ้ำแบบที่ schema_version หายไป (เช่น ซ่อม DB มาผิดวิธี)
        self.conn.executescript(SEED_FILE.read_text(encoding="utf-8"))
        self.conn.commit()

        self.assertEqual(db.require_pref(self.conn, "friday_anchor_date"), "2026-08-14:home")
        row = self.conn.execute(
            "SELECT last_done FROM routines WHERE name = 'diode'"
        ).fetchone()
        self.assertEqual(row["last_done"], "2026-08-12")

    def _counts(self) -> tuple[int, int, int]:
        def n(table: str) -> int:
            return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

        return n("routines"), n("preferences"), n("class_schedule")


class TestRoutinesSeed(SeedTestBase):
    def test_exactly_three_routines(self) -> None:
        rows = self.conn.execute("SELECT name FROM routines ORDER BY name").fetchall()
        self.assertEqual([r["name"] for r in rows], ["diode", "eyebrow", "haircut"])

    def test_values_match_kit(self) -> None:
        for name, expected in EXPECTED_ROUTINES.items():
            with self.subTest(routine=name):
                row = self.conn.execute(
                    "SELECT * FROM routines WHERE name = ?", (name,)
                ).fetchone()
                self.assertIsNotNone(row, f"ไม่พบ routine '{name}'")
                self.assertEqual(row["name_th"], expected["name_th"])
                self.assertEqual(row["interval_days"], expected["interval_days"])
                self.assertEqual(row["day_of_week"], expected["day_of_week"])
                self.assertEqual(row["active"], 1)

    def test_haircut_is_tuesday_not_any_other_day(self) -> None:
        # checklist B: "เตือนตัดผมทุกวันอังคาร ไม่เตือนวันอื่น"
        row = self.conn.execute(
            "SELECT day_of_week FROM routines WHERE name = 'haircut'"
        ).fetchone()
        self.assertEqual(row["day_of_week"], TUESDAY)
        self.assertNotEqual(row["day_of_week"], MONDAY)

    def test_haircut_notes_carry_shop_details(self) -> None:
        row = self.conn.execute("SELECT notes FROM routines WHERE name = 'haircut'").fetchone()
        self.assertIsNotNone(row["notes"])
        for fragment in ("เกษมเกษา", "ปตท.", "บ้านสัน", "ตอนเย็น"):
            self.assertIn(fragment, row["notes"])

    def test_last_done_is_null_on_fresh_seed(self) -> None:
        """[ต้องกรอก] ของ kit → NULL ในคอลัมน์นี้ (routines.py ถือว่าถึงรอบ)

        ห้ามเป็นสตริง '[ต้องกรอก]' เพราะคอลัมน์นี้ถูกเอาไปแปลงเป็นวันที่โดยตรง
        """
        rows = self.conn.execute("SELECT name, last_done FROM routines").fetchall()
        for row in rows:
            with self.subTest(routine=row["name"]):
                self.assertIsNone(row["last_done"])

    def test_interval_and_weekday_are_mutually_exclusive(self) -> None:
        # CHECK ใน 001 บังคับไว้ — ยืนยันว่า seed ไม่ได้เลี่ยงกฎนี้
        rows = self.conn.execute("SELECT name, interval_days, day_of_week FROM routines").fetchall()
        for row in rows:
            with self.subTest(routine=row["name"]):
                self.assertNotEqual(
                    row["interval_days"] is None,
                    row["day_of_week"] is None,
                    "ต้องมีอย่างใดอย่างหนึ่งเท่านั้น",
                )


class TestPreferencesSeed(SeedTestBase):
    def test_all_kit_keys_present_and_no_extras(self) -> None:
        rows = self.conn.execute("SELECT key, value FROM preferences").fetchall()
        got = {r["key"]: r["value"] for r in rows}
        self.assertEqual(set(got), set(EXPECTED_PREFS), "ชุดคีย์ต้องตรงกับ kit เป๊ะ")
        self.assertEqual(got, EXPECTED_PREFS)

    def test_get_pref_reads_seeded_values(self) -> None:
        self.assertEqual(db.get_pref(self.conn, "wake_time"), "06:50")
        self.assertEqual(db.get_pref(self.conn, "wake_time_wed"), "06:30")
        self.assertEqual(db.get_pref(self.conn, "timezone"), "Asia/Bangkok")

    def test_wednesday_wake_is_earlier_than_normal(self) -> None:
        # kit ข้อ 3: วันพุธต้องต่างจากปกติจริงๆ ไม่งั้นบรรทัด ⚠️ ก็ไม่มีความหมาย
        self.assertLess(
            db.get_pref(self.conn, "wake_time_wed"),
            db.get_pref(self.conn, "wake_time"),
        )

    def test_line_quota_warn_below_free_limit(self) -> None:
        # red-team H14: LINE ฟรี 300/เดือน ต้องเตือนก่อนเต็ม ไม่ใช่ตอนเต็มแล้ว
        self.assertLess(int(db.get_pref(self.conn, "line_quota_warn_at")), 300)

    def test_require_pref_ok_for_filled_values(self) -> None:
        self.assertEqual(db.require_pref(self.conn, "school_arrive_by"), "07:35")
        self.assertEqual(db.require_pref(self.conn, "home_address"), "จอมทอง เชียงใหม่")

    def test_require_pref_raises_on_fresh_friday_anchor(self) -> None:
        """หัวใจของไฟล์ seed นี้ — anchor ที่ยังไม่กรอกต้องระเบิด ไม่ใช่เดินต่อเงียบๆ"""
        with self.assertRaises(db.MissingPreference):
            db.require_pref(self.conn, "friday_anchor_date")

    def test_require_pref_message_tells_how_to_fix(self) -> None:
        with self.assertRaises(db.MissingPreference) as ctx:
            db.require_pref(self.conn, "friday_anchor_date")
        self.assertIn("friday_anchor_date", str(ctx.exception))

    def test_require_pref_passes_after_user_fills_anchor(self) -> None:
        db.set_pref(self.conn, "friday_anchor_date", "2026-08-14:hotel")
        self.assertEqual(db.require_pref(self.conn, "friday_anchor_date"), "2026-08-14:hotel")

    def test_friday_anchor_is_the_only_placeholder(self) -> None:
        rows = self.conn.execute("SELECT key, value FROM preferences").fetchall()
        placeholders = [r["key"] for r in rows if r["value"].strip() in db.PLACEHOLDERS]
        self.assertEqual(placeholders, ["friday_anchor_date"])

    def test_anchor_note_documents_the_format(self) -> None:
        # ค่าที่ต้องกรอกต้องมีคำใบ้ว่ากรอกยังไง ไม่งั้นกรอกผิดรูปแบบแล้วพังที่อื่น
        row = self.conn.execute(
            "SELECT notes FROM preferences WHERE key = 'friday_anchor_date'"
        ).fetchone()
        self.assertIsNotNone(row["notes"])
        self.assertIn("home", row["notes"])
        self.assertIn("hotel", row["notes"])


class TestClassScheduleSeed(SeedTestBase):
    def test_five_weekdays_only(self) -> None:
        rows = self.conn.execute(
            "SELECT day_of_week FROM class_schedule ORDER BY day_of_week"
        ).fetchall()
        self.assertEqual([r["day_of_week"] for r in rows], [MONDAY, 1, WEDNESDAY, 3, FRIDAY])
        self.assertEqual(len(rows), 5, "เสาร์/อาทิตย์ต้องไม่มีแถว")

    def test_each_day_matches_kit(self) -> None:
        for dow, (subject, periods, notes) in EXPECTED_SCHEDULE.items():
            with self.subTest(day_of_week=dow):
                row = self.conn.execute(
                    "SELECT * FROM class_schedule WHERE day_of_week = ?", (dow,)
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["first_subject"], subject)
                self.assertEqual(row["period_count"], periods)
                self.assertEqual(row["notes"], notes)

    def test_wednesday_is_half_day_with_rd(self) -> None:
        # วันพุธคือวันที่ต่างจากปกติที่สุด — ถ้าแถวนี้เพี้ยน digest วันพุธจะผิดทั้งวัน
        row = self.conn.execute(
            "SELECT * FROM class_schedule WHERE day_of_week = ?", (WEDNESDAY,)
        ).fetchone()
        self.assertEqual(row["period_count"], "ครึ่งวัน")
        self.assertIn("ร.ด.", row["notes"])

    def test_tuesday_notes_mention_haircut(self) -> None:
        row = self.conn.execute(
            "SELECT notes FROM class_schedule WHERE day_of_week = ?", (TUESDAY,)
        ).fetchone()
        self.assertIn("ตัดผม", row["notes"])

    def test_weekend_lookup_returns_nothing(self) -> None:
        for dow in (5, 6):
            with self.subTest(day_of_week=dow):
                row = self.conn.execute(
                    "SELECT * FROM class_schedule WHERE day_of_week = ?", (dow,)
                ).fetchone()
                self.assertIsNone(row)


class TestSeedFileHygiene(unittest.TestCase):
    """กฎเหล็กที่ตรวจจากตัวไฟล์ SQL ตรงๆ"""

    def setUp(self) -> None:
        self.sql = SEED_FILE.read_text(encoding="utf-8")

    def test_file_is_picked_up_by_migrate_glob(self) -> None:
        # migrate() ใช้ glob '[0-9][0-9][0-9]_*.sql' — ชื่อไฟล์ต้องเข้าเงื่อนไข
        self.assertIn(SEED_FILE, sorted(db.SCHEMA_DIR.glob("[0-9][0-9][0-9]_*.sql")))

    def test_no_sqlite_now_in_business_columns(self) -> None:
        """กฎเหล็กข้อ 1: ห้ามให้ SQLite ตัดสินว่า 'วันนี้วันไหน' (มันคิดเป็น UTC)"""
        lowered = self.sql.lower()
        for banned in ("date('now')", "current_timestamp", "datetime('now')"):
            self.assertNotIn(banned, lowered, f"พบ {banned} ในไฟล์ seed")

    def test_uses_insert_or_ignore_never_replace(self) -> None:
        lowered = self.sql.lower()
        self.assertIn("insert or ignore", lowered)
        self.assertNotIn("insert or replace", lowered)

    def test_header_documents_the_three_values_to_fill(self) -> None:
        header = self.sql.split("-- --- routines")[0]
        self.assertIn("friday_anchor_date", header)
        self.assertIn("diode", header)
        self.assertIn("eyebrow", header)
        self.assertIn("UPDATE preferences SET value", header)
        self.assertIn("UPDATE routines SET last_done", header)


class TestSeedOnPreExistingDatabase(unittest.TestCase):
    """ถ้ามีตารางอยู่แล้วแต่ยังไม่เคยรัน seed (DB จาก 001 ล้วน)"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "old.db"
        self.conn = db.connect(self.db_path)
        # จำลอง DB ที่รันแค่ 001 มาก่อน
        self.conn.executescript((SCHEMA_DIR / "001_init.sql").read_text(encoding="utf-8"))
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_seed_fills_empty_tables(self) -> None:
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM routines").fetchone()[0], 0
        )
        version = db.migrate(self.conn)
        self.assertGreaterEqual(version, 2)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM routines").fetchone()[0], 3
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM preferences").fetchone()[0],
            len(EXPECTED_PREFS),
        )

    def test_seed_respects_rows_already_present(self) -> None:
        # โอมเพิ่ม routine ชื่อเดียวกันไว้เองก่อน seed จะรัน → ของเดิมต้องไม่ถูกทับ
        self.conn.execute(
            "INSERT INTO routines (name, name_th, interval_days, last_done) "
            "VALUES ('eyebrow', 'ทำคิ้ว', 7, '2026-08-01')"
        )
        self.conn.commit()
        db.migrate(self.conn)
        row = self.conn.execute(
            "SELECT last_done FROM routines WHERE name = 'eyebrow'"
        ).fetchone()
        self.assertEqual(row["last_done"], "2026-08-01")

    def test_foreign_keys_stay_on_after_migrate(self) -> None:
        # executescript อาจ commit ระหว่างทาง — PRAGMA ต้องยังเปิดอยู่หลัง migrate
        db.migrate(self.conn)
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)


class TestSchemaConstraintsStillBite(SeedTestBase):
    """ยืนยันว่า seed ไม่ได้ทำให้ CHECK ของ 001 หลวมลง"""

    def test_duplicate_routine_name_rejected(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO routines (name, name_th, interval_days) VALUES ('diode', 'ซ้ำ', 14)"
            )

    def test_routine_with_both_kinds_rejected(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO routines (name, name_th, interval_days, day_of_week) "
                "VALUES ('bogus', 'มั่ว', 14, 1)"
            )

    def test_duplicate_schedule_day_rejected(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO class_schedule (day_of_week, first_subject, period_count) "
                "VALUES (0, 'ซ้ำ', '7')"
            )


if __name__ == "__main__":
    unittest.main()
