"""
ตัวเชื่อมระบบบัญชี scaccouting.com — อ่านอย่างเดียว

⚠️ นี่คือโมดูลที่อันตรายที่สุดในระบบทั้งหมด อ่าน red-team H11 ก่อนแก้อะไรในไฟล์นี้:

    "Jarvis ถือ token ที่มีสิทธิ์ manager เต็มของระบบบัญชี = ถ้า VPS ถูกเจาะ
     ผู้บุกรุกได้สิทธิ์เข้าถึงข้อมูลการเงินของลูกค้าบริษัทจริง
     นี่ไม่ใช่ข้อมูลส่วนตัวของเราคนเดียว แต่เป็นข้อมูลลูกค้าคนอื่น"

ข้อบังคับ 3 ข้อจาก H11 ที่บังคับไว้ในโค้ดนี้ ไม่ใช่แค่เขียนไว้ใน prompt:
  1. whitelist เฉพาะ GET endpoint ที่ระบุชื่อไว้ — เมธอดอื่นและ path นอกลิสต์ = ปฏิเสธ
  2. ทุก request ลง audit_log
  3. เงิน _satang หาร 100 ก่อนแสดง (ไม่งั้นตัวเลขผิด 100 เท่า)

บุคลิกข้อ "ขอบเขต" ย้ำอีกชั้น:
  "ระบบบัญชีบริษัท: อ่านอย่างเดียว ห้ามแก้ไข อนุมัติ หรือลบอะไรทั้งสิ้น
   ไม่ว่าจะถูกสั่งหรือไม่"
→ โมดูลนี้จึงไม่มีฟังก์ชันเขียนเลยแม้แต่ตัวเดียว ไม่ใช่แค่ไม่เรียกใช้

สถานะ: โครงสร้างและด่านความปลอดภัยพร้อมแล้ว ตัวยิง HTTP จริงยังไม่ต่อ
(Phase 2 ค่อยต่อ พร้อม LINE Login OAuth) — ดู `_transport` ท้ายไฟล์
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Callable, Mapping

# --- whitelist ---------------------------------------------------------------
# spec v3 Phase 2 ข้อ 3 ระบุ endpoint ที่อนุญาตไว้ 9 ตัว คัดมาตรงๆ
# เพิ่มเข้าลิสต์นี้ = ขยายสิทธิ์ที่ Jarvis มีต่อข้อมูลลูกค้าบริษัท
# ต้องคิดให้จบก่อนเพิ่ม และเพิ่มได้เฉพาะ endpoint ที่เป็น GET เท่านั้น
ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    "tasks",
    "work-plans",
    "monthly-control-cards",
    "vat-audits",
    "pnd51",
    "wht-certificates",
    "billing",
    "documents",
    "receipts",
})

# path ต้องเป็น <endpoint> หรือ <endpoint>/<id ที่เป็นตัวเลขหรือ slug ปลอดภัย>
# กัน path traversal ('../') และ query string แอบแฝง
_PATH_RE = re.compile(r"^(?P<endpoint>[a-z0-9-]+)(?:/(?P<ident>[A-Za-z0-9_-]{1,64}))?$")

AUDIT_TARGET = "scaccounting"


class ForbiddenRequest(PermissionError):
    """คำขอที่ด่านความปลอดภัยปฏิเสธ — อย่าจับ exception นี้แล้วลองใหม่

    ถ้าเห็น exception นี้แปลว่ามีอะไรพยายามทำสิ่งที่ระบบตั้งใจไม่ให้ทำ
    ซึ่งควรดังจนมีคนเห็น ไม่ใช่เงียบแล้วข้ามไป
    """


def _audit(conn: sqlite3.Connection, action: str, detail: str | None = None) -> None:
    """บันทึกทุก request ลง audit_log — H11 ข้อ 2

    บันทึก "ก่อน" ยิงจริงเสมอ ไม่ใช่หลัง เพราะถ้ายิงแล้ว process ตายกลางคัน
    เราจะไม่มีร่องรอยเลยว่าเคยยิงอะไรออกไป
    """
    conn.execute(
        "INSERT INTO audit_log (target, action, detail) VALUES (?, ?, ?)",
        (AUDIT_TARGET, action, detail),
    )
    conn.commit()


def check_request(method: str, path: str) -> str:
    """ด่านความปลอดภัย — ผ่านแล้วคืนชื่อ endpoint ไม่ผ่านโยน ForbiddenRequest

    แยกออกมาเป็นฟังก์ชันเดี่ยวเพื่อให้เทสต์ยิงตรงได้โดยไม่ต้องมี DB หรือเน็ต
    """
    if method.upper() != "GET":
        raise ForbiddenRequest(
            f"อนุญาตเฉพาะ GET — ปฏิเสธ {method.upper()} (ระบบบัญชีเป็นแบบอ่านอย่างเดียว)"
        )
    cleaned = path.strip().strip("/")
    if not cleaned:
        raise ForbiddenRequest("path ว่างเปล่า")
    if "?" in cleaned or "#" in cleaned or ".." in cleaned or "//" in cleaned:
        raise ForbiddenRequest(f"path มีอักขระที่ไม่อนุญาต: {path!r}")
    match = _PATH_RE.match(cleaned)
    if match is None:
        raise ForbiddenRequest(f"รูปแบบ path ไม่ถูกต้อง: {path!r}")
    endpoint = match.group("endpoint")
    if endpoint not in ALLOWED_ENDPOINTS:
        raise ForbiddenRequest(
            f"endpoint '{endpoint}' ไม่อยู่ใน whitelist\n"
            f"ที่อนุญาต: {', '.join(sorted(ALLOWED_ENDPOINTS))}"
        )
    return endpoint


def satang_to_baht(value: int | float | None) -> float | None:
    """แปลงสตางค์เป็นบาท — spec: 'เงิน _satang หาร 100 ก่อนแสดง'

    ลืมข้อนี้ = ตัวเลขเงินผิด 100 เท่าในทุกที่ที่แสดง
    """
    if value is None:
        return None
    return round(value / 100, 2)


def normalize_money(payload: Any) -> Any:
    """ไล่หา key ที่ลงท้าย _satang ทั้ง payload แล้วเพิ่ม key คู่กันเป็นบาท

    เก็บ key เดิมไว้ด้วยเพื่อให้ตรวจย้อนได้ว่าค่าดิบคืออะไร
    เดินลง dict/list ซ้อนกันได้ เพราะ payload จริงมักซ้อนหลายชั้น
    """
    if isinstance(payload, list):
        return [normalize_money(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    out: dict[str, Any] = {}
    for key, value in payload.items():
        out[key] = normalize_money(value)
        if key.endswith("_satang") and isinstance(value, (int, float)):
            out[f"{key[:-len('_satang')]}_baht"] = satang_to_baht(value)
    return out


# ตัวยิง HTTP จริง — Phase 2 ค่อยใส่ ตอนนี้เป็น None เพื่อให้เทสต์ฉีดตัวปลอมเข้ามาได้
# แยกออกมาแบบนี้ทำให้ทดสอบด่านความปลอดภัยได้ครบโดยไม่ต้องมีเน็ตหรือ token จริง
Transport = Callable[[str, Mapping[str, str]], Any]


def fetch(
    conn: sqlite3.Connection,
    path: str,
    *,
    method: str = "GET",
    params: Mapping[str, str] | None = None,
    transport: Transport | None = None,
) -> Any:
    """ดึงข้อมูลจากระบบบัญชี ผ่านด่านความปลอดภัยและบันทึก audit ทุกครั้ง

    transport=None → ยก NotImplementedError (Phase 2 ค่อยต่อของจริง)
    จงใจให้ระเบิดมากกว่าคืนข้อมูลปลอม เพราะข้อมูลบัญชีปลอมอันตรายกว่าไม่มีข้อมูล
    """
    params = dict(params or {})
    # ตรวจก่อนบันทึก: คำขอที่ถูกปฏิเสธก็ต้องมีร่องรอย แต่ต้องรู้ก่อนว่าปฏิเสธเพราะอะไร
    try:
        endpoint = check_request(method, path)
    except ForbiddenRequest as exc:
        _audit(conn, f"{method.upper()} {path}", f"ปฏิเสธ: {exc}")
        raise
    _audit(conn, f"GET {path}", json.dumps(params, ensure_ascii=False) if params else None)
    if transport is None:
        raise NotImplementedError(
            f"ยังไม่ได้ต่อ transport จริงสำหรับ '{endpoint}' — Phase 2 ค่อยทำ "
            f"(ต้องมี LINE Login OAuth + refresh token ใน secret store ก่อน)"
        )
    return normalize_money(transport(path, params))
