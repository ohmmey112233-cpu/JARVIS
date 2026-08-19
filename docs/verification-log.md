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

### บั๊ก 3 ตัวที่เจอตอนทดสอบ และแก้แล้ว

1. **`verify-phase0b.sh` รายงานว่า gateway รันอยู่ทั้งที่ไม่ได้รัน**
   ข้อความจริงคือ `Gateway is not running` ซึ่งมีคำว่า `running` อยู่ด้วย — grep เดิมเลยจับติด
   *แก้:* เช็ค `not running|inactive|dead|failed` ก่อนเสมอ

2. **`gate-trial-teardown.sh` บอกว่าลบเสร็จ แต่ไม่ได้ลบอะไรเลย**
   awk ที่มากับ Ubuntu คือ **mawk 1.3.4 ซึ่งไม่รองรับ regex แบบ `{6,}`** — pattern เลยไม่ match แบบเงียบๆ
   *แก้:* ใช้ `length($1) >= 6` แทน ทำงานได้ทั้ง mawk และ gawk

3. **`$USER` ทำสคริปต์ตายกลางคัน** ในสภาพแวดล้อมที่ไม่ได้ตั้งตัวแปรนี้ (เจอตอนรันผ่าน systemd/cron ได้)
   *แก้:* ใช้ `WHOAMI="${USER:-$(id -un)}"`

ทั้งสามตัวถ้าไม่ได้รันจริงจะไม่มีทางเจอ — โดยเฉพาะข้อ 1 และ 2 ที่ "ดูเหมือนสำเร็จ" ทั้งที่ผิด

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
