"""
เทสต์ของ core/booking.py — spec v3 Phase 3 ข้อ 1-2

สามอย่างที่เทสต์ชุดนี้มีไว้ปกป้อง (พังแล้วไม่มี traceback ให้เห็น มีแต่ผลเสียในโลกจริง):
    1. ซองคำตอบล่วงหน้าต้องมีทางออก "ไม่เอา ให้โทรกลับมาถาม" เป็นตัวสุดท้ายเสมอ
       หายไปเมื่อไหร่ = โอมถูกบีบให้ผูกมัดล่วงหน้าทุกครั้งที่สั่งจอง
    2. confirmed ต้องมี result_note — กันไม่ให้รายงานว่า "เรียบร้อย" ทั้งที่ยังไม่มีใครยืนยัน
    3. booking_date ต้องเป็นคีย์วันแบบเวลาไทย — เที่ยงคืนกว่าของไทยยังเป็นเมื่อวานใน UTC
       ถ้าใช้ UTC จะจองไว้ผิดวันหนึ่งวันเต็มโดยไม่มีอะไรฟ้อง จนไปถึงร้านแล้วเขาไม่มีคิว

ทุกเทสต์ฉีดเวลาเองผ่าน `when` ไม่มีข้อไหนพึ่งวันจริงของเครื่อง
ใช้ไฟล์ DB ชั่วคราวเสมอ ไม่แตะ ~/.jarvis/jarvis.db ไม่ต้องมี API key ไม่ต้องต่อเน็ต
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from core import booking, db
from core.localdate import TZ

# ปฏิทินอ้างอิง: 2026-08-21 เป็นวันศุกร์
FRI = date(2026, 8, 21)
# 00:30 ของวันที่ 21 ตามเวลาไทย = 17:30 ของวันที่ 20 ตาม UTC — ตัวชี้ขาดข้อ 3 ข้างบน
AFTER_MIDNIGHT = datetime(2026, 8, 21, 0, 30, tzinfo=TZ)


class BookingTestBase(unittest.TestCase):
    """DB ชั่วคราวที่ migrate แล้ว 1 ชุดต่อ 1 เทสต์

    favorite_places ไม่มี seed มาให้ (002_seed.sql ไม่แตะตารางนี้ เพราะร้านประจำจริง
    ยังไม่ได้เก็บ) เทสต์จึงใส่ร้านเองทุกครั้ง — ตรงกับสภาพตอนติดตั้งใหม่
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "jarvis-test.db"
        self.conn = db.connect(self.db_path)
        db.migrate(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def add_place(
        self,
        kind: str,
        name: str,
        *,
        is_default: bool = False,
        phone: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO favorite_places (kind, name, phone, is_default) VALUES (?, ?, ?, ?)",
            (kind, name, phone, 1 if is_default else 0),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def seed_defaults(self) -> dict[str, int]:
        """ร้านประจำครบทั้ง 4 ชนิด — ชุดเดียวกับที่ Phase 3 จะใช้จริง"""
        return {
            booking.RESTAURANT: self.add_place(
                booking.RESTAURANT, "ร้านประจำ", is_default=True, phone="053-000-001"
            ),
            booking.EYEBROW: self.add_place(booking.EYEBROW, "ร้านคิ้วประจำ", is_default=True),
            booking.LASER: self.add_place(booking.LASER, "คลินิกเลเซอร์ประจำ", is_default=True),
            booking.HOTEL: self.add_place(booking.HOTEL, "โรงแรมประจำ", is_default=True),
        }

    def row(self, booking_id: int):
        return self.conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()


class ResolvePlaceTests(BookingTestBase):
    """หาว่า "ร้านไหน" — spec v3 Phase 3 ข้อ 1 "ดึงร้าน default ถ้าไม่ระบุ" """

    def test_default_place_per_kind(self) -> None:
        ids = self.seed_defaults()
        expected = {
            booking.RESTAURANT: "ร้านประจำ",
            booking.EYEBROW: "ร้านคิ้วประจำ",
            booking.LASER: "คลินิกเลเซอร์ประจำ",
            booking.HOTEL: "โรงแรมประจำ",
        }
        # ทั้ง 4 ชนิดต้องหยิบร้านของชนิดตัวเอง ไม่ใช่ร้านแรกที่เจอในตาราง
        for kind, name in expected.items():
            with self.subTest(kind=kind):
                row = booking.resolve_place(self.conn, kind, None)
                self.assertEqual(row["name"], name)
                self.assertEqual(row["kind"], kind)
                self.assertEqual(row["id"], ids[kind])

    def test_default_ignores_non_default_rows_of_same_kind(self) -> None:
        self.add_place(booking.RESTAURANT, "ร้านที่เคยไปครั้งเดียว")
        self.add_place(booking.RESTAURANT, "ร้านประจำ", is_default=True)
        row = booking.resolve_place(self.conn, booking.RESTAURANT, None)
        self.assertEqual(row["name"], "ร้านประจำ")

    def test_missing_default_raises_lookup_error(self) -> None:
        # มีร้านประจำของ restaurant แต่ไม่มีของ hotel → ถามหา hotel ต้องไม่ไปหยิบของ restaurant มา
        self.add_place(booking.RESTAURANT, "ร้านประจำ", is_default=True)
        with self.assertRaises(LookupError):
            booking.resolve_place(self.conn, booking.HOTEL, None)

    def test_missing_default_message_tells_how_to_fix(self) -> None:
        with self.assertRaises(LookupError) as ctx:
            booking.resolve_place(self.conn, booking.LASER, None)
        self.assertIn("favorite_places", str(ctx.exception))
        self.assertIn(booking.LASER, str(ctx.exception))

    def test_blank_place_is_treated_as_not_given(self) -> None:
        self.seed_defaults()
        row = booking.resolve_place(self.conn, booking.EYEBROW, "   ")
        self.assertEqual(row["name"], "ร้านคิ้วประจำ")

    def test_named_favorite_wins_over_default(self) -> None:
        self.add_place(booking.RESTAURANT, "ร้านประจำ", is_default=True)
        other = self.add_place(booking.RESTAURANT, "ร้านหมูกระทะ", phone="053-000-002")
        row = booking.resolve_place(self.conn, booking.RESTAURANT, "ร้านหมูกระทะ")
        self.assertEqual(row["id"], other)
        self.assertEqual(row["phone"], "053-000-002")

    def test_partial_name_matches_single_favorite(self) -> None:
        pid = self.add_place(booking.RESTAURANT, "Sushiro เมญ่า")
        row = booking.resolve_place(self.conn, booking.RESTAURANT, "sushiro")
        self.assertEqual(row["id"], pid)

    def test_ambiguous_partial_name_is_not_guessed(self) -> None:
        # สองร้านที่ชื่อคล้ายกัน → ห้ามเดาแทนโอม ให้ถือเป็นร้านนอกรายการแทน
        self.add_place(booking.RESTAURANT, "Sushiro เมญ่า")
        self.add_place(booking.RESTAURANT, "Sushiro เซ็นทรัล")
        row = booking.resolve_place(self.conn, booking.RESTAURANT, "Sushiro")
        self.assertIsNone(row["id"])
        self.assertEqual(row["name"], "Sushiro")

    def test_unknown_place_becomes_adhoc_row(self) -> None:
        # "จองร้าน X พรุ่งนี้" ต้องทำได้ทั้งที่ X ไม่เคยอยู่ในรายการโปรด
        row = booking.resolve_place(self.conn, booking.RESTAURANT, "ร้านใหม่ที่เพิ่งเห็นในไอจี")
        self.assertIsNone(row["id"])
        self.assertEqual(row["name"], "ร้านใหม่ที่เพิ่งเห็นในไอจี")
        self.assertEqual(row["kind"], booking.RESTAURANT)

    def test_invalid_kind_raises_value_error(self) -> None:
        for bad in ("dentist", "", None, "RESTAURANTS"):
            with self.subTest(kind=bad):
                with self.assertRaises(ValueError):
                    booking.resolve_place(self.conn, bad, "ที่ไหนสักแห่ง")

    def test_kind_is_case_insensitive(self) -> None:
        self.seed_defaults()
        row = booking.resolve_place(self.conn, "Restaurant", None)
        self.assertEqual(row["name"], "ร้านประจำ")


class MakeBookingTests(BookingTestBase):
    """สร้างแถวการจอง — ยังไม่โทร สถานะต้องเป็น pending เท่านั้น"""

    def test_creates_pending_row_with_default_place(self) -> None:
        ids = self.seed_defaults()
        bid = booking.make_booking(
            self.conn, booking.RESTAURANT, date=FRI, time="18:00", party_size=4
        )
        row = self.row(bid)
        self.assertEqual(row["status"], booking.PENDING)
        self.assertEqual(row["place_name"], "ร้านประจำ")
        self.assertEqual(row["place_id"], ids[booking.RESTAURANT])
        self.assertEqual(row["booking_date"], "2026-08-21")
        self.assertEqual(row["booking_time"], "18:00")
        self.assertEqual(row["party_size"], 4)
        self.assertIsNone(row["result_note"])

    def test_adhoc_place_stores_name_without_place_id(self) -> None:
        bid = booking.make_booking(
            self.conn, booking.RESTAURANT, "ร้านลับริมน้ำ", date=FRI, time="19:00"
        )
        row = self.row(bid)
        self.assertEqual(row["place_name"], "ร้านลับริมน้ำ")
        self.assertIsNone(row["place_id"])

    def test_missing_default_raises_lookup_error(self) -> None:
        with self.assertRaises(LookupError):
            booking.make_booking(self.conn, booking.EYEBROW, date=FRI, time="15:00")

    def test_invalid_kind_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            booking.make_booking(self.conn, "massage", "ร้านนวด", date=FRI)
        # ต้องไม่มีแถวค้างในฐานข้อมูลจากการเรียกที่ล้มเหลว
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0], 0)

    def test_booking_date_uses_thai_local_day_not_utc(self) -> None:
        """00:30 คืนวันที่ 21 ตามเวลาไทย = 17:30 วันที่ 20 ตาม UTC — ต้องได้ 21"""
        self.seed_defaults()
        bid = booking.make_booking(
            self.conn, booking.RESTAURANT, time="18:00", when=AFTER_MIDNIGHT
        )
        self.assertEqual(self.row(bid)["booking_date"], "2026-08-21")

    def test_booking_date_from_aware_utc_clock(self) -> None:
        """ฉีดเวลาเป็น UTC ตรงๆ ก็ต้องแปลงเป็นวันไทยก่อนเก็บ"""
        self.seed_defaults()
        utc_clock = AFTER_MIDNIGHT.astimezone(timezone.utc)
        self.assertEqual(utc_clock.date(), date(2026, 8, 20))  # ยืนยันว่าคนละวันจริงๆ
        bid = booking.make_booking(self.conn, booking.RESTAURANT, when=utc_clock)
        self.assertEqual(self.row(bid)["booking_date"], "2026-08-21")

    def test_explicit_date_accepts_string_and_datetime(self) -> None:
        self.seed_defaults()
        first = booking.make_booking(self.conn, booking.RESTAURANT, date="2026-08-21")
        second = booking.make_booking(
            self.conn, booking.RESTAURANT, date=datetime(2026, 8, 21, 23, 59, tzinfo=TZ)
        )
        self.assertEqual(self.row(first)["booking_date"], "2026-08-21")
        self.assertEqual(self.row(second)["booking_date"], "2026-08-21")

    def test_explicit_date_wins_over_clock(self) -> None:
        self.seed_defaults()
        tomorrow = FRI + timedelta(days=1)
        bid = booking.make_booking(
            self.conn, booking.RESTAURANT, date=tomorrow, when=AFTER_MIDNIGHT
        )
        self.assertEqual(self.row(bid)["booking_date"], "2026-08-22")

    def test_time_is_normalized(self) -> None:
        self.seed_defaults()
        for given, expected in (("9:05", "09:05"), ("18.30", "18:30"), (time(20, 0), "20:00")):
            with self.subTest(time=given):
                bid = booking.make_booking(
                    self.conn, booking.RESTAURANT, date=FRI, time=given
                )
                self.assertEqual(self.row(bid)["booking_time"], expected)

    def test_bad_time_raises_value_error(self) -> None:
        self.seed_defaults()
        for bad in ("หกโมงเย็น", "25:00", "18:70", "6"):
            with self.subTest(time=bad):
                with self.assertRaises(ValueError):
                    booking.make_booking(self.conn, booking.RESTAURANT, date=FRI, time=bad)

    def test_time_optional_for_kinds_without_a_clock_time(self) -> None:
        self.seed_defaults()
        bid = booking.make_booking(self.conn, booking.HOTEL, date=FRI)
        row = self.row(bid)
        self.assertIsNone(row["booking_time"])
        self.assertIsNone(row["party_size"])

    def test_party_size_must_be_positive(self) -> None:
        self.seed_defaults()
        for bad in (0, -1, "สี่"):
            with self.subTest(party_size=bad):
                with self.assertRaises(ValueError):
                    booking.make_booking(
                        self.conn, booking.RESTAURANT, date=FRI, party_size=bad
                    )

    def test_fallback_slots_stored_as_json(self) -> None:
        self.seed_defaults()
        bid = booking.make_booking(
            self.conn,
            booking.RESTAURANT,
            date=FRI,
            time="18:00",
            fallback_slots=["19:30", "20:00"],
        )
        self.assertEqual(json.loads(self.row(bid)["fallback_slots"]), ["19:30", "20:00"])

    def test_fallback_slots_drop_primary_and_duplicates(self) -> None:
        self.seed_defaults()
        bid = booking.make_booking(
            self.conn,
            booking.RESTAURANT,
            date=FRI,
            time="18:00",
            fallback_slots=["18:00", "19.30", "19:30", "20:00"],
        )
        self.assertEqual(json.loads(self.row(bid)["fallback_slots"]), ["19:30", "20:00"])

    def test_no_fallback_slots_stores_null(self) -> None:
        self.seed_defaults()
        bid = booking.make_booking(self.conn, booking.RESTAURANT, date=FRI, time="18:00")
        self.assertIsNone(self.row(bid)["fallback_slots"])

    def test_request_for_round_trip(self) -> None:
        self.seed_defaults()
        bid = booking.make_booking(
            self.conn,
            booking.RESTAURANT,
            date=FRI,
            time="18:00",
            party_size=4,
            fallback_slots=("19:30", "20:00"),
        )
        req = booking.request_for(self.conn, bid)
        self.assertEqual(
            req,
            booking.BookingRequest(
                kind=booking.RESTAURANT,
                place="ร้านประจำ",
                date="2026-08-21",
                time="18:00",
                party_size=4,
                fallback_slots=["19:30", "20:00"],
            ),
        )

    def test_request_for_unknown_id_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            booking.request_for(self.conn, 999)


class AnswerEnvelopeTests(unittest.TestCase):
    """ซองคำตอบล่วงหน้า — spec v3 Phase 3 ข้อ 2 กลไกหลัก (ไม่ต้องใช้ DB)"""

    def request(self, **kwargs) -> booking.BookingRequest:
        base = {
            "kind": booking.RESTAURANT,
            "place": "ร้านประจำ",
            "date": "2026-08-21",
            "time": "18:00",
            "party_size": 4,
            "fallback_slots": ["19:30", "20:00"],
        }
        base.update(kwargs)
        return booking.BookingRequest(**base)

    def test_matches_spec_example(self) -> None:
        """spec: "ถ้า 18:00 เต็ม เอา [19:30] [20:00] [ไม่เอา ให้โทรกลับมาถาม]" """
        env = booking.answer_envelope(self.request())
        self.assertEqual(env["options"], ["19:30", "20:00", booking.OPT_OUT])
        self.assertIn("18:00", env["question"])
        self.assertIn("ร้านประจำ", env["question"])
        self.assertIn("21 ส.ค.", env["question"])

    def test_opt_out_is_always_last(self) -> None:
        cases = [
            self.request(),
            self.request(fallback_slots=[]),
            self.request(fallback_slots=["19:30"]),
            self.request(time=None, fallback_slots=[]),
            self.request(time=None, fallback_slots=["19:30", "20:00", "21:00"]),
            self.request(place="", date="2026-08-21", time=None, fallback_slots=[]),
        ]
        for req in cases:
            with self.subTest(time=req.time, slots=req.fallback_slots):
                env = booking.answer_envelope(req)
                self.assertEqual(env["options"][-1], booking.OPT_OUT)
                self.assertTrue(booking.is_opt_out(env["options"][-1]))
                # ต้องโผล่ครั้งเดียว ไม่ใช่ปุ่มซ้ำสองปุ่ม
                self.assertEqual(env["options"].count(booking.OPT_OUT), 1)

    def test_empty_envelope_still_offers_opt_out(self) -> None:
        """ไม่มีเวลาสำรองสักช่อง = ยังต้องมีปุ่ม "ให้โทรกลับมาถาม" ให้กด"""
        env = booking.answer_envelope(self.request(fallback_slots=[]))
        self.assertEqual(env["options"], [booking.OPT_OUT])
        self.assertEqual(env["opt_out"], booking.OPT_OUT)

    def test_primary_time_never_offered_as_fallback(self) -> None:
        env = booking.answer_envelope(self.request(fallback_slots=["18:00", "19:30"]))
        self.assertEqual(env["options"], ["19:30", booking.OPT_OUT])

    def test_slot_order_follows_ohm_preference(self) -> None:
        env = booking.answer_envelope(self.request(fallback_slots=["20:00", "19:30"]))
        self.assertEqual(env["options"], ["20:00", "19:30", booking.OPT_OUT])

    def test_question_without_primary_time(self) -> None:
        env = booking.answer_envelope(
            self.request(kind=booking.HOTEL, place="โรงแรมประจำ", time=None, party_size=None)
        )
        self.assertIn("โรงแรมประจำ", env["question"])
        self.assertNotIn("เต็ม เอาเวลาไหน", env["question"])
        self.assertEqual(env["options"][-1], booking.OPT_OUT)

    def test_envelope_has_contract_keys(self) -> None:
        env = booking.answer_envelope(self.request())
        self.assertIsInstance(env["question"], str)
        self.assertIsInstance(env["options"], list)
        for option in env["options"]:
            self.assertIsInstance(option, str)

    def test_is_opt_out_only_matches_the_opt_out_text(self) -> None:
        self.assertTrue(booking.is_opt_out(booking.OPT_OUT))
        self.assertTrue(booking.is_opt_out(f" {booking.OPT_OUT} "))
        self.assertFalse(booking.is_opt_out("19:30"))
        self.assertFalse(booking.is_opt_out("ไม่เอา"))


class UpdateStatusTests(BookingTestBase):
    """ห้ามรายงานว่า "เรียบร้อย" ถ้ายังไม่ได้ยืนยันว่าสำเร็จจริง — บังคับด้วยโค้ด"""

    def setUp(self) -> None:
        super().setUp()
        self.seed_defaults()
        self.bid = booking.make_booking(
            self.conn, booking.RESTAURANT, date=FRI, time="18:00", party_size=4
        )

    def test_confirmed_without_note_raises(self) -> None:
        with self.assertRaises(ValueError):
            booking.update_status(self.conn, self.bid, booking.CONFIRMED)
        # และต้องไม่แอบเปลี่ยนสถานะไปแล้วก่อนระเบิด
        self.assertEqual(self.row(self.bid)["status"], booking.PENDING)

    def test_confirmed_with_blank_note_raises(self) -> None:
        for blank in ("", "   ", "\n"):
            with self.subTest(note=blank):
                with self.assertRaises(ValueError):
                    booking.update_status(self.conn, self.bid, booking.CONFIRMED, blank)
        self.assertEqual(self.row(self.bid)["status"], booking.PENDING)

    def test_confirmed_with_note_succeeds(self) -> None:
        booking.update_status(
            self.conn, self.bid, booking.CONFIRMED, "ร้านยืนยัน 18:00 4 ที่ ชื่อโอม"
        )
        row = self.row(self.bid)
        self.assertEqual(row["status"], booking.CONFIRMED)
        self.assertEqual(row["result_note"], "ร้านยืนยัน 18:00 4 ที่ ชื่อโอม")

    def test_other_statuses_do_not_need_a_note(self) -> None:
        for status in (booking.CALLING, booking.NEEDS_INPUT, booking.FAILED, booking.CANCELLED):
            with self.subTest(status=status):
                booking.update_status(self.conn, self.bid, status)
                self.assertEqual(self.row(self.bid)["status"], status)

    def test_invalid_status_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            booking.update_status(self.conn, self.bid, "done", "ร้านรับแล้ว")
        self.assertEqual(self.row(self.bid)["status"], booking.PENDING)

    def test_unknown_booking_id_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            booking.update_status(self.conn, self.bid + 999, booking.FAILED)

    def test_note_is_kept_when_status_changes_later(self) -> None:
        # คำตอบของร้านที่จดไว้ตอนโทรคือหลักฐาน ยกเลิกทีหลังต้องไม่ลบทิ้ง
        booking.update_status(self.conn, self.bid, booking.CONFIRMED, "ร้านยืนยัน 18:00")
        booking.update_status(self.conn, self.bid, booking.CANCELLED)
        row = self.row(self.bid)
        self.assertEqual(row["status"], booking.CANCELLED)
        self.assertEqual(row["result_note"], "ร้านยืนยัน 18:00")

    def test_note_can_be_replaced(self) -> None:
        booking.update_status(self.conn, self.bid, booking.FAILED, "โทรไม่ติด")
        booking.update_status(self.conn, self.bid, booking.CONFIRMED, "โทรรอบสอง ร้านรับ 19:30")
        self.assertEqual(self.row(self.bid)["result_note"], "โทรรอบสอง ร้านรับ 19:30")

    def test_status_is_case_insensitive(self) -> None:
        booking.update_status(self.conn, self.bid, "CONFIRMED", "ร้านยืนยันแล้ว")
        self.assertEqual(self.row(self.bid)["status"], booking.CONFIRMED)

    def test_full_phase3_flow(self) -> None:
        """เส้นทางเต็มของ Phase 3 โดยไม่โทรจริง: pending → ซอง → calling → confirmed"""
        req = booking.request_for(self.conn, self.bid)
        env = booking.answer_envelope(req._replace(fallback_slots=["19:30", "20:00"]))
        self.assertEqual(env["options"][-1], booking.OPT_OUT)

        booking.update_status(self.conn, self.bid, booking.CALLING)
        self.assertEqual(self.row(self.bid)["status"], booking.CALLING)

        # สมมติ AI ใช้สิทธิ์ในซอง เลือก 19:30 เพราะ 18:00 เต็ม
        chosen = env["options"][0]
        self.assertFalse(booking.is_opt_out(chosen))
        booking.update_status(self.conn, self.bid, booking.CONFIRMED, f"ร้านยืนยัน {chosen} 4 ที่")
        row = self.row(self.bid)
        self.assertEqual(row["status"], booking.CONFIRMED)
        self.assertIn("19:30", row["result_note"])


if __name__ == "__main__":
    unittest.main()
