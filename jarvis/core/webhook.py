"""
รับคำสั่งเสียงจาก Siri Shortcut — red-team PART 2.5 ("แก้ H1") + spec v3 Phase 2 ข้อ 1

ฝั่งมือถือไม่มีโค้ดเลย เป็น Shortcut 3 action ตาม red-team:
    Dictate Text → Get Contents of URL (POST, JSON body, custom headers) → Speak Text
ต้นทุน ฿0 ไม่ต้องสร้างแอป ไม่ต้องสมัคร Apple Developer Program
ของทั้งหมดที่ต้องเขียนจึงเหลือแค่ฝั่ง VPS คือไฟล์นี้

ทำไมไฟล์นี้ไม่ผูกพอร์ตและไม่ import web framework:
    CONTRACTS.md ข้อแรก — core/ ต้องย้ายไป Track B ได้ทันทีถ้า gate trial ของ Hermes ไม่ผ่าน
    ถ้าผูกกับ framework ไหนไว้ วันที่ต้องย้ายจะต้องรื้อตรรกะความปลอดภัยตามไปด้วย
    ไฟล์นี้จึงเป็น "ตรรกะล้วน": แกะ → ตรวจ → คืน dict ให้ชั้นนอกเอาไปตอบเอง
    ผลพลอยได้คือเทสต์รันได้โดยไม่ต้องเปิดพอร์ต ไม่ต้องมี API key ไม่ต้องต่อเน็ต

ทำไมไม่มีพารามิเตอร์ `clock`:
    กฎเหล็กข้อ 1 บังคับเฉพาะฟังก์ชันที่แตะเวลา ไฟล์นี้ไม่แตะเวลาเลยสักจุด
    (ไม่มี timestamp ในค่าที่คืน) จึงไม่มีอะไรให้ฉีด — และห้ามแอบเรียก datetime.now()
    เข้ามาภายหลัง ถ้าวันหน้าต้องบันทึกเวลาที่รับคำสั่ง ให้ผู้เรียกดึงจาก core.localdate
    แล้วส่งลงมา ไม่ใช่ให้ไฟล์นี้ไปถามนาฬิกาเครื่องเอง

ภัยที่ไฟล์นี้ยืนรับอยู่คนเดียว:
    endpoint นี้เปิดสู่อินเทอร์เน็ตสาธารณะ ใครก็ยิงเข้ามาได้ ไม่มีชั้นอื่นกันให้
    ใครเดา secret ถูก = สั่งบ้าน สั่งจอง อ่านความจำได้ทั้งหมด
    บรรทัดที่สำคัญที่สุดของโมดูลคือ hmac.compare_digest() ใน verify_secret()
"""

from __future__ import annotations

import hmac
import json
from typing import Any

# ชื่อ header ที่ตั้งใน action "Get Contents of URL" ของ Shortcut
# ประกาศไว้ที่เดียวเพื่อให้เอกสาร setup กับโค้ดอ้างตัวเดียวกัน พิมพ์ผิดแล้วจะรู้ทันที
SECRET_HEADER = "X-Jarvis-Secret"

# ค่าสูงสุดของข้อความที่รับ — Dictate Text พูดรวดเดียวไม่มีทางถึง 2000 ตัวอักษร
# อะไรที่ยาวกว่านี้แปลว่าไม่ใช่เสียงพูดของโอม (สคริปต์ยิงมั่ว / พยายามถล่มระบบ)
MAX_TEXT_LEN = 2000

# เพดานของ body ดิบก่อนแกะ JSON — กันไม่ให้ต้องแกะก้อนใหญ่ๆ ทิ้งเปล่า
# ภาษาไทย 1 ตัวอักษร = 3 ไบต์ใน UTF-8 บวกการ escape ของ JSON อีก จึงเผื่อไว้ 8 เท่า
# เผื่อมากกว่าที่ควรดีกว่าตัดข้อความจริงของโอมทิ้งเพราะคำนวณพลาด
MAX_BODY_BYTES = MAX_TEXT_LEN * 8

# ต้นทางของคำสั่ง — ไม่ระบุมาถือว่ามาจาก Siri เพราะนั่นคือทางเข้าหลักตาม red-team
# ฝั่ง Android (Google Assistant routine) ให้ส่ง source มาเองเป็น 'android'
DEFAULT_SOURCE = "siri"

# ชื่อ source ยาวเกินนี้ไม่ใช่ชื่อช่องทาง แต่เป็นขยะที่จะไปโผล่ใน log
MAX_SOURCE_LEN = 32

# secret ที่ยัง "ไม่ได้กรอกจริง" — ล้อค่าเดียวกับ db.PLACEHOLDERS
# ไม่ import db เข้ามาเพราะไฟล์นี้ไม่แตะ DB เลย การผูกกันไว้จะทำให้ย้ายไปโฮสต์ที่อื่นยากขึ้น
_PLACEHOLDER_SECRETS = frozenset({"[ต้องกรอก]", "[TODO]", "TODO", "None", "null", "changeme"})

# ค่าที่เอาไว้เทียบตอนไม่มี header ส่งมา — ให้เส้นทาง "ไม่มี header" กับ "secret ผิด"
# ใช้เวลาใกล้เคียงกัน จะได้ไม่บอกใบ้ผู้โจมตีว่าเดาถูกครึ่งทางแล้ว
_DUMMY_SECRET = "0" * 64

# ข้อความสำรองตอนไม่มีคำตอบให้พูด — Speak Text ที่ได้ค่าว่างจะเงียบสนิท
# ซึ่งแยกไม่ออกจาก "ระบบล่ม" เลยต้องมีเสียงออกเสมอ (บุคลิก: ไม่สำเร็จต้องบอกว่าไม่สำเร็จ)
FALLBACK_SPEAK_OK = "รับคำสั่งแล้วครับ แต่ยังไม่มีคำตอบกลับมา"
FALLBACK_SPEAK_ERROR = "ขอโทษครับ มีบางอย่างผิดพลาด"


class WebhookError(Exception):
    """ข้อผิดพลาดที่แปลงเป็น HTTP status ได้ตรงๆ

    message ถูกเขียนให้ "พูดออกเสียงแล้วรู้เรื่อง" เพราะมันจะไปโผล่ในคีย์ 'speak'
    ที่ Siri อ่านให้ฟัง ไม่ใช่ stack trace ที่ต้องเปิดจอดู

    ห้ามใส่ค่า secret (ทั้งตัวจริงและตัวที่ส่งมา) ลงใน message เด็ดขาด
    ข้อความ error ของ endpoint สาธารณะ = สิ่งที่ผู้โจมตีอ่านได้ฟรีทุกครั้งที่ยิง
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _header_value(headers: dict, name: str) -> str | None:
    """ดึงค่า header แบบไม่สนตัวพิมพ์ใหญ่เล็ก

    RFC บอกว่าชื่อ header ไม่สนตัวพิมพ์ และของจริงก็แปลงร่างระหว่างทางเสมอ:
    Shortcuts ส่ง 'X-Jarvis-Secret', nginx/uvicorn ส่งต่อเป็น 'x-jarvis-secret',
    WSGI แปลงเป็น 'HTTP_X_JARVIS_SECRET' ถ้าเทียบชื่อแบบตรงตัวจะกลายเป็น 401
    ทุกครั้งที่เปลี่ยน reverse proxy — แล้วจะไปไล่หาสาเหตุผิดจุดว่า secret ตั้งผิด
    """
    if not isinstance(headers, dict):
        return None
    wanted = name.lower()
    # รองรับรูปแบบ WSGI ด้วย เพราะชั้นโฮสต์อาจเป็น http.server ธรรมดา
    wanted_wsgi = "http_" + wanted.replace("-", "_")
    for key, value in headers.items():
        if not isinstance(key, str):
            continue
        normalized = key.lower()
        if normalized != wanted and normalized != wanted_wsgi:
            continue
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return None
        if isinstance(value, str):
            return value
        # ค่าที่ไม่ใช่ข้อความ (list จาก framework บางตัว, None) ถือว่าไม่มี header
        return None
    return None


def verify_secret(headers: dict, expected: str) -> None:
    """ตรวจ header ยืนยันตัวตน — ผ่านแล้วคืน None เฉยๆ ไม่ผ่านโยน WebhookError

    บรรทัดที่สำคัญที่สุดของทั้งโมดูลอยู่ในฟังก์ชันนี้: hmac.compare_digest
    การเทียบสตริงแบบปกติของ Python จะหยุดทันทีที่เจอไบต์แรกที่ต่างกัน
    เวลาที่ใช้จึงแปรตามจำนวนไบต์แรกที่เดาถูก ผู้โจมตีวัดเวลาตอบกลับซ้ำๆ
    แล้วไล่เดาทีละตัวอักษรได้ — เปลี่ยนงานระดับ "เดา 62^32 แบบ" ให้เหลือ "เดา 62x32 ครั้ง"
    compare_digest ใช้เวลาคงที่ไม่ว่าจะต่างกันตรงไหน จึงไม่มีข้อมูลให้วัด

    expected ว่าง → 500 ไม่ใช่ 401 เพราะนี่คือความผิดของฝั่งเซิร์ฟเวอร์ (ลืมตั้งค่า)
    ไม่ใช่ความผิดของผู้เรียก — และที่สำคัญกว่าคือมันต้อง **ปิดประตู** ไม่ใช่เปิด
    ถ้าปล่อยให้ expected ว่างไหลไปเทียบต่อ ใครส่ง header ว่างมาก็จะผ่านหมดทั้งอินเทอร์เน็ต
    """
    provided = _header_value(headers, SECRET_HEADER)

    expected_text = expected if isinstance(expected, str) else ""
    # ยังไม่ได้ตั้ง secret จริง = ล้มแบบปิดประตู ห้ามเดาว่า "คงไม่เป็นไร"
    if not expected_text.strip() or expected_text.strip() in _PLACEHOLDER_SECRETS:
        raise WebhookError(500, "เซิร์ฟเวอร์ยังไม่ได้ตั้งรหัสยืนยันตัวตน ยังรับคำสั่งไม่ได้ครับ")

    # ไม่มี header ก็ยังเทียบกับค่าหลอกให้ครบรอบ เพื่อไม่ให้เวลาตอบกลับต่างจากกรณี secret ผิด
    candidate = provided if provided is not None else _DUMMY_SECRET

    # เทียบเป็นไบต์ ไม่ใช่ str เพราะ compare_digest แบบ str รับได้เฉพาะ ASCII
    # secret ที่มีอักขระไทยหรือสัญลักษณ์พิเศษจะทำให้มันโยน TypeError ทิ้งกลางทาง
    matched = hmac.compare_digest(
        candidate.encode("utf-8", "surrogatepass"),
        expected_text.encode("utf-8", "surrogatepass"),
    )
    if provided is None or not matched:
        # ข้อความเดียวกันทั้งสองกรณี ไม่บอกว่า "ไม่มี header" หรือ "ค่าผิด"
        # เพราะการบอกว่าพลาดตรงไหนคือการช่วยผู้โจมตีตัดตัวเลือกให้แคบลง
        raise WebhookError(401, "รหัสยืนยันตัวตนไม่ถูกต้องครับ")


def _decode_body(body: bytes | str) -> str:
    """แปลง body เป็นข้อความ พร้อมกันก้อนใหญ่เกินเหตุตั้งแต่ยังไม่แกะ"""
    if isinstance(body, (bytes, bytearray, memoryview)):
        raw = bytes(body)
        if len(raw) > MAX_BODY_BYTES:
            raise WebhookError(413, "คำสั่งยาวเกินไปครับ ลองพูดสั้นลง")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            # Shortcuts ส่ง JSON เป็น UTF-8 เสมอ อ่านไม่ออก = ไม่ใช่ของจาก Shortcut
            raise WebhookError(400, "อ่านข้อมูลที่ส่งมาไม่ออกครับ") from exc
    if isinstance(body, str):
        if len(body.encode("utf-8", "surrogatepass")) > MAX_BODY_BYTES:
            raise WebhookError(413, "คำสั่งยาวเกินไปครับ ลองพูดสั้นลง")
        return body
    raise WebhookError(400, "รูปแบบข้อมูลที่ส่งมาไม่ถูกต้องครับ")


def _extract_text(payload: dict[str, Any]) -> str:
    """ดึงคีย์ 'text' ออกมาและตรวจว่าใช้งานได้จริง

    เคสที่เกิดจริงและต้องกันให้ได้: Dictate Text ไม่ได้ยินอะไรเลยแล้วส่ง "" มา
    ถ้าปล่อยผ่าน ชั้นบนจะเอาสตริงว่างไปให้ LLM ตีความ แล้วมันจะ "เดา" คำสั่งขึ้นมาเอง
    ซึ่งอาจกลายเป็นการสั่งงานบ้านที่โอมไม่เคยพูด — ต้องตัดจบตรงนี้
    """
    if "text" not in payload:
        raise WebhookError(400, "ไม่มีข้อความคำสั่งส่งมาครับ")
    value = payload["text"]
    if not isinstance(value, str):
        raise WebhookError(400, "ข้อความคำสั่งต้องเป็นข้อความครับ")
    text = value.strip()
    if not text:
        # เว้นวรรค/ขึ้นบรรทัดล้วนๆ นับเป็นว่างเหมือนกัน ไม่ใช่คำสั่งที่ยาว 5 ตัวอักษร
        raise WebhookError(400, "ไม่ได้ยินคำสั่งครับ ลองพูดใหม่อีกครั้ง")
    if len(text) > MAX_TEXT_LEN:
        raise WebhookError(413, "คำสั่งยาวเกินไปครับ ลองพูดสั้นลง")
    return text


def _extract_source(payload: dict[str, Any]) -> str:
    """ต้นทางของคำสั่ง — ไม่ส่งมาถือว่าเป็น Siri"""
    if "source" not in payload or payload["source"] is None:
        return DEFAULT_SOURCE
    value = payload["source"]
    if not isinstance(value, str):
        raise WebhookError(400, "ชื่อต้นทางไม่ถูกต้องครับ")
    source = value.strip()
    if not source:
        return DEFAULT_SOURCE
    if len(source) > MAX_SOURCE_LEN:
        # ไม่ตัดให้สั้นเงียบๆ เพราะ source ที่ถูกตัดจะไปนั่งอยู่ใน log แบบดูเหมือนถูกต้อง
        raise WebhookError(400, "ชื่อต้นทางยาวเกินไปครับ")
    return source


def parse_request(body: bytes | str, headers: dict, secret: str) -> dict:
    """แกะ POST จาก Shortcut → {'text': ..., 'source': ...}

    ลำดับการตรวจตั้งใจให้ยืนยันตัวตน **ก่อน** แตะ body เลยแม้แต่ไบต์เดียว
    คนที่ไม่มี secret ไม่ควรได้รับข้อมูลใดๆ กลับไป แม้แต่ข้อมูลว่า "JSON ของแกพัง"
    เพราะข้อความ error ที่ต่างกันคือช่องให้ลองยิงหาโครงสร้างของ endpoint

    body มาจาก action 'Get Contents of URL' ที่ตั้ง Request Body = JSON
    รูปแบบ: {"text": "<ผลจาก Dictate Text>"}  (จะใส่ "source" มาด้วยก็ได้)
    """
    verify_secret(headers, secret)

    text_body = _decode_body(body)
    try:
        payload = json.loads(text_body)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise WebhookError(400, "ข้อมูลที่ส่งมาไม่ใช่ JSON ที่อ่านได้ครับ") from exc

    if not isinstance(payload, dict):
        # JSON ที่ถูกต้องแต่เป็น list/ตัวเลข/สตริง — ถูกตามไวยากรณ์ แต่ผิดสัญญา
        raise WebhookError(400, "รูปแบบข้อมูลที่ส่งมาไม่ถูกต้องครับ")

    return {"text": _extract_text(payload), "source": _extract_source(payload)}


def build_response(reply: str, *, ok: bool = True) -> dict:
    """สร้างคำตอบให้ Shortcut — คีย์ 'speak' ต้องมีเสมอทุกกรณี

    action 'Speak Text' ของ Shortcut ถูกตั้งให้อ่านค่าจากคีย์ 'speak' ตัวเดียว
    ถ้าคีย์นี้หายไปหรือเป็นค่าว่าง โอมจะได้ยิน "ความเงียบ" ซึ่งแยกไม่ออกเลยว่า
    ระบบทำงานสำเร็จแบบไม่มีอะไรจะพูด หรือระบบตายไปแล้ว
    ตอนพลาดยิ่งต้องมีเสียง — ผิดแล้วบอกว่าผิดดีกว่าเงียบให้เดาเอง
    """
    if isinstance(reply, str):
        spoken = reply.strip()
    elif reply is None:
        spoken = ""
    else:
        spoken = str(reply).strip()

    if not spoken:
        spoken = FALLBACK_SPEAK_OK if ok else FALLBACK_SPEAK_ERROR

    # 'reply' ซ้ำกับ 'speak' ไว้ให้ช่องทางที่อ่านอย่างเดียว (Show Result / log) ใช้
    # โดยไม่ต้องรู้ว่าคีย์สำหรับเสียงชื่ออะไร
    return {"ok": bool(ok), "speak": spoken, "reply": spoken}


def error_response(error: WebhookError) -> dict:
    """แปลง WebhookError เป็นคำตอบพร้อมส่ง — ชั้นโฮสต์เอา 'status' ไปตั้งเป็น HTTP status

    มีไว้เพื่อไม่ให้แต่ละที่ที่โฮสต์ endpoint นี้ (Hermes หรือเซิร์ฟเวอร์เดี่ยว)
    ต้องเขียนตรรกะ "อย่าลืมใส่ speak ตอน error" ซ้ำเอง — ลืมที่ไหนที่นั่นเงียบ
    """
    payload = build_response(error.message, ok=False)
    payload["status"] = error.status
    return payload
