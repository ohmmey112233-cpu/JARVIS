"""
ความจำที่โอมสอน Jarvis — CRUD เต็มรูปแบบ (phase1-kit "ต่อรอบหน้า" ข้อ 5)

4 คำสั่งที่ต้องรองรับผ่านแชท:
    "จำไว้ว่า..."               → remember()
    "แก้ความจำเรื่อง X เป็น..."  → revise()
    "ลืมเรื่อง X"                → forget()
    "จำอะไรเกี่ยวกับ X ไว้บ้าง"  → recall()

ทำไมโมดูลนี้ถึงไม่ใช่ append-only (red-team H13):
    ถ้าเก็บอย่างเดียวไม่เคยทับ พอเดือนหน้าโอมบอกว่า "ร้านนี้จองวันต่อวันได้แล้ว"
    ฐานข้อมูลจะมี 2 ข้อที่ขัดกันโดยที่ระบบไม่รู้ว่าอันไหนใหม่กว่า
    → ทุกครั้งที่จำเรื่องเดิม ของเก่าจะถูกตั้ง superseded_by ชี้มาที่ข้อใหม่
      และ recall() จะเห็นเฉพาะข้อที่ superseded_by IS NULL AND archived_at IS NULL

ทำไม remember/revise ถึงคืน "ข้อที่ถูกทับ" กลับไปด้วย:
    บุคลิกข้อ "การเรียนรู้": "ถ้า lesson ใหม่ขัดกับของเก่า ให้ถือว่าของใหม่ทับของเก่า
    และบอกโอมว่าทับอันไหนไป" — ถ้าไม่คืนค่านี้ ตัวเรียกจะรายงานไม่ได้เลย
    ทับเงียบๆ = โอมไม่มีทางรู้ว่าความจำเดิมหายไปตอนไหน

ทำไมลบแล้วยังกู้ได้:
    kit ข้อ 5: "การลบต้องยืนยันก่อนเสมอ และควรเก็บลง trash ที่กู้คืนได้
    ไม่ใช่ลบทิ้งทันที (เผื่อสั่งลบผิด)" → forget() มีสองจังหวะเสมอ
    และ consolidate() ตี 2 แค่ mark archived_at ห้ามลบจริงเด็ดขาด
    (H13: "consolidation ที่ mark archived เอง = ความจำหายเงียบๆ โดยไม่มีใครตรวจ")

หมายเหตุเรื่องเวลา (กฎเหล็กข้อ 1):
    ทุกคอลัมน์เวลาในตารางนี้มี DEFAULT เป็น datetime('now') ของ SQLite ซึ่งเป็น **UTC**
    โมดูลนี้จึงเขียนค่าเวลาเองทุกครั้ง ไม่ปล่อยให้ DEFAULT ทำงาน —
    เก็บเป็นเวลาไทย 'YYYY-MM-DD HH:MM:SS' ผ่าน localdate เท่านั้น
    ไม่งั้นความจำที่จำตอน 3 ทุ่มจะถูกบันทึกเป็นวันถัดไป และ consolidate จะนับอายุเพี้ยน 7 ชม.

หมายเหตุชื่อพารามิเตอร์:
    CONTRACTS.md ตรึงชื่อพารามิเตอร์ฉีดเวลาของโมดูลนี้ไว้ว่า `when` (เหมือน friday.py
    ไม่ใช่ `clock`) — ทำหน้าที่เดียวกันคือให้เทสต์ยัดเวลาเข้ามาได้ ห้ามเปลี่ยนชื่อ
    เพราะโมดูลอื่นถูกเขียนขนานกันโดยอิงสัญญาเดิม
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time
from typing import Any, Iterable, NamedTuple, Sequence

from . import localdate

# เงื่อนไข "ยังใช้อยู่" — ประกาศที่เดียว เพราะถ้าที่ไหนลืมเช็ค archived_at
# ความจำที่ถูกพักไว้จะโผล่กลับมาปนกับของจริงโดยไม่มีใครสังเกต
LIVE_CONDITION = "superseded_by IS NULL AND archived_at IS NULL"

# ตัวคั่น tags ในคอลัมน์เดียว (schema: "คั่นด้วยคอมมา เช่น 'restaurant,booking'")
TAG_SEPARATOR = ","

# ตัวหนีสำหรับ LIKE — ถ้าโอมค้นคำที่มี % หรือ _ อยู่จริง ต้องค้นเจอตามตัวอักษร
# ไม่ใช่กลายเป็น wildcard ที่คืนความจำทั้งฐาน
_LIKE_ESCAPE = "\\"

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

_LESSON_COLUMNS = "id, topic, content, tags, created_at, superseded_by, archived_at"


class Lesson(NamedTuple):
    """ความจำ 1 ก้อน

    tags เป็น list[str] ตรงนี้ แต่ในตารางเก็บเป็นสตริงคั่นคอมมา —
    การแปลงกลับไปกลับมาอยู่ใน _split_tags/_join_tags ที่เดียว
    เพื่อไม่ให้มีที่ไหนเผลอส่งสตริงดิบออกไปให้ตัวเรียกเจอ
    """

    id: int
    topic: str
    content: str
    tags: list[str]
    created_at: str
    superseded_by: int | None
    archived_at: str | None


# --- ตัวช่วยภายใน -------------------------------------------------------------


def _as_datetime(when: str | date | datetime | None) -> datetime | None:
    """รับค่าฉีดเวลาได้หลายแบบ แล้วส่งต่อให้ localdate.now() ตัดสินเรื่อง timezone

    รับ date/สตริงวันที่ด้วย เพราะเทสต์และงาน cron บางที่ถือแค่ "วันไหน" ไม่มีเวลา
    naive datetime ปล่อยผ่านไปให้ localdate ตีความว่าเป็นเวลาไทย (ตามสัญญาของมัน)

    สตริงที่มีเวลาต่อท้าย ('2026-08-20 23:30:00') ต้องเก็บเวลานั้นไว้ ห้ามตัดเป็นเที่ยงคืน —
    ตัดทิ้งคือเลื่อนเวลาที่บันทึกได้ถึง 23 ชั่วโมง ซึ่งย้อนแย้งกับเหตุผลทั้งหมด
    ที่โมดูลนี้เขียน timestamp เองแทนที่จะปล่อยให้ DEFAULT ของ SQLite ทำงาน
    """
    if when is None or isinstance(when, datetime):
        return when
    if isinstance(when, str):
        text = when.strip()
        if "T" in text or " " in text:
            return datetime.fromisoformat(text)
    return datetime.combine(localdate.to_date(when), time(0, 0))


def _stamp(when: str | date | datetime | None = None) -> tuple[str, str]:
    """คืน (เวลาไทยแบบ 'YYYY-MM-DD HH:MM:SS', คีย์วันที่ 'YYYY-MM-DD')

    เก็บแบบไม่มี offset ต่อท้ายเพื่อให้เรียงด้วยสตริงได้ตรงกับลำดับเวลาจริง
    และหน้าตาเหมือนค่าที่ SQLite เขียนเอง (แต่เป็นเวลาไทย ไม่ใช่ UTC)
    """
    moment = localdate.now(_as_datetime(when))
    return moment.strftime(_TIMESTAMP_FORMAT), moment.date().isoformat()


def _require_text(value: Any, field: str) -> str:
    """ข้อความที่ขาดไม่ได้ — ว่างเปล่าต้องระเบิด ไม่ใช่บันทึกก้อนว่างเข้าไป

    ความจำที่ topic ว่างจะค้นไม่เจอตลอดกาล และไปกินที่ในการทับของเก่าด้วย
    """
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field} ห้ามว่าง")
    return text


def _require_limit(limit: Any) -> int:
    """limit ต้องมากกว่า 0 — limit=0 คืนลิสต์ว่างจะดูเหมือน "ไม่มีความจำเรื่องนี้"

    ซึ่งเป็นคำตอบที่ผิดแบบเงียบๆ แบบที่ red-team เตือนไว้ทั้งเอกสาร
    """
    value = int(limit)
    if value < 1:
        raise ValueError(f"limit ต้องมากกว่า 0 ได้รับ {limit!r}")
    return value


def _normalize_tags(tags: Iterable[str] | str | None) -> list[str]:
    """ทำ tags ให้เป็นลิสต์สะอาด: ตัดช่องว่าง ทิ้งตัวว่าง ตัดตัวซ้ำ คงลำดับเดิม

    แตกคอมมาซ้ำอีกชั้นแม้จะรับมาเป็นลิสต์แล้ว เพราะตัวเรียกบางทางส่ง
    ['cafe,nimman'] มาก้อนเดียว ถ้าไม่แตกตรงนี้ ค่าที่เก็บกับค่าที่อ่านกลับจะไม่ตรงกัน
    (เก็บ 'cafe,nimman' → อ่านกลับได้ 2 ตัว ทั้งที่ใส่เข้าไปตัวเดียว)
    """
    if tags is None:
        return []
    items: Iterable[str] = [tags] if isinstance(tags, str) else tags

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item is None:
            # JSON ที่ส่งมาจาก skill ใส่ null ปนมาได้ — str(None) จะกลายเป็นแท็ก 'None'
            # ที่ค้นเจอจริงและติดไปกับความจำตลอดไป ต้องทิ้งตั้งแต่ตรงนี้
            continue
        for part in str(item).split(TAG_SEPARATOR):
            tag = part.strip()
            if not tag:
                continue
            key = tag.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(tag)
    return cleaned


def _join_tags(tags: Iterable[str] | str | None) -> str:
    return TAG_SEPARATOR.join(_normalize_tags(tags))


def _split_tags(raw: str | None) -> list[str]:
    """อ่าน tags จาก DB — คอลัมน์ว่าง (ค่า default) ต้องได้ [] ไม่ใช่ ['']"""
    return _normalize_tags(raw)


def _row_to_lesson(row: sqlite3.Row) -> Lesson:
    return Lesson(
        id=int(row["id"]),
        topic=row["topic"],
        content=row["content"],
        tags=_split_tags(row["tags"]),
        created_at=row["created_at"],
        superseded_by=None if row["superseded_by"] is None else int(row["superseded_by"]),
        archived_at=row["archived_at"],
    )


def _fetch(conn: sqlite3.Connection, lesson_id: int) -> Lesson:
    row = conn.execute(
        f"SELECT {_LESSON_COLUMNS} FROM lessons WHERE id = ?", (lesson_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"ไม่มีความจำ id {lesson_id}")
    return _row_to_lesson(row)


def _rows_for_topic(
    conn: sqlite3.Connection, topic: str, *, live_only: bool
) -> list[sqlite3.Row]:
    """ทุกแถวของ topic นั้น เรียงใหม่สุดก่อน

    เทียบ topic แบบ COLLATE NOCASE เพราะโอมพิมพ์ผ่านแชท/เสียง ตัวพิมพ์ใหญ่เล็ก
    ของชื่อร้านภาษาอังกฤษไม่ควรกลายเป็นความจำคนละก้อน (ภาษาไทยไม่มีเคส
    NOCASE จึงเท่ากับเทียบตรงตัวอยู่แล้ว)
    """
    where = "topic = ? COLLATE NOCASE"
    if live_only:
        where += f" AND {LIVE_CONDITION}"
    return conn.execute(
        f"SELECT {_LESSON_COLUMNS} FROM lessons WHERE {where} "
        f"ORDER BY created_at DESC, id DESC",
        (topic,),
    ).fetchall()


def _like_pattern(term: str) -> str:
    """ทำคำค้นให้เป็น pattern แบบ substring พร้อมหนีอักขระพิเศษของ LIKE"""
    escaped = (
        term.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"


def _timestamp_date(value: str | None) -> date | None:
    """ดึงเฉพาะส่วนวันของ timestamp — อ่านไม่ออกคืน None ไม่ใช่ระเบิด

    แถวที่เวลาพังต้องไม่ทำให้งานตี 2 ตายทั้งงาน แต่ก็ห้ามหายเงียบ —
    consolidate() จะเก็บแถวพวกนี้ไว้ในคีย์ 'skipped' ให้ไปโผล่ในรายงานเช้า
    """
    if not value:
        return None
    try:
        return localdate.to_date(str(value))
    except (ValueError, TypeError):
        return None


# --- 4 คำสั่งหลัก -------------------------------------------------------------


def remember(
    conn: sqlite3.Connection,
    topic: str,
    content: str,
    tags: Iterable[str] | str = (),
    when: str | date | datetime | None = None,
) -> tuple[Lesson, Lesson | None]:
    """"จำไว้ว่า..." → คืน (ข้อใหม่, ข้อเก่าที่ถูกทับ|None)

    ถ้ามีความจำ topic เดียวกันที่ยังใช้อยู่ ทุกก้อนจะถูกตั้ง superseded_by ชี้มาที่ข้อใหม่
    (ทับ "ทุกก้อน" ไม่ใช่แค่ก้อนล่าสุด เพราะถ้าเผลอเหลือไว้ recall จะคืนความจำ
     ที่ขัดกันเองสองก้อนพร้อมกัน ซึ่งคือปัญหา H13 ที่โมดูลนี้ตั้งใจปิด)
    ค่าที่คืนกลับเป็นก้อนล่าสุด — ตัวเรียก **ต้อง** เอาไปบอกโอมว่าทับอันไหน
    """
    topic_clean = _require_text(topic, "topic")
    content_clean = _require_text(content, "content")
    tag_text = _join_tags(tags)
    stamp, _ = _stamp(when)

    previous = _rows_for_topic(conn, topic_clean, live_only=True)

    cursor = conn.execute(
        "INSERT INTO lessons (topic, content, tags, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (topic_clean, content_clean, tag_text, stamp, stamp),
    )
    new_id = int(cursor.lastrowid)

    if previous:
        old_ids = [int(row["id"]) for row in previous]
        marks = ", ".join("?" for _ in old_ids)
        conn.execute(
            f"UPDATE lessons SET superseded_by = ?, updated_at = ? WHERE id IN ({marks})",
            (new_id, stamp, *old_ids),
        )
    conn.commit()

    # อ่านของเก่ากลับมาใหม่หลังอัปเดต เพื่อให้ค่า superseded_by ที่คืนออกไปเป็นค่าจริง
    superseded = _fetch(conn, int(previous[0]["id"])) if previous else None
    return _fetch(conn, new_id), superseded


def recall(
    conn: sqlite3.Connection, topic_or_tag: str, *, limit: int = 20
) -> list[Lesson]:
    """"จำอะไรเกี่ยวกับ X ไว้บ้าง" → เฉพาะข้อที่ยังไม่ถูกทับและยังไม่ถูกพักไว้

    ค้นแบบ substring ทั้งคอลัมน์ topic และ tags (คำค้นว่าง = ขอดูทั้งหมดที่ยังใช้อยู่)
    เรียงใหม่สุดก่อน เพราะเวลาเอาไปยัดใส่ context ของงาน ตัวที่ใหม่ที่สุดสำคัญที่สุด
    """
    count = _require_limit(limit)
    term = "" if topic_or_tag is None else str(topic_or_tag).strip()

    if not term:
        rows = conn.execute(
            f"SELECT {_LESSON_COLUMNS} FROM lessons WHERE {LIVE_CONDITION} "
            f"ORDER BY created_at DESC, id DESC LIMIT ?",
            (count,),
        ).fetchall()
    else:
        pattern = _like_pattern(term)
        rows = conn.execute(
            f"SELECT {_LESSON_COLUMNS} FROM lessons "
            f"WHERE {LIVE_CONDITION} AND ("
            f"  topic LIKE ? ESCAPE '{_LIKE_ESCAPE}'"
            f"  OR tags LIKE ? ESCAPE '{_LIKE_ESCAPE}')"
            f" ORDER BY created_at DESC, id DESC LIMIT ?",
            (pattern, pattern, count),
        ).fetchall()
    return [_row_to_lesson(row) for row in rows]


def revise(
    conn: sqlite3.Connection,
    topic: str,
    new_content: str,
    when: str | date | datetime | None = None,
) -> tuple[Lesson, Lesson]:
    """"แก้ความจำเรื่อง X เป็น..." → ทับของเก่า คืน (ใหม่, เก่า)

    ยก tags ของก้อนเดิมมาให้ก้อนใหม่ เพราะคำสั่งนี้ไม่มีที่ให้ระบุ tags
    ถ้าปล่อยว่างไว้ ความจำที่แก้แล้วจะหลุดจากการค้นด้วย tag เดิมทันที
    (เช่นแก้เรื่องร้าน แล้ว tag 'restaurant' หาย → ตอนจองครั้งหน้าไม่มีใครดึงมาใช้)

    ไม่มี topic นั้นที่ยังใช้อยู่ → KeyError (ห้ามสร้างใหม่ให้เงียบๆ เพราะ
    "แก้" กับ "จำใหม่" คนละเจตนา และหัวข้อที่พิมพ์ผิดต้องได้ยินว่าไม่เจอ)
    """
    topic_clean = _require_text(topic, "topic")
    current = _rows_for_topic(conn, topic_clean, live_only=True)
    if not current:
        raise KeyError(f"ไม่มีความจำเรื่อง '{topic_clean}' ที่ยังใช้อยู่")

    inherited_tags = _split_tags(current[0]["tags"])
    new_lesson, superseded = remember(conn, topic_clean, new_content, inherited_tags, when)
    assert superseded is not None  # มีของเก่าแน่นอน เพราะเช็คไปแล้วข้างบน
    return new_lesson, superseded


def forget(
    conn: sqlite3.Connection,
    topic: str,
    *,
    confirmed: bool = False,
    reason: str | None = None,
    when: str | date | datetime | None = None,
) -> tuple[bool, list[Lesson]]:
    """"ลืมเรื่อง X" → คืน (ลบไปแล้วหรือยัง, รายการที่เกี่ยวข้อง)

    confirmed=False → **ไม่แตะ DB เลย** แค่คืนรายการที่จะโดนลบให้ไปถามยืนยันก่อน
    (kit: "การลบต้องยืนยันก่อนเสมอ" / บุคลิก: "ถ้าคำสั่งไหนจะทำให้เกิดการ
     เปลี่ยนแปลงถาวร ให้ถามยืนยันก่อนเสมอ")
    confirmed=True → คัดลอกลง lessons_trash ก่อน แล้วค่อยลบจาก lessons

    ทำไมต้องเอาทั้งก้อนที่ถูกทับแล้วและก้อนที่พักไว้ไปด้วย ไม่ใช่เฉพาะก้อนที่ใช้อยู่:
        superseded_by ประกาศไว้ว่า ON DELETE SET NULL — ถ้าลบเฉพาะก้อนล่าสุด
        ก้อนเก่าที่ชี้มาหามันจะกลายเป็น superseded_by = NULL คือ **ฟื้นกลับมามีชีวิต**
        กลายเป็นสั่งลืมแล้วได้ความจำเวอร์ชันเก่ากว่าคืนมาแทน ซึ่งแย่กว่าไม่ลบเสียอีก
    """
    topic_clean = _require_text(topic, "topic")
    rows = _rows_for_topic(conn, topic_clean, live_only=False)
    if not rows:
        raise KeyError(f"ไม่มีความจำเรื่อง '{topic_clean}'")

    lessons = [_row_to_lesson(row) for row in rows]
    if not confirmed:
        # จังหวะที่ 1: ยังไม่ลบ — ตรงนี้ห้ามมี execute ที่เขียน DB เด็ดขาด
        return False, lessons

    stamp, date_key = _stamp(when)
    conn.executemany(
        "INSERT INTO lessons_trash "
        "(original_id, topic, content, tags, deleted_at, deleted_key, reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (item.id, item.topic, item.content, TAG_SEPARATOR.join(item.tags),
             stamp, date_key, reason)
            for item in lessons
        ],
    )
    marks = ", ".join("?" for _ in lessons)
    conn.execute(
        f"DELETE FROM lessons WHERE id IN ({marks})", tuple(item.id for item in lessons)
    )
    conn.commit()
    return True, lessons


# --- ถังขยะ + การพักความจำ ----------------------------------------------------


def restore(
    conn: sqlite3.Connection,
    original_id: int,
    when: str | date | datetime | None = None,
) -> Lesson:
    """กู้จาก trash กลับมาเป็นความจำที่ใช้อยู่

    หมายเหตุ: แถวที่กู้กลับมาจะได้ id ใหม่ (id เดิมอาจถูกแถวอื่นใช้ไปแล้ว)
    ถ้าอยากรู้ด้วยว่าการกู้ครั้งนี้ไปทับของที่ใช้อยู่หรือเปล่า ให้เรียก restore_detailed()
    """
    return restore_detailed(conn, original_id, when)[0]


def restore_detailed(
    conn: sqlite3.Connection,
    original_id: int,
    when: str | date | datetime | None = None,
) -> tuple[Lesson, Lesson | None]:
    """กู้จาก trash + บอกด้วยว่าไปทับก้อนไหน (คืน (ก้อนที่กู้, ก้อนที่ถูกทับ|None))

    มีฟังก์ชันนี้เพิ่มเพราะสัญญาให้ restore() คืนค่าเดียว แต่กติกาบุคลิกบังคับว่า
    "ทับของเก่าต้องบอกว่าทับอันไหน" — ถ้าไม่มีทางรู้ ตัวเรียกจะรายงานไม่ครบ

    ทำไมของที่กู้มาถึงทับของที่ใช้อยู่ (ไม่ใช่กลับมาแบบถูกทับ):
        การกดกู้คือเจตนาล่าสุดของโอม ถ้าให้กลับมาแบบถูกทับไว้ตั้งแต่แรก
        recall() จะไม่เห็นมันเลย = กู้แล้วเหมือนไม่ได้กู้ ซึ่งคือความเงียบแบบที่ H13 ห้าม
    """
    row = conn.execute(
        "SELECT * FROM lessons_trash WHERE original_id = ? "
        "ORDER BY deleted_at DESC, id DESC LIMIT 1",
        (int(original_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"ไม่มีความจำ id {original_id} ในถังขยะ")

    new_lesson, superseded = remember(
        conn, row["topic"], row["content"], _split_tags(row["tags"]), when
    )
    # เอาออกจากถังขยะหลังกู้สำเร็จเท่านั้น — กู้ซ้ำแล้วได้ความจำซ้ำสองก้อนคือบั๊ก
    conn.execute("DELETE FROM lessons_trash WHERE id = ?", (int(row["id"]),))
    conn.commit()
    return new_lesson, superseded


def list_trash(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """ดูของในถังขยะ (ใหม่สุดก่อน) — original_id คือเลขที่ใช้สั่ง restore()"""
    count = _require_limit(limit)
    rows = conn.execute(
        "SELECT id, original_id, topic, content, tags, deleted_at, deleted_key, reason "
        "FROM lessons_trash ORDER BY deleted_at DESC, id DESC LIMIT ?",
        (count,),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "original_id": int(row["original_id"]),
            "topic": row["topic"],
            "content": row["content"],
            "tags": _split_tags(row["tags"]),
            "deleted_at": row["deleted_at"],
            "deleted_key": row["deleted_key"],
            "reason": row["reason"],
        }
        for row in rows
    ]


def list_archived(conn: sqlite3.Connection, limit: int = 20) -> list[Lesson]:
    """"ดูความจำที่พัก" — รายการที่ consolidate() พักไว้ (kit ส่วนที่ 1 รายงานความฝัน)

    ต้องมีฟังก์ชันนี้ ไม่งั้น archived_at จะเป็นหลุมดำ: recall() ไม่คืน
    และไม่มีทางอื่นให้เปิดดู = "ความจำหายเงียบๆ โดยไม่มีใครตรวจ" ตรงตาม H13 เป๊ะ
    """
    count = _require_limit(limit)
    rows = conn.execute(
        f"SELECT {_LESSON_COLUMNS} FROM lessons WHERE archived_at IS NOT NULL "
        f"ORDER BY archived_at DESC, id DESC LIMIT ?",
        (count,),
    ).fetchall()
    return [_row_to_lesson(row) for row in rows]


def unarchive(
    conn: sqlite3.Connection,
    lesson_id: int,
    when: str | date | datetime | None = None,
) -> Lesson:
    """เอาความจำที่พักไว้กลับขึ้นหิ้ง (ล้าง archived_at)

    ล้างแค่ archived_at ไม่ยุ่งกับ superseded_by — ก้อนที่ถูกทับไปแล้วยังถือว่า
    เป็นประวัติ ไม่ใช่ความจริงปัจจุบัน ถ้าโอมอยากให้กลับมาเป็นความจริงปัจจุบันจริงๆ
    ให้สั่ง "จำไว้ว่า..." ด้วยเนื้อความนั้นอีกครั้ง (จะได้มีบันทึกว่าทับอะไรไปตามกติกา)
    """
    stamp, _ = _stamp(when)
    row = conn.execute(
        "SELECT id FROM lessons WHERE id = ?", (int(lesson_id),)
    ).fetchone()
    if row is None:
        raise KeyError(f"ไม่มีความจำ id {lesson_id}")
    conn.execute(
        "UPDATE lessons SET archived_at = NULL, updated_at = ? WHERE id = ?",
        (stamp, int(lesson_id)),
    )
    conn.commit()
    return _fetch(conn, int(lesson_id))


# --- งานตี 2 -----------------------------------------------------------------


def consolidate(
    conn: sqlite3.Connection,
    *,
    unused_days: int = 60,
    when: str | date | datetime | None = None,
) -> dict:
    """จัดระเบียบความจำ (cron ตี 2) — พักเฉพาะก้อนที่ "ถูกทับแล้วและทิ้งไว้นาน"

    เงื่อนไข: superseded_by IS NOT NULL และไม่ได้ถูกใช้มาแล้ว >= unused_days วัน
    นับอายุจาก updated_at เพราะนั่นคือวันที่ก้อนนี้ "หยุดเป็นความจริงปัจจุบัน"
    (ถ้านับจาก created_at ความจำที่เพิ่งถูกทับเมื่อวานแต่จำไว้ตั้งแต่ปีที่แล้ว
     จะโดนพักทันทีทั้งที่เพิ่งใช้อยู่เมื่อวาน)

    **ห้ามลบจริงเด็ดขาด** — แค่ใส่ archived_at (H13) แล้วคืนสรุปให้ digest
    เอาไปเขียนรายงาน "ความฝัน" ตอนเช้า ทุกก้อนที่ถูกพักต้องปรากฏในรายงาน
    และกู้กลับได้ด้วย list_archived() / unarchive()

    รูปคีย์ที่คืน (สัญญาไม่ได้ตรึงไว้ — เลือกให้ตรงกับข้อความตัวอย่างใน kit ส่วนที่ 1):
        date_key, ran_at, unused_days
        archived_count, archived[]        → "พักไว้ N ก้อนที่ไม่ได้ใช้มา ..."
        merged_topics[]                   → "รวมเรื่องซ้ำ N ก้อนเป็นก้อนเดียว (เรื่อง X)"
        live_count, superseded_pending, archived_total, trash_count
        skipped[], nothing_to_report
    """
    if int(unused_days) < 0:
        raise ValueError(f"unused_days ต้องไม่ติดลบ ได้รับ {unused_days!r}")
    threshold = int(unused_days)

    stamp, date_key = _stamp(when)
    today = localdate.local_date(_as_datetime(when))

    candidates = conn.execute(
        f"SELECT {_LESSON_COLUMNS}, updated_at FROM lessons "
        f"WHERE superseded_by IS NOT NULL AND archived_at IS NULL "
        f"ORDER BY created_at ASC, id ASC"
    ).fetchall()

    doomed: list[tuple[Lesson, int]] = []
    skipped: list[dict] = []
    pending = 0
    for row in candidates:
        idle_from = _timestamp_date(row["updated_at"]) or _timestamp_date(row["created_at"])
        if idle_from is None:
            # เวลาอ่านไม่ออก = ไม่รู้ว่าเก่าแค่ไหน → ไม่พัก แต่ต้องฟ้องในรายงาน
            skipped.append({"id": int(row["id"]), "topic": row["topic"],
                            "why": "อ่านเวลาใน updated_at/created_at ไม่ออก"})
            continue
        idle_days = localdate.days_between(idle_from, today)
        if idle_days >= threshold:
            doomed.append((_row_to_lesson(row), idle_days))
        else:
            pending += 1

    if doomed:
        marks = ", ".join("?" for _ in doomed)
        conn.execute(
            f"UPDATE lessons SET archived_at = ?, updated_at = ? WHERE id IN ({marks})",
            (stamp, stamp, *(item.id for item, _ in doomed)),
        )
        conn.commit()

    archived = [
        {
            "id": item.id,
            "topic": item.topic,
            "content": item.content,
            "tags": item.tags,
            "created_at": item.created_at,
            "idle_days": idle_days,
            "archived_at": stamp,
        }
        for item, idle_days in doomed
    ]

    return {
        "date_key": date_key,
        "ran_at": stamp,
        "unused_days": threshold,
        "archived_count": len(archived),
        "archived": archived,
        "merged_topics": _merge_summary(conn, doomed),
        "live_count": _count(conn, f"SELECT COUNT(*) FROM lessons WHERE {LIVE_CONDITION}"),
        "superseded_pending": pending,
        "archived_total": _count(
            conn, "SELECT COUNT(*) FROM lessons WHERE archived_at IS NOT NULL"
        ),
        "trash_count": _count(conn, "SELECT COUNT(*) FROM lessons_trash"),
        "skipped": skipped,
        # kit หลักการข้อ 4: ไม่มีอะไรเปลี่ยนก็บอกบรรทัดเดียวพอ
        "nothing_to_report": not archived and not skipped,
    }


def _merge_summary(
    conn: sqlite3.Connection, doomed: Sequence[tuple[Lesson, int]]
) -> list[dict]:
    """สรุปต่อหัวข้อว่า "รวม N ก้อนเหลือกี่ก้อน" สำหรับประโยคแรกของรายงานความฝัน

    merged_from = ก้อนที่พักไป + ก้อนที่ยังใช้อยู่ของหัวข้อนั้น
    ตรงกับข้อความตัวอย่างใน kit: "รวมเรื่องซ้ำ 3 ก้อนเป็นก้อนเดียว (เรื่อง...)"
    """
    grouped: dict[str, list[Lesson]] = {}
    for item, _ in doomed:
        grouped.setdefault(item.topic, []).append(item)

    summary: list[dict] = []
    for topic, items in grouped.items():
        live = _rows_for_topic(conn, topic, live_only=True)
        kept = len(live)
        summary.append(
            {
                "topic": topic,
                "archived": len(items),
                "kept": kept,
                "merged_from": len(items) + kept,
                "kept_id": int(live[0]["id"]) if live else None,
                "kept_content": live[0]["content"] if live else None,
            }
        )
    summary.sort(key=lambda entry: (-entry["archived"], entry["topic"]))
    return summary


def _count(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row else 0
