# Backup & Restore — ข้อบังคับตั้งแต่ Phase 1

> spec v3 §3: *"Backup บังคับ ตั้งแต่ Phase 1 — cron ทุกคืน: `jarvis.db` + โฟลเดอร์ความจำ
> Hermes → อัปโหลดออกนอก VPS เก็บย้อนหลัง ≥7 วัน ทดสอบ restore จริง 1 ครั้งก่อนปิด Phase 1"*
>
> checklist E4: **"backup ที่ไม่เคยทดสอบ restore ถือว่ายังไม่มี backup"**

เครื่องมือมี 2 ตัว อยู่ใน `scripts/`:

| สคริปต์ | หน้าที่ |
|---|---|
| `backup-jarvis.sh` | อัดทุกอย่างเป็น `jarvis-backup-YYYYMMDD-HHMMSS.tar.gz` (เวลาไทย) + อัปโหลดออกนอกเครื่อง + ลบของเก่าเกิน 14 ชุด |
| `restore-jarvis.sh` | กู้จากไฟล์สำรองกลับที่เดิม — ของเดิมถูกย้าย (ไม่ลบ) ไป `~/.jarvis/pre-restore-<timestamp>/` ก่อนเสมอ |

ในไฟล์สำรองมีอะไรบ้าง: `jarvis.db` (snapshot ผ่าน sqlite backup API — ไม่ใช่ cp
เพราะ DB เปิด WAL mode ข้อมูลส่วนหนึ่งอยู่ในไฟล์ `-wal` ที่ cp ตรงๆ จะตกหล่น),
`~/.hermes/memories/`, `config.yaml`, `.env` (คงสิทธิ์ 600), `~/.hermes/skills/`
และ `MANIFEST.txt` บอกที่มา + checksum

⚠ ไฟล์สำรองมี API key อยู่ข้างใน (จาก `.env`) — สคริปต์ตั้งสิทธิ์ไฟล์เป็น 600 ให้แล้ว
**ห้าม**เอาไปวางในที่สาธารณะ เช่น GitHub repo แบบ public

---

## 1. ตั้ง cron ทุกคืน 03:30

ใช้ `--no-agent` เพราะงานนี้เป็นแค่การรันเชลล์สคริปต์ ไม่ต้องเปลืองการเรียกโมเดล
(เหตุผลเดียวกับ digest ใน `jarvis/CONTRACTS.md` งวดที่ 2) — เวลา 03:30 เลือกช่วงที่
ไม่มีใครใช้ระบบและไม่ชนกับ digest (การจัดระเบียบความจำเกิดตอน 06:18 พร้อมรายงาน
"ความฝัน" — สำรองก่อนหรือหลังไม่ต่างกัน เพราะ consolidation แค่ mark archived ไม่ลบจริง)

ข้อจำกัดของ Hermes 0.20.4 ที่ต้องรู้ก่อน: `--no-agent` **ใช้ได้กับ `--script` เท่านั้น**
(ส่งคำสั่ง shell เป็นข้อความตรงๆ ไม่ได้ — ตำแหน่งนั้นคือ prompt ของ LLM) และไฟล์
สคริปต์ต้องอยู่ใต้ `~/.hermes/scripts/` เท่านั้น (ตัว scheduler บล็อก path นอกโฟลเดอร์นี้)
จึงต้องสร้างสคริปต์ตัวกลางก่อนแล้วชี้ cron ไปที่มัน — แบบแผนเดียวกับที่
`scripts/phase1-digests-setup.sh` ทำกับ digest

สคริปต์ตัวกลางส่งแจ้งเตือนเข้า Telegram **เฉพาะคืนที่ล้มเหลว** — คืนที่สำเร็จ
stdout ว่าง Hermes จะไม่ส่งอะไร ไม่รบกวน และไม่กินโควตาข้อความ:

```bash
mkdir -p ~/.hermes/scripts ~/.jarvis
cat > ~/.hermes/scripts/jarvis-nightly-backup.sh <<'EOF'
#!/usr/bin/env bash
# no-agent cron: Hermes เอา stdout ส่งเข้า Telegram ตรงๆ — stdout ว่าง = ไม่ส่ง
# จึงพิมพ์ข้อความเฉพาะคืนที่ล้มเหลว (คืนที่สำเร็จ = เงียบ)
set -uo pipefail
LOG="$HOME/.jarvis/last-backup.log"
RC=0
bash "$HOME/jarvis/scripts/backup-jarvis.sh" >"$LOG" 2>&1 || RC=$?
if [ "$RC" -ne 0 ]; then
  echo "⚠ backup คืนนี้ล้มเหลว (exit $RC) — ssh เข้าไปดู $LOG"
fi
EOF

hermes cron create "30 3 * * *" \
  --name jarvis-nightly-backup --no-agent \
  --script "$HOME/.hermes/scripts/jarvis-nightly-backup.sh" --deliver telegram
```

ถ้า clone repo ไว้ที่อื่นที่ไม่ใช่ `~/jarvis` ให้แก้ path ในสคริปต์ตัวกลางตามจริง
ตรวจว่าตั้งติดแล้วและเวลาเป็นเวลาไทย:

```bash
hermes cron list          # ต้องเห็น jarvis-nightly-backup, Next run ลงท้าย +07:00
```

> cron ของ Hermes ยิงได้ก็ต่อเมื่อ gateway รันอยู่ (systemd + lingering — checklist E1)
> ถ้า digest เช้ามาปกติ แปลว่าท่อเดียวกันนี้ใช้ได้กับ backup ด้วย

ทดสอบรันมือหนึ่งครั้งก่อนปล่อยให้ cron ทำเอง:

```bash
bash ~/jarvis/scripts/backup-jarvis.sh
ls -lh ~/backups/jarvis/
```

---

## 2. ตั้งอัปโหลดออกนอก VPS (RCLONE_REMOTE)

spec **บังคับ** เก็บนอกเครื่อง — ตราบใดที่ยังไม่ได้ตั้ง สคริปต์จะขึ้นคำเตือนตัวใหญ่ทุกครั้ง
(ตั้งใจให้รำคาญ เพราะสำรองที่อยู่บนเครื่องเดียวกับต้นฉบับ = หายพร้อมกันวันที่ VPS พัง)

ค่า config อ่านจากไฟล์ `~/.jarvis/backup.env` (cron รันด้วย env ว่างเปล่า
การ `export` ใน shell ปกติจึงไม่ถึงมัน):

```bash
mkdir -p ~/.jarvis
cat > ~/.jarvis/backup.env <<'EOF'
RCLONE_REMOTE=r2:jarvis-backups/daily
EOF
chmod 600 ~/.jarvis/backup.env
```

ติดตั้ง rclone (ครั้งเดียว): `curl https://rclone.org/install.sh | sudo bash`

### ทางเลือก A — Cloudflare R2 (แนะนำ: ฟรี 10GB ไม่มีค่า egress)

1. Cloudflare dashboard → R2 → สร้าง bucket ชื่อ `jarvis-backups`
2. R2 → Manage R2 API Tokens → สร้าง token แบบ **Object Read & Write** จำกัดเฉพาะ bucket นี้
3. บน VPS:

```bash
rclone config create r2 s3 \
  provider=Cloudflare \
  access_key_id=<ACCESS_KEY> \
  secret_access_key=<SECRET_KEY> \
  endpoint=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

4. ใน `~/.jarvis/backup.env` ตั้ง `RCLONE_REMOTE=r2:jarvis-backups/daily`

### ทางเลือก B — Google Drive

```bash
rclone config    # เลือก n (new) → ชื่อ gdrive → ประเภท drive → ทำตามขั้น OAuth
```

VPS ไม่มีเบราว์เซอร์ — ตอน rclone ถามเรื่อง auto config ให้ตอบ `n` แล้วรัน
`rclone authorize "drive"` บนเครื่องตัวเอง เอาโค้ดที่ได้มาวางกลับใน VPS
จากนั้นตั้ง `RCLONE_REMOTE=gdrive:jarvis-backups`

### ตรวจว่าขึ้นจริง

```bash
bash ~/jarvis/scripts/backup-jarvis.sh        # ต้องเห็น "อัปโหลดขึ้น ... แล้ว" ไม่ใช่คำเตือน
rclone ls "$(grep ^RCLONE_REMOTE= ~/.jarvis/backup.env | cut -d= -f2-)"
```

### การเก็บย้อนหลัง

- **บนเครื่อง:** สคริปต์เก็บ 14 ชุดล่าสุด ลบเก่ากว่านั้นเอง (ปรับได้ด้วย `BACKUP_KEEP`)
  — เกินขั้นต่ำ ≥7 วันของ spec ไว้เท่าตัว
- **บน remote:** rclone `copy` ไม่ลบของเก่าให้ ไฟล์จะพอกไปเรื่อยๆ (วันละ ~ไม่กี่ MB
  ไม่รีบร้อน) ถ้าอยากเก็บกวาด เดือนละครั้ง:

```bash
rclone delete --min-age 60d r2:jarvis-backups/daily
```

---

## 3. ซ้อม restore จริง (checklist E4 — ต้องทำก่อนปิด Phase 1)

> ทำบน VPS จริง กับไฟล์สำรองจริงของเมื่อคืน — ไม่ใช่ไฟล์ที่เพิ่งสร้างสดๆ เมื่อกี้
> เพราะสิ่งที่กำลังพิสูจน์คือ "ของที่ cron ทำไว้เอง เอากลับมาใช้ได้จริงไหม"

1. **จดสภาพก่อนซ้อม** — เอาไว้เทียบข้อ 6:

   ```bash
   python3 - <<'PY'
   import sqlite3, os
   con = sqlite3.connect(os.path.expanduser("~/.jarvis/jarvis.db"))
   for t in ("routines", "preferences", "lessons"):
       print(t, con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
   PY
   ```

2. **หยุด gateway** (restore จะไม่ยอมรันถ้ายังเปิดอยู่ — ป้องกัน DB เสียกลางคัน):

   ```bash
   hermes gateway stop
   ```

3. **เลือกไฟล์สำรอง** — ปกติใช้ตัวล่าสุดในเครื่อง แต่รอบซ้อมให้ **ดึงจาก remote**
   มาอย่างน้อยหนึ่งครั้ง เพื่อพิสูจน์ว่าขา off-VPS ก็ใช้ได้จริง:

   ```bash
   rclone copy r2:jarvis-backups/daily/jarvis-backup-<วันล่าสุด>.tar.gz /tmp/drill/
   ```

4. **กู้:**

   ```bash
   bash ~/jarvis/scripts/restore-jarvis.sh /tmp/drill/jarvis-backup-<วันล่าสุด>.tar.gz
   ```

   สคริปต์จะโชว์ว่าจะทับอะไรบ้าง → พิมพ์ `yes` → ต้องจบด้วย
   `integrity_check = ok` พร้อมจำนวนแถวของทุกตาราง และบอกว่าของเดิมถูกย้ายไปที่
   `~/.jarvis/pre-restore-<timestamp>/`

5. **เปิดระบบกลับ แล้วใช้งานจริง:**

   ```bash
   hermes gateway start
   ```

   ทัก Telegram ถามอะไรที่ต้องแตะข้อมูล เช่น "รอบไดโอดถึงหรือยัง" กับ
   "จำอะไรเกี่ยวกับร้านกาแฟไว้บ้าง" — ต้องตอบได้จากข้อมูลที่กู้มา
   (E4: *"restore ขึ้นมาแล้วเปิดใช้งานได้จริง ไม่ใช่แค่ไฟล์ดาวน์โหลดมาได้"*)

6. **เทียบจำนวนแถว** กับที่จดไว้ข้อ 1 — ต่างได้เท่าที่อธิบายได้ (แถวที่เพิ่มหลังเวลาสำรอง)

7. **เก็บกวาด** — แน่ใจแล้วว่าระบบปกติค่อยลบ `~/.jarvis/pre-restore-<timestamp>/`
   ด้วยมือ (สคริปต์ไม่ลบให้ ตามกฎ "ลบต้องกู้คืนได้")

### บันทึกการซ้อม

| ครั้งที่ | วันที่ทำจริง | ไฟล์ที่ใช้ | ผล (integrity / จำนวนแถว / บอทตอบได้) | ผู้ทำ |
|---|---|---|---|---|
| 1 (ก่อนปิด Phase 1) | ____________ | ____________ | ____________ | ____ |
| ซ้อมซ้ำ (ทุก ~3 เดือน) | ____________ | ____________ | ____________ | ____ |

---

## อ้างอิงเร็ว: exit code

| สคริปต์ | code | ความหมาย |
|---|---|---|
| backup | 0 | สำเร็จ (ถ้ายังไม่ตั้ง off-VPS จะมีคำเตือนแต่ไม่ถือว่าพัง) |
| backup | 1 | ไม่มี `jarvis.db` / ไม่มีอะไรให้สำรอง |
| backup | 2 | snapshot DB พัง หรือ integrity_check ไม่ผ่าน |
| backup | 3 | อัด tar ไม่สำเร็จ (เช็คพื้นที่ดิสก์) |
| backup | 4 | ตั้ง `RCLONE_REMOTE` ไว้แต่อัปโหลดล้มเหลว (ไฟล์ local ยังอยู่) |
| restore | 0 | สำเร็จ หรือผู้ใช้ยกเลิกเอง |
| restore | 1 | เรียกใช้ผิด / หาไฟล์สำรองไม่เจอ |
| restore | 2 | gateway ยังรันอยู่ — `hermes gateway stop` ก่อน (หรือ `--force`) |
| restore | 3 | ไฟล์สำรองแตกไม่ออก/โครงสร้างผิด |
| restore | 4 | integrity_check ไม่ผ่าน (ของเดิมยังอยู่ครบใน pre-restore) |
| restore | 5 | รันแบบไม่มี terminal และไม่ใส่ `--yes` |
