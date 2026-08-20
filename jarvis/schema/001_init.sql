-- =============================================================================
-- jarvis.db — schema เริ่มต้น (Phase 1)
-- =============================================================================
-- ที่มาของแต่ละตาราง:
--   [v3 verbatim] = คัดลอกจาก jarvis-build-spec-v3.md §3 ตรงๆ ไม่แก้
--   [kit]         = คอลัมน์มาจาก jarvis-phase1-kit.md ส่วนที่ 3 (seed data จริง)
--   [inferred]    = spec v3 บอกว่า "ตาม spec v2" แต่ไม่มีไฟล์ v2 ให้ → อนุมานจากบริบท
--                   ⚠️ ตรวจกับ spec v2 ก่อนใช้จริง ถ้าหาไฟล์เจอ
--
-- กฎเหล็กข้อ 3: คอลัมน์ที่เก็บ "วัน" เป็น TEXT 'YYYY-MM-DD' ที่มาจาก
-- localDateKey() แบบ Asia/Bangkok เสมอ — ห้ามใช้ DATE('now') ของ SQLite
-- เพราะ SQLite คิดเป็น UTC ซึ่งจะเพี้ยนไป 7 ชั่วโมง
-- =============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- --- routines [kit] ----------------------------------------------------------
-- งานที่ทำซ้ำเป็นรอบ มี 2 แบบ:
--   แบบนับวัน  (interval_days) เช่น ไดโอดทุก 14 วัน, คิ้วทุก 7 วัน
--   แบบวันประจำ (day_of_week)  เช่น ตัดผมทุกวันอังคาร
-- ต้องมีอย่างใดอย่างหนึ่ง ห้ามมีทั้งคู่หรือไม่มีเลย (บังคับด้วย CHECK)
CREATE TABLE IF NOT EXISTS routines (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,        -- 'diode' | 'eyebrow' | 'haircut'
  name_th       TEXT NOT NULL,               -- ชื่อที่เอาไปแสดงในข้อความ
  interval_days INTEGER,                     -- รอบเป็นจำนวนวัน
  day_of_week   INTEGER,                     -- 0=จันทร์ ... 6=อาทิตย์ (ตรงกับ Python)
  last_done     TEXT,                        -- 'YYYY-MM-DD' จาก localDateKey()
  notes         TEXT,
  active        INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  CHECK (day_of_week IS NULL OR (day_of_week BETWEEN 0 AND 6)),
  CHECK (interval_days IS NULL OR interval_days > 0),
  -- ต้องเป็นแบบใดแบบหนึ่งเท่านั้น
  CHECK ((interval_days IS NOT NULL) <> (day_of_week IS NOT NULL))
);

-- --- preferences [kit] -------------------------------------------------------
-- ค่าคงที่ของระบบ เก็บเป็น key-value เพื่อแก้ได้โดยไม่ต้องแก้โค้ด
CREATE TABLE IF NOT EXISTS preferences (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  notes      TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- --- class_schedule [kit] ----------------------------------------------------
-- ตารางเรียน ใช้ให้ digest เช้าบอกคาบแรกและจำนวนคาบ
CREATE TABLE IF NOT EXISTS class_schedule (
  day_of_week   INTEGER PRIMARY KEY,         -- 0=จันทร์ ... 4=ศุกร์
  first_subject TEXT NOT NULL,               -- วิชาคาบแรก 08:20
  period_count  TEXT NOT NULL,               -- '7' หรือ 'ครึ่งวัน' → เก็บเป็น TEXT
  notes         TEXT,
  CHECK (day_of_week BETWEEN 0 AND 6)
);

-- --- lessons [kit §5 + red-team H13] -----------------------------------------
-- ความจำที่โอมสอน Jarvis
-- H13: ห้ามเป็น append-only ล้วน ไม่งั้นจะมี 2 ข้อขัดกันแล้วระบบไม่รู้ว่าอันไหนใหม่
--      → มี superseded_by ชี้ว่าถูกทับด้วยข้อไหน และตอนดึง context เอาเฉพาะข้อล่าสุด
CREATE TABLE IF NOT EXISTS lessons (
  id             INTEGER PRIMARY KEY,
  topic          TEXT NOT NULL,              -- หัวเรื่องสำหรับค้นและทับ เช่น 'ร้านกาแฟ'
  content        TEXT NOT NULL,              -- เนื้อความที่จำ
  tags           TEXT NOT NULL DEFAULT '',   -- คั่นด้วยคอมมา เช่น 'restaurant,booking'
  source         TEXT NOT NULL DEFAULT 'chat',
  superseded_by  INTEGER REFERENCES lessons(id) ON DELETE SET NULL,
  archived_at    TEXT,                       -- consolidation ตี 2 mark ตรงนี้ ไม่ลบจริง
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_lessons_topic  ON lessons(topic);
CREATE INDEX IF NOT EXISTS idx_lessons_live   ON lessons(superseded_by, archived_at);

-- --- lessons_trash [kit §5 + red-team H13] -----------------------------------
-- ลบ = ย้ายมาที่นี่ก่อนเสมอ กู้คืนได้ (เผื่อสั่งลบผิด)
CREATE TABLE IF NOT EXISTS lessons_trash (
  id            INTEGER PRIMARY KEY,
  original_id   INTEGER NOT NULL,
  topic         TEXT NOT NULL,
  content       TEXT NOT NULL,
  tags          TEXT NOT NULL DEFAULT '',
  deleted_at    TEXT NOT NULL DEFAULT (datetime('now')),
  deleted_key   TEXT NOT NULL,               -- localDateKey() ตอนลบ
  reason        TEXT
);

-- --- bookings [inferred] -----------------------------------------------------
-- ⚠️ spec v3 บอก "ตามตาราง spec v2" แต่ไม่มีไฟล์ v2 → คอลัมน์นี้อนุมานจาก
--    Phase 3 ข้อ 1: make_booking(kind, place, date, time, party_size)
--    + กติกา "ซองคำตอบล่วงหน้า" ใน Phase 3 ข้อ 2
CREATE TABLE IF NOT EXISTS bookings (
  id             INTEGER PRIMARY KEY,
  kind           TEXT NOT NULL,              -- 'restaurant'|'eyebrow'|'laser'|'hotel'
  place_name     TEXT NOT NULL,
  place_id       INTEGER REFERENCES favorite_places(id) ON DELETE SET NULL,
  booking_date   TEXT NOT NULL,              -- 'YYYY-MM-DD' จาก localDateKey()
  booking_time   TEXT,                       -- 'HH:MM' เวลาไทย
  party_size     INTEGER,
  status         TEXT NOT NULL DEFAULT 'pending',
                 -- pending|calling|confirmed|failed|cancelled|needs_input
  fallback_slots TEXT,                       -- JSON: ซองคำตอบล่วงหน้า ["19:30","20:00"]
  result_note    TEXT,                       -- ผลจริงที่ร้านตอบ
  calendar_event_id TEXT,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
  CHECK (kind IN ('restaurant','eyebrow','laser','hotel')),
  CHECK (status IN ('pending','calling','confirmed','failed','cancelled','needs_input')),
  CHECK (party_size IS NULL OR party_size > 0)
);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(booking_date, status);

-- --- call_logs [inferred] ----------------------------------------------------
-- ⚠️ อนุมาน — บันทึกสายที่โทรออกจริง (Phase 3) ใช้ตรวจ latency ตาม H5
CREATE TABLE IF NOT EXISTS call_logs (
  id             INTEGER PRIMARY KEY,
  booking_id     INTEGER REFERENCES bookings(id) ON DELETE CASCADE,
  phone          TEXT NOT NULL,
  provider       TEXT,                       -- 'twilio' | 'vapi' | ...
  started_at     TEXT NOT NULL DEFAULT (datetime('now')),
  ended_at       TEXT,
  duration_sec   INTEGER,
  outcome        TEXT,                       -- 'answered'|'no_answer'|'busy'|'failed'
  transcript     TEXT,
  max_turn_latency_ms INTEGER,               -- H5: เกณฑ์ผ่านคือ ≤2 วิต่อ turn
  cost_usd       REAL
);

-- --- notifications_sent [inferred + red-team H14] ----------------------------
-- ⚠️ อนุมาน — H14: LINE ฟรีแค่ 300 ข้อความ/เดือน ต้องนับเองไม่งั้นหมดโควตาตอน debug
--    month_key เป็น 'YYYY-MM' แบบเวลาไทย เพื่อให้รอบเดือนตรงกับที่ LINE นับ
CREATE TABLE IF NOT EXISTS notifications_sent (
  id          INTEGER PRIMARY KEY,
  channel     TEXT NOT NULL,                 -- 'line' | 'telegram'
  kind        TEXT NOT NULL,                 -- 'digest_morning'|'digest_evening'|...
  sent_at     TEXT NOT NULL DEFAULT (datetime('now')),
  date_key    TEXT NOT NULL,                 -- localDateKey() ตอนส่ง
  month_key   TEXT NOT NULL,                 -- 'YYYY-MM' เวลาไทย ใช้นับโควตา
  counts_toward_quota INTEGER NOT NULL DEFAULT 1,  -- Telegram = 0 (ฟรีไม่จำกัด)
  ok          INTEGER NOT NULL DEFAULT 1,
  error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_notif_quota ON notifications_sent(channel, month_key, counts_toward_quota);
-- กันส่ง digest ซ้ำวันเดียวกัน (cron ยิงซ้ำ / restart แล้วยิงใหม่)
CREATE UNIQUE INDEX IF NOT EXISTS idx_notif_once_per_day
  ON notifications_sent(channel, kind, date_key) WHERE ok = 1;

-- --- audit_log [v3 verbatim §3] ----------------------------------------------
-- คัดจาก spec v3 ตรงๆ + เพิ่ม index
-- red-team H11: Jarvis ถือ token ระดับ manager ของระบบบัญชี → ต้องมีบันทึกทุก request
CREATE TABLE IF NOT EXISTS audit_log (
  id     INTEGER PRIMARY KEY,
  at     DATETIME DEFAULT CURRENT_TIMESTAMP,
  target TEXT NOT NULL,                      -- 'scaccounting' | 'twilio' | 'ha' | ...
  action TEXT NOT NULL,                      -- endpoint/คำสั่งที่เรียก
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_log(target, at);

-- --- favorite_places [v3 verbatim §3] ----------------------------------------
-- คัดจาก spec v3 ตรงๆ
CREATE TABLE IF NOT EXISTS favorite_places (
  id         INTEGER PRIMARY KEY,
  kind       TEXT NOT NULL,                  -- 'restaurant'|'eyebrow'|'laser'|'hotel'
  name       TEXT NOT NULL,
  phone      TEXT,
  notes      TEXT,                           -- เวลาที่ชอบไป ชื่อช่างประจำ สิ่งที่ร้านมักถาม
  is_default INTEGER DEFAULT 0               -- 1 = ร้านประจำของ kind นั้น
);
-- ร้านประจำของแต่ละ kind ต้องมีได้ไม่เกิน 1 ร้าน
CREATE UNIQUE INDEX IF NOT EXISTS idx_places_one_default
  ON favorite_places(kind) WHERE is_default = 1;

-- --- schema_version ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO schema_version (version) VALUES (1);
