"""
ดึงข้อมูล API ภายนอกมาเสริม digest เช้า — spec v3 Phase 1 ข้อ 7

4 แหล่งตาม red-team สถานการณ์ 1 (cron 06:20):
    Google Routes   → หอ→โรงเรียน ตอนนี้ใช้กี่นาที (+ ควรออกกี่โมง)
    Longdo Weather  → ฝนตกช่วงเช้าไหม / อุณหภูมิ
    Air4Thai        → ค่าฝุ่นเชียงใหม่เช้านี้
    Google Calendar → วันนี้มีนัดอะไร

ทำไมทุก provider ต้อง "ล้มเงียบ" (checklist E2):
    digest เช้าคือของที่ต้องมาถึง 7 วันติดไม่ขาด (checklist A ข้อแรก)
    API ภายนอก 4 ตัวล่มกันคนละวันแน่นอน ถ้าตัวเดียวพาทั้งก้อนพัง
    โอมจะตื่นมาเจอความเงียบ ซึ่งแยกไม่ออกจากระบบตายทั้งระบบ
    → exception ของ provider ไหนถูกจับ log ลง stderr แล้วข้ามคีย์นั้นไปเฉยๆ
    renderer (digest.py) ออกแบบให้ "หัวข้อหายทั้งบรรทัด" เมื่อไม่มีคีย์อยู่แล้ว

ทำไม transport ฉีดได้:
    กฎเหล็กข้อ 2 — เทสต์ต้องรันออฟไลน์โดยไม่มี API key
    urllib จริงอยู่ใน _default_transport ที่เดียว และถูกเรียกเฉพาะตอน
    transport=None เท่านั้น เทสต์ทุกตัวฉีดตัวปลอมเข้ามาแทน

ทำไม parser แยกเป็นฟังก์ชันเล็กต่อ API:
    เราเขียน shape ของ response จากเอกสารสาธารณะโดยยังไม่ได้ยิงของจริง
    (เครื่อง dev ออกเน็ตไม่ได้) วันที่ต่อจริงแล้ว shape ไม่ตรง ต้องแก้ได้
    โดยแตะฟังก์ชันเดียวจบ ไม่ลามไปทั้งไฟล์
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, time, timedelta
from typing import Any

from . import localdate
from .db import PLACEHOLDERS

__all__ = [
    "Transport", "fetch_extras", "BUFFER_MINUTES", "ROUND_TO_MINUTES",
    "MIN_ROUTING_DISTANCE_M",
]

# สัญญาที่ตรึงไว้ใน CONTRACTS.md งวดที่ 2 — (url, params) -> parsed JSON
Transport = Callable[[str, Mapping[str, str]], Any]

# --- ค่าคงที่ ----------------------------------------------------------------

# เผื่อเวลา 10 นาทีระหว่าง "เวลาขับตามแผนที่" กับ "ถึงจริง":
# Routes บอกเวลารถถึงหน้าประตู แต่ไม่รวมลงจากรถ เดินเข้าแถว และรถติดสะสม
# หน้าโรงเรียนมงฟอร์ตช่วง 07:20-07:40 ที่แกว่งวันต่อวัน — ข้อความบอกว่า
# "ออก HH:MM ถึงสบายๆ" (kit หลักการข้อ 6) จึงต้องเผื่อให้ "สบายๆ" เป็นจริง
BUFFER_MINUTES = 10

# ใกล้กว่านี้ = ไม่ต้องถาม API เรื่องเวลาเดินทางเลย
# หอกับโรงเรียนของโอมห่างกัน 165 เมตร (เดิน 2 นาที) การยิง Distance Matrix
# ทุกเช้าเพื่อได้คำตอบว่า "1 นาที" คือเสียเงินและเสียเวลาเปล่า
# เช็คระยะตรงจากพิกัดก่อน (ฟรี ไม่ต้องต่อเน็ต) แล้วค่อยตัดสินใจว่าจะยิงไหม
# ผลพลอยได้ที่สำคัญ: Phase 1 ไม่ต้องใช้ GOOGLE_MAPS_API_KEY อีกต่อไป
# ถ้าวันหน้าโอมย้ายหอ พิกัดเปลี่ยน ระบบจะกลับมายิง API เองโดยไม่ต้องแก้โค้ด
MIN_ROUTING_DISTANCE_M = 1000

# ปัดเวลาออกให้เป็นเลขกลมๆ — ดู _leave_by() ว่าทำไม
ROUND_TO_MINUTES = 5

# หน้าต่างเช้าที่สนใจเรื่องฝน: ออกจากหอ ~07:1x ถึงเข้าแถว 08:20
# ขยับขอบมาที่ 06:00-09:00 เผื่อฝนมาก่อน/ลากยาว (red-team ดู 07:00-07:40)
MORNING_START_HOUR = 6
MORNING_END_HOUR = 9

# ปริมาณ/ความน่าจะเป็นฝนที่ถือว่า "ตก" — ต่ำกว่านี้คือละอองที่ไม่ต้องพกร่ม
# ⚠️ หน่วยจริงของ field 'rain' ของ Longdo ยังไม่ยืนยัน — ปรับตอนต่อจริง
RAIN_THRESHOLD = 0.1

# พิกัดย่านหอพัก/โรงเรียนมงฟอร์ต เชียงใหม่ — Longdo ต้องการ lat/lon ไม่รับที่อยู่
# ความละเอียดระดับตำบลพอ เพราะพยากรณ์ฝนหยาบกว่านั้นมาก
LONGDO_LAT = "18.78"
LONGDO_LON = "99.00"

# Air4Thai รายงานทั้งประเทศ — กรองเฉพาะสถานีเชียงใหม่ (spec Phase 1 ข้อ 7)
AIR4THAI_PROVINCE = "เชียงใหม่"

# Routes API v2 ตัวจริงเป็น POST + field-mask header ซึ่งไม่เข้ากับสัญญา
# Transport (url, params) ที่ตรึงไว้ — ใช้ Distance Matrix (ตระกูล Routes เดิม
# แบบ GET) ที่ให้ duration_in_traffic เหมือนกัน คีย์ API ตัวเดียวกันใช้ได้
GOOGLE_ROUTES_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
LONGDO_FORECAST_URL = "https://api.longdo.com/weather/json/forecast/hourly"
AIR4THAI_URL = "http://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
GOOGLE_CALENDAR_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

DEFAULT_TIMEOUT_SECONDS = 10.0


# --- ตัวช่วยกลาง --------------------------------------------------------------


def _warn(provider: str, problem: object) -> None:
    """log ลง stderr แล้วไปต่อ — stdout เป็นของ digest ห้ามมีอะไรปน

    (cli digest ส่ง stdout เข้า Telegram ทั้งก้อน ถ้า log หลุดไป stdout
    ข้อความเช้าจะมี traceback โผล่ให้โอมอ่าน)
    """
    print(f"[fetchers] {provider}: ข้าม — {problem}", file=sys.stderr)


def _pref(prefs: Mapping[str, str], key: str) -> str | None:
    """อ่าน preference แบบไม่ระเบิด — ค่า placeholder ('[ต้องกรอก]') = ไม่มี

    ใช้ชุด PLACEHOLDERS เดียวกับ db.require_pref เพื่อให้ 'ยังไม่ได้กรอก'
    แปลว่าเหมือนกันทั้งระบบ ไม่ใช่ที่หนึ่งข้าม ที่หนึ่งเอาไปยิง API จริง
    """
    try:
        value = prefs.get(key)
    except AttributeError:
        return None
    if not isinstance(value, str) or value.strip() in PLACEHOLDERS:
        return None
    return value.strip()


def _to_int(value: Any) -> int | None:
    """ตัวเลขจาก JSON ภายนอก → int หรือ None — Air4Thai ส่งเลขมาเป็นสตริง

    กัน bool เพราะ True กลายเป็น 1 แล้วดูเหมือนข้อมูลจริงทั้งที่ชนิดผิด
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        try:
            return round(float(str(value).strip()))
        except ValueError:
            return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _hhmm_to_minutes(text: str | None) -> int | None:
    """'07:35' → 455 — รูปแบบผิด = None ไม่ใช่ exception (ค่ามาจาก prefs ที่คนพิมพ์)"""
    if not isinstance(text, str):
        return None
    parts = text.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def _minutes_to_hhmm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


# --- transport จริง (ที่เดียวที่ urllib อยู่ได้ — เทสต์ห้ามมาถึงตรงนี้) ------------


def _default_transport(url: str, params: Mapping[str, str]) -> Any:
    """GET แล้ว parse JSON — ใช้เฉพาะตอน fetch_extras(transport=None)

    import urllib ในฟังก์ชันโดยเจตนา: กฎโปรเจกต์อนุญาต urllib เฉพาะใน
    default transport ตัวนี้ — เทสต์ที่เผลอมาเรียกจะเห็นชัดจาก traceback
    และการ import ระดับโมดูลจะไม่ล่อให้ใครหยิบไปใช้ที่อื่นในไฟล์
    """
    import urllib.parse
    import urllib.request

    query = urllib.parse.urlencode(dict(params))
    full_url = f"{url}?{query}" if query else url
    request = urllib.request.Request(full_url, headers={"User-Agent": "jarvis/1.0"})
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            # urlopen โยน HTTPError ให้เองเกือบทุกกรณี — เช็คซ้ำกัน edge แปลกๆ
            # (redirect ที่จบด้วย status อื่น) เพราะ body ที่ไม่ใช่ 200 parse ไม่ได้
            raise RuntimeError(f"HTTP {status} จาก {url}")
        return json.loads(response.read().decode("utf-8"))


# --- Google Routes: เวลาเดินทาง + เวลาที่ควรออก --------------------------------


def _parse_travel_minutes(payload: Any) -> int | None:
    """Distance Matrix JSON → นาที (ปัดเป็นจำนวนเต็ม อย่างน้อย 1)

    ⚠️ ยังไม่ได้ทดสอบกับ API จริง — ตรวจ shape ตอนต่อจริง
    shape ที่คาด (เอกสารสาธารณะของ Google):
        {"status": "OK", "rows": [{"elements": [{
            "status": "OK",
            "duration": {"value": วินาที},
            "duration_in_traffic": {"value": วินาที}}]}]}
    ใช้ duration_in_traffic ก่อนเสมอ — ตัวเลขที่โอมต้องการคือ "ตอนนี้กี่นาที"
    ไม่ใช่เวลาถนนโล่ง (จันทร์ 12 / พุธ 15 ใน kit คือค่าที่มีรถติดแล้ว)
    """
    if not isinstance(payload, Mapping) or payload.get("status") != "OK":
        return None
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], Mapping):
        return None
    elements = rows[0].get("elements")
    if not isinstance(elements, list) or not elements:
        return None
    element = elements[0]
    if not isinstance(element, Mapping) or element.get("status") != "OK":
        return None
    for field in ("duration_in_traffic", "duration"):
        block = element.get(field)
        if isinstance(block, Mapping):
            seconds = _to_int(block.get("value"))
            if seconds is not None and seconds > 0:
                return max(1, round(seconds / 60))
    return None


def _parse_latlng(value: str | None) -> tuple[float, float] | None:
    """'18.7678368,99.0211007' → (lat, lng) — ไม่ใช่พิกัดก็คืน None เฉยๆ

    ค่านี้อาจเป็นชื่อสถานที่ก็ได้ (ระบบยอมให้ใส่ได้ทั้งสองแบบ) จึงไม่ถือว่า
    แกะไม่ออกเป็นข้อผิดพลาด
    """
    if not value or "," not in value:
        return None
    lat_text, _, lng_text = value.partition(",")
    try:
        lat, lng = float(lat_text.strip()), float(lng_text.strip())
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """ระยะตรงระหว่างสองพิกัด (เมตร) — haversine

    ใช้แค่ตัดสินว่า "ใกล้เกินกว่าจะต้องถาม API ไหม" ไม่ได้เอาไปรายงานเป็นระยะทาง
    จริง (ระยะตรงสั้นกว่าระยะถนนเสมอ) ความแม่นระดับนี้พอสำหรับการตัดสินใจนั้น
    """
    import math

    (lat1, lng1), (lat2, lng2) = a, b
    radius = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def _too_close_to_route(origin: str, destination: str) -> bool:
    """ต้นทางกับปลายทางใกล้กันเกินกว่าจะต้องถาม API ไหม

    แกะพิกัดไม่ได้ทั้งคู่ (เป็นชื่อสถานที่) = ตอบว่าไม่ใกล้ ให้ยิงไปตามปกติ
    เพราะเราไม่มีทางรู้ระยะโดยไม่ถาม
    """
    a, b = _parse_latlng(origin), _parse_latlng(destination)
    if a is None or b is None:
        return False
    return _distance_m(a, b) < MIN_ROUTING_DISTANCE_M


def _leave_by(prefs: Mapping[str, str], travel_minutes: int) -> str | None:
    """เวลาออกจากหอ = school_arrive_by − เวลาเดินทาง − BUFFER_MINUTES

    นี่คือ kit หลักการข้อ 6 ("ตัวเลขต้องแปลงเป็นการตัดสินใจ") ฝั่งข้อมูล:
    renderer เอาค่านี้ไปพิมพ์ "ออก 07:15 ถึงสบายๆ" — ไม่มีค่านี้ก็รายงานได้
    แค่นาที ซึ่งโอมต้องคิดเลขเองตอนเพิ่งตื่น
    """
    arrive = _hhmm_to_minutes(_pref(prefs, "school_arrive_by"))
    if arrive is None:
        return None
    depart = arrive - travel_minutes - BUFFER_MINUTES
    if depart < 0:
        # ข้ามเที่ยงคืนแปลว่าค่าใดค่าหนึ่งเพี้ยน — ไม่พิมพ์ ดีกว่าบอกเวลาผี
        return None
    # ปัดเป็นเลข 5 นาทีที่ใกล้ที่สุด — คนไม่ได้ออกจากบ้าน 07:13 คนออก 07:15
    # ยืนยันกับตัวอย่างใน kit: จันทร์ (เดินทาง 12) → 07:13 ปัดเป็น 07:15 ✓
    #                        พุธ  (เดินทาง 15) → 07:10 ตรงอยู่แล้ว     ✓
    # ทั้งสองตัวอย่างตรงพอดีเมื่อปัดแบบนี้ ซึ่งเป็นหลักฐานว่า kit คิดแบบเดียวกัน
    depart = int(round(depart / ROUND_TO_MINUTES) * ROUND_TO_MINUTES)
    if depart >= 24 * 60:
        return None
    return _minutes_to_hhmm(depart)


def _fetch_travel(
    transport: Transport,
    env: Mapping[str, str],
    prefs: Mapping[str, str],
    when: datetime | None,
) -> dict[str, Any]:
    key = env.get("GOOGLE_MAPS_API_KEY")
    if not key:
        return {}  # ไม่ได้ตั้งคีย์ = ตั้งใจไม่ใช้ ไม่ใช่ error
    # พิกัดแม่นกว่าชื่อสถานที่เสมอ — ใช้ก่อนถ้ามี แล้วค่อยถอยไปใช้ชื่อ
    # (ชื่ออำเภอกว้างๆ ทำให้ Google เดาจุดกลางอำเภอ เวลาเดินทางจะไม่ตรงกับ
    #  ที่เปิด Maps ดูเอง ซึ่ง checklist B4 บังคับว่าต้องตรง)
    origin = _pref(prefs, "dorm_latlng") or _pref(prefs, "dorm_address")
    destination = _pref(prefs, "school_latlng") or _pref(prefs, "school_address")
    if origin and destination and _too_close_to_route(origin, destination):
        # เดินถึงอยู่แล้ว — ไม่ต้องเสีย API call รายวันเพื่อยืนยันสิ่งที่รู้อยู่
        return {}
    if not origin or not destination:
        # ที่อยู่ยังไม่กรอก — ยิง API ด้วยที่อยู่ว่างมีแต่จะได้ ZERO_RESULTS กลับมา
        return {}
    payload = transport(
        GOOGLE_ROUTES_URL,
        {
            "origins": origin,
            "destinations": destination,
            "mode": "driving",
            "language": "th",
            # 'now' ฝั่งเซิร์ฟเวอร์ Google — cron ยิงตอน 06:20 พอดีอยู่แล้ว
            # จึงไม่ต้องแปลง when เป็น epoch (และไม่ต้องเดาเวลาอนาคต)
            "departure_time": "now",
            "key": key,
        },
    )
    minutes = _parse_travel_minutes(payload)
    if minutes is None:
        _warn("travel", "รูปร่าง JSON ไม่ตรงที่คาด")
        return {}
    extras: dict[str, Any] = {"travel_minutes": minutes}
    leave = _leave_by(prefs, minutes)
    if leave is not None:
        extras["leave_by"] = leave
    return extras


# --- Longdo Weather: สรุปอากาศ + ช่วงฝน ---------------------------------------


def _forecast_hour(value: Any) -> int | None:
    """'2026-08-20 07:00:00' / ISO → ชั่วโมง หรือ None ถ้าอ่านไม่ออก"""
    if not isinstance(value, str) or len(value) < 13:
        return None
    try:
        return datetime.fromisoformat(value.strip().replace(" ", "T", 1)).hour
    except ValueError:
        return None


def _parse_longdo_forecast(payload: Any) -> tuple[str | None, str | None]:
    """Longdo hourly forecast → (weather_summary, rain_window)

    ⚠️ ยังไม่ได้ทดสอบกับ API จริง — ตรวจ shape ตอนต่อจริง
    shape ที่คาด (จากเอกสาร Longdo Map API):
        [{"lat": .., "lon": .., "data": [
            {"time": "2026-08-20 07:00:00", "temperature": 27.6, "rain": 0.0},
            ...]}]
        หรือ {"data": [...]} แบบไม่มีชั้น list ครอบ
    สนใจเฉพาะชั่วโมง 06:00-08:59 — ฝนตอนบ่ายไม่เกี่ยวกับขาไปโรงเรียน
    """
    if isinstance(payload, Mapping):
        entries = payload.get("data")
    elif isinstance(payload, list) and payload and isinstance(payload[0], Mapping):
        entries = payload[0].get("data")
    else:
        entries = None
    if not isinstance(entries, list):
        return None, None

    first_temp: float | None = None
    rainy_hours: list[int] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        hour = _forecast_hour(entry.get("time"))
        if hour is None or not MORNING_START_HOUR <= hour < MORNING_END_HOUR:
            continue
        if first_temp is None:
            first_temp = _to_float(entry.get("temperature"))
        rain = _to_float(entry.get("rain"))
        if rain is not None and rain > RAIN_THRESHOLD:
            rainy_hours.append(hour)

    rain_window: str | None = None
    if rainy_hours:
        # ช่วงเดียวคลุมชั่วโมงฝนทั้งหมด ('07:00-08:00' ตามแบบใน kit) —
        # แม้ฝนเว้นช่วง การบอกช่วงกว้างไว้ก่อนปลอดภัยกว่าบอกหลายช่วงให้งง
        rain_window = f"{min(rainy_hours):02d}:00-{max(rainy_hours) + 1:02d}:00"

    summary: str | None = None
    if first_temp is not None:
        summary = f"{round(first_temp)}°"
        if rain_window is None:
            # ประโยคตามแบบ kit — มีฝนเมื่อไหร่ renderer ขึ้นบรรทัด 🌧️ เอง
            summary += " ไม่มีฝนช่วงเช้า"
    return summary, rain_window


def _fetch_weather(
    transport: Transport,
    env: Mapping[str, str],
    prefs: Mapping[str, str],
    when: datetime | None,
) -> dict[str, Any]:
    key = env.get("LONGDO_API_KEY")
    if not key:
        return {}
    payload = transport(
        LONGDO_FORECAST_URL,
        {"key": key, "lat": LONGDO_LAT, "lon": LONGDO_LON},
    )
    summary, rain_window = _parse_longdo_forecast(payload)
    extras: dict[str, Any] = {}
    if summary is not None:
        extras["weather_summary"] = summary
    if rain_window is not None:
        extras["rain_window"] = rain_window
    if not extras:
        _warn("weather", "รูปร่าง JSON ไม่ตรงที่คาด")
    return extras


# --- Air4Thai: ค่าฝุ่นเชียงใหม่ -------------------------------------------------


def _parse_air4thai(payload: Any) -> int | None:
    """getNewAQI_JSON → AQI ของสถานีเชียงใหม่ที่แย่ที่สุด

    ⚠️ ยังไม่ได้ทดสอบกับ API จริง — ตรวจ shape ตอนต่อจริง
    shape ที่คาด (จากเอกสาร/ตัวอย่างสาธารณะของกรมควบคุมมลพิษ):
        {"stations": [{"nameTH": .., "areaTH": "ต.ศรีภูมิ อ.เมือง, เชียงใหม่",
                       "AQILast": {"AQI": {"aqi": "42"}}}, ...]}
    ใช้ค่าสถานีที่แย่ที่สุดในจังหวัด ไม่ใช่ค่าเฉลี่ย — คำเตือนใส่แมสก์
    (AQI > 100) พลาดฝั่ง "เตือนเกิน" ถูกกว่าพลาดฝั่ง "ไม่เตือน" เสมอ
    ค่าติดลบ = สถานีเสีย (Air4Thai ใช้ -1) ต้องกรองทิ้ง
    """
    if not isinstance(payload, Mapping):
        return None
    stations = payload.get("stations")
    if not isinstance(stations, list):
        return None
    worst: int | None = None
    for station in stations:
        if not isinstance(station, Mapping):
            continue
        location = " ".join(
            str(station.get(field, "")) for field in ("areaTH", "provinceTH", "nameTH")
        )
        if AIR4THAI_PROVINCE not in location:
            continue
        aqi_last = station.get("AQILast")
        if not isinstance(aqi_last, Mapping):
            continue
        aqi_block = aqi_last.get("AQI")
        if not isinstance(aqi_block, Mapping):
            continue
        value = _to_int(aqi_block.get("aqi"))
        if value is None or value < 0:
            continue
        worst = value if worst is None else max(worst, value)
    return worst


def _fetch_aqi(
    transport: Transport,
    env: Mapping[str, str],
    prefs: Mapping[str, str],
    when: datetime | None,
) -> dict[str, Any]:
    # Air4Thai เป็น API สาธารณะ ไม่มีคีย์ — จึงไม่มีทาง "ตั้งใจปิด" ด้วย env
    payload = transport(AIR4THAI_URL, {})
    aqi = _parse_air4thai(payload)
    if aqi is None:
        _warn("aqi", "ไม่พบสถานีเชียงใหม่ที่มีค่าใช้ได้")
        return {}
    return {"aqi": aqi}


# --- Google Calendar: นัดของวันนี้ ---------------------------------------------


def _event_label(item: Any) -> str | None:
    """1 event → 'หาหมอฟัน 17:00' หรือ 'ประชุมครอบครัว' (งาน all-day ไม่มีเวลา)

    ⚠️ ยังไม่ได้ทดสอบกับ API จริง — ตรวจ shape ตอนต่อจริง
    เวลาแปลงเป็นเวลาไทยเสมอ — Google ส่ง dateTime พร้อม offset ของปฏิทิน
    ซึ่งอาจไม่ใช่ +07:00 ถ้านัดถูกสร้างจากเครื่องที่ timezone เพี้ยน
    """
    if not isinstance(item, Mapping):
        return None
    summary = item.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None  # นัดไม่มีชื่อ บอกไปโอมก็ไม่รู้ว่าคือนัดอะไร
    label = " ".join(summary.split())
    start = item.get("start")
    if isinstance(start, Mapping):
        raw = start.get("dateTime")
        if isinstance(raw, str):
            try:
                moment = localdate.now(datetime.fromisoformat(raw))
            except ValueError:
                moment = None
            if moment is not None:
                label += f" {moment:%H:%M}"
    return label


def _fetch_calendar(
    transport: Transport,
    env: Mapping[str, str],
    prefs: Mapping[str, str],
    when: datetime | None,
) -> dict[str, Any]:
    token = env.get("GOOGLE_CALENDAR_ACCESS_TOKEN")
    if not token:
        # OAuth flow เต็มเป็นของ Phase 2 — ตอนนี้ใช้ได้เฉพาะคนที่วาง token เอง
        return {}
    # หน้าต่าง "วันนี้" ตามวันไทย (localdate) — ตัดวันด้วย UTC เมื่อไหร่
    # นัดหลัง 7 โมงเช้าจะหลุดไปอยู่ผิดวัน (เหตุผลเดียวกับที่ localdate.py มีอยู่)
    day = localdate.local_date(when)
    time_min = datetime.combine(day, time.min, tzinfo=localdate.TZ)
    time_max = time_min + timedelta(days=1)
    payload = transport(
        GOOGLE_CALENDAR_URL,
        {
            # ส่ง token เป็น query param เพราะสัญญา Transport ไม่มีช่อง header
            # (รูปแบบ access_token ของ OAuth2 ที่ Google ยังรับ) — ถ้าต่อจริง
            # แล้วโดนปฏิเสธ ให้ขยาย default transport ไม่ใช่แก้สัญญา
            "access_token": token,
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "20",
        },
    )
    if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), list):
        _warn("calendar", "รูปร่าง JSON ไม่ตรงที่คาด")
        return {}
    labels = [label for label in map(_event_label, payload["items"]) if label]
    # list ว่าง = ดึงสำเร็จแล้ววันนี้ไม่มีนัดจริงๆ — คืนคีย์ไปได้เลย
    # (renderer ไม่พิมพ์หัวข้อ 📅 เมื่อ list ว่างอยู่แล้ว)
    return {"calendar_items": labels}


# --- จุดเข้าเดียว --------------------------------------------------------------

# ลำดับตายตัวเพื่อให้ log อ่านเทียบกันได้วันต่อวัน — ไม่มีผลกับข้อความ
# เพราะแต่ละ provider เขียนคีย์คนละชุด ไม่ทับกัน
_PROVIDERS: tuple[tuple[str, Callable[..., dict[str, Any]]], ...] = (
    ("travel", _fetch_travel),
    ("weather", _fetch_weather),
    ("aqi", _fetch_aqi),
    ("calendar", _fetch_calendar),
)


def fetch_extras(
    prefs: Mapping[str, str],
    *,
    transport: Transport | None = None,
    env: Mapping[str, str] | None = None,
    when: datetime | None = None,
) -> dict:
    """ดึงข้อมูลเสริม digest — คืนเฉพาะคีย์ที่ดึงสำเร็จ **ไม่โยน exception เด็ดขาด**

    คีย์ที่เป็นไปได้ (ตรงกับ field ใน DigestContext / assemble.morning_context):
        travel_minutes: int   leave_by: 'HH:MM'   weather_summary: str
        rain_window: 'HH:MM-HH:MM'   aqi: int   calendar_items: list[str]

    provider ล้ม (เน็ตล่ม, JSON พัง, คีย์หมดอายุ) = log stderr แล้วข้ามคีย์นั้น
    คีย์ env ไม่ได้ตั้ง = ข้ามเงียบๆ ไม่ log (เป็นการตั้งค่า ไม่ใช่ความผิดปกติ)
    """
    live: Transport = transport if transport is not None else _default_transport
    environ: Mapping[str, str] = env if env is not None else os.environ
    extras: dict[str, Any] = {}
    for name, provider in _PROVIDERS:
        try:
            extras.update(provider(live, environ, prefs, when))
        except Exception as exc:  # ตั้งใจกว้าง — checklist E2: ห้ามตัวเดียวพาทั้งก้อนพัง
            _warn(name, repr(exc))
    return extras
