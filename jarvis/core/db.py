"""
การเชื่อมต่อ jarvis.db + migration + อ่าน/เขียน preferences

ทุกโมดูลใน core/ ต่อ DB ผ่านไฟล์นี้เท่านั้น ไม่เปิด sqlite3 เองที่อื่น
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
DEFAULT_DB = Path.home() / ".jarvis" / "jarvis.db"

# ค่าที่ถือว่า "ยังไม่ได้กรอก" — phase1-kit ใช้ [ต้องกรอก] เป็นตัวยึด
PLACEHOLDERS = {"", "[ต้องกรอก]", "[TODO]", "TODO", "None", "null"}


class MissingPreference(RuntimeError):
    """preference ที่จำเป็นยังไม่ได้กรอก หรือยังเป็น placeholder อยู่

    ต้องเป็น exception ไม่ใช่คืนค่า default เงียบๆ เพราะค่าอย่าง friday_anchor_date
    ที่ผิด จะทำให้ระบบสลับด้านทั้งหมดโดยไม่มีอะไรฟ้อง (phase1-kit ส่วนที่ 3)
    """


def resolve_db_path(path: str | Path | None = None) -> Path:
    """หาไฟล์ DB ตามลำดับ: พารามิเตอร์ → env JARVIS_DB → ~/.jarvis/jarvis.db"""
    if path is not None:
        return Path(path).expanduser()
    env = os.environ.get("JARVIS_DB")
    if env:
        return Path(env).expanduser()
    return DEFAULT_DB


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """เปิดการเชื่อมต่อ พร้อมตั้งค่าที่ต้องตั้งทุกครั้ง

    - foreign_keys=ON  : SQLite ปิดไว้เป็นค่าเริ่มต้น ต้องเปิดทุก connection
                         ไม่ใช่ครั้งเดียวตอนสร้างตาราง
    - row_factory      : เข้าถึงคอลัมน์ด้วยชื่อได้ อ่านโค้ดง่ายกว่า index ตัวเลข
    """
    target = resolve_db_path(path)
    if str(target) != ":memory:":
        target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return set()
    return {r[0] for r in conn.execute("SELECT version FROM schema_version")}


def migrate(conn: sqlite3.Connection, target_version: int | None = None) -> int:
    """รันไฟล์ schema ที่ยังไม่ได้รัน เรียงตามเลขนำหน้าชื่อไฟล์

    idempotent — รันซ้ำได้ ไฟล์ที่รันไปแล้วจะถูกข้าม

    target_version = หยุดที่เวอร์ชันนี้ (รวมตัวมันเอง) ไม่ระบุ = รันทั้งหมด
        มีไว้ให้เทสต์ตรึงสภาพฐานข้อมูล ณ จุดใดจุดหนึ่งได้ เช่นเทสต์ที่ตรวจว่า
        "seed สดๆ ตามแบบ kit หน้าตาเป็นยังไง" ต้องหยุดที่ 002 ไม่งั้น 003
        ที่เติมค่าจริงของโอมจะทำให้เทสต์นั้นเห็นสภาพที่ไม่ใช่ seed สด
    """
    done = _applied_versions(conn)
    files = sorted(SCHEMA_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    for f in files:
        version = int(f.name[:3])
        if version in done:
            continue
        if target_version is not None and version > target_version:
            break
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (version,))
        conn.commit()
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def get_pref(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
    return row["value"] if row is not None else default


def set_pref(
    conn: sqlite3.Connection, key: str, value: str, notes: str | None = None
) -> None:
    conn.execute(
        """INSERT INTO preferences (key, value, notes, updated_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(key) DO UPDATE SET
             value      = excluded.value,
             notes      = COALESCE(excluded.notes, preferences.notes),
             updated_at = datetime('now')""",
        (key, value, notes),
    )
    conn.commit()


def require_pref(conn: sqlite3.Connection, key: str) -> str:
    """อ่าน preference ที่ขาดไม่ได้ — ไม่มีหรือยังเป็น placeholder = ระเบิดทันที

    ดังกว่าเงียบดีกว่า: ค่าที่ผิดแบบเงียบๆ จะไปโผล่เป็น digest ที่บอกวันผิด
    ซึ่งกว่าจะรู้ตัวก็ผ่านไปหลายวันแล้ว
    """
    value = get_pref(conn, key)
    if value is None or value.strip() in PLACEHOLDERS:
        raise MissingPreference(
            f"preference '{key}' ยังไม่ได้กรอก (ค่าปัจจุบัน: {value!r})\n"
            f"กรอกก่อนใช้งาน:  UPDATE preferences SET value='...' WHERE key='{key}';"
        )
    return value.strip()
