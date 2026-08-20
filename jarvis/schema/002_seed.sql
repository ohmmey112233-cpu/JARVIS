-- =============================================================================
-- jarvis.db — seed data (Phase 1)
-- =============================================================================
-- ที่มา: jarvis-phase1-kit.md "ส่วนที่ 3 — Seed Data" คัดลอกมาตรงๆ ทุกค่า
-- ห้ามแก้ค่าในไฟล์นี้เพื่อ "ให้เทสต์ผ่าน" — ถ้าค่าจริงเปลี่ยน ให้แก้ที่ kit ก่อน
--
-- ใช้ INSERT OR IGNORE ทุกแถว เพราะ migrate() อาจถูกเรียกซ้ำ (restart / restore backup)
-- และที่สำคัญกว่า: ถ้าโอมกรอกค่าจริงทับ placeholder ไปแล้ว การรันซ้ำต้องไม่ล้างทิ้ง
-- (OR REPLACE จะลบค่าที่กรอกเอง — ห้ามใช้เด็ดขาด)
--
-- ไม่เขียน created_at / updated_at เอง ปล่อยให้ DEFAULT ของ 001 ทำงาน:
-- คอลัมน์พวกนี้เป็น metadata ว่าแถวถูกสร้างเมื่อไหร่ ไม่ใช่ข้อมูลธุรกิจที่เอาไปคำนวณรอบ
-- ส่วนคอลัมน์ที่เป็น "วัน" ของธุรกิจ (last_done) เว้นว่างไว้ให้ localDateKey() เติมทีหลัง
--
-- -----------------------------------------------------------------------------
-- ⚠️  3 ค่าที่โอมต้องกรอกเองก่อนใช้งานจริง (kit ส่วนที่ 3 ท้ายหัวข้อ)
-- -----------------------------------------------------------------------------
-- 1) preferences.friday_anchor_date  ← seed เป็น '[ต้องกรอก]'
--    รูปแบบ: 'YYYY-MM-DD:home' หรือ 'YYYY-MM-DD:hotel' (ศุกร์ล่าสุดที่ผ่านมา)
--    kit เตือนไว้ว่า "ถ้าผิด ระบบจะสลับกลับด้านทั้งหมด" — เดาไม่ได้ ต้องถามเจ้าตัว
--    จึง seed เป็น placeholder ให้ require_pref() ยก MissingPreference ทันที
--    ดีกว่าปล่อยให้ระบบเดินต่อเงียบๆ แล้วบอกวันกลับบ้านสลับด้านอยู่หลายสัปดาห์
--
--      UPDATE preferences SET value = '2026-08-14:home'
--       WHERE key = 'friday_anchor_date';        -- แก้วันที่/สถานะให้ตรงของจริง
--
-- 2) routines.last_done ของ 'diode'   ← seed เป็น NULL
-- 3) routines.last_done ของ 'eyebrow' ← seed เป็น NULL
--    NULL = "ยังไม่เคยทำ" ซึ่ง routines.py ถือว่าถึงรอบทันที
--    เลือก NULL แทน '[ต้องกรอก]' เพราะคอลัมน์นี้ถูกเอาไปคำนวณวันที่โดยตรง
--    สตริงที่ไม่ใช่วันที่จะทำให้ to_date() ระเบิดกลางทาง แทนที่จะเตือนเบาๆ ว่าถึงรอบ
--
--      UPDATE routines SET last_done = '2026-08-12' WHERE name = 'diode';
--      UPDATE routines SET last_done = '2026-08-18' WHERE name = 'eyebrow';
--
--    ตรวจว่ากรอกครบแล้วหรือยัง:
--      SELECT key, value FROM preferences WHERE value = '[ต้องกรอก]';
--      SELECT name, last_done FROM routines WHERE last_done IS NULL AND interval_days IS NOT NULL;
-- =============================================================================

-- --- routines [kit ส่วนที่ 3 ตาราง routines] ---------------------------------
-- แบบนับวัน (interval_days) กับแบบวันประจำ (day_of_week) ห้ามมีทั้งคู่ในแถวเดียว
-- CHECK ใน 001 บังคับไว้แล้ว จึงต้องใส่ NULL ให้อีกฝั่งเสมอ
INSERT OR IGNORE INTO routines (name, name_th, interval_days, day_of_week, last_done, notes) VALUES
  ('diode',   'เลเซอร์ไดโอดกำจัดขน', 14,   NULL, NULL, NULL),
  ('eyebrow', 'ทำคิ้ว',                7,   NULL, NULL, NULL),
  -- day_of_week = 1 คืออังคาร (0=จันทร์ ตรงกับ date.weekday() ของ Python)
  -- ไม่ต้องมี last_done เพราะแบบวันประจำดูจากวันในสัปดาห์ ไม่ได้นับวันจากครั้งก่อน
  ('haircut', 'ตัดผม',              NULL,      1, NULL,
   'ร้านเกษมเกษา ปั๊ม ปตท. บ้านสัน (ตอนเย็น)');

-- --- preferences [kit ส่วนที่ 3 ตาราง preferences] ---------------------------
-- ทั้ง 12 คีย์ตามลำดับในตารางของ kit — notes คือคอลัมน์ "หมายเหตุ" ของ kit
INSERT OR IGNORE INTO preferences (key, value, notes) VALUES
  ('wake_time',           '06:50',                              NULL),
  ('wake_time_wed',       '06:30',                              'วันพุธตื่นเร็วกว่าปกติ 20 นาที'),
  ('school_arrive_by',    '07:35',                              'ถึงโรงเรียน 07:30-07:40'),
  ('home_by_normal',      '17:45',                              'กลับหอ 17:30-18:00'),
  ('rd_end_estimate',     '16:45',                              'ร.ด. วันพุธ เลิก ~16:30-17:00'),
  -- ค่าเดียวในไฟล์นี้ที่จงใจ seed เป็น placeholder — ดูเหตุผลในหัวไฟล์
  ('friday_anchor_date',  '[ต้องกรอก]',
   '⚠️ ศุกร์ล่าสุดที่ผ่านมา ระบุ hotel หรือ home — รูปแบบ YYYY-MM-DD:home | YYYY-MM-DD:hotel'),
  ('dorm_address',        'หอพักมงฟอร์ตเรสซิเดนซ์',                'ต้นทางคำนวณเส้นทางเช้า'),
  ('school_address',      'โรงเรียนมงฟอร์ตวิทยาลัย เชียงใหม่',        NULL),
  ('home_address',        'จอมทอง เชียงใหม่',                      'ปลายทางศุกร์สัปดาห์กลับบ้าน'),
  ('aqi_alert_threshold', '100',                                'เกินเท่านี้ถึงเตือนใส่แมสก์'),
  ('line_quota_warn_at',  '250',                                'เตือนเมื่อใกล้เต็ม 300'),
  -- เก็บไว้เป็นหลักฐานว่าระบบตั้งใจใช้โซนไหน ตัวโค้ดยึด core.localdate.TZ เป็นหลัก
  ('timezone',            'Asia/Bangkok',                       NULL);

-- --- class_schedule [kit ส่วนที่ 3 ตารางเรียน] -------------------------------
-- period_count เป็น TEXT เพราะวันพุธไม่ใช่ตัวเลข ('ครึ่งวัน') — ดู 001
-- มีแค่ จ.-ศ. (0-4) เสาร์/อาทิตย์ไม่มีแถว = ไม่มีเรียน ให้ digest ข้ามหัวข้อไปเลย
INSERT OR IGNORE INTO class_schedule (day_of_week, first_subject, period_count, notes) VALUES
  (0, 'ชีววิทยา',            '7',        NULL),
  (1, 'คณิตศาสตร์เพิ่มเติม',  '7',        'เย็น: ตัดผม'),
  (2, 'ชีววิทยา',            'ครึ่งวัน',   'บ่าย ร.ด.'),
  (3, 'เคมี',                '7',        NULL),
  (4, 'ชีววิทยา',            '7',        NULL);

INSERT OR IGNORE INTO schema_version (version) VALUES (2);
