"""
เทสต์ความจำ — จุดที่ต้องพิสูจน์คือ "ความจำห้ามหายเงียบๆ" (red-team H13)

3 บั๊กที่เทสต์ไฟล์นี้ตั้งใจดักไว้เป็นพิเศษ:
    1. สอนเรื่องเดิม 3 รอบแล้ว recall คืนของเก่ากลับมาปนกับของใหม่
    2. "ลืมเรื่อง X" ที่ยังไม่ยืนยัน ดันไปแตะ DB จริง (checklist: ต้องยืนยันก่อนเสมอ)
    3. งานตี 2 ไปพักความจำที่ยังใช้อยู่ หรือลบทิ้งจริงจนกู้ไม่ได้

ทุกเทสต์ใช้ DB ในหน่วยความจำ ไม่แตะไฟล์จริง ไม่ต้องมีเน็ต/API key
เวลาถูกฉีดเข้าไปทุกจุดผ่านพารามิเตอร์ `when` — ไม่มีเทสต์ไหนพึ่งเวลาปัจจุบันจริง
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from core import db, memory

# วันอ้างอิงของทั้งไฟล์ (เวลาไทย) — ตั้งไว้ให้เห็นชัดว่าอะไรเกิดก่อนหลัง
DAY1 = datetime(2026, 6, 1, 9, 0)
DAY2 = datetime(2026, 6, 15, 10, 30)
DAY3 = datetime(2026, 7, 1, 20, 15)


class MemoryTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = db.connect(":memory:")
        db.migrate(self.conn)
        self.addCleanup(self.conn.close)

    # --- ตัวช่วยอ่านสถานะดิบ (ไม่ผ่านโค้ดที่กำลังทดสอบ เพื่อไม่ให้เทสต์หลอกตัวเอง) ---

    def lesson_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]

    def trash_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM lessons_trash").fetchone()[0]

    def raw(self, lesson_id: int) -> dict:
        row = self.conn.execute(
            "SELECT * FROM lessons WHERE id = ?", (lesson_id,)
        ).fetchone()
        self.assertIsNotNone(row, f"ไม่พบแถว id {lesson_id}")
        return {k: row[k] for k in row.keys()}

    def three_generations(self) -> tuple[memory.Lesson, memory.Lesson, memory.Lesson]:
        """สอนเรื่องเดียวกัน 3 รอบ — สถานการณ์ตัวอย่างของ H13"""
        gen1, _ = memory.remember(
            self.conn, "ร้านกาแฟ", "Ristr8to สั่งลาเต้ร้อน", ["cafe", "nimman"], DAY1
        )
        gen2, _ = memory.remember(
            self.conn, "ร้านกาแฟ", "Ristr8to สั่งลาเต้เย็นไม่หวาน", ["cafe"], DAY2
        )
        gen3, _ = memory.remember(
            self.conn, "ร้านกาแฟ", "Ristr8to ปิดวันจันทร์", ["cafe"], DAY3
        )
        return gen1, gen2, gen3


class RememberTest(MemoryTestBase):
    def test_first_lesson_has_nothing_superseded(self) -> None:
        lesson, superseded = memory.remember(
            self.conn, "ร้านกาแฟ", "Ristr8to นิมมาน", ["cafe"], DAY1
        )
        self.assertIsNone(superseded)
        self.assertEqual(lesson.topic, "ร้านกาแฟ")
        self.assertEqual(lesson.content, "Ristr8to นิมมาน")
        self.assertEqual(lesson.tags, ["cafe"])
        self.assertIsNone(lesson.superseded_by)
        self.assertIsNone(lesson.archived_at)

    def test_supersede_chain_across_three_generations(self) -> None:
        gen1, gen2, gen3 = self.three_generations()

        # โซ่ต้องชี้ไปข้างหน้าทีละขั้น ไม่ใช่ทุกก้อนชี้ไปที่ก้อนสุดท้าย
        self.assertEqual(self.raw(gen1.id)["superseded_by"], gen2.id)
        self.assertEqual(self.raw(gen2.id)["superseded_by"], gen3.id)
        self.assertIsNone(self.raw(gen3.id)["superseded_by"])
        # ห้ามลบของเก่าทิ้ง ประวัติต้องอยู่ครบ
        self.assertEqual(self.lesson_count(), 3)

    def test_returns_the_lesson_it_overwrote(self) -> None:
        # บุคลิกบังคับว่าต้องบอกได้ว่า "ทับอันไหน" — ค่าที่คืนต้องเป็นก้อนก่อนหน้าจริงๆ
        gen1, _ = memory.remember(self.conn, "ร้านกาแฟ", "เวอร์ชัน 1", (), DAY1)
        gen2, old1 = memory.remember(self.conn, "ร้านกาแฟ", "เวอร์ชัน 2", (), DAY2)
        gen3, old2 = memory.remember(self.conn, "ร้านกาแฟ", "เวอร์ชัน 3", (), DAY3)

        self.assertEqual(old1.id, gen1.id)
        self.assertEqual(old1.content, "เวอร์ชัน 1")
        self.assertEqual(old2.id, gen2.id)
        # ค่าที่คืนต้องสะท้อนสถานะหลังถูกทับแล้ว ไม่ใช่ค่าก่อนอัปเดต
        self.assertEqual(old1.superseded_by, gen2.id)
        self.assertEqual(old2.superseded_by, gen3.id)

    def test_topic_match_ignores_ascii_case(self) -> None:
        first, _ = memory.remember(self.conn, "Ristr8to", "ลาเต้ร้อน", (), DAY1)
        second, old = memory.remember(self.conn, "ristr8to", "ลาเต้เย็น", (), DAY2)
        self.assertIsNotNone(old)
        self.assertEqual(old.id, first.id)
        self.assertEqual(len(memory.recall(self.conn, "ristr8to")), 1)
        self.assertEqual(memory.recall(self.conn, "Ristr8to")[0].id, second.id)

    def test_different_topics_do_not_supersede_each_other(self) -> None:
        memory.remember(self.conn, "ร้านกาแฟ", "Ristr8to", (), DAY1)
        _, old = memory.remember(self.conn, "ร้านอาหาร", "จองล่วงหน้า 2 วัน", (), DAY2)
        self.assertIsNone(old)
        self.assertEqual(len(memory.recall(self.conn, "ร้าน")), 2)

    def test_supersedes_every_live_row_of_the_topic(self) -> None:
        # ข้อมูลเก่าจากยุคที่ยังเป็น append-only อาจมีสองก้อนที่ยังใช้อยู่พร้อมกัน
        # ถ้าทับแค่ก้อนล่าสุด อีกก้อนจะค้างเป็นความจำที่ขัดกันเอง = ปัญหา H13 ที่ยังไม่หาย
        for content in ("ของเก่า A", "ของเก่า B"):
            self.conn.execute(
                "INSERT INTO lessons (topic, content, tags, created_at, updated_at) "
                "VALUES ('ร้านกาแฟ', ?, '', '2026-05-01 08:00:00', '2026-05-01 08:00:00')",
                (content,),
            )
        self.conn.commit()

        new, old = memory.remember(self.conn, "ร้านกาแฟ", "ของใหม่", (), DAY1)
        live = memory.recall(self.conn, "ร้านกาแฟ")
        self.assertEqual([item.id for item in live], [new.id])
        self.assertEqual(old.content, "ของเก่า B")  # ก้อนล่าสุดในบรรดาของเก่า

    def test_blank_topic_or_content_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            memory.remember(self.conn, "   ", "เนื้อความ", (), DAY1)
        with self.assertRaises(ValueError):
            memory.remember(self.conn, "ร้านกาแฟ", "  ", (), DAY1)
        self.assertEqual(self.lesson_count(), 0)

    def test_timestamps_are_bangkok_not_utc(self) -> None:
        # 2026-06-01 18:30 UTC = 2026-06-02 01:30 เวลาไทย → ต้องบันทึกเป็นวันที่ 2
        utc_night = datetime(2026, 6, 1, 18, 30, tzinfo=timezone.utc)
        lesson, _ = memory.remember(self.conn, "ทดสอบเวลา", "จำตอนดึก", (), utc_night)
        self.assertEqual(lesson.created_at, "2026-06-02 01:30:00")
        self.assertEqual(self.raw(lesson.id)["updated_at"], "2026-06-02 01:30:00")


class TagsTest(MemoryTestBase):
    def test_tags_roundtrip_from_list(self) -> None:
        lesson, _ = memory.remember(
            self.conn, "ร้านอาหาร", "จอง 2 วันล่วงหน้า", ["restaurant", "booking"], DAY1
        )
        self.assertEqual(lesson.tags, ["restaurant", "booking"])
        self.assertEqual(self.raw(lesson.id)["tags"], "restaurant,booking")
        self.assertEqual(memory.recall(self.conn, "booking")[0].tags,
                         ["restaurant", "booking"])

    def test_no_tags_gives_empty_list_not_blank_string(self) -> None:
        lesson, _ = memory.remember(self.conn, "เรื่องหนึ่ง", "เนื้อความ", (), DAY1)
        self.assertEqual(lesson.tags, [])
        self.assertEqual(self.raw(lesson.id)["tags"], "")
        self.assertEqual(memory.recall(self.conn, "เรื่องหนึ่ง")[0].tags, [])

    def test_dirty_tags_are_cleaned(self) -> None:
        lesson, _ = memory.remember(
            self.conn, "เรื่องสอง", "เนื้อความ",
            ["  cafe ", "", "CAFE", "nimman", "   "], DAY1,
        )
        self.assertEqual(lesson.tags, ["cafe", "nimman"])

    def test_tags_given_as_one_comma_string(self) -> None:
        # ทาง CLI/แชทส่งมาเป็นสตริงเดียวได้ ต้องได้ผลเท่ากับส่งเป็นลิสต์
        lesson, _ = memory.remember(
            self.conn, "เรื่องสาม", "เนื้อความ", "cafe,nimman", DAY1
        )
        self.assertEqual(lesson.tags, ["cafe", "nimman"])
        self.assertEqual(self.raw(lesson.id)["tags"], "cafe,nimman")

    def test_tag_containing_separator_still_roundtrips(self) -> None:
        lesson, _ = memory.remember(
            self.conn, "เรื่องสี่", "เนื้อความ", ["cafe,nimman"], DAY1
        )
        # ใส่เข้าไปก้อนเดียวแต่มีคอมมา → ต้องอ่านกลับได้เท่าที่เก็บจริง ไม่ใช่ ['cafe,nimman']
        self.assertEqual(lesson.tags, ["cafe", "nimman"])
        self.assertEqual(memory.recall(self.conn, "เรื่องสี่")[0].tags, lesson.tags)


class RecallTest(MemoryTestBase):
    def test_recall_returns_only_the_latest_generation(self) -> None:
        _, _, gen3 = self.three_generations()
        found = memory.recall(self.conn, "ร้านกาแฟ")
        self.assertEqual([item.id for item in found], [gen3.id])
        self.assertEqual(found[0].content, "Ristr8to ปิดวันจันทร์")

    def test_recall_excludes_archived_rows(self) -> None:
        lesson, _ = memory.remember(self.conn, "เรื่องเก่า", "เนื้อความ", (), DAY1)
        self.conn.execute(
            "UPDATE lessons SET archived_at = '2026-07-01 02:00:00' WHERE id = ?",
            (lesson.id,),
        )
        self.conn.commit()
        self.assertEqual(memory.recall(self.conn, "เรื่องเก่า"), [])

    def test_recall_by_tag_substring(self) -> None:
        memory.remember(self.conn, "ร้านอาหาร A", "จอง 2 วัน", ["restaurant"], DAY1)
        memory.remember(self.conn, "ร้านอาหาร B", "วอล์กอินได้", ["restaurant"], DAY2)
        memory.remember(self.conn, "ตัดผม", "ร้านเกษมเกษา", ["haircut"], DAY2)

        found = memory.recall(self.conn, "restaurant")
        self.assertEqual({item.topic for item in found}, {"ร้านอาหาร A", "ร้านอาหาร B"})
        # substring จริง ไม่ใช่ต้องตรงทั้งคำ
        self.assertEqual(len(memory.recall(self.conn, "restau")), 2)

    def test_recall_by_topic_substring(self) -> None:
        memory.remember(self.conn, "ร้านกาแฟนิมมาน", "Ristr8to", ["cafe"], DAY1)
        self.assertEqual(len(memory.recall(self.conn, "กาแฟ")), 1)
        self.assertEqual(memory.recall(self.conn, "ร้านชา"), [])

    def test_recall_newest_first(self) -> None:
        old, _ = memory.remember(self.conn, "เรื่อง A", "เก่า", ["x"], DAY1)
        new, _ = memory.remember(self.conn, "เรื่อง B", "ใหม่", ["x"], DAY3)
        self.assertEqual([item.id for item in memory.recall(self.conn, "x")],
                         [new.id, old.id])

    def test_recall_wildcards_are_literal(self) -> None:
        # ถ้าไม่หนี % ไว้ คำค้นนี้จะกลายเป็น wildcard แล้วคืนความจำทั้งฐาน
        memory.remember(self.conn, "ส่วนลด", "ลด 50% วันศุกร์", ["promo"], DAY1)
        memory.remember(self.conn, "ตัดผม", "ร้านเกษมเกษา", ["haircut"], DAY2)
        self.assertEqual(memory.recall(self.conn, "%"), [])
        self.assertEqual(len(memory.recall(self.conn, "ส่วน_ลด")), 0)

    def test_recall_empty_term_returns_everything_live(self) -> None:
        memory.remember(self.conn, "เรื่อง A", "หนึ่ง", (), DAY1)
        memory.remember(self.conn, "เรื่อง B", "สอง", (), DAY2)
        self.assertEqual(len(memory.recall(self.conn, "   ")), 2)

    def test_recall_limit(self) -> None:
        for index in range(5):
            memory.remember(self.conn, f"เรื่อง {index}", "เนื้อความ", ["bulk"], DAY1)
        self.assertEqual(len(memory.recall(self.conn, "bulk", limit=3)), 3)

    def test_recall_rejects_useless_limit(self) -> None:
        # limit=0 คืนลิสต์ว่างจะดูเหมือน "ไม่มีความจำเรื่องนี้" ซึ่งเป็นคำตอบผิดแบบเงียบๆ
        for bad in (0, -1):
            with self.subTest(limit=bad), self.assertRaises(ValueError):
                memory.recall(self.conn, "อะไรก็ได้", limit=bad)


class ReviseTest(MemoryTestBase):
    def test_revise_supersedes_and_returns_both(self) -> None:
        original, _ = memory.remember(
            self.conn, "ร้านอาหาร", "จองล่วงหน้า 2 วัน", ["restaurant"], DAY1
        )
        new, old = memory.revise(self.conn, "ร้านอาหาร", "จองวันต่อวันได้แล้ว", DAY2)

        self.assertEqual(old.id, original.id)
        self.assertEqual(old.superseded_by, new.id)
        self.assertEqual(new.content, "จองวันต่อวันได้แล้ว")
        self.assertEqual([item.id for item in memory.recall(self.conn, "ร้านอาหาร")],
                         [new.id])

    def test_revise_keeps_the_old_tags(self) -> None:
        # ถ้า tags หลุด ความจำที่แก้แล้วจะไม่ถูกดึงมาใช้ตอนทำงานที่ tag ตรงกันอีกเลย
        memory.remember(self.conn, "ร้านอาหาร", "เดิม", ["restaurant", "booking"], DAY1)
        new, _ = memory.revise(self.conn, "ร้านอาหาร", "ใหม่", DAY2)
        self.assertEqual(new.tags, ["restaurant", "booking"])
        self.assertEqual([item.id for item in memory.recall(self.conn, "booking")],
                         [new.id])

    def test_revise_unknown_topic_raises(self) -> None:
        with self.assertRaises(KeyError):
            memory.revise(self.conn, "เรื่องที่ไม่เคยสอน", "เนื้อความใหม่", DAY2)
        self.assertEqual(self.lesson_count(), 0)

    def test_revise_on_archived_only_topic_raises(self) -> None:
        # ก้อนที่ถูกพักไว้ไม่ถือว่า "ยังใช้อยู่" → แก้ไม่ได้ ต้องได้ยินว่าไม่เจอ
        lesson, _ = memory.remember(self.conn, "เรื่องพัก", "เนื้อความ", (), DAY1)
        self.conn.execute(
            "UPDATE lessons SET archived_at = '2026-07-01 02:00:00' WHERE id = ?",
            (lesson.id,),
        )
        self.conn.commit()
        with self.assertRaises(KeyError):
            memory.revise(self.conn, "เรื่องพัก", "เนื้อความใหม่", DAY2)


class ForgetTest(MemoryTestBase):
    def test_unconfirmed_forget_touches_nothing(self) -> None:
        gen1, gen2, gen3 = self.three_generations()
        before_rows = self.conn.execute(
            "SELECT id, superseded_by, archived_at FROM lessons ORDER BY id"
        ).fetchall()

        deleted, affected = memory.forget(self.conn, "ร้านกาแฟ", when=DAY3)

        self.assertFalse(deleted)
        self.assertEqual(self.lesson_count(), 3)
        self.assertEqual(self.trash_count(), 0)
        after_rows = self.conn.execute(
            "SELECT id, superseded_by, archived_at FROM lessons ORDER BY id"
        ).fetchall()
        self.assertEqual([tuple(r) for r in before_rows], [tuple(r) for r in after_rows])
        # ต้องบอกให้ครบว่าจะลบอะไรบ้าง เพื่อเอาไปถามยืนยัน
        self.assertEqual({item.id for item in affected}, {gen1.id, gen2.id, gen3.id})

    def test_unconfirmed_forget_reports_newest_first(self) -> None:
        _, _, gen3 = self.three_generations()
        _, affected = memory.forget(self.conn, "ร้านกาแฟ", when=DAY3)
        self.assertEqual(affected[0].id, gen3.id)

    def test_confirmed_forget_moves_everything_to_trash(self) -> None:
        gen1, gen2, gen3 = self.three_generations()
        deleted, affected = memory.forget(
            self.conn, "ร้านกาแฟ", confirmed=True, reason="สั่งลืมเอง", when=DAY3
        )

        self.assertTrue(deleted)
        self.assertEqual(len(affected), 3)
        self.assertEqual(self.lesson_count(), 0)
        self.assertEqual(self.trash_count(), 3)
        self.assertEqual(memory.recall(self.conn, "ร้านกาแฟ"), [])

        trash = memory.list_trash(self.conn)
        self.assertEqual({row["original_id"] for row in trash},
                         {gen1.id, gen2.id, gen3.id})
        self.assertTrue(all(row["deleted_key"] == "2026-07-01" for row in trash))
        self.assertTrue(all(row["reason"] == "สั่งลืมเอง" for row in trash))
        # tags ของแต่ละก้อนต้องติดไปกับก้อนนั้นจริง ไม่ใช่ปนกันตอนเขียนลงถังขยะ
        by_original = {row["original_id"]: row for row in trash}
        self.assertEqual(by_original[gen1.id]["tags"], ["cafe", "nimman"])
        self.assertEqual(by_original[gen3.id]["tags"], ["cafe"])
        self.assertEqual(by_original[gen2.id]["content"], "Ristr8to สั่งลาเต้เย็นไม่หวาน")

    def test_confirmed_forget_does_not_resurrect_old_generations(self) -> None:
        # superseded_by ตั้งไว้ ON DELETE SET NULL — ถ้าลบเฉพาะก้อนล่าสุด
        # ก้อนเก่าจะกลับมามีชีวิตทันที กลายเป็น "สั่งลืมแล้วได้ของเก่ากว่าคืนมา"
        self.three_generations()
        memory.forget(self.conn, "ร้านกาแฟ", confirmed=True, when=DAY3)
        self.assertEqual(memory.recall(self.conn, "ร้านกาแฟ"), [])
        self.assertEqual(memory.recall(self.conn, "cafe"), [])
        self.assertEqual(self.lesson_count(), 0)

    def test_forget_only_touches_the_named_topic(self) -> None:
        keep, _ = memory.remember(self.conn, "ตัดผม", "ร้านเกษมเกษา", (), DAY1)
        memory.remember(self.conn, "ร้านกาแฟ", "Ristr8to", (), DAY1)
        memory.forget(self.conn, "ร้านกาแฟ", confirmed=True, when=DAY3)
        self.assertEqual([item.id for item in memory.recall(self.conn, "ตัดผม")],
                         [keep.id])

    def test_forget_unknown_topic_raises(self) -> None:
        with self.assertRaises(KeyError):
            memory.forget(self.conn, "เรื่องที่ไม่มี", when=DAY3)
        with self.assertRaises(KeyError):
            memory.forget(self.conn, "เรื่องที่ไม่มี", confirmed=True, when=DAY3)
        self.assertEqual(self.trash_count(), 0)


class RestoreTest(MemoryTestBase):
    def test_restore_roundtrip(self) -> None:
        original, _ = memory.remember(
            self.conn, "ร้านกาแฟ", "Ristr8to ปิดวันจันทร์", ["cafe", "nimman"], DAY1
        )
        memory.forget(self.conn, "ร้านกาแฟ", confirmed=True, when=DAY2)
        self.assertEqual(memory.recall(self.conn, "ร้านกาแฟ"), [])

        restored = memory.restore(self.conn, original.id, DAY3)

        self.assertEqual(restored.topic, "ร้านกาแฟ")
        self.assertEqual(restored.content, "Ristr8to ปิดวันจันทร์")
        self.assertEqual(restored.tags, ["cafe", "nimman"])
        self.assertIsNone(restored.superseded_by)
        self.assertIsNone(restored.archived_at)
        # กลับมาใช้งานได้จริง ไม่ใช่แค่มีแถวอยู่เฉยๆ
        self.assertEqual([item.id for item in memory.recall(self.conn, "ร้านกาแฟ")],
                         [restored.id])
        self.assertEqual([item.id for item in memory.recall(self.conn, "nimman")],
                         [restored.id])
        # ออกจากถังขยะแล้ว กู้ซ้ำไม่ได้ความจำซ้ำ
        self.assertEqual(self.trash_count(), 0)
        with self.assertRaises(KeyError):
            memory.restore(self.conn, original.id, DAY3)

    def test_restore_overwrites_current_and_reports_it(self) -> None:
        old, _ = memory.remember(self.conn, "ร้านกาแฟ", "เวอร์ชันเก่า", (), DAY1)
        memory.forget(self.conn, "ร้านกาแฟ", confirmed=True, when=DAY1)
        current, _ = memory.remember(self.conn, "ร้านกาแฟ", "เวอร์ชันใหม่", (), DAY2)

        restored, superseded = memory.restore_detailed(self.conn, old.id, DAY3)

        self.assertEqual(superseded.id, current.id)
        self.assertEqual([item.id for item in memory.recall(self.conn, "ร้านกาแฟ")],
                         [restored.id])

    def test_restore_unknown_id_raises(self) -> None:
        with self.assertRaises(KeyError):
            memory.restore(self.conn, 999, DAY3)

    def test_list_trash_is_newest_first_and_limited(self) -> None:
        memory.remember(self.conn, "เรื่อง A", "หนึ่ง", (), DAY1)
        memory.remember(self.conn, "เรื่อง B", "สอง", (), DAY1)
        memory.forget(self.conn, "เรื่อง A", confirmed=True, when=DAY1)
        memory.forget(self.conn, "เรื่อง B", confirmed=True, when=DAY2)

        trash = memory.list_trash(self.conn)
        self.assertEqual([row["topic"] for row in trash], ["เรื่อง B", "เรื่อง A"])
        self.assertEqual(len(memory.list_trash(self.conn, limit=1)), 1)
        with self.assertRaises(ValueError):
            memory.list_trash(self.conn, limit=0)


class ConsolidateTest(MemoryTestBase):
    def test_leaves_live_lessons_alone(self) -> None:
        live, _ = memory.remember(self.conn, "ตัดผม", "ร้านเกษมเกษา", (), DAY1)
        summary = memory.consolidate(
            self.conn, unused_days=0, when=DAY1 + timedelta(days=365)
        )
        self.assertEqual(summary["archived_count"], 0)
        self.assertIsNone(self.raw(live.id)["archived_at"])
        self.assertEqual([item.id for item in memory.recall(self.conn, "ตัดผม")],
                         [live.id])

    def test_archives_only_superseded_rows_that_sat_long_enough(self) -> None:
        gen1, gen2, gen3 = self.three_generations()
        # gen1 ถูกทับตอน DAY2 (นิ่งมา 17 วัน) / gen2 ถูกทับตอน DAY3 (นิ่งมาวันเดียว)
        # → เกณฑ์ 15 วันต้องพักแค่ gen1 ก้อนเดียว ส่วน gen3 ยังใช้อยู่ห้ามแตะ
        summary = memory.consolidate(
            self.conn, unused_days=15, when=DAY3 + timedelta(days=1)
        )
        self.assertEqual(summary["archived_count"], 1)
        self.assertEqual(summary["archived"][0]["id"], gen1.id)
        self.assertIsNotNone(self.raw(gen1.id)["archived_at"])
        self.assertIsNone(self.raw(gen2.id)["archived_at"])
        self.assertIsNone(self.raw(gen3.id)["archived_at"])
        self.assertEqual(summary["superseded_pending"], 1)

    def test_boundary_at_exactly_unused_days(self) -> None:
        memory.remember(self.conn, "ร้านกาแฟ", "เก่า", (), DAY1)
        memory.remember(self.conn, "ร้านกาแฟ", "ใหม่", (), DAY2)  # DAY2 = วันที่ของเก่าตาย

        early = memory.consolidate(
            self.conn, unused_days=60, when=DAY2 + timedelta(days=59)
        )
        self.assertEqual(early["archived_count"], 0)

        exact = memory.consolidate(
            self.conn, unused_days=60, when=DAY2 + timedelta(days=60)
        )
        self.assertEqual(exact["archived_count"], 1)

    def test_never_deletes_anything(self) -> None:
        self.three_generations()
        memory.consolidate(self.conn, unused_days=0, when=DAY3 + timedelta(days=90))
        # พักไว้ = ยังอยู่ในตาราง กู้กลับได้ ไม่ใช่หายไปเงียบๆ (H13)
        self.assertEqual(self.lesson_count(), 3)
        self.assertEqual(self.trash_count(), 0)

    def test_summary_shape_for_the_dream_report(self) -> None:
        self.three_generations()
        memory.remember(self.conn, "ตัดผม", "ร้านเกษมเกษา", (), DAY1)

        summary = memory.consolidate(
            self.conn, unused_days=30, when=DAY3 + timedelta(days=60)
        )

        self.assertEqual(summary["archived_count"], 2)
        self.assertEqual(summary["unused_days"], 30)
        self.assertEqual(summary["date_key"], "2026-08-30")
        self.assertFalse(summary["nothing_to_report"])
        self.assertEqual(summary["skipped"], [])
        # ประโยค "รวมเรื่องซ้ำ 3 ก้อนเป็นก้อนเดียว (เรื่องร้านกาแฟ)" ประกอบจากตรงนี้
        self.assertEqual(len(summary["merged_topics"]), 1)
        merged = summary["merged_topics"][0]
        self.assertEqual(merged["topic"], "ร้านกาแฟ")
        self.assertEqual(merged["archived"], 2)
        self.assertEqual(merged["kept"], 1)
        self.assertEqual(merged["merged_from"], 3)
        self.assertEqual(merged["kept_content"], "Ristr8to ปิดวันจันทร์")
        # ก้อนที่ยังใช้อยู่: ร้านกาแฟ (ล่าสุด) + ตัดผม
        self.assertEqual(summary["live_count"], 2)
        self.assertEqual(summary["archived_total"], 2)
        self.assertEqual(summary["trash_count"], 0)
        self.assertTrue(all("content" in row for row in summary["archived"]))
        self.assertEqual(summary["archived"][0]["tags"], ["cafe", "nimman"])

    def test_quiet_night_says_nothing_to_report(self) -> None:
        memory.remember(self.conn, "ตัดผม", "ร้านเกษมเกษา", (), DAY1)
        summary = memory.consolidate(self.conn, when=DAY2)
        self.assertTrue(summary["nothing_to_report"])
        self.assertEqual(summary["archived_count"], 0)
        self.assertEqual(summary["merged_topics"], [])

    def test_running_twice_is_idempotent(self) -> None:
        self.three_generations()
        first = memory.consolidate(self.conn, unused_days=0, when=DAY3 + timedelta(days=1))
        second = memory.consolidate(self.conn, unused_days=0, when=DAY3 + timedelta(days=2))
        self.assertEqual(first["archived_count"], 2)
        self.assertEqual(second["archived_count"], 0)
        self.assertTrue(second["nothing_to_report"])

    def test_unreadable_timestamp_is_reported_not_crashed(self) -> None:
        # แถวเวลาพังต้องไม่ทำให้งานตี 2 ตาย และต้องไม่หายเงียบ — ต้องโผล่ในรายงาน
        gen1, _, _ = self.three_generations()
        self.conn.execute(
            "UPDATE lessons SET updated_at = 'ไม่ใช่วันที่', created_at = 'พังเหมือนกัน' "
            "WHERE id = ?",
            (gen1.id,),
        )
        self.conn.commit()

        summary = memory.consolidate(self.conn, unused_days=0, when=DAY3 + timedelta(days=1))

        self.assertEqual([row["id"] for row in summary["skipped"]], [gen1.id])
        self.assertIsNone(self.raw(gen1.id)["archived_at"])
        self.assertFalse(summary["nothing_to_report"])

    def test_negative_unused_days_rejected(self) -> None:
        with self.assertRaises(ValueError):
            memory.consolidate(self.conn, unused_days=-1, when=DAY3)


class ArchivedAccessTest(MemoryTestBase):
    def test_archived_lessons_stay_visible_and_recoverable(self) -> None:
        gen1, _, _ = self.three_generations()
        memory.consolidate(self.conn, unused_days=0, when=DAY3 + timedelta(days=1))

        archived = memory.list_archived(self.conn)
        self.assertIn(gen1.id, [item.id for item in archived])

        back = memory.unarchive(self.conn, gen1.id, DAY3 + timedelta(days=2))
        self.assertIsNone(back.archived_at)
        self.assertEqual(back.content, "Ristr8to สั่งลาเต้ร้อน")
        # ยังถูกทับอยู่ตามเดิม — เอากลับมาดูได้ แต่ไม่ปนกับความจริงปัจจุบัน
        self.assertIsNotNone(back.superseded_by)
        self.assertEqual(len(memory.recall(self.conn, "ร้านกาแฟ")), 1)

    def test_unarchive_unknown_id_raises(self) -> None:
        with self.assertRaises(KeyError):
            memory.unarchive(self.conn, 4242, DAY3)


if __name__ == "__main__":
    unittest.main()
