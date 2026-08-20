# บันทึกการทดสอบ — อะไรพิสูจน์แล้ว อะไรยัง

เขียนไว้เพื่อให้รู้ว่าตรงไหนเชื่อได้ ตรงไหนต้องไปพิสูจน์เองบน VPS

**สภาพแวดล้อมที่ใช้ทดสอบ:** Ubuntu 24.04, Python 3.11.15, Hermes Agent **0.20.4**
(commit `b5455fdd`) ติดตั้งจริงจาก source ด้วย `uv pip install -e ".[anthropic,messaging]"`

---

## ✅ ทดสอบจริงแล้ว — ยืนยันด้วยผลรัน

| # | เรื่อง | หลักฐาน |
|---|---|---|
| 1 | Hermes 0.20.4 ติดตั้งและรันได้บน Ubuntu 24.04 / Python 3.11 | `hermes --help` ตอบปกติ |
| 2 | **provider `anthropic` มีอยู่จริงและรองรับ `ANTHROPIC_API_KEY`** | `plugins/model-providers/anthropic/__init__.py` — `env_vars=("ANTHROPIC_API_KEY", ...)`, `api_mode="anthropic_messages"` (ยิงตรง ไม่ผ่านคนกลาง) |
| 3 | **Haiku ถูกใช้เป็นโมเดลผู้ช่วยอัตโนมัติ** เมื่อ provider เป็น anthropic | โค้ดเดียวกัน บรรทัด `default_aux_model="claude-haiku-4-5-20251001"` — ตรงกับ spec ที่ต้องการ Haiku สำหรับงานจำแนก โดยไม่ต้องตั้งค่าเพิ่ม |
| 4 | `hermes config set timezone / model.provider / model.default` เขียน `~/.hermes/config.yaml` ถูกต้อง | รันจริง เห็นผลในไฟล์ |
| 5 | **timezone Asia/Bangkok ทำให้ cron ยิงตามเวลาไทยจริง** ← กฎเหล็กข้อ 3 | สร้าง job `20 6 * * *` แล้ว Hermes ตอบ `Next run: 2026-08-20T06:20:00+07:00` |
| 6 | `hermes cron create` รับ prompt ภาษาไทย + `--deliver telegram` + `--repeat` ได้ | สร้าง job สำเร็จ เห็นใน `cron list` |
| 7 | `scripts/02-configure-jarvis.sh` ทำงานครบ และ **idempotent** | รัน 2 รอบ → `.env` ไม่มีคีย์ซ้ำ สิทธิ์ไฟล์เป็น 600 |
| 8 | `scripts/verify-phase0b.sh` ตรวจครบและ exit code ถูก | exit 1 เมื่อมี ✗, ตรวจจับ `+07:00` ได้จริง |
| 9 | `scripts/gate-trial-setup.sh` สร้าง job ทั้งตัวจริงและ smoke test ได้ | เห็นทั้ง 2 job ใน `cron list` |
| 10 | `scripts/gate-trial-teardown.sh` **ลบเฉพาะ job ของตัวเอง** | ทดสอบกับ 3 job → ลบ `jarvis-gate-*` 2 ตัว เหลือ job อื่นไว้ครบ |
| 11 | `~/.hermes/.env` และ `~/.hermes/config.yaml` คือที่เก็บจริง | `hermes config env-path` / `config path` |
| 12 | ต้องมี extras `anthropic` + `messaging` ถึงจะใช้ Claude ตรงและ Telegram ได้ | `pyproject.toml` — `anthropic = ["anthropic==0.87.0"]` และ `messaging` มี `python-telegram-bot` (สคริปต์ขั้นที่ 1 เช็คและเติมให้อัตโนมัติ) |
| 13 | `scripts/00-digitalocean-prep.sh` รันจบครบทุกขั้นและ **idempotent** | รันจริง 2 รอบบน Ubuntu 24.04 — สร้าง swap 2GB, ตั้ง timezone เป็น Asia/Bangkok, ลงเครื่องมือพื้นฐาน, สร้าง user `jarvis` เข้ากลุ่ม sudo; รอบสองตรวจเจอว่าทำไปแล้วทุกข้อและข้ามให้ |
| 14 | ตั้ง timezone ได้แม้ไม่มี systemd | เครื่องทดสอบไม่มี systemd เป็น PID 1 → `timedatectl` ใช้ไม่ได้ สคริปต์ตกไปใช้ `/etc/localtime` แทนแล้วได้ `23:15 +07` ถูกต้อง |

### บั๊ก 5 ตัวที่เจอตอนทดสอบ และแก้แล้ว

1. **`verify-phase0b.sh` รายงานว่า gateway รันอยู่ทั้งที่ไม่ได้รัน**
   ข้อความจริงคือ `Gateway is not running` ซึ่งมีคำว่า `running` อยู่ด้วย — grep เดิมเลยจับติด
   *แก้:* เช็ค `not running|inactive|dead|failed` ก่อนเสมอ

2. **`gate-trial-teardown.sh` บอกว่าลบเสร็จ แต่ไม่ได้ลบอะไรเลย**
   awk ที่มากับ Ubuntu คือ **mawk 1.3.4 ซึ่งไม่รองรับ regex แบบ `{6,}`** — pattern เลยไม่ match แบบเงียบๆ
   *แก้:* ใช้ `length($1) >= 6` แทน ทำงานได้ทั้ง mawk และ gawk

3. **`$USER` ทำสคริปต์ตายกลางคัน** ในสภาพแวดล้อมที่ไม่ได้ตั้งตัวแปรนี้ (เจอตอนรันผ่าน systemd/cron ได้)
   *แก้:* ใช้ `WHOAMI="${USER:-$(id -un)}"`

4. **`$HERMES_SRC[anthropic,messaging]`** — bash อ่าน `$VAR[...]` เป็น array expansion (shellcheck SC1087 จับได้)
   *แก้:* ใส่วงเล็บปีกกา `${HERMES_SRC}[...]`

5. **ทางติดตั้งสำรองจะตายก่อนสร้าง symlink** — `setup-hermes.sh` ของ Hermes มี `read -p` 2 จุด
   และใช้ `set -e` ถ้าป้อน `/dev/null` เข้าไป `read` จะคืนค่า non-zero แล้วสคริปต์ตายที่บรรทัด 280
   ทั้งที่ symlink อยู่บรรทัด 354 → จะไม่มีคำสั่ง `hermes` ให้ใช้
   *แก้:* ลง ripgrep ไว้ก่อนให้มันข้ามคำถาม + ป้อน `n` แทน `/dev/null` + สร้าง symlink เองซ้ำถ้ายังไม่มี

ทั้งห้าตัวถ้าไม่ได้รันจริงจะไม่มีทางเจอ — โดยเฉพาะข้อ 1, 2 และ 5 ที่ "ดูเหมือนสำเร็จ" ทั้งที่ผิด

---

## ⚠️ ยังไม่ได้ทดสอบ — ต้องไปพิสูจน์บน VPS

ทำในเครื่องทดสอบไม่ได้ เพราะไม่มี key จริงและไม่มี VPS ของโอม

| เรื่อง | ทำไมทดสอบไม่ได้ | ใครตรวจให้ |
|---|---|---|
| ส่ง/รับข้อความ Telegram จริง | ต้องมี bot token จริง | ขั้นที่ 3 + `verify-phase0b.sh` ข้อ 5 |
| เรียก Claude API จริง | ต้องมี API key จริง | `verify-phase0b.sh` ยิง `/v1/models` จริงไปเช็ค |
| systemd service + lingering | container ทดสอบไม่มี systemd แบบเต็ม | ขั้นที่ 3 + `verify-phase0b.sh` ข้อ 6 |
| digest ยิงจริงตอน 06:20 | ต้องรอเวลาจริง | gate trial ข้อ 2 (3 เช้าติด) |
| installer ทางการ (`install.sh`) | เครื่องทดสอบต่อ `hermes-agent.nousresearch.com` ไม่ได้ (network policy) | ขั้นที่ 1 — **มี fallback ติดตั้งจาก source ให้แล้ว ถ้า installer ล่ม** |
| firewall (ufw) และ lingering | เครื่องทดสอบไม่มี ufw และไม่มี systemd — สคริปต์ข้ามให้เองพร้อมเตือน | `00-digitalocean-prep.sh` + `verify-phase0b.sh` ข้อ 6 |
| ราคา droplet ของ DigitalOcean | เครื่องทดสอบต่อ digitalocean.com ไม่ได้ (network policy) — ราคาในเอกสารมาจากความรู้เดิม | **เช็คหน้า Droplet Pricing เองก่อนกดสร้าง** |
| คุณภาพภาษาไทยผ่าน Telegram | ต้องเห็นบนหน้าจอ Telegram จริง | gate trial ข้อ 1 |
| ความจำ CRUD ผ่านแชท | ต้องคุยกับบอทจริง | gate trial ข้อ 3 |

> ช่องขวาสุดคือประเด็นสำคัญ: ทุกอย่างที่ทดสอบไม่ได้ในเครื่องทดสอบ **มีตัวตรวจรออยู่แล้ว**
> ไม่มีอะไรที่ต้องเชื่อโดยไม่มีหลักฐาน — แค่หลักฐานนั้นเกิดขึ้นบน VPS

---

## เอกสารต้นทางที่อ้างอิง

- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — โค้ดจริงที่ clone มาอ่าน
- `website/docs/user-guide/messaging/telegram.md` — ขั้นตอน BotFather, allowlist, polling vs webhook
- `website/docs/user-guide/messaging/index.md` — `hermes gateway install` และการจัดการ systemd
- `website/docs/user-guide/configuration.md` — คีย์ `timezone` (มีผลกับ cron และเวลาใน system prompt)
- `cli-config.yaml.example` — รายชื่อ provider ที่รองรับ และ `updates.pre_update_backup`
- `plugins/model-providers/anthropic/__init__.py` — env var, api mode, aux model

---

# Phase 1 — โค้ดแกน (เพิ่มเมื่อ 20 ส.ค. 2026)

> ส่วนบนของไฟล์นี้เป็นเรื่อง Phase 0B (ติดตั้ง Hermes) ส่วนนี้เป็นเรื่องโค้ด Phase 1
> ที่เขียนไว้ล่วงหน้าระหว่างรอเครื่องต่อกับ VPS

**สภาพแวดล้อมที่ทดสอบ:** Python 3.11.15 / stdlib + sqlite3 เท่านั้น
**ผลรวม: 295 เทสต์ผ่านทั้งหมด** — โค้ดแกน 2,968 บรรทัด เทสต์ 3,308 บรรทัด

```bash
PYTHONPATH=jarvis python3 -m unittest discover -s jarvis/tests
```

## ✅ พิสูจน์แล้วด้วยการรันจริง

| โมดูล | เทสต์ | สิ่งที่พิสูจน์ได้ |
|---|---|---|
| `localdate` | (ใช้ร่วมทุกตัว) | 18:00 UTC อ่านเป็นวันถัดไปตามเวลาไทยถูกต้อง — กันบั๊กที่ routine จะรีเซ็ตตอน 7 โมงเช้า |
| `friday` | 35 | สลับถูกทั้งก่อนและหลัง anchor / anchor ที่ไม่ใช่ศุกร์ = ValueError ไม่ปัดให้เงียบๆ |
| `webhook` | 55 | ใช้ `hmac.compare_digest` จริง / secret ว่าง = 500 ปิดประตู ไม่ใช่ปล่อยผ่าน |
| `memory` | 47 | ทับ 3 ชั้นแล้ว recall ได้เฉพาะข้อล่าสุด / `forget` ไม่ยืนยัน = ไม่ลบจริง (นับแถวยืนยันแล้ว) |
| `booking` | 46 | ซองคำตอบมีตัวเลือกปฏิเสธปิดท้ายเสมอ / ตั้ง confirmed โดยไม่มี result_note = ValueError |
| `routines` | 42 | ขอบเขต 13 วัน (ยังไม่ถึง) กับ 14 วัน (ถึงรอบ) / ตัดผมเตือนเฉพาะอังคาร |
| `seed` | 34 | ข้อมูลจริงจาก kit ครบ / `require_pref` ระเบิดเมื่อเจอ `[ต้องกรอก]` |
| `digest` | 15 | **เทียบผลลัพธ์กับตัวอย่างใน kit ทีละตัวอักษร 7 แบบ** / API ล่มทุกตัวยังส่งได้ / คำว่า "ล็อค" ไม่โผล่แม้ค่าจาก API จะมีคำนั้นปนมา |
| `scaccounting` | 12 | ปฏิเสธทุกเมธอดที่ไม่ใช่ GET / กัน path traversal / บันทึก audit แม้คำขอถูกปฏิเสธ / ไม่มีฟังก์ชันเขียนเลย |
| `cli` | 9 | JSON ที่ออกไปมีชื่อคีย์เสมอ / output parse เป็น JSON ได้ตลอด |

### บั๊กที่เจอตอนต่อของจริง (เทสต์ระดับโมดูลจับไม่ได้)

**`NamedTuple` ถูก serialize เป็น array แทน object** — `NamedTuple` เป็น subclass ของ
`tuple` ด้วย `_rows()` ใน `cli.py` จึงเข้าเงื่อนไข `isinstance(x, tuple)` ก่อนถึงเงื่อนไข
`_asdict` ผลคือ Hermes skill ทุกตัวที่อ่านผลด้วยชื่อคีย์จะพังหมด

บั๊กนี้ไม่ได้อยู่ในโมดูลไหนเลย มันอยู่ที่ "รอยต่อ" — แต่ละฝั่งถูกต้องในตัวเอง
เจอเพราะลองเดินคำสั่งจริงผ่าน CLI ไม่ใช่เพราะรันเทสต์
แก้แล้วพร้อมเทสต์กันย้อนกลับใน `jarvis/tests/test_cli.py`

## ⚠️ ยังพิสูจน์ไม่ได้ — ต้องมีของจริงก่อน

| เรื่อง | ติดตรงไหน |
|---|---|
| digest ยิงจริงตอน 06:20 | ต้องรันบน VPS จริง — checklist A1 (7 วันติด) |
| ตัวเลขเดินทาง/อากาศ/ฝุ่นถูกไหม | ยังไม่มีตัวดึง API — `DigestContext` รับค่าไว้แล้วแต่ไม่มีใครเติม |
| โทรจองจริง | `booking.py` บันทึกได้แต่ยังโทรไม่ได้ — Phase 3 |
| ต่อระบบบัญชีจริง | ด่านความปลอดภัยพร้อม แต่ยังไม่มี transport — Phase 2 ต้องมี OAuth ก่อน |
| ศุกร์สลับถูกด้านจริงไหม | **ต้องกรอก `friday_anchor_date` ก่อน** ตรรกะถูกแล้ว แต่ค่าตั้งต้นเป็นเรื่องของคน |

## สิ่งที่คนต้องทำเอง ระบบเดาแทนไม่ได้

`PYTHONPATH=jarvis python3 -m cli doctor` จะฟ้อง 3 ค่านี้จนกว่าจะกรอก

```sql
UPDATE preferences SET value = 'YYYY-MM-DD:home'  WHERE key = 'friday_anchor_date';
UPDATE routines    SET last_done = 'YYYY-MM-DD'   WHERE name = 'diode';
UPDATE routines    SET last_done = 'YYYY-MM-DD'   WHERE name = 'eyebrow';
```

จงใจให้ระเบิดแทนที่จะใส่ค่า default — kit เตือนว่า *"ถ้าผิด ระบบจะสลับกลับด้านทั้งหมด"*
และ H10 บอกว่า Sushiro no-show ซ้ำๆ โดนแบนเร็วกว่าเรื่อง ToS

## ถ้าจะทำต่อ — งานถัดไปเรียงตามลำดับที่ควรทำ

1. **ติดตั้งบน VPS + gate trial 3 วัน** (Phase 0B) — ตัดสิน Track A/B ก่อนเขียนอะไรเพิ่ม
2. ผ่านแล้ว → ติดตั้ง skill ทั้ง 3 ตัว + กรอก 3 ค่าข้างบน + ตั้ง cron digest จริง
3. เขียนตัวดึง API เสริม digest (Routes / Longdo / Air4Thai / Calendar)
4. backup ทุกคืน + **ทดสอบ restore จริง 1 ครั้ง** (kit: backup ที่ไม่เคยทดสอบ restore = ยังไม่มี backup)
5. ใช้จริง 1 เดือน → นับวันที่เปิดอ่าน → ตัดสินตามเกณฑ์ใน `phase1-checklist.md` ส่วน F
