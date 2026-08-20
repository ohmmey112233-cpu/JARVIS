"""เทสต์ด่านความปลอดภัยของตัวเชื่อมระบบบัญชี (red-team H11)"""

from __future__ import annotations

import sqlite3
import unittest

from core import db, scaccounting as sc


class SecurityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = db.connect(":memory:")
        db.migrate(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    # --- whitelist ---------------------------------------------------------
    def test_อนุญาตทุก_endpoint_ในลิสต์(self) -> None:
        for endpoint in sc.ALLOWED_ENDPOINTS:
            self.assertEqual(sc.check_request("GET", endpoint), endpoint)

    def test_ปฏิเสธ_endpoint_นอกลิสต์(self) -> None:
        for path in ("users", "admin", "payroll", "settings"):
            with self.assertRaises(sc.ForbiddenRequest):
                sc.check_request("GET", path)

    def test_ปฏิเสธทุกเมธอดที่ไม่ใช่_GET(self) -> None:
        # บุคลิก: "ห้ามแก้ไข อนุมัติ หรือลบ ไม่ว่าจะถูกสั่งหรือไม่"
        for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            with self.assertRaises(sc.ForbiddenRequest):
                sc.check_request(method, "tasks")

    def test_ปฏิเสธ_path_traversal(self) -> None:
        for path in ("../admin", "tasks/../users", "tasks//secret", "tasks?x=1", "tasks#f"):
            with self.assertRaises(sc.ForbiddenRequest):
                sc.check_request("GET", path)

    def test_รับ_path_ที่มี_id_ต่อท้าย(self) -> None:
        self.assertEqual(sc.check_request("GET", "tasks/123"), "tasks")
        self.assertEqual(sc.check_request("GET", "/receipts/abc-1/"), "receipts")

    # --- เงิน ---------------------------------------------------------------
    def test_แปลงสตางค์เป็นบาท(self) -> None:
        self.assertEqual(sc.satang_to_baht(123456), 1234.56)
        self.assertEqual(sc.satang_to_baht(0), 0.0)
        self.assertIsNone(sc.satang_to_baht(None))

    def test_normalize_money_เดินลงชั้นซ้อน(self) -> None:
        payload = {"items": [{"total_satang": 250000, "name": "ก"}], "fee_satang": 5000}
        out = sc.normalize_money(payload)
        self.assertEqual(out["fee_baht"], 50.0)
        self.assertEqual(out["items"][0]["total_baht"], 2500.0)
        # ค่าดิบต้องยังอยู่ เพื่อตรวจย้อนได้
        self.assertEqual(out["items"][0]["total_satang"], 250000)

    # --- audit -------------------------------------------------------------
    def test_บันทึก_audit_ทุกครั้งที่ยิง(self) -> None:
        sc.fetch(self.conn, "tasks", transport=lambda p, q: {"ok": 1})
        rows = self.conn.execute("SELECT * FROM audit_log").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], "scaccounting")
        self.assertEqual(rows[0]["action"], "GET tasks")

    def test_คำขอที่ถูกปฏิเสธก็ต้องถูกบันทึก(self) -> None:
        # สำคัญ: ความพยายามที่ถูกบล็อกคือสิ่งที่อยากเห็นใน log มากที่สุด
        with self.assertRaises(sc.ForbiddenRequest):
            sc.fetch(self.conn, "users", transport=lambda p, q: {})
        rows = self.conn.execute("SELECT * FROM audit_log").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIn("ปฏิเสธ", rows[0]["detail"])

    def test_ไม่มี_transport_ต้องระเบิดไม่ใช่คืนข้อมูลปลอม(self) -> None:
        with self.assertRaises(NotImplementedError):
            sc.fetch(self.conn, "tasks")

    def test_ผลลัพธ์ผ่าน_normalize_money_เสมอ(self) -> None:
        out = sc.fetch(self.conn, "billing", transport=lambda p, q: {"amount_satang": 99900})
        self.assertEqual(out["amount_baht"], 999.0)

    # --- ไม่มีทางเขียน -------------------------------------------------------
    def test_โมดูลไม่มีฟังก์ชันเขียนเลย(self) -> None:
        # อ่านอย่างเดียวต้องบังคับด้วยโครงสร้าง ไม่ใช่ด้วยวินัยของคนเรียก
        forbidden = ("post", "put", "patch", "delete", "create", "update", "approve")
        names = [n.lower() for n in dir(sc) if not n.startswith("_")]
        for word in forbidden:
            self.assertFalse(
                [n for n in names if n.startswith(word)],
                f"เจอฟังก์ชันที่อาจเขียนข้อมูลได้ ขึ้นต้นด้วย '{word}'",
            )


if __name__ == "__main__":
    unittest.main()
