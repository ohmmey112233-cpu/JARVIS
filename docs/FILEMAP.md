# แผนที่ไฟล์ทั้งหมด — เปิดไฟล์นี้ก่อน

> repo นี้มี 58 ไฟล์ · โค้ด Python 8,614 บรรทัด · สคริปต์ shell 1,619 บรรทัด · **370 เทสต์ผ่านทั้งหมด**
> ทุกเทสต์รันได้แบบ offline ไม่ต้องมี API key ไม่ต้องมี VPS

```bash
git clone https://github.com/ohmmey112233-cpu/JARVIS.git ~/jarvis
cd ~/jarvis && git checkout claude/hermes-agent-phase-0b-upmjjr
PYTHONPATH=jarvis python3 -m unittest discover -s jarvis/tests    # ควรได้ OK 370 เทสต์
```

---

## 🚀 อยากติดตั้งเลย — อ่าน 3 ไฟล์นี้พอ

| ไฟล์ | ใช้ตอนไหน |
|---|---|
| **`docs/setup-when-mac-arrives.md`** | ⭐ **เริ่มที่นี่** — เช็คลิสต์ติ๊กได้ตั้งแต่สมัคร API → สร้าง droplet → ติดตั้ง → gate trial |
| `docs/digitalocean-setup.md` | คู่มือ DigitalOcean ทีละคลิก (⛔ ต้องใช้ Droplets ห้าม App Platform) |
| `docs/troubleshooting.md` | ติดตรงไหนเปิดอันนี้ เรียงตามอาการที่เจอบ่อย |

## 🖥 สคริปต์ — รันตามลำดับเลข

| ไฟล์ | รันในฐานะ | ทำอะไร | เวลา |
|---|---|---|---|
| `scripts/00-digitalocean-prep.sh` | **root** | swap 2GB · timezone ไทย · สร้าง user `jarvis` · firewall · lingering | 2-3 นาที |
| `scripts/01-install-hermes.sh` | jarvis | ติดตั้ง Hermes + ตรวจ dependency + บันทึกเวอร์ชัน | 5-15 นาที |
| `scripts/02-configure-jarvis.sh` | jarvis | ตั้ง Claude เป็นโมเดลหลัก + เขียนค่าลับลง `~/.hermes/.env` | 10 วินาที |
| `scripts/03-start-gateway.sh` | jarvis | ติดตั้ง gateway เป็น systemd service | 30 วินาที |
| `scripts/verify-phase0b.sh` | jarvis | ✅ ตรวจ 7 หมวด + **ยิง API จริง**เช็คว่า key ใช้ได้ | 1 นาที |

**gate trial (3 วัน):** `gate-trial-setup.sh --smoke` → ทดสอบ → `gate-trial-teardown.sh`
**หลังผ่าน gate:** `phase1-digests-setup.sh` (ตั้ง cron digest 5 job) · `backup-jarvis.sh` + `restore-jarvis.sh`

> ทุกสคริปต์ **รันซ้ำได้** (idempotent) และผ่าน shellcheck แล้ว

## 🧠 โค้ดแกน — `jarvis/core/` ไม่ผูกกับ Hermes เลย

Python ล้วน + stdlib + sqlite3 เท่านั้น **ไม่มีการเรียก LLM ไม่มีการต่อเน็ต**
ถ้า gate trial ไม่ผ่านแล้วต้องไป Track B โฟลเดอร์นี้ยกไปใช้ต่อได้ทั้งก้อน

| ไฟล์ | หน้าที่ | เทสต์ |
|---|---|---|
| `localdate.py` | ⚠️ **กฎเหล็กข้อ 3** — `local_date_key()` แบบ Asia/Bangkok ทุกที่ที่ถามว่า "วันนี้วันไหน" | (ใช้ร่วมทุกตัว) |
| `db.py` | เปิด DB · migration · `require_pref()` ที่ระเบิดเมื่อเจอค่ายังไม่กรอก | — |
| `friday.py` | ศุกร์กลับบ้าน/โรงแรม — **คาดเดา + ยืนยันรายสัปดาห์** · ประตู Sushiro (H10) | 39 |
| `routines.py` | ไดโอด 14 วัน · คิ้ว 7 วัน · ตัดผมทุกอังคาร | 42 |
| `memory.py` | จำ/ดู/แก้/ลืม + `superseded_by` + ถังขยะกู้คืนได้ (H13) | 47 |
| `digest.py` | เรนเดอร์ข้อความ 8 แบบ **ตรงกับ kit ทีละตัวอักษร** ไม่เรียก LLM | 19 |
| `assemble.py` | สะพาน DB → ข้อความ | 12 |
| `fetchers.py` | ดึง Longdo/Air4Thai/Calendar · API ล่มตัวเดียวไม่พาทั้งก้อนพัง | 25 |
| `booking.py` | tool กลาง 4 ประเภท + ซองคำตอบล่วงหน้า (ยังโทรจริงไม่ได้) | 46 |
| `webhook.py` | รับคำสั่งเสียงจาก Siri Shortcut · `hmac.compare_digest` | 55 |
| `scaccounting.py` | ⚠️ **H11** — whitelist 9 GET endpoint · audit ทุก request · ไม่มีฟังก์ชันเขียนเลย | 12 |
| `cli.py` | สะพาน Hermes ↔ core คืน JSON (ยกเว้น `digest` ที่คืนข้อความล้วน) | 17 |

## 🗄 ฐานข้อมูล — `jarvis/schema/` รันเรียงเลขอัตโนมัติ

| ไฟล์ | เนื้อหา |
|---|---|
| `001_init.sql` | 11 ตาราง · `audit_log`+`favorite_places` คัดจาก spec v3 ตรงๆ |
| `002_seed.sql` | ข้อมูลจริงจาก phase1-kit (routine 3 ตัว · preference 12 ค่า · ตารางเรียน) |
| `003_ohm_values.sql` | anchor ศุกร์ `2026-08-14:hotel` · last_done ไดโอด/คิ้ว `2026-08-15` |
| `004_friday_overrides.sql` | ตารางยืนยันศุกร์รายสัปดาห์ |
| `005` + `006` | พิกัดบ้าน/หอ/โรงเรียน |

## 🔌 Hermes skills — `skills/` บางมาก ไม่มีตรรกะ

`jarvis-routines` · `jarvis-memory` · `jarvis-digest` · `jarvis-booking`
แค่บอก agent ว่าเมื่อไหร่ควรเรียก CLI และตอบยังไง — ตรรกะจริงอยู่ใน `core/` หมด

## 📖 เอกสารอ้างอิง

| ไฟล์ | เนื้อหา |
|---|---|
| `jarvis/CONTRACTS.md` | API ของทุกโมดูล **อ่านก่อนแก้โค้ด** |
| `docs/architecture.md` | ทำไมแยก `core/` ออกจาก `skills/` + ไหลของข้อมูล |
| `docs/verification-log.md` | ⭐ อะไรพิสูจน์แล้ว อะไรยัง + **กับดัก 4 ข้อที่คนรับช่วงต้องรู้** |
| `docs/gate-trial.md` | ชุดทดสอบ 3 ข้อ + ตารางกรอกผล + เกณฑ์ Track A/B |
| `docs/phase1-checklist.md` | เกณฑ์ตรวจรับ A-F รวมเกณฑ์สุดท้าย 25/30 วัน |
| `docs/backup.md` | ตั้ง cron 03:30 · rclone ไป R2 · ขั้นตอนซ้อม restore |
| `jarvis/prompts/personality.md` | บุคลิก Jarvis — **แก้ที่เดียวมีผลทั้งระบบ** |

---

## ⚠️ 5 ข้อที่ต้องรู้ก่อนแตะอะไร

1. **`friday_anchor_date` ผิด = ทุกศุกร์ผิดทั้งปีโดยไม่มีอะไรฟ้อง** — ตอนนี้ตั้ง `2026-08-14:hotel`
   และการสลับเป็นแค่**การคาดเดา** ระบบจะถามยืนยันทุกสัปดาห์ Sushiro จองได้เฉพาะศุกร์ที่ยืนยันแล้ว (H10)
2. **ห้ามเพิ่ม cron consolidate ตอนตี 2** — `digest dream` 06:18 จัดระเบียบ+รายงานในคำสั่งเดียว
   ถ้าแยก job รายงานเช้าจะว่างตลอดกาล
3. **`--record` เป็นของ cron เท่านั้น** — ใส่ตอนรันมือจะไปกินสิทธิ์ของรอบจริงวันนั้น
4. **parser ของ fetchers ยังไม่เคยเจอ API จริง** — ติดป้าย ⚠️ ไว้ทุกตัว แก้ทีละฟังก์ชัน
5. **ไม่ต้องใช้ Google Maps API แล้ว** — โอมเดินไปโรงเรียน 2 นาที บรรทัด 🚗 ถูกตัดออก
   ระบบข้ามการยิง API เองเมื่อระยะ <1 กม. และจะกลับมาทำงานเองถ้าย้ายหอ

## ✅ ยังไม่ได้ทำ (ตั้งใจ)

โทรจองจริง Twilio/Vapi (Phase 3 · ติด H3) · ต่อระบบบัญชีจริง (Phase 2 · ติด OAuth) ·
LINE gateway (Phase 2) · Home Assistant (Phase 5 · ติด H6/H7) · dashboard (Phase 6 · พักไว้)
