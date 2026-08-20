"""
เทสต์ของ core/webhook.py — red-team PART 2.5 (แก้ H1) + spec v3 Phase 2 ข้อ 1

endpoint นี้เป็นจุดเดียวในระบบที่เปิดสู่อินเทอร์เน็ตสาธารณะโดยตรง
ไม่มีชั้นไหนกันให้ข้างหน้ามัน สิ่งที่เทสต์ชุดนี้ปกป้องจึงไม่ใช่ "ฟังก์ชันคืนค่าถูกไหม"
แต่คือสี่อย่างที่พังแล้วไม่มี traceback ให้เห็น มีแต่ผลเสียในโลกจริง:

    1. การเทียบ secret ต้องใช้เวลาคงที่ — มีเทสต์อ่าน source ของ verify_secret ตรงๆ
       ถ้าวันหน้าใครรีแฟกเตอร์แล้วเผลอเปลี่ยนกลับไปใช้ == เทสต์จะแดงทันที
       (เทสต์พฤติกรรมจับ timing leak ไม่ได้เลย เพราะผลลัพธ์ "ถูก/ผิด" เหมือนกันเป๊ะ)
    2. secret ฝั่งเซิร์ฟเวอร์ว่าง ต้องล้มแบบ "ปิดประตู" (500) ไม่ใช่ปล่อยผ่านทุกคน
       บั๊กแบบนี้ทำให้ทั้งอินเทอร์เน็ตสั่งบ้านโอมได้ โดยระบบยังดูทำงานปกติทุกอย่าง
    3. คีย์ 'speak' ต้องมีเสมอ — Shortcut อ่านคีย์นี้ตัวเดียว หายเมื่อไหร่โอมได้ยิน
       ความเงียบ ซึ่งแยกไม่ออกว่าสำเร็จแบบไม่มีอะไรจะพูด หรือระบบตายไปแล้ว
    4. ข้อความว่าง/มีแต่เว้นวรรค ต้องถูกตีกลับ ไม่ใช่ไหลไปให้ชั้นบนตีความ
       เพราะ Dictate Text ที่ไม่ได้ยินอะไรจะส่ง "" มา แล้ว LLM จะ "เดา" คำสั่งขึ้นเอง

ทุกเทสต์รันได้โดยไม่ต้องเปิดพอร์ต ไม่ต้องมี API key ไม่ต้องต่อเน็ต ไม่แตะ DB
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
import unittest

from core import webhook
from core.webhook import WebhookError

SECRET = "s3cr3t-jarvis-2026"
HEADERS = {"X-Jarvis-Secret": SECRET, "Content-Type": "application/json"}


def body_of(**payload: object) -> str:
    """สร้าง body แบบเดียวกับที่ action 'Get Contents of URL' ส่งมาจริง"""
    return json.dumps(payload, ensure_ascii=False)


class WebhookTestBase(unittest.TestCase):
    def assertStatus(self, status: int, fn, *args, **kwargs) -> WebhookError:
        """เรียกแล้วต้องล้มด้วย status ที่ระบุ — คืน error ไว้ตรวจต่อ"""
        with self.assertRaises(WebhookError) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(
            status,
            ctx.exception.status,
            f"คาด HTTP {status} แต่ได้ {ctx.exception.status}: {ctx.exception.message}",
        )
        return ctx.exception


# --------------------------------------------------------------------------
# 1. กันการรั่วผ่านเวลา — เทสต์ที่อ่าน source ไม่ใช่ผลลัพธ์
# --------------------------------------------------------------------------


def _code_without_comments(func) -> str:
    """คืนโค้ดของฟังก์ชันโดยตัดคอมเมนต์และ docstring ออก

    ต้องตัดออกก่อนตรวจ เพราะคอมเมนต์ภาษาไทยอาจพูดถึงเครื่องหมายเทียบเท่า
    ในเชิงอธิบาย ซึ่งไม่ใช่โค้ดที่รันจริง — ใช้ ast.unparse เพราะมันสร้างข้อความ
    จากต้นไม้ไวยากรณ์ล้วน คอมเมนต์กับ docstring จึงหายไปเองโดยไม่ต้องเขียน regex
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    node = tree.body[0]
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return "\n".join(ast.unparse(stmt) for stmt in body)


class TimingSafetyTest(WebhookTestBase):
    """เทสต์ที่มีไว้กันการรีแฟกเตอร์ในอนาคต ไม่ใช่กันบั๊กวันนี้"""

    def test_verify_secret_uses_compare_digest(self) -> None:
        code = _code_without_comments(webhook.verify_secret)
        self.assertIn(
            "compare_digest",
            code,
            "verify_secret ต้องเทียบ secret ด้วย hmac.compare_digest เท่านั้น",
        )
        self.assertIn(
            "hmac.compare_digest(",
            code,
            "ต้องเรียก compare_digest ในตัว verify_secret เอง ไม่ใช่ซ่อนไว้ที่อื่น",
        )

    def test_verify_secret_has_no_equality_comparison(self) -> None:
        """ห้ามมีการเทียบเท่า/ไม่เท่าในฟังก์ชันนี้เลยแม้แต่ที่เดียว

        เทียบ secret ด้วย == จะหยุดที่ไบต์แรกที่ต่าง เวลาที่ใช้เลยบอกใบ้ว่าเดาถูกกี่ตัว
        ผู้โจมตีวัดเวลาตอบซ้ำๆ แล้วไล่เดาทีละตัวอักษรได้
        กติกาที่บังคับตรงนี้คือ "ห้ามมี == เลย" เพราะถ้าอนุญาตให้มีบางที่
        คนแก้ครั้งหน้าจะเถียงได้เสมอว่าอันของตัวเองไม่เกี่ยวกับ secret
        """
        code = _code_without_comments(webhook.verify_secret)
        for operator in ("==", "!="):
            self.assertNotIn(
                operator,
                code,
                f"เจอ '{operator}' ใน verify_secret — timing leak กลับมาแล้ว",
            )

    def test_module_has_no_network_or_llm_import(self) -> None:
        """กฎเหล็กข้อ 2 — core/ ต้องเป็น stdlib ล้วน เทสต์ต้องรันได้โดยไม่มี API key"""
        source = inspect.getsource(webhook)
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(imported, {"__future__", "hmac", "json", "typing"})

    def test_module_never_asks_the_system_clock(self) -> None:
        """กฎเหล็กข้อ 1 — ห้ามถามนาฬิกาเครื่องเอง แม้จะดูไม่มีพิษภัย

        ตรวจจากต้นไม้ไวยากรณ์ ไม่ใช่ค้นข้อความ เพราะคอมเมนต์ที่ "ห้ามเรียก now()"
        ก็มีคำว่า now() อยู่ในตัวมันเอง — ค้นข้อความจะแดงเพราะเอกสารที่ถูกต้อง
        """
        tree = ast.parse(inspect.getsource(webhook))
        forbidden = {"now", "today", "utcnow", "time", "monotonic"}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            self.assertNotIn(called, forbidden, f"โมดูลนี้ห้ามเรียก {called}()")


# --------------------------------------------------------------------------
# 2. verify_secret
# --------------------------------------------------------------------------


class VerifySecretTest(WebhookTestBase):
    def test_correct_secret_passes_silently(self) -> None:
        self.assertIsNone(webhook.verify_secret(HEADERS, SECRET))

    def test_header_name_is_case_insensitive(self) -> None:
        """proxy แต่ละตัวแปลงตัวพิมพ์ชื่อ header ไม่เหมือนกัน ต้องรับได้หมด

        พังตรงนี้จะกลายเป็น 401 ทุกครั้งหลังเปลี่ยน reverse proxy
        แล้วคนแก้จะไปไล่หาว่า secret ตั้งผิด ทั้งที่ secret ถูกอยู่แล้ว
        """
        for name in ("x-jarvis-secret", "X-JARVIS-SECRET", "X-Jarvis-Secret", "HTTP_X_JARVIS_SECRET"):
            with self.subTest(header=name):
                self.assertIsNone(webhook.verify_secret({name: SECRET}, SECRET))

    def test_bytes_header_value_is_accepted(self) -> None:
        self.assertIsNone(webhook.verify_secret({"X-Jarvis-Secret": SECRET.encode()}, SECRET))

    def test_wrong_secret_is_401(self) -> None:
        self.assertStatus(401, webhook.verify_secret, {"X-Jarvis-Secret": "wrong"}, SECRET)

    def test_secret_off_by_one_character_is_401(self) -> None:
        self.assertStatus(401, webhook.verify_secret, {"X-Jarvis-Secret": SECRET + "x"}, SECRET)
        self.assertStatus(401, webhook.verify_secret, {"X-Jarvis-Secret": SECRET[:-1]}, SECRET)

    def test_missing_header_is_401(self) -> None:
        self.assertStatus(401, webhook.verify_secret, {"Content-Type": "application/json"}, SECRET)

    def test_no_headers_at_all_is_401(self) -> None:
        self.assertStatus(401, webhook.verify_secret, {}, SECRET)
        self.assertStatus(401, webhook.verify_secret, None, SECRET)

    def test_empty_header_value_is_401(self) -> None:
        self.assertStatus(401, webhook.verify_secret, {"X-Jarvis-Secret": ""}, SECRET)

    def test_non_string_header_value_is_401(self) -> None:
        """framework บางตัวคืน header เป็น list — ห้ามให้ค่าประหลาดเล็ดลอดผ่าน"""
        for value in ([SECRET], None, 12345, {"v": SECRET}):
            with self.subTest(value=value):
                self.assertStatus(401, webhook.verify_secret, {"X-Jarvis-Secret": value}, SECRET)

    def test_missing_and_wrong_secret_give_identical_message(self) -> None:
        """ข้อความ error ต้องเหมือนกัน ไม่บอกว่าพลาดเพราะไม่มี header หรือค่าผิด

        การบอกว่าพลาดตรงไหนคือการช่วยผู้โจมตีตัดตัวเลือกให้แคบลงฟรีๆ
        """
        missing = self.assertStatus(401, webhook.verify_secret, {}, SECRET)
        wrong = self.assertStatus(401, webhook.verify_secret, {"X-Jarvis-Secret": "nope"}, SECRET)
        self.assertEqual(missing.message, wrong.message)

    def test_error_message_never_echoes_the_secret(self) -> None:
        """ข้อความ error ของ endpoint สาธารณะ = สิ่งที่ผู้โจมตีอ่านได้ฟรีทุกครั้งที่ยิง"""
        err = self.assertStatus(401, webhook.verify_secret, {"X-Jarvis-Secret": "guess"}, SECRET)
        self.assertNotIn(SECRET, err.message)
        self.assertNotIn(SECRET, str(err))

    def test_empty_expected_secret_fails_closed_with_500(self) -> None:
        """ข้อที่สำคัญที่สุดรองจาก compare_digest

        ถ้าลืมตั้ง secret แล้วระบบเลือก "ปล่อยผ่าน" ทั้งอินเทอร์เน็ตจะสั่งบ้านได้
        โดยทุกอย่างยังดูทำงานปกติ — ไม่มีใครรู้จนกว่าจะสาย
        """
        for expected in ("", "   ", "\t\n", None):
            with self.subTest(expected=expected):
                self.assertStatus(500, webhook.verify_secret, HEADERS, expected)

    def test_empty_secret_on_both_sides_still_fails(self) -> None:
        """เคสที่บั๊กจริงชอบซ่อนตัว: ฝั่งเซิร์ฟเวอร์ว่าง + ผู้เรียกส่งค่าว่างมา

        ถ้าเทียบสองค่าว่างกันตรงๆ มันจะ "ตรงกัน" แล้วผ่านทันที
        ต้องได้ 500 (ความผิดของเซิร์ฟเวอร์) ไม่ใช่ 200
        """
        self.assertStatus(500, webhook.verify_secret, {"X-Jarvis-Secret": ""}, "")

    def test_placeholder_secret_fails_closed_with_500(self) -> None:
        """secret ที่ยังเป็นค่าตัวอย่างในไฟล์ config = ยังไม่ได้ตั้ง"""
        for expected in ("[ต้องกรอก]", "changeme", "TODO"):
            with self.subTest(expected=expected):
                self.assertStatus(500, webhook.verify_secret, {"X-Jarvis-Secret": expected}, expected)

    def test_non_ascii_secret_works(self) -> None:
        """compare_digest แบบ str รับได้เฉพาะ ASCII — ถ้าไม่ encode ก่อนจะ TypeError

        พังแบบนี้จะกลายเป็น 500 ทุก request แทนที่จะเป็น 401/200 ตามจริง
        """
        thai = "รหัสลับ-ภาษาไทย-๒๕๖๙"
        self.assertIsNone(webhook.verify_secret({"X-Jarvis-Secret": thai}, thai))
        self.assertStatus(401, webhook.verify_secret, {"X-Jarvis-Secret": "รหัสลับอื่น"}, thai)

    def test_very_long_supplied_secret_is_rejected_not_crashed(self) -> None:
        self.assertStatus(401, webhook.verify_secret, {"X-Jarvis-Secret": "a" * 100_000}, SECRET)


# --------------------------------------------------------------------------
# 3. parse_request
# --------------------------------------------------------------------------


class ParseRequestTest(WebhookTestBase):
    def test_valid_request_parses(self) -> None:
        got = webhook.parse_request(body_of(text="เปิดไฟห้องนอนให้หน่อย"), HEADERS, SECRET)
        self.assertEqual({"text": "เปิดไฟห้องนอนให้หน่อย", "source": "siri"}, got)

    def test_returns_exactly_the_contracted_keys(self) -> None:
        """สัญญาเขียนไว้ว่าคืน {'text', 'source'} — คีย์เกินมาจะทำให้ผู้เรียกที่เทียบ dict พัง"""
        got = webhook.parse_request(body_of(text="ทดสอบ"), HEADERS, SECRET)
        self.assertEqual({"text", "source"}, set(got))

    def test_bytes_body_parses(self) -> None:
        """Shortcut ส่งมาเป็นไบต์ UTF-8 ชั้นโฮสต์บางตัวไม่ decode ให้"""
        raw = body_of(text="พรุ่งนี้มีเรียนอะไรบ้าง").encode("utf-8")
        got = webhook.parse_request(raw, HEADERS, SECRET)
        self.assertEqual("พรุ่งนี้มีเรียนอะไรบ้าง", got["text"])

    def test_text_is_trimmed_but_inner_spacing_kept(self) -> None:
        got = webhook.parse_request(body_of(text="  จำไว้ว่า ครูให้ส่งงาน วันศุกร์  "), HEADERS, SECRET)
        self.assertEqual("จำไว้ว่า ครูให้ส่งงาน วันศุกร์", got["text"])

    def test_source_defaults_to_siri(self) -> None:
        """ทางเข้าหลักตาม red-team คือ Siri — ไม่ระบุมาถือว่ามาจากที่นั่น"""
        self.assertEqual("siri", webhook.parse_request(body_of(text="ก"), HEADERS, SECRET)["source"])

    def test_explicit_source_is_kept(self) -> None:
        """ฝั่ง Android ใช้ Google Assistant routine ต้องแยกออกจาก Siri ได้ใน log"""
        got = webhook.parse_request(body_of(text="ก", source="android"), HEADERS, SECRET)
        self.assertEqual("android", got["source"])

    def test_blank_or_null_source_falls_back_to_siri(self) -> None:
        for value in ("", "   ", None):
            with self.subTest(source=value):
                got = webhook.parse_request(body_of(text="ก", source=value), HEADERS, SECRET)
                self.assertEqual("siri", got["source"])

    def test_absurd_source_is_400(self) -> None:
        """source ไปนั่งอยู่ใน log — ยาวเกินจริงหรือไม่ใช่ข้อความ ต้องตีกลับ ไม่ใช่ตัดเงียบๆ"""
        self.assertStatus(400, webhook.parse_request, body_of(text="ก", source="x" * 200), HEADERS, SECRET)
        self.assertStatus(400, webhook.parse_request, body_of(text="ก", source=99), HEADERS, SECRET)

    def test_unknown_keys_are_ignored(self) -> None:
        """Shortcut รุ่นหลังอาจแนบ field เพิ่ม ห้ามพังเพราะเจอของที่ไม่รู้จัก"""
        body = body_of(text="ก", source="siri", device="iPhone", locale="th-TH")
        self.assertEqual({"text": "ก", "source": "siri"}, webhook.parse_request(body, HEADERS, SECRET))

    # --- ยืนยันตัวตน มาก่อนทุกอย่าง ---------------------------------------

    def test_wrong_secret_is_401(self) -> None:
        bad = {"X-Jarvis-Secret": "wrong"}
        self.assertStatus(401, webhook.parse_request, body_of(text="เปิดแอร์"), bad, SECRET)

    def test_missing_header_is_401(self) -> None:
        self.assertStatus(401, webhook.parse_request, body_of(text="เปิดแอร์"), {}, SECRET)

    def test_empty_expected_secret_is_500_even_with_valid_body(self) -> None:
        self.assertStatus(500, webhook.parse_request, body_of(text="เปิดแอร์"), HEADERS, "")

    def test_auth_is_checked_before_the_body_is_touched(self) -> None:
        """JSON พัง + secret ผิด ต้องได้ 401 ไม่ใช่ 400

        ถ้าตอบ 400 แปลว่าเราแกะ body ของคนที่ยังไม่ยืนยันตัวตนแล้ว
        และยังบอกใบ้เขาด้วยว่า endpoint นี้คาดหวัง JSON แบบไหน
        """
        bad = {"X-Jarvis-Secret": "wrong"}
        self.assertStatus(401, webhook.parse_request, "{ไม่ใช่ JSON", bad, SECRET)

    def test_auth_is_checked_before_the_size_cap(self) -> None:
        bad = {"X-Jarvis-Secret": "wrong"}
        self.assertStatus(401, webhook.parse_request, "x" * 500_000, bad, SECRET)

    # --- body ที่ผิดรูป ----------------------------------------------------

    def test_malformed_json_is_400(self) -> None:
        for raw in ("{ไม่ใช่ JSON", "", "{'text': 'ก'}", '{"text": "ก"', "undefined"):
            with self.subTest(body=raw):
                self.assertStatus(400, webhook.parse_request, raw, HEADERS, SECRET)

    def test_json_that_is_not_an_object_is_400(self) -> None:
        """ถูกตามไวยากรณ์ JSON แต่ผิดสัญญา — list/ตัวเลข/สตริงเดี่ยว"""
        for raw in ('["ก"]', '"ก"', "123", "null", "true"):
            with self.subTest(body=raw):
                self.assertStatus(400, webhook.parse_request, raw, HEADERS, SECRET)

    def test_undecodable_bytes_are_400(self) -> None:
        """Shortcut ส่ง UTF-8 เสมอ อ่านไม่ออก = ไม่ใช่ของจาก Shortcut"""
        self.assertStatus(400, webhook.parse_request, b'{"text": "\xff\xfe"}', HEADERS, SECRET)

    def test_wrong_body_type_is_400(self) -> None:
        for raw in (None, 42, {"text": "ก"}):
            with self.subTest(body=raw):
                self.assertStatus(400, webhook.parse_request, raw, HEADERS, SECRET)

    # --- ข้อความคำสั่ง -----------------------------------------------------

    def test_missing_text_key_is_400(self) -> None:
        self.assertStatus(400, webhook.parse_request, body_of(source="siri"), HEADERS, SECRET)

    def test_empty_text_is_400(self) -> None:
        """Dictate Text ที่ไม่ได้ยินอะไรเลยจะส่ง "" มา — ต้องตัดจบตรงนี้

        ปล่อยผ่านแล้วชั้นบนจะเอาสตริงว่างไปให้ LLM ตีความ แล้วมันจะเดาคำสั่งขึ้นมาเอง
        ซึ่งอาจกลายเป็นการสั่งงานบ้านที่โอมไม่เคยพูด
        """
        self.assertStatus(400, webhook.parse_request, body_of(text=""), HEADERS, SECRET)

    def test_whitespace_only_text_is_400(self) -> None:
        for raw in ("   ", "\n", "\t\t", " \r\n ", " "):
            with self.subTest(text=repr(raw)):
                self.assertStatus(400, webhook.parse_request, body_of(text=raw), HEADERS, SECRET)

    def test_non_string_text_is_400(self) -> None:
        for value in (None, 123, ["ก"], {"v": "ก"}, True):
            with self.subTest(text=value):
                self.assertStatus(400, webhook.parse_request, body_of(text=value), HEADERS, SECRET)

    def test_text_at_the_limit_is_accepted(self) -> None:
        exact = "ก" * webhook.MAX_TEXT_LEN
        got = webhook.parse_request(body_of(text=exact), HEADERS, SECRET)
        self.assertEqual(webhook.MAX_TEXT_LEN, len(got["text"]))

    def test_text_one_over_the_limit_is_413(self) -> None:
        """นับเป็นตัวอักษร ไม่ใช่ไบต์ — ไทย 1 ตัว = 3 ไบต์ ถ้านับไบต์จะตัดที่ 666 ตัว

        โอมพูดยาวๆ ทีเดียวแล้วโดนตีกลับทั้งที่ยังไม่ถึงครึ่งเพดาน = บั๊กที่หาสาเหตุยาก
        """
        self.assertStatus(413, webhook.parse_request, body_of(text="ก" * 2001), HEADERS, SECRET)
        self.assertStatus(413, webhook.parse_request, body_of(text="a" * 2001), HEADERS, SECRET)

    def test_length_is_measured_after_trimming(self) -> None:
        padded = " " * 500 + "ก" * webhook.MAX_TEXT_LEN + " " * 500
        got = webhook.parse_request(body_of(text=padded), HEADERS, SECRET)
        self.assertEqual(webhook.MAX_TEXT_LEN, len(got["text"]))

    def test_oversized_raw_body_is_413(self) -> None:
        """กันก้อนใหญ่ตั้งแต่ยังไม่แกะ JSON — ไม่ต้องเสียแรงแกะของที่จะทิ้งอยู่แล้ว"""
        huge = "x" * (webhook.MAX_BODY_BYTES + 1)
        self.assertStatus(413, webhook.parse_request, huge, HEADERS, SECRET)
        self.assertStatus(413, webhook.parse_request, huge.encode(), HEADERS, SECRET)


# --------------------------------------------------------------------------
# 4. build_response — คีย์ 'speak' ต้องมีเสมอ
# --------------------------------------------------------------------------


class BuildResponseTest(WebhookTestBase):
    def test_ok_response_has_speak(self) -> None:
        got = webhook.build_response("เปิดไฟให้แล้วครับ")
        self.assertEqual("เปิดไฟให้แล้วครับ", got["speak"])
        self.assertTrue(got["ok"])

    def test_error_response_has_speak(self) -> None:
        """ตอนพลาดยิ่งต้องมีเสียง — ผิดแล้วบอกว่าผิด ดีกว่าเงียบให้เดาเอง"""
        got = webhook.build_response("จองไม่สำเร็จครับ ร้านไม่รับสาย", ok=False)
        self.assertIn("speak", got)
        self.assertEqual("จองไม่สำเร็จครับ ร้านไม่รับสาย", got["speak"])
        self.assertFalse(got["ok"])

    def test_speak_is_never_empty(self) -> None:
        """Speak Text ที่ได้ค่าว่างจะเงียบสนิท ซึ่งแยกไม่ออกจากระบบตาย"""
        for reply in ("", "   ", "\n", None):
            for ok in (True, False):
                with self.subTest(reply=repr(reply), ok=ok):
                    got = webhook.build_response(reply, ok=ok)
                    self.assertTrue(got["speak"].strip(), "คีย์ speak ต้องมีเสียงเสมอ")

    def test_fallback_text_differs_between_ok_and_error(self) -> None:
        """เงียบไม่ได้ และพูดเหมือนกันทั้งสำเร็จ/ไม่สำเร็จก็ไม่ได้ — โอมต้องแยกออกด้วยหู"""
        self.assertNotEqual(
            webhook.build_response("", ok=True)["speak"],
            webhook.build_response("", ok=False)["speak"],
        )

    def test_reply_mirrors_speak_for_text_only_channels(self) -> None:
        got = webhook.build_response("  พรุ่งนี้เรียนคณิตคาบแรกครับ  ")
        self.assertEqual(got["speak"], got["reply"])

    def test_response_is_json_serializable(self) -> None:
        """ชั้นโฮสต์ต้อง dump เป็น JSON ส่งกลับได้เลย ไม่ต้องแปลงอะไรเพิ่ม"""
        payload = json.loads(json.dumps(webhook.build_response("ทดสอบครับ"), ensure_ascii=False))
        self.assertEqual("ทดสอบครับ", payload["speak"])

    def test_every_rejection_path_still_speaks(self) -> None:
        """ไล่ทุกทางที่ endpoint ตีกลับ แล้วยืนยันว่าแปลงเป็นคำตอบที่มีเสียงได้ทุกทาง

        นี่คือเทสต์ที่กันอาการ "ยิงคำสั่งไปแล้ว Siri เงียบ" ซึ่งเป็นบั๊กที่โอมจะเจอ
        ตอนกำลังขับรถหรือกำลังรีบ แล้วไม่มีทางรู้ว่าเกิดอะไรขึ้น
        """
        cases = [
            ("secret ผิด", body_of(text="ก"), {"X-Jarvis-Secret": "no"}, SECRET, 401),
            ("ไม่มี header", body_of(text="ก"), {}, SECRET, 401),
            ("เซิร์ฟเวอร์ลืมตั้ง secret", body_of(text="ก"), HEADERS, "", 500),
            ("JSON พัง", "{พัง", HEADERS, SECRET, 400),
            ("ข้อความว่าง", body_of(text="   "), HEADERS, SECRET, 400),
            ("ยาวเกิน", body_of(text="ก" * 2001), HEADERS, SECRET, 413),
        ]
        for label, body, headers, secret, status in cases:
            with self.subTest(case=label):
                err = self.assertStatus(status, webhook.parse_request, body, headers, secret)
                spoken = webhook.build_response(err.message, ok=False)
                self.assertTrue(spoken["speak"].strip())
                self.assertFalse(spoken["ok"])
                self.assertEqual(status, webhook.error_response(err)["status"])
                self.assertTrue(webhook.error_response(err)["speak"].strip())


class WebhookErrorTest(unittest.TestCase):
    def test_carries_status_and_message(self) -> None:
        err = WebhookError(418, "ยังไม่พร้อมครับ")
        self.assertEqual(418, err.status)
        self.assertEqual("ยังไม่พร้อมครับ", err.message)
        self.assertEqual("ยังไม่พร้อมครับ", str(err))

    def test_is_catchable_as_exception(self) -> None:
        with self.assertRaises(Exception):
            raise WebhookError(400, "พัง")


if __name__ == "__main__":
    unittest.main(verbosity=2)
