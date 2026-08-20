"""เทสต์สะพาน CLI — จุดที่โมดูลที่เขียนแยกกันมาเจอกันจริง

บั๊กที่เจอตอนต่อจริงแล้วเทสต์ของแต่ละโมดูลจับไม่ได้:
NamedTuple "เป็น" tuple ด้วย ถ้า _rows() เช็ค isinstance(x, tuple) ก่อนเช็ค _asdict
ผลจะออกมาเป็น array แทน object ทำให้ฝั่งที่อ่านเข้าถึงด้วยชื่อคีย์ไม่ได้
เทสต์ในไฟล์นี้จึงเน้น "รูปร่างของ JSON ที่ออกไป" ไม่ใช่ตรรกะทางธุรกิจ
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from typing import NamedTuple

import cli


class RowsSerialisationTests(unittest.TestCase):
    """_rows() ต้องแปลงทุกชนิดที่ core/ คืนมาให้เป็น JSON ที่มีชื่อคีย์"""

    def test_namedtuple_ต้องเป็น_object_ไม่ใช่_array(self) -> None:
        class Sample(NamedTuple):
            name: str
            count: int

        out = cli._rows(Sample("คิ้ว", 7))
        self.assertIsInstance(out, dict, "NamedTuple ต้องกลายเป็น object ไม่ใช่ array")
        self.assertEqual(out["name"], "คิ้ว")

    def test_namedtuple_ที่ซ้อนใน_list(self) -> None:
        class Sample(NamedTuple):
            name: str

        out = cli._rows([Sample("ก"), Sample("ข")])
        self.assertEqual(out, [{"name": "ก"}, {"name": "ข"}])

    def test_namedtuple_ที่ซ้อนใน_namedtuple(self) -> None:
        class Inner(NamedTuple):
            v: int

        class Outer(NamedTuple):
            inner: Inner

        self.assertEqual(cli._rows(Outer(Inner(1))), {"inner": {"v": 1}})

    def test_tuple_ธรรมดายังเป็น_array(self) -> None:
        self.assertEqual(cli._rows((1, 2, 3)), [1, 2, 3])


class CliEndToEndTests(unittest.TestCase):
    """เรียก main() จริงแล้วอ่าน JSON ที่พิมพ์ออกมา"""

    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.path)

    def tearDown(self) -> None:
        if os.path.exists(self.path):
            os.unlink(self.path)

    def _run(self, *argv: str) -> dict:
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--db", self.path, *argv])
        return json.loads(buf.getvalue())

    def test_routines_due_คืน_object_ที่มีชื่อคีย์(self) -> None:
        payload = self._run("routines", "due")
        self.assertTrue(payload["ok"])
        for row in payload["data"]:
            self.assertIsInstance(row, dict)
            self.assertIn("name_th", row)

    def test_ความจำ_ทับของเก่าแล้วรายงานว่าทับอันไหน(self) -> None:
        self._run("memory", "remember", "--topic", "ร้าน", "--content", "เก่า")
        payload = self._run("memory", "remember", "--topic", "ร้าน", "--content", "ใหม่")
        self.assertEqual(payload["data"]["lesson"]["content"], "ใหม่")
        # ต้องบอกได้ว่าทับอันไหน ไม่ใช่ทับเงียบๆ
        self.assertEqual(payload["data"]["superseded"]["content"], "เก่า")

    def test_ลืมโดยไม่ใส่_confirm_ต้องไม่ลบจริง(self) -> None:
        self._run("memory", "remember", "--topic", "ร้าน", "--content", "จำไว้")
        payload = self._run("memory", "forget", "--topic", "ร้าน")
        self.assertFalse(payload["data"]["deleted"], "ไม่ใส่ --confirm ต้องไม่ลบ")
        still = self._run("memory", "recall", "--topic", "ร้าน")
        self.assertEqual(len(still["data"]), 1, "ของต้องยังอยู่ครบ")

    def test_doctor_รายงานพร้อมเมื่อกรอกค่าครบแล้ว(self) -> None:
        # migration 003 เติมค่าที่โอมกรอกไว้แล้ว doctor จึงต้องบอกว่าพร้อม
        payload = self._run("doctor")
        self.assertTrue(payload["data"]["ready"], payload["data"]["problems"])
        self.assertEqual(payload["data"]["problems"], [])

    def test_doctor_ฟ้องเมื่อยังไม่ได้กรอก(self) -> None:
        """ตรวจทางที่ doctor ต้องฟ้อง โดยตรึงฐานข้อมูลไว้ที่ 002 (ก่อนเติมค่าจริง)

        เรียก cmd_doctor ตรงๆ ไม่ผ่าน main() เพราะ main() จะ migrate ถึง 003
        แล้วค่าจะถูกเติมจนไม่เหลืออะไรให้ฟ้อง
        """
        import argparse
        from core import db as core_db

        conn = core_db.connect(":memory:")
        core_db.migrate(conn, target_version=2)
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.cmd_doctor(argparse.Namespace(), conn)
        conn.close()
        data = json.loads(buf.getvalue())["data"]
        self.assertFalse(data["ready"])
        self.assertTrue(
            any("friday_anchor_date" in p for p in data["problems"]),
            "doctor ต้องฟ้องว่า friday_anchor_date ยังไม่ได้กรอก",
        )

    def test_ผลลัพธ์เป็น_JSON_ที่อ่านได้เสมอ(self) -> None:
        # Hermes skill อ่านผลด้วยการ parse JSON ถ้าพิมพ์อย่างอื่นปนออกมาจะพัง
        for args in (("routines", "list"), ("routines", "due"), ("doctor",)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cli.main(["--db", self.path, *args])
            json.loads(buf.getvalue())  # พังตรงนี้ = มีอะไรพิมพ์ปนออกมา


if __name__ == "__main__":
    unittest.main()


class CliDigestTests(unittest.TestCase):
    """กลุ่ม digest — คำสั่งเดียวที่พิมพ์ข้อความล้วน เพราะผู้อ่านคือคน ไม่ใช่ agent"""

    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.path)

    def tearDown(self) -> None:
        if os.path.exists(self.path):
            os.unlink(self.path)

    def _run(self, *argv: str) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--db", self.path, *argv])
        self.assertEqual(code, 0)
        return buf.getvalue()

    def test_พิมพ์ข้อความล้วน_ไม่ใช่_JSON(self) -> None:
        out = self._run("digest", "morning", "--at", "2026-08-24T06:20")
        self.assertIn("อรุณสวัสดิ์ครับ", out)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)

    def test_at_ฉีดเวลาได้_วันพุธขึ้นคำเตือน(self) -> None:
        out = self._run("digest", "morning", "--at", "2026-08-26T06:00")
        self.assertIn("⚠️ วันนี้พุธ", out)

    def test_record_กันส่งซ้ำวันเดียวกัน(self) -> None:
        first = self._run("digest", "morning", "--at", "2026-08-26T06:00", "--record", "telegram")
        self.assertIn("อรุณสวัสดิ์ครับ", first)
        # ยิงซ้ำวันเดิม (คนละเวลา) → ต้องว่างสนิท = cron จะไม่ส่งอะไร
        again = self._run("digest", "morning", "--at", "2026-08-26T07:00", "--record", "telegram")
        self.assertEqual(again, "")
        # วันถัดไปต้องส่งได้ใหม่
        tomorrow = self._run("digest", "morning", "--at", "2026-08-27T06:20", "--record", "telegram")
        self.assertIn("อรุณสวัสดิ์ครับ", tomorrow)

    def test_โควตา_telegram_ไม่นับ_line_นับ(self) -> None:
        self._run("digest", "morning", "--at", "2026-08-26T06:00", "--record", "telegram")
        self._run("digest", "evening", "--at", "2026-08-26T18:30", "--record", "line")
        import sqlite3 as sq

        conn = sq.connect(self.path)
        rows = dict(conn.execute(
            "SELECT channel, counts_toward_quota FROM notifications_sent"
        ).fetchall())
        conn.close()
        self.assertEqual(rows, {"telegram": 0, "line": 1})

    def test_dream_ไม่มีอะไร_ต้องเงียบและไม่บันทึก(self) -> None:
        out = self._run("digest", "dream", "--record", "telegram")
        self.assertEqual(out, "")
        import sqlite3 as sq

        conn = sq.connect(self.path)
        n = conn.execute("SELECT COUNT(*) FROM notifications_sent").fetchone()[0]
        conn.close()
        # เงียบต้องเงียบจริง: ไม่พิมพ์ และไม่บันทึกว่าส่ง (บันทึกทั้งที่ไม่ส่ง = โกหกตัวเอง)
        self.assertEqual(n, 0)

    def test_evening_ผ่าน_CLI_มีเนื้อหาจริง(self) -> None:
        out = self._run("digest", "evening", "--at", "2026-08-24T18:30")
        self.assertIn("เย็นนี้เป็นไงบ้างครับ", out)

    def test_weekly_ผ่าน_CLI_มีตารางสัปดาห์(self) -> None:
        out = self._run("digest", "weekly", "--at", "2026-08-23T20:00")
        self.assertIn("สัปดาห์หน้ามีอะไรบ้าง", out)
        self.assertIn("ศ. — 🏨", out)
