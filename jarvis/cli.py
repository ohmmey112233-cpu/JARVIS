"""
สะพานระหว่าง Hermes กับโค้ดแกน

Hermes skill เรียกคำสั่งเชลล์ ไม่ได้ import Python โดยตรง ไฟล์นี้จึงเปิด core/
ออกมาเป็นคำสั่งบรรทัดเดียว คืนผลเป็น JSON ให้ agent อ่านต่อได้แน่นอน

ตั้งใจให้ "บาง" — ไม่มีตรรกะทางธุรกิจในไฟล์นี้เลย มีแต่การแปลง argv เป็นการเรียก
ฟังก์ชันใน core/ แล้วแปลงผลกลับเป็น JSON
เหตุผล: ถ้า gate trial ไม่ผ่านแล้วต้องไป Track B ไฟล์นี้คือไฟล์เดียวที่ทิ้ง
โค้ดใน core/ ใช้ต่อได้ทั้งหมดโดยไม่ต้องแก้

    python3 -m cli routines due
    python3 -m cli memory remember --topic "ร้านกาแฟ" --content "..."
    python3 -m cli friday state
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from core import db


def _out(payload: Any, *, ok: bool = True, code: int = 0) -> int:
    """พิมพ์ผลเป็น JSON บรรทัดเดียว — agent parse ได้แน่นอนกว่าอ่านข้อความอิสระ"""
    print(json.dumps({"ok": ok, "data": payload}, ensure_ascii=False, default=str))
    return code


def _err(message: str, *, code: int = 1) -> int:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False), file=sys.stderr)
    return code


def _rows(items: Any) -> Any:
    """แปลงผลจาก core/ ให้เป็นอะไรที่ json.dumps รับได้

    ⚠️ ลำดับการเช็คสำคัญมาก: NamedTuple "เป็น" tuple ด้วย
    ถ้าเช็ค isinstance(x, tuple) ก่อน NamedTuple จะถูกแปลงเป็น array
    แล้วฝั่งที่อ่านจะเข้าถึงด้วยชื่อคีย์ไม่ได้ ต้องเช็ค _asdict ก่อนเสมอ
    """
    if hasattr(items, "_asdict"):          # NamedTuple — ต้องมาก่อน tuple
        return {k: _rows(v) for k, v in items._asdict().items()}
    if hasattr(items, "keys"):             # sqlite3.Row
        return {k: _rows(items[k]) for k in items.keys()}
    if isinstance(items, (list, tuple)):
        return [_rows(i) for i in items]
    return items


# --- routines ----------------------------------------------------------------

def cmd_routines(args: argparse.Namespace, conn) -> int:
    from core import routines

    if args.action == "list":
        return _out(_rows(routines.list_routines(conn)))
    if args.action == "due":
        return _out(_rows(routines.due_today(conn)))
    if args.action == "upcoming":
        return _out(_rows(routines.upcoming(conn, days=args.days)))
    if args.action == "status":
        return _out(_rows(routines.status(conn, args.name)))
    if args.action == "done":
        return _out(_rows(routines.mark_done(conn, args.name)))
    return _err(f"ไม่รู้จักคำสั่ง routines '{args.action}'")


# --- memory ------------------------------------------------------------------

def cmd_memory(args: argparse.Namespace, conn) -> int:
    from core import memory

    if args.action == "remember":
        tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
        new, old = memory.remember(conn, args.topic, args.content, tags)
        # ส่ง superseded กลับไปด้วยเสมอ เพื่อให้ Jarvis บอกได้ว่า "ทับอันไหน"
        return _out({"lesson": _rows(new), "superseded": _rows(old) if old else None})
    if args.action == "recall":
        return _out(_rows(memory.recall(conn, args.topic)))
    if args.action == "revise":
        new, old = memory.revise(conn, args.topic, args.content)
        return _out({"lesson": _rows(new), "superseded": _rows(old)})
    if args.action == "forget":
        # ไม่ใส่ --confirm = แค่ดูว่าจะลบอะไร ยังไม่ลบจริง (kit: ต้องยืนยันก่อนเสมอ)
        deleted, affected = memory.forget(conn, args.topic, confirmed=args.confirm)
        return _out({"deleted": deleted, "lessons": _rows(affected)})
    if args.action == "restore":
        return _out(_rows(memory.restore(conn, args.id)))
    if args.action == "trash":
        return _out(_rows(memory.list_trash(conn)))
    if args.action == "consolidate":
        return _out(memory.consolidate(conn))
    return _err(f"ไม่รู้จักคำสั่ง memory '{args.action}'")


# --- friday ------------------------------------------------------------------

def cmd_friday(args: argparse.Namespace, conn) -> int:
    from core import friday

    plan = friday.friday_state_from_db(conn)
    return _out(_rows(plan))


# --- booking -----------------------------------------------------------------

def cmd_booking(args: argparse.Namespace, conn) -> int:
    from core import booking

    if args.action == "create":
        slots = [s.strip() for s in (args.fallback or "").split(",") if s.strip()]
        bid = booking.make_booking(
            conn, args.kind, place=args.place, date=args.date,
            time=args.time, party_size=args.party_size, fallback_slots=slots,
        )
        return _out({"booking_id": bid})
    if args.action == "places":
        rows = conn.execute(
            "SELECT * FROM favorite_places WHERE kind = ? ORDER BY is_default DESC",
            (args.kind,),
        ).fetchall()
        return _out(_rows(rows))
    return _err(f"ไม่รู้จักคำสั่ง booking '{args.action}'")


# --- doctor ------------------------------------------------------------------

def cmd_doctor(args: argparse.Namespace, conn) -> int:
    """ตรวจว่าค่าที่ต้องกรอกเองกรอกครบหรือยัง — เรียกก่อนใช้งานจริงครั้งแรก"""
    from core.db import MissingPreference

    problems: list[str] = []
    for key in ("friday_anchor_date",):
        try:
            db.require_pref(conn, key)
        except MissingPreference as exc:
            problems.append(str(exc).splitlines()[0])

    never_done = conn.execute(
        "SELECT name, name_th FROM routines WHERE last_done IS NULL AND interval_days IS NOT NULL"
    ).fetchall()
    for row in never_done:
        problems.append(
            f"routine '{row['name']}' ({row['name_th']}) ยังไม่มี last_done — "
            f"กรอกก่อนไม่งั้นจะเตือนว่าถึงรอบทุกวัน"
        )
    return _out({"ready": not problems, "problems": problems}, code=0 if not problems else 2)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jarvis", description="Jarvis core CLI")
    p.add_argument("--db", help="ที่อยู่ไฟล์ jarvis.db (ไม่ระบุ = env JARVIS_DB หรือ ~/.jarvis/jarvis.db)")
    sub = p.add_subparsers(dest="group", required=True)

    r = sub.add_parser("routines", help="งานที่ทำเป็นรอบ")
    r.add_argument("action", choices=["list", "due", "upcoming", "status", "done"])
    r.add_argument("--name"); r.add_argument("--days", type=int, default=7)
    r.set_defaults(func=cmd_routines)

    m = sub.add_parser("memory", help="ความจำ (จำ/ดู/แก้/ลืม)")
    m.add_argument("action", choices=["remember", "recall", "revise", "forget", "restore", "trash", "consolidate"])
    m.add_argument("--topic"); m.add_argument("--content"); m.add_argument("--tags")
    m.add_argument("--id", type=int)
    m.add_argument("--confirm", action="store_true", help="ยืนยันลบจริง (ไม่ใส่ = แค่ดูว่าจะลบอะไร)")
    m.set_defaults(func=cmd_memory)

    f = sub.add_parser("friday", help="ศุกร์สลับสัปดาห์")
    f.add_argument("action", nargs="?", default="state", choices=["state"])
    f.set_defaults(func=cmd_friday)

    b = sub.add_parser("booking", help="การจอง")
    b.add_argument("action", choices=["create", "places"])
    b.add_argument("--kind", required=True); b.add_argument("--place")
    b.add_argument("--date"); b.add_argument("--time")
    b.add_argument("--party-size", type=int, dest="party_size")
    b.add_argument("--fallback", help="ซองคำตอบล่วงหน้า คั่นด้วยคอมมา เช่น '19:30,20:00'")
    b.set_defaults(func=cmd_booking)

    d = sub.add_parser("doctor", help="ตรวจว่าค่าที่ต้องกรอกเองครบหรือยัง")
    d.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = db.connect(args.db)
    db.migrate(conn)
    try:
        return args.func(args, conn)
    except db.MissingPreference as exc:
        return _err(str(exc), code=2)
    except (KeyError, LookupError) as exc:
        return _err(f"ไม่พบข้อมูล: {exc}", code=3)
    except ValueError as exc:
        return _err(f"ข้อมูลไม่ถูกต้อง: {exc}", code=4)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
