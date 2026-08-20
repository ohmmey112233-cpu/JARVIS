"""
เทสต์ของ core/fetchers.py — checklist E2: API ตัวเดียวล่ม ห้ามพา digest ทั้งก้อนพัง

สิ่งที่ชุดนี้ปกป้องจริงๆ ไม่ใช่ "parse ถูกไหม" แต่คือสัญญา 3 ข้อที่พังแล้วเงียบ:
    1. fetch_extras ห้ามโยน exception ไม่ว่าอะไรจะเกิด — มันยืนอยู่หน้า cron
       06:20 ที่ต้องส่ง digest 7 วันติด ถ้ามันระเบิด โอมได้ความเงียบแทนข้อความ
    2. คีย์ env ที่ไม่ได้ตั้ง = ข้าม API นั้นโดย **ไม่ยิง request เลย**
       (ยิงไปทั้งที่ไม่มีคีย์ = 401 รัวๆ ใน log ทุกเช้า จนของจริงพังแล้วมองไม่เห็น)
    3. leave_by ต้องเป๊ะระดับนาที — ข้อความ "ออก 07:13 ถึงสบายๆ" ที่คลาดไป
       5 นาทีแปลว่าไปโรงเรียนสายทั้งที่ระบบดูทำงานปกติทุกอย่าง

ทุกเทสต์ฉีด transport ปลอม — ห้ามมีเทสต์ไหนเรียก transport=None เด็ดขาด
เพราะ Air4Thai ไม่ต้องใช้คีย์ ตัว default transport จะออกเน็ตจริงทันที
"""

from __future__ import annotations

import contextlib
import io
import unittest
from datetime import datetime
from typing import Any

from core import fetchers
from core.fetchers import (
    AIR4THAI_URL,
    BUFFER_MINUTES,
    GOOGLE_CALENDAR_URL,
    GOOGLE_ROUTES_URL,
    LONGDO_FORECAST_URL,
    fetch_extras,
)
from core.localdate import TZ

# --- ข้อมูลตั้งต้น ------------------------------------------------------------

PREFS = {
    "dorm_address": "หอพักมงฟอร์ตเรสซิเดนซ์",
    "school_address": "โรงเรียนมงฟอร์ตวิทยาลัย เชียงใหม่",
    "school_arrive_by": "07:35",
}

ENV_ALL = {
    "GOOGLE_MAPS_API_KEY": "maps-key",
    "LONGDO_API_KEY": "longdo-key",
    "GOOGLE_CALENDAR_ACCESS_TOKEN": "cal-token",
}

WHEN = datetime(2026, 8, 20, 6, 20, tzinfo=TZ)  # พฤหัสบดี 06:20 ตามฉาก red-team


def routes_payload(traffic_seconds: int | None = 720, seconds: int = 660) -> dict:
    """shape ตามเอกสาร Distance Matrix — 720 วิ = 12 นาที (ตัวอย่างวันจันทร์ใน kit)"""
    element: dict[str, Any] = {"status": "OK", "duration": {"value": seconds}}
    if traffic_seconds is not None:
        element["duration_in_traffic"] = {"value": traffic_seconds}
    return {"status": "OK", "rows": [{"elements": [element]}]}


def longdo_payload(rain_hours: tuple[int, ...] = ()) -> list:
    """พยากรณ์รายชั่วโมง 05:00-10:00 — นอกหน้าต่างเช้ามีไว้ล่อให้ parser กรองผิด"""
    data = []
    for hour in (5, 6, 7, 8, 9, 10):
        data.append(
            {
                "time": f"2026-08-20 {hour:02d}:00:00",
                "temperature": 25.0 + hour * 0.4,  # 06:00 → 27.4 → ปัดเป็น 27
                "rain": 5.0 if hour in rain_hours else 0.0,
            }
        )
    return [{"lat": 18.78, "lon": 99.0, "data": data}]


def air4thai_payload() -> dict:
    """สถานีจริงหน้าตาแบบนี้ — กรุงเทพฯ ค่าแย่กว่ามีไว้ล่อให้ลืมกรองจังหวัด"""
    return {
        "stations": [
            {
                "stationID": "05t",
                "nameTH": "ริมถนนดินแดง",
                "areaTH": "เขตดินแดง, กรุงเทพฯ",
                "AQILast": {"AQI": {"aqi": "154"}},
            },
            {
                "stationID": "35t",
                "nameTH": "ศูนย์ราชการจังหวัดเชียงใหม่",
                "areaTH": "ต.ช้างเผือก อ.เมือง, เชียงใหม่",
                "AQILast": {"AQI": {"aqi": "42"}},
            },
            {
                "stationID": "36t",
                "nameTH": "โรงเรียนยุพราชวิทยาลัย",
                "areaTH": "ต.ศรีภูมิ อ.เมือง, เชียงใหม่",
                "AQILast": {"AQI": {"aqi": "57"}},
            },
            {
                # สถานีเสีย — Air4Thai ส่ง -1 มาแทนค่า ห้ามให้ชนะ max
                "stationID": "37t",
                "areaTH": "อ.แม่ริม, เชียงใหม่",
                "AQILast": {"AQI": {"aqi": "-1"}},
            },
        ]
    }


def calendar_payload() -> dict:
    return {
        "items": [
            {"summary": "หาหมอฟัน", "start": {"dateTime": "2026-08-20T17:00:00+07:00"}},
            {"summary": "ประชุมครอบครัว", "start": {"date": "2026-08-20"}},
            {"start": {"dateTime": "2026-08-20T19:00:00+07:00"}},  # ไม่มีชื่อ → ข้าม
        ]
    }


def all_ok_responses() -> dict:
    return {
        GOOGLE_ROUTES_URL: routes_payload(),
        LONGDO_FORECAST_URL: longdo_payload(),
        AIR4THAI_URL: air4thai_payload(),
        GOOGLE_CALENDAR_URL: calendar_payload(),
    }


class FakeTransport:
    """transport ปลอม — จำทุก call ไว้ให้เทสต์ตรวจว่า "ไม่ยิง" จริงๆ ด้วย"""

    def __init__(self, responses: dict) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, params: Any) -> Any:
        self.calls.append((url, dict(params)))
        result = self.responses[url]
        if isinstance(result, Exception):
            raise result
        return result

    def called_urls(self) -> set[str]:
        return {url for url, _ in self.calls}


def run(prefs=PREFS, responses=None, env=ENV_ALL, when=WHEN):
    """เรียก fetch_extras พร้อมเก็บ stderr — คืน (extras, transport, stderr_text)"""
    transport = FakeTransport(all_ok_responses() if responses is None else responses)
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        extras = fetch_extras(prefs, transport=transport, env=env, when=when)
    return extras, transport, buffer.getvalue()


# --------------------------------------------------------------------------
# 1. เส้นทางปกติ — ทุก API ตอบครบ
# --------------------------------------------------------------------------


class AllProvidersTest(unittest.TestCase):
    def test_all_keys_present_and_exact(self) -> None:
        extras, transport, _ = run()
        self.assertEqual(
            {
                "travel_minutes": 12,
                "leave_by": "07:15",
                "weather_summary": "27° ไม่มีฝนช่วงเช้า",
                "aqi": 57,
                "calendar_items": ["หาหมอฟัน 17:00", "ประชุมครอบครัว"],
            },
            extras,
        )
        # ไม่มีฝน = ห้ามมีคีย์ rain_window โผล่มาพร้อมค่า None
        self.assertNotIn("rain_window", extras)
        self.assertEqual(
            {GOOGLE_ROUTES_URL, LONGDO_FORECAST_URL, AIR4THAI_URL, GOOGLE_CALENDAR_URL},
            transport.called_urls(),
        )

    def test_rain_window_single_hour(self) -> None:
        # ฝนเฉพาะ 07:00-07:59 → ช่วง '07:00-08:00' ตรงตามแบบใน kit
        responses = all_ok_responses()
        responses[LONGDO_FORECAST_URL] = longdo_payload(rain_hours=(7,))
        extras, _, _ = run(responses=responses)
        self.assertEqual("07:00-08:00", extras["rain_window"])
        # มีฝนแล้ว summary เหลือแค่อุณหภูมิ — ประโยค "ไม่มีฝน" ต้องหายไป
        self.assertEqual("27°", extras["weather_summary"])

    def test_rain_outside_morning_window_ignored(self) -> None:
        # ฝน 10 โมง (หลังเข้าแถวแล้ว) ไม่เกี่ยวกับขาไปโรงเรียน
        responses = all_ok_responses()
        responses[LONGDO_FORECAST_URL] = longdo_payload(rain_hours=(10,))
        extras, _, _ = run(responses=responses)
        self.assertNotIn("rain_window", extras)

    def test_travel_falls_back_to_duration_without_traffic(self) -> None:
        responses = all_ok_responses()
        responses[GOOGLE_ROUTES_URL] = routes_payload(traffic_seconds=None, seconds=660)
        extras, _, _ = run(responses=responses)
        self.assertEqual(11, extras["travel_minutes"])

    def test_aqi_filters_bangkok_and_broken_stations(self) -> None:
        # 154 (กทม.) และ -1 (สถานีเสีย) ต้องไม่ชนะ — เหลือค่าแย่สุดของเชียงใหม่
        extras, _, _ = run()
        self.assertEqual(57, extras["aqi"])

    def test_calendar_event_time_converted_to_thai(self) -> None:
        # นัดที่สร้างจากเครื่อง timezone อื่น (Z = UTC) ต้องแสดงเป็นเวลาไทย
        responses = all_ok_responses()
        responses[GOOGLE_CALENDAR_URL] = {
            "items": [{"summary": "ประชุมออนไลน์", "start": {"dateTime": "2026-08-20T03:30:00Z"}}]
        }
        extras, _, _ = run(responses=responses)
        self.assertEqual(["ประชุมออนไลน์ 10:30"], extras["calendar_items"])

    def test_calendar_success_with_zero_events(self) -> None:
        # ดึงสำเร็จแต่ไม่มีนัด = list ว่าง (renderer ไม่พิมพ์หัวข้อเอง) ไม่ใช่คีย์หาย
        responses = all_ok_responses()
        responses[GOOGLE_CALENDAR_URL] = {"items": []}
        extras, _, _ = run(responses=responses)
        self.assertEqual([], extras["calendar_items"])


# --------------------------------------------------------------------------
# 2. leave_by — เลขต้องเป๊ะระดับนาที (kit หลักการข้อ 6)
# --------------------------------------------------------------------------


class LeaveByTest(unittest.TestCase):
    def test_exact_arithmetic(self) -> None:
        # 07:35 − 12 นาทีเดินทาง − 10 นาที buffer = 07:13
        self.assertEqual(10, BUFFER_MINUTES)
        extras, _, _ = run()
        # 455 − 12 − 10 = 433 (07:13) แล้วปัดเป็นเลข 5 นาทีใกล้สุด → 07:15 ตรงกับตัวอย่างใน kit
        self.assertEqual("07:15", extras["leave_by"])

    def test_missing_arrive_pref_gives_travel_without_leave_by(self) -> None:
        prefs = {k: v for k, v in PREFS.items() if k != "school_arrive_by"}
        extras, _, _ = run(prefs=prefs)
        self.assertEqual(12, extras["travel_minutes"])
        self.assertNotIn("leave_by", extras)

    def test_malformed_arrive_pref_skips_leave_by_only(self) -> None:
        for bad in ("7 โมงครึ่ง", "25:00", "07:99", "", "[ต้องกรอก]"):
            with self.subTest(bad=bad):
                extras, _, _ = run(prefs={**PREFS, "school_arrive_by": bad})
                self.assertEqual(12, extras["travel_minutes"])
                self.assertNotIn("leave_by", extras)

    def test_crossing_midnight_is_nonsense_not_a_time(self) -> None:
        # เดินทาง 8 ชม. (ค่าหลุดจาก API) — 07:35 ลบแล้วติดลบ ห้ามพิมพ์เวลาผี
        responses = all_ok_responses()
        responses[GOOGLE_ROUTES_URL] = routes_payload(traffic_seconds=8 * 3600)
        extras, _, _ = run(responses=responses)
        self.assertNotIn("leave_by", extras)


# --------------------------------------------------------------------------
# 3. checklist E2 — ตัวเดียวล่ม ตัวอื่นต้องรอด และ fetch_extras ห้ามโยนเด็ดขาด
# --------------------------------------------------------------------------


class FailureIsolationTest(unittest.TestCase):
    def test_one_provider_raising_leaves_others_intact(self) -> None:
        responses = all_ok_responses()
        responses[AIR4THAI_URL] = ConnectionError("air4thai down")
        extras, _, stderr_text = run(responses=responses)
        self.assertNotIn("aqi", extras)
        self.assertEqual(12, extras["travel_minutes"])
        # 455 − 12 − 10 = 433 (07:13) แล้วปัดเป็นเลข 5 นาทีใกล้สุด → 07:15 ตรงกับตัวอย่างใน kit
        self.assertEqual("07:15", extras["leave_by"])
        self.assertIn("weather_summary", extras)
        self.assertIn("calendar_items", extras)
        # ล้มแล้วต้องทิ้งร่องรอยไว้ใน stderr — เงียบสนิทคือหายนะแบบตรวจย้อนไม่ได้
        self.assertIn("aqi", stderr_text)
        self.assertIn("air4thai down", stderr_text)

    def test_never_raises_even_when_transport_always_throws(self) -> None:
        class ExplodingTransport:
            def __call__(self, url: str, params: Any) -> Any:
                raise RuntimeError(f"เน็ตล่มทั้งหอ: {url}")

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            try:
                extras = fetch_extras(
                    PREFS, transport=ExplodingTransport(), env=ENV_ALL, when=WHEN
                )
            except Exception as exc:  # pragma: no cover - จับไว้ให้ข้อความเทสต์ชัด
                self.fail(f"fetch_extras โยน exception ออกมา: {exc!r}")
        self.assertEqual({}, extras)

    def test_even_broken_prefs_object_cannot_crash(self) -> None:
        # ผู้เรียกส่งของผิดชนิดมา (None แทน Mapping) — ก็ยังห้ามระเบิด
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            extras = fetch_extras(
                None,  # type: ignore[arg-type]
                transport=FakeTransport(all_ok_responses()),
                env=ENV_ALL,
                when=WHEN,
            )
        self.assertIsInstance(extras, dict)

    def test_malformed_shapes_skip_provider_not_crash(self) -> None:
        garbage_by_url = {
            GOOGLE_ROUTES_URL: [
                {"status": "OVER_QUERY_LIMIT"},
                {"status": "OK", "rows": []},
                {"status": "OK", "rows": [{"elements": [{"status": "NOT_FOUND"}]}]},
                {"rows": "อะไรก็ไม่รู้"},
                "ไม่ใช่ dict ด้วยซ้ำ",
                {"status": "OK", "rows": [{"elements": [{"status": "OK", "duration": {"value": "งง"}}]}]},
            ],
            LONGDO_FORECAST_URL: [
                {},
                [],
                [{"data": "ผิดชนิด"}],
                [{"data": [{"time": "ไม่ใช่เวลา", "temperature": "ไม่ใช่เลข", "rain": None}]}],
                42,
            ],
            AIR4THAI_URL: [
                {},
                {"stations": "ผิดชนิด"},
                {"stations": [{"areaTH": "เชียงใหม่"}]},  # ไม่มี AQILast
                {"stations": [{"areaTH": "เชียงใหม่", "AQILast": {"AQI": {"aqi": "-1"}}}]},
                {"stations": [{"areaTH": "กรุงเทพฯ", "AQILast": {"AQI": {"aqi": "80"}}}]},
            ],
            GOOGLE_CALENDAR_URL: [
                {},
                {"items": "ผิดชนิด"},
                ["ไม่ใช่ dict"],
            ],
        }
        keys_by_url = {
            GOOGLE_ROUTES_URL: {"travel_minutes", "leave_by"},
            LONGDO_FORECAST_URL: {"weather_summary", "rain_window"},
            AIR4THAI_URL: {"aqi"},
            GOOGLE_CALENDAR_URL: {"calendar_items"},
        }
        for url, garbage_list in garbage_by_url.items():
            for garbage in garbage_list:
                with self.subTest(url=url, garbage=garbage):
                    responses = all_ok_responses()
                    responses[url] = garbage
                    extras, _, _ = run(responses=responses)
                    # provider ที่โดนขยะหายไปเฉพาะคีย์ตัวเอง ตัวอื่นอยู่ครบ
                    for key in keys_by_url[url]:
                        self.assertNotIn(key, extras)
                    for other_url, keys in keys_by_url.items():
                        if other_url != url:
                            self.assertTrue(keys & set(extras))


# --------------------------------------------------------------------------
# 4. env/prefs ไม่ครบ = ข้ามแบบ "ไม่ยิง request" ไม่ใช่ยิงแล้วพัง
# --------------------------------------------------------------------------


class SkipWithoutCallingTest(unittest.TestCase):
    def test_missing_google_key_skips_travel_without_request(self) -> None:
        env = {k: v for k, v in ENV_ALL.items() if k != "GOOGLE_MAPS_API_KEY"}
        extras, transport, stderr_text = run(env=env)
        self.assertNotIn("travel_minutes", extras)
        self.assertNotIn("leave_by", extras)
        self.assertNotIn(GOOGLE_ROUTES_URL, transport.called_urls())
        # เป็นการตั้งค่า ไม่ใช่ความผิดปกติ — ห้าม log ให้ดูเหมือนพัง
        self.assertNotIn("travel", stderr_text)

    def test_missing_longdo_key_skips_weather_without_request(self) -> None:
        env = {k: v for k, v in ENV_ALL.items() if k != "LONGDO_API_KEY"}
        extras, transport, _ = run(env=env)
        self.assertNotIn("weather_summary", extras)
        self.assertNotIn("rain_window", extras)
        self.assertNotIn(LONGDO_FORECAST_URL, transport.called_urls())

    def test_missing_calendar_token_skips_calendar_without_request(self) -> None:
        env = {k: v for k, v in ENV_ALL.items() if k != "GOOGLE_CALENDAR_ACCESS_TOKEN"}
        extras, transport, _ = run(env=env)
        self.assertNotIn("calendar_items", extras)
        self.assertNotIn(GOOGLE_CALENDAR_URL, transport.called_urls())

    def test_empty_env_still_fetches_keyless_air4thai(self) -> None:
        extras, transport, _ = run(env={})
        self.assertEqual({"aqi": 57}, extras)
        self.assertEqual({AIR4THAI_URL}, transport.called_urls())

    def test_missing_address_pref_skips_travel_without_request(self) -> None:
        for missing in ("dorm_address", "school_address"):
            with self.subTest(missing=missing):
                prefs = {k: v for k, v in PREFS.items() if k != missing}
                extras, transport, _ = run(prefs=prefs)
                self.assertNotIn("travel_minutes", extras)
                self.assertNotIn(GOOGLE_ROUTES_URL, transport.called_urls())

    def test_placeholder_address_treated_as_missing(self) -> None:
        # seed data ใช้ '[ต้องกรอก]' เป็นตัวยึด — ห้ามเอาไปเป็นที่อยู่ยิง API
        prefs = {**PREFS, "dorm_address": "[ต้องกรอก]"}
        extras, transport, _ = run(prefs=prefs)
        self.assertNotIn("travel_minutes", extras)
        self.assertNotIn(GOOGLE_ROUTES_URL, transport.called_urls())


# --------------------------------------------------------------------------
# 5. เวลา — หน้าต่างปฏิทินต้องเป็น "วันไทย" ของ when ที่ฉีดเข้ามา (กฎเหล็กข้อ 1)
# --------------------------------------------------------------------------


class CalendarWindowTest(unittest.TestCase):
    def _calendar_params(self, when: datetime) -> dict:
        _, transport, _ = run(when=when)
        for url, params in transport.calls:
            if url == GOOGLE_CALENDAR_URL:
                return params
        self.fail("ไม่ได้เรียก Google Calendar เลย")

    def test_window_covers_injected_thai_day(self) -> None:
        params = self._calendar_params(WHEN)
        self.assertEqual("2026-08-20T00:00:00+07:00", params["timeMin"])
        self.assertEqual("2026-08-21T00:00:00+07:00", params["timeMax"])
        self.assertEqual("cal-token", params["access_token"])
        self.assertEqual("true", params["singleEvents"])

    def test_utc_evening_is_next_thai_day(self) -> None:
        # 19:30 UTC = 02:30 เช้าวันถัดไปตามเวลาไทย — หน้าต่างต้องเป็นวันไทย
        # ไม่ใช่วัน UTC (เหตุผลเดียวกับที่ localdate.py มีอยู่ทั้งโมดูล)
        from zoneinfo import ZoneInfo

        when = datetime(2026, 8, 20, 19, 30, tzinfo=ZoneInfo("UTC"))
        params = self._calendar_params(when)
        self.assertEqual("2026-08-21T00:00:00+07:00", params["timeMin"])
        self.assertEqual("2026-08-22T00:00:00+07:00", params["timeMax"])


# --------------------------------------------------------------------------
# 6. กฎโปรเจกต์ — urllib อยู่ได้เฉพาะใน default transport
# --------------------------------------------------------------------------


class PurityTest(unittest.TestCase):
    def test_urllib_not_imported_at_module_level(self) -> None:
        # import ระดับโมดูลจะล่อให้โค้ดอื่นในไฟล์หยิบไปใช้นอก default transport
        # (และทำให้ 'เทสต์ไม่แตะเน็ต' พิสูจน์ยากขึ้น) — บังคับไว้ด้วยเทสต์เลย
        import inspect

        source = inspect.getsource(fetchers)
        module_level = [
            line
            for line in source.splitlines()
            if line.startswith(("import ", "from ")) and "urllib" in line
        ]
        self.assertEqual([], module_level)

    def test_injected_transport_is_the_only_io_path(self) -> None:
        # ทุก request ของรอบที่ inject transport ต้องผ่านตัวปลอมครบ 4 เส้น —
        # ถ้ามีเส้นไหนแอบไปทางอื่น จำนวน call จะไม่ครบ
        _, transport, _ = run()
        self.assertEqual(4, len(transport.calls))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TooCloseToRouteTest(unittest.TestCase):
    """หอห่างจากโรงเรียน 165 เมตร — ไม่ต้องยิง Distance Matrix ทุกเช้า

    โอมเดินเองแล้วยืนยัน 2 นาที (20 ส.ค. 2026) ตัวเลข 12/15 นาทีใน kit
    เขียนไว้ก่อนมีใครวัดจริง
    """

    DORM = "18.7678368,99.0211007"
    SCHOOL = "18.7667810,99.0200037"
    HOME = "18.4501443,98.7127309"

    def test_แกะพิกัดได้(self) -> None:
        self.assertEqual(fetchers._parse_latlng(self.DORM), (18.7678368, 99.0211007))

    def test_แกะชื่อสถานที่ไม่ได้_คืน_None(self) -> None:
        for bad in ("หอพักมงฟอร์ตเรสซิเดนซ์", "", None, "abc,def", "999,999"):
            self.assertIsNone(fetchers._parse_latlng(bad), bad)

    def test_ระยะหอถึงโรงเรียนราว_165_เมตร(self) -> None:
        d = fetchers._distance_m((18.7678368, 99.0211007), (18.7667810, 99.0200037))
        self.assertAlmostEqual(d, 165, delta=15)

    def test_หอกับโรงเรียนถือว่าใกล้เกินกว่าจะยิง_API(self) -> None:
        self.assertTrue(fetchers._too_close_to_route(self.DORM, self.SCHOOL))

    def test_หอกับจอมทองไม่ใกล้(self) -> None:
        self.assertFalse(fetchers._too_close_to_route(self.DORM, self.HOME))

    def test_ชื่อสถานที่ล้วน_ต้องยิงตามปกติเพราะไม่รู้ระยะ(self) -> None:
        self.assertFalse(fetchers._too_close_to_route("หอมงฟอร์ต", "โรงเรียนมงฟอร์ต"))

    def test_fetch_extras_ไม่ยิง_API_เลยเมื่อใกล้(self) -> None:
        calls: list[str] = []

        def transport(url, params):
            calls.append(url)
            return {}

        prefs = {
            "dorm_latlng": self.DORM,
            "school_latlng": self.SCHOOL,
            "school_arrive_by": "07:35",
        }
        out = fetchers.fetch_extras(
            prefs, transport=transport, env={"GOOGLE_MAPS_API_KEY": "x"}
        )
        self.assertEqual([c for c in calls if "distancematrix" in c], [])
        self.assertNotIn("travel_minutes", out)
        self.assertNotIn("leave_by", out)

    def test_ย้ายไปไกลแล้วกลับมายิงเองโดยไม่ต้องแก้โค้ด(self) -> None:
        calls: list[str] = []

        def transport(url, params):
            calls.append(url)
            raise RuntimeError("พอแค่ดูว่ายิงไหม")

        prefs = {
            "dorm_latlng": self.HOME,          # จำลองว่าย้ายไปอยู่จอมทอง
            "school_latlng": self.SCHOOL,
            "school_arrive_by": "07:35",
        }
        fetchers.fetch_extras(prefs, transport=transport, env={"GOOGLE_MAPS_API_KEY": "x"})
        self.assertTrue([c for c in calls if "distancematrix" in c])
