# Jarvis — Phase 0B: ติดตั้ง Hermes Agent + ต่อ Telegram + ตั้ง Claude เป็นสมอง

ชุดสคริปต์ติดตั้ง [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research, MIT) บน VPS
ตาม `jarvis-build-spec-v3.md` **ส่วน Phase 0B เท่านั้น** — เป้าหมายคือให้ Hermes รันได้ พร้อมทดสอบ gate trial

## ขอบเขต

**ทำในชุดนี้**
- ติดตั้ง Hermes Agent บน VPS
- ตั้ง Claude (Anthropic API) เป็นโมเดลหลัก — ยิงตรง ไม่ผ่าน OpenRouter
- ต่อ Telegram bot ให้คุยได้จริง
- ตั้ง timezone เป็น Asia/Bangkok ทั้ง OS และ Hermes (กฎเหล็กข้อ 3)
- เปิด gateway เป็น systemd service รัน 24 ชม. รอดหลังรีบูต
- เครื่องมือทดสอบ gate trial ครบ 3 ข้อ

**ยังไม่ทำ (ตามที่สั่ง)**
- custom skill ใดๆ — `routines`, `booking`, `scaccouting`
- `jarvis.db` / SQLite
- digest ตัวจริงตาม `phase1-kit` (ตอนนี้เป็นแค่ข้อความทดสอบว่ามาตรงเวลาไหม)
- บุคลิก Jarvis, backup, LINE gateway, เสียง — ทั้งหมดอยู่ Phase 1 ขึ้นไป

---

## ต้องมีก่อน

| อย่าง | รายละเอียด |
|---|---|
| VPS | Ubuntu 22.04/24.04, **RAM ≥1GB** (2GB สบายกว่า), ดิสก์ว่าง ≥3GB, สิงคโปร์ ~$5-10/เดือน |
| user ธรรมดา | ห้ามติดตั้งด้วย root — `sudo adduser jarvis && sudo usermod -aG sudo jarvis` |
| บัญชี Anthropic | มีเครดิตอยู่ — ⚠️ เคลียร์เรื่องผู้เปิดบัญชี/บัตรก่อน (H2 ใน red team) |
| แอป Telegram | ใช้สร้างบอทและหา user ID |

---

## ขั้นตอน

### เตรียม — ดึงโค้ดลง VPS

```bash
ssh jarvis@<ip-ของ-vps>
git clone <url-ของ-repo-นี้> ~/jarvis && cd ~/jarvis
git checkout claude/hermes-agent-phase-0b-upmjjr
```

### ขั้นที่ 1 — ติดตั้ง Hermes

```bash
bash scripts/01-install-hermes.sh
```

ใช้เวลา 5-15 นาที ทำ 5 อย่าง: ตั้ง timezone ของ VPS → ติดตั้ง Hermes → เช็คว่า dependency ของ Anthropic กับ Telegram ครบ → บันทึกเวอร์ชันที่ติดตั้งลง `~/.hermes/jarvis-version.lock` → เปิด backup อัตโนมัติก่อน update

รันซ้ำได้ ถ้าติดตั้งไว้แล้วจะข้ามไปตรวจอย่างเดียว

### ขั้นที่ 2 — หาค่าลับ 3 ตัว

<details>
<summary><b>ก. ANTHROPIC_API_KEY</b> — สมองของ Jarvis</summary>

1. เข้า [console.anthropic.com](https://console.anthropic.com)
2. Settings → API Keys → **Create Key**
3. คัดลอกเก็บไว้ทันที (ปิดหน้าต่างแล้วดูซ้ำไม่ได้)
4. เช็คที่ Billing ว่ามีเครดิตเหลือ

</details>

<details>
<summary><b>ข. TELEGRAM_BOT_TOKEN</b> — ตัวบอท</summary>

1. เปิด Telegram หา [@BotFather](https://t.me/BotFather)
2. ส่ง `/newbot`
3. ตั้งชื่อที่แสดง — อะไรก็ได้ เช่น `Jarvis`
4. ตั้ง username — ต้องไม่ซ้ำใครและ**ลงท้ายด้วย `bot`** เช่น `ohm_jarvis_bot`
5. BotFather ตอบ token กลับมา หน้าตาแบบ `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`

ทำเพิ่มก็ดี (ไม่บังคับ): `/setdescription`, `/setuserpic`

</details>

<details>
<summary><b>ค. TELEGRAM_ALLOWED_USERS</b> — ด่านกันคนอื่น</summary>

1. ใน Telegram ทักหา [@userinfobot](https://t.me/userinfobot)
2. มันตอบเลข ID กลับมาทันที เช่น `123456789`

⚠️ ต้องเป็น **ตัวเลข** ไม่ใช่ `@username` — ถ้าใส่ผิดจะกันตัวเองออกจากบอทตัวเอง
ถ้าเว้นว่างไว้ = ใครก็สั่ง Jarvis ได้

</details>

กรอกลงไฟล์:

```bash
cp config/jarvis.env.example config/jarvis.env
nano config/jarvis.env
bash scripts/02-configure-jarvis.sh
```

สคริปต์จะตรวจรูปแบบให้ก่อน แล้วเขียนลง `~/.hermes/.env` (chmod 600) และตั้ง `~/.hermes/config.yaml` ให้

### ขั้นที่ 3 — เปิด gateway

```bash
bash scripts/03-start-gateway.sh
```

**ทดสอบเลย:** เปิด Telegram → ทักบอท → พิมพ์ `สวัสดี` → ถ้าตอบไทยกลับมา = ต่อครบวงจร 🎉

### ขั้นที่ 4 — ตรวจให้ครบก่อนเริ่ม trial

```bash
bash scripts/verify-phase0b.sh
```

ตรวจ 7 หมวด และ**ยิง API จริง**ไปทดสอบทั้ง Anthropic และ Telegram ว่า key ใช้ได้จริง ไม่ใช่แค่ตัวอักษรครบ
ต้องไม่มี ✗ เหลือก่อนไปขั้นต่อไป

### ขั้นที่ 5 — gate trial 3 วัน

```bash
bash scripts/gate-trial-setup.sh --smoke
```

`--smoke` ยิงข้อความทดสอบเข้า Telegram ใน 3 นาที — รอให้มาถึงก่อนค่อยเริ่มนับวัน

แล้วทำตาม **[`docs/gate-trial.md`](docs/gate-trial.md)** — มีชุดคำถามทดสอบภาษาไทย ตารางเช็ค digest 3 เช้า ลำดับทดสอบความจำ 9 ขั้น และช่องกรอกสรุปเพื่อตัดสิน Track A / Track B

เสร็จแล้วเก็บกวาด: `bash scripts/gate-trial-teardown.sh`

---

## ค่าที่ตั้งไว้ และเหตุผล

| ตั้งอะไร | เป็นค่าอะไร | ทำไม |
|---|---|---|
| `model.provider` | `anthropic` | ยิงตรง Anthropic API ตาม spec ไม่ผ่านคนกลางอย่าง OpenRouter |
| `model.default` | `claude-opus-5` | โมเดลหลัก — **เปลี่ยนได้ ดูหัวข้อค่าใช้จ่ายด้านล่าง** |
| โมเดลผู้ช่วย | `claude-haiku-4-5` | Hermes เลือกให้เองเมื่อ provider เป็น anthropic — ตรงกับ spec ที่ต้องการ Haiku สำหรับงานจำแนกสั้นๆ พอดี ไม่ต้องตั้งเพิ่ม |
| `timezone` | `Asia/Bangkok` | กฎเหล็กข้อ 3 — ตั้งทั้งใน Hermes และ OS |
| Telegram | polling mode | VPS รันตลอดอยู่แล้ว ไม่ต้องเปิดพอร์ตรับ webhook เข้ามา |
| gateway | systemd + lingering | รอดทั้งตอนปิด SSH และตอน VPS รีบูต |
| `updates.pre_update_backup` | `true` | สำรองอัตโนมัติก่อน `hermes update` ทุกครั้ง (ความเสี่ยงข้อ 1 ใน spec) |
| `telemetry.shared_metrics` | `false` | ระบบนี้เก็บเรื่องส่วนตัว ไม่ส่ง metrics ออกนอกเครื่อง |

### ค่าใช้จ่าย — ต้องตัดสินใจเอง

ราคาต่อ 1 ล้าน token (input / output):

| โมเดล | ราคา | |
|---|---|---|
| `claude-opus-5` | $5 / $25 | **ค่าที่ตั้งไว้** — ฉลาดที่สุด |
| `claude-sonnet-5` | $3 / $15 | ถูกกว่าราว 40% (ช่วงโปรถึง 31 ส.ค. 2026: $2 / $10) |
| `claude-haiku-4-5` | $1 / $5 | Hermes ใช้เป็นตัวช่วยงานสั้นอยู่แล้ว |

⚠️ **spec ตั้งงบ Claude API ไว้ $2-10/เดือน — ถ้าคุยเยอะทุกวัน opus-5 มีสิทธิ์เกินงบ**
ตั้ง opus-5 เป็น default ไว้ก่อนเพราะเป็นตัวเลือกที่ดีที่สุด และการลดสเปกเพื่อประหยัดควรเป็นการตัดสินใจของโอมเอง ไม่ใช่ตัดสินให้

เปลี่ยนได้ทุกเมื่อ:
```bash
hermes config set model.default claude-sonnet-5 && hermes gateway restart
```

วิธีตัดสิน: รัน gate trial 3 วันด้วย opus-5 → ดูยอดจริงด้วย `/usage` ในแชท → คูณ 10 คร่าวๆ = ต่อเดือน → เกินงบค่อยลดเป็น sonnet-5

---

## คำสั่งที่ใช้บ่อย

```bash
hermes gateway status        # gateway รันอยู่ไหม
hermes gateway restart       # ใช้ทุกครั้งหลังแก้ config หรือ .env
hermes cron list             # ดู job ที่ตั้งไว้ (เช็คว่า Next run ลงท้าย +07:00)
hermes cron runs             # ประวัติว่ายิงจริงไหม
hermes config get model.default
journalctl --user -u hermes-gateway -f --no-pager    # ดู log สด
```

ในแชท Telegram: `/new` เริ่มบทสนทนาใหม่ (ช่วยลดค่า API) · `/usage` ดูยอดใช้ · `/status` ดูสถานะ · `/help` ดูทั้งหมด

---

## โครงสร้างไฟล์

```
scripts/
  01-install-hermes.sh       ติดตั้ง Hermes + ตั้ง timezone + บันทึกเวอร์ชัน
  02-configure-jarvis.sh     ตั้ง Claude เป็นโมเดลหลัก + เขียนค่าลับ Telegram
  03-start-gateway.sh        ติดตั้ง systemd service + เปิด lingering
  verify-phase0b.sh          ตรวจ 7 หมวด + ยิง API จริงไปเช็ค key
  gate-trial-setup.sh        ตั้ง cron digest 06:20 (+ smoke test 3 นาที)
  gate-trial-teardown.sh     ลบเฉพาะ job ของ gate trial
config/
  jarvis.env.example         แม่แบบค่าลับ (คัดลอกเป็น jarvis.env แล้วกรอก)
docs/
  gate-trial.md              ชุดทดสอบ 3 ข้อ + ตารางกรอกผล + เกณฑ์ตัดสิน
  troubleshooting.md         อาการที่เจอบ่อยเรียงตามความถี่
  verification-log.md        บันทึกว่าอะไรถูกทดสอบจริงแล้วบ้าง
```

---

## หมายเหตุสำคัญ

สคริปต์ทั้งหมดถูก **ทดสอบจริงกับ Hermes Agent 0.20.4** ที่ติดตั้งจริงในเครื่องทดสอบ ไม่ได้เขียนลอยๆ จากเอกสาร
รายละเอียดว่าอะไรถูกพิสูจน์แล้วบ้าง และอะไรที่ยังต้องไปพิสูจน์บน VPS จริง อยู่ใน [`docs/verification-log.md`](docs/verification-log.md)

**สิ่งที่ยังไม่ได้ทดสอบ** เพราะทำได้เฉพาะบน VPS จริงที่มี key จริง: การส่งข้อความ Telegram จริง, การเรียก Claude API จริง, systemd service, และ digest ที่ยิงตอน 06:20 จริง — ทั้งหมดนี้คือสิ่งที่ `verify-phase0b.sh` และ gate trial มีไว้ตรวจให้
